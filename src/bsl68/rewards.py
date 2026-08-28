from __future__ import annotations

import random
from dataclasses import dataclass

from .account import PlayerAccount
from .catalog import BRAWLER_BY_ID
from .static_data import StaticDataCatalog

RARITY_NAMES = ("rare", "super_rare", "epic", "mythic", "legendary")
RARITY_COLUMNS = (
    "TicketsInRareStar",
    "TicketsInSuperRareStar",
    "TicketsInEpicStar",
    "TicketsInMythicStar",
    "TicketsInLegendaryStar",
)
CARD_RARITIES = {"rare": 1, "super_rare": 2, "epic": 3, "mythic": 4, "legendary": 5}


@dataclass(frozen=True, slots=True)
class RewardDefinition:
    name: str
    reward_type: str
    type_value: int
    price_min: int
    price_max: int
    amount_min: int
    amount_max: int
    fallback_type: str
    fallback_amount: int
    weight: int


@dataclass(frozen=True, slots=True)
class RewardRoll:
    rarity: int
    definition: RewardDefinition
    amount: int

    @property
    def rarity_name(self) -> str:
        return RARITY_NAMES[self.rarity]


@dataclass(frozen=True, slots=True)
class AppliedReward:
    reward_type: str
    amount: int
    data_reference: tuple[int, ...] = (0,)
    used_fallback: bool = False


def _weighted_choice(items, weights, rng: random.Random):
    total = sum(weights)
    if total <= 0:
        raise ValueError("reward table has no positive weights")
    ticket = rng.randrange(total)
    for item, weight in zip(items, weights):
        ticket -= weight
        if ticket < 0:
            return item
    raise AssertionError("unreachable weighted-choice state")


class RandomRewardEngine:
    """Starr Drop tables read directly from v68 random_rewards.csv."""

    def __init__(self, catalog: StaticDataCatalog):
        self.catalog = catalog
        containers = catalog.table("random_reward_containers")
        container_by_name = {row.name: row for row in containers}
        self.rarity_weights = tuple(
            container_by_name[name].integer("TicketsInWinGamesDraw")
            for name in ("RareStar", "SuperRareStar", "EpicStar", "MythicStar", "LegendaryStar")
        )
        reward_rows = catalog.table("random_rewards")
        self.tables = tuple(
            self._definitions(reward_rows, column) for column in RARITY_COLUMNS
        )
        self._character_ids = {
            row.name: row.row_id - 1 for row in catalog.table("characters") if row.name
        }
        self._brawler_rarities = self._load_brawler_rarities()

    @staticmethod
    def _definitions(rows, column: str) -> tuple[RewardDefinition, ...]:
        definitions = []
        for row in rows:
            weight = row.integer(column)
            if not row.name or weight <= 0:
                continue
            definitions.append(
                RewardDefinition(
                    row.name,
                    row.get("TypeName", ""),
                    row.integer("TypeValue"),
                    row.integer("TypePriceMin"),
                    row.integer("TypePriceMax"),
                    row.integer("AmountMin"),
                    row.integer("AmountMax"),
                    row.get("FallbackTypeName", ""),
                    row.integer("FallbackAmount"),
                    weight,
                )
            )
        return tuple(definitions)

    def _load_brawler_rarities(self) -> dict[int, int]:
        result: dict[int, int] = {}
        for row in self.catalog.table("cards"):
            if row.get("Type") != "unlock":
                continue
            character_id = self._character_ids.get(row.get("Target", ""))
            if character_id in BRAWLER_BY_ID:
                result[character_id] = CARD_RARITIES.get(row.get("Rarity", "").casefold(), 0)
        return result

    def roll(self, rarity: int | None = None, rng: random.Random | None = None) -> RewardRoll:
        rng = rng or random.Random()
        if rarity is None:
            rarity = _weighted_choice(range(5), self.rarity_weights, rng)
        if rarity not in range(5):
            raise ValueError("rarity must be between 0 and 4")
        table = self.tables[rarity]
        definition = _weighted_choice(table, [item.weight for item in table], rng)
        low, high = sorted((definition.amount_min, definition.amount_max))
        amount = rng.randint(low, high) if high else 0
        return RewardRoll(rarity, definition, amount)

    def _fallback(self, account: PlayerAccount, definition: RewardDefinition) -> AppliedReward:
        reward_type = definition.fallback_type or "Coins"
        amount = max(0, definition.fallback_amount)
        self._grant(account, reward_type, amount)
        return AppliedReward(reward_type, amount, (0,), True)

    @staticmethod
    def _grant(account: PlayerAccount, reward_type: str, amount: int) -> bool:
        keyword = {
            "Coins": "coins",
            "Gems": "gems",
            "PowerPoints": "power_points",
            "Credits": "credits",
            "Bling": "bling",
            "TokenDoubler": "token_doubler",
        }.get(reward_type)
        if keyword is None:
            return False
        account.grant_resources(**{keyword: amount})
        return True

    def apply(
        self,
        account: PlayerAccount,
        roll: RewardRoll,
        rng: random.Random | None = None,
    ) -> AppliedReward:
        rng = rng or random.Random()
        definition = roll.definition
        if self._grant(account, definition.reward_type, roll.amount):
            return AppliedReward(definition.reward_type, roll.amount)

        if definition.reward_type == "Brawler":
            candidates = [
                character_id for character_id, rarity in self._brawler_rarities.items()
                if rarity == definition.type_value and str(character_id) not in account.brawlers
            ]
            if candidates:
                character_id = rng.choice(candidates)
                account.unlock_brawler(character_id, 0, currency="coins")
                return AppliedReward("Brawler", 1, (16, character_id))

        if definition.reward_type == "Skin":
            candidates: list[int] = []
            for row in self.catalog.table("skins"):
                price = row.integer("PriceGems", -1)
                if (
                    not row.boolean("Disabled")
                    and definition.price_min <= price <= definition.price_max
                    and row.row_id not in account.owned_skins
                ):
                    candidates.append(row.row_id)
            if candidates:
                skin_id = rng.choice(candidates)
                account.owned_skins.append(skin_id)
                account.owned_skins.sort()
                return AppliedReward("Skin", 1, (29, skin_id))

        return self._fallback(account, definition)
