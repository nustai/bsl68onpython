from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .catalog import (
    BRAWLER_BY_ID,
    BRAWLERS,
    NAME_COLOR_IDS,
    PLAYER_THUMBNAIL_IDS,
    SKIN_IDS,
    VANITY_IDS,
)


@dataclass(slots=True)
class ServerConfig:
    initial_name: str = "Player"
    starting_coins: int = 2000
    starting_gems: int = 2000
    starting_power_points: int = 2000
    starting_brawler_trophies: int = 100_000
    starting_power_level: int = 1
    unlock_all_brawlers: bool = False
    brawler_price: int = 1
    colt_gem_price: int = 1
    region: str = "RU"
    motd: str = ""

    @classmethod
    def load(cls, path: Path | None) -> ServerConfig:
        if path is None or not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        allowed = {name for name in cls.__dataclass_fields__}
        values = {key: value for key, value in raw.items() if key in allowed}
        try:
            config = cls(**values)
        except TypeError:
            return cls()
        defaults = cls()
        if not isinstance(config.initial_name, str):
            config.initial_name = defaults.initial_name
        for field_name in (
            "starting_coins",
            "starting_gems",
            "starting_power_points",
            "starting_brawler_trophies",
            "starting_power_level",
            "brawler_price",
            "colt_gem_price",
        ):
            value = getattr(config, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                setattr(config, field_name, getattr(defaults, field_name))
        config.starting_coins = max(0, config.starting_coins)
        config.starting_gems = max(0, config.starting_gems)
        config.starting_power_points = max(0, config.starting_power_points)
        config.starting_brawler_trophies = max(0, config.starting_brawler_trophies)
        config.starting_power_level = max(1, min(11, config.starting_power_level))
        config.brawler_price = max(0, config.brawler_price)
        config.colt_gem_price = max(0, config.colt_gem_price)
        if not isinstance(config.unlock_all_brawlers, bool):
            config.unlock_all_brawlers = defaults.unlock_all_brawlers
        if not isinstance(config.region, str) or not config.region.strip():
            config.region = defaults.region
        else:
            config.region = config.region.strip()[:8]
        if not isinstance(config.motd, str):
            config.motd = defaults.motd
        else:
            config.motd = config.motd.strip()[:255]
        return config


@dataclass(slots=True)
class BrawlerProgress:
    character_id: int
    unlock_card_id: int
    trophies: int = 0
    highest_trophies: int = 0
    power_level: int = 1
    power_points: int = 0
    seen_state: int = 2

    @classmethod
    def create(cls, character_id: int) -> BrawlerProgress:
        spec = BRAWLER_BY_ID[character_id]
        return cls(spec.character_id, spec.unlock_card_id)


@dataclass(slots=True)
class PlayerAccount:
    schema_version: int = 2
    account_high: int = 0
    account_low: int = 1
    # Tokens are generated for fresh local profiles; never use a shared default.
    pass_token: str = ""
    name: str = "Player"
    name_set: bool = True
    coins: int = 2000
    gems: int = 2000
    power_points: int = 2000
    credits: int = 0
    bling: int = 0
    token_doubler: int = 0
    selected_brawler: int = 0
    thumbnail: int = 0
    name_color: int = 0
    region: str = "RU"
    selected_skins: dict[str, int] = field(default_factory=dict)
    owned_skins: list[int] = field(default_factory=list)
    emote_slots: dict[str, int] = field(default_factory=dict)
    profile_vanity: dict[str, int] = field(default_factory=dict)
    experience: int = 1488
    trophy_road_tier: int = 454
    player_level: int = 100
    wins_3v3: int = 0
    solo_wins: int = 0
    duo_wins: int = 0
    losses: int = 0
    battle_count: int = 0
    brawlers: dict[str, BrawlerProgress] = field(default_factory=dict)

    @classmethod
    def fresh(cls, config: ServerConfig) -> PlayerAccount:
        # `name_set=False` makes the stock v68 client show its own Supercell
        # name dialog. The placeholder is used only until it is confirmed.
        account = cls(
            pass_token=secrets.token_hex(13),
            name=config.initial_name[:60] or "Player",
            name_set=False,
            coins=max(0, config.starting_coins),
            gems=max(0, config.starting_gems),
            power_points=max(0, config.starting_power_points),
            region=config.region,
        )
        starter_ids = (
            (spec.character_id for spec in BRAWLERS)
            if config.unlock_all_brawlers
            else (0,)
        )
        for character_id in starter_ids:
            progress = BrawlerProgress.create(character_id)
            progress.power_level = config.starting_power_level
            if config.unlock_all_brawlers:
                progress.power_points = config.starting_power_points
            account.brawlers[str(character_id)] = progress
        # The stock client treats a completely empty profile as unfinished
        # tutorial state and starts its scripted battle before the name dialog.
        # Match the ready-account progression used by the working C# v68
        # server, while keeping name_set=False so the nickname dialog appears.
        account.brawlers["0"].trophies = config.starting_brawler_trophies
        account.brawlers["0"].highest_trophies = config.starting_brawler_trophies
        return account

    @property
    def account_id(self) -> tuple[int, int]:
        return self.account_high, self.account_low

    @property
    def total_trophies(self) -> int:
        return sum(brawler.trophies for brawler in self.brawlers.values())

    @property
    def highest_trophies(self) -> int:
        return sum(brawler.highest_trophies for brawler in self.brawlers.values())

    @property
    def unlocked_brawlers(self) -> tuple[BrawlerProgress, ...]:
        return tuple(sorted(self.brawlers.values(), key=lambda value: value.character_id))

    @property
    def locked_brawler_ids(self) -> tuple[int, ...]:
        return tuple(spec.character_id for spec in BRAWLERS if str(spec.character_id) not in self.brawlers)

    def unlock_brawler(
        self,
        character_id: int,
        price: int,
        power_points: int = 0,
        currency: str = "coins",
    ) -> bool:
        key = str(character_id)
        if character_id not in BRAWLER_BY_ID or key in self.brawlers or price < 0:
            return False
        if currency == "gems":
            if self.gems < price:
                return False
            self.gems -= price
        elif currency == "coins":
            if self.coins < price:
                return False
            self.coins -= price
        else:
            return False
        self.brawlers[key] = BrawlerProgress.create(character_id)
        self.brawlers[key].power_points = max(0, power_points)
        return True

    def unlock_skin(self, skin_id: int, price: int = 1) -> bool:
        if (
            skin_id not in SKIN_IDS
            or skin_id in self.owned_skins
            or price < 0
            or self.gems < price
        ):
            return False
        self.gems -= price
        self.owned_skins.append(skin_id)
        self.owned_skins.sort()
        return True

    def grant_resources(
        self,
        coins: int = 0,
        gems: int = 0,
        power_points: int = 0,
        credits: int = 0,
        bling: int = 0,
        token_doubler: int = 0,
    ) -> None:
        """Apply a bounded administrative/reward resource grant."""
        limit = (1 << 31) - 1
        self.coins = max(0, min(limit, self.coins + int(coins)))
        self.gems = max(0, min(limit, self.gems + int(gems)))
        self.power_points = max(0, min(limit, self.power_points + int(power_points)))
        self.credits = max(0, min(limit, self.credits + int(credits)))
        self.bling = max(0, min(limit, self.bling + int(bling)))
        self.token_doubler = max(0, min(limit, self.token_doubler + int(token_doubler)))

    def unlock_all_brawlers(self, power_level: int = 1, power_points: int = 0) -> int:
        level = max(1, min(11, int(power_level)))
        added = 0
        for spec in BRAWLERS:
            key = str(spec.character_id)
            if key not in self.brawlers:
                self.brawlers[key] = BrawlerProgress.create(spec.character_id)
                added += 1
            progress = self.brawlers[key]
            progress.power_level = max(progress.power_level, level)
            progress.power_points = max(progress.power_points, int(power_points), 0)
        return added

    def apply_offline_battle_result(
        self,
        result: int,
        rank: int,
        heroes: list[object] | tuple[object, ...],
    ) -> bool:
        self.battle_count += 1
        placement = max(1, min(10, rank))
        won = result == 0 and placement == 1
        if won:
            self.solo_wins += 1
        else:
            self.losses += 1

        if not heroes:
            return True

        character_id: int | None = None
        for hero in heroes:
            reference = getattr(hero, "brawler_reference", ())
            if (
                getattr(hero, "is_player", False)
                and len(reference) == 2
                and reference[0] == 16
                and reference[1] in BRAWLER_BY_ID
                and str(reference[1]) in self.brawlers
            ):
                character_id = reference[1]
                break
        if character_id is None:
            character_id = self.selected_brawler
        progress = self.brawlers.get(str(character_id))
        if progress is None:
            return True

        trophy_delta = {1: 8, 2: 4, 3: 2}.get(placement, -2)
        progress.trophies = max(0, progress.trophies + trophy_delta)
        progress.highest_trophies = max(progress.highest_trophies, progress.trophies)
        return True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], config: ServerConfig) -> PlayerAccount:
        if not isinstance(raw, dict):
            raise TypeError("account data must be an object")
        defaults = cls()
        fields = {name for name in cls.__dataclass_fields__ if name != "brawlers"}
        values: dict[str, Any] = {}
        for key in fields:
            if key not in raw:
                continue
            value = raw[key]
            default = getattr(defaults, key)
            if isinstance(default, bool):
                if isinstance(value, bool):
                    values[key] = value
            elif isinstance(default, int):
                if isinstance(value, int) and not isinstance(value, bool):
                    values[key] = max(-(1 << 31), min((1 << 31) - 1, value))
            elif isinstance(default, str) and isinstance(value, str):
                values[key] = value
            elif isinstance(default, dict) and isinstance(value, dict):
                clean: dict[str, int] = {}
                for item_key, item_value in value.items():
                    if isinstance(item_key, str) and isinstance(item_value, int) and not isinstance(item_value, bool):
                        clean[item_key] = max(-(1 << 31), min((1 << 31) - 1, item_value))
                values[key] = clean
            elif isinstance(default, list) and isinstance(value, list):
                values[key] = [
                    item for item in value
                    if isinstance(item, int) and not isinstance(item, bool)
                ]
        account = cls(**values)
        raw_brawlers = raw.get("brawlers", {})
        if not isinstance(raw_brawlers, dict):
            raise TypeError("brawlers must be an object")
        for value in raw_brawlers.values():
            if not isinstance(value, dict):
                continue
            try:
                progress = BrawlerProgress(**value)
            except (TypeError, ValueError):
                continue
            numeric_values = (
                progress.character_id,
                progress.unlock_card_id,
                progress.trophies,
                progress.highest_trophies,
                progress.power_level,
                progress.power_points,
                progress.seen_state,
            )
            if (
                all(isinstance(item, int) and not isinstance(item, bool) for item in numeric_values)
                and progress.character_id in BRAWLER_BY_ID
                and progress.unlock_card_id
                == BRAWLER_BY_ID[progress.character_id].unlock_card_id
            ):
                progress.trophies = max(0, progress.trophies)
                progress.highest_trophies = max(progress.trophies, progress.highest_trophies)
                progress.power_level = max(1, min(11, progress.power_level))
                progress.power_points = max(0, progress.power_points)
                progress.seen_state = max(0, progress.seen_state)
                account.brawlers[str(progress.character_id)] = progress
        if "0" not in account.brawlers:
            account.brawlers["0"] = BrawlerProgress.create(0)
        if raw.get("schema_version", 0) < 2:
            # Upgrade profiles written by the earlier Python port. Those
            # profiles had zero progression/currencies and permanently put
            # v68 into the forced tutorial battle, even after client data was
            # cleared because the zeroed JSON remained on the server.
            starter = account.brawlers["0"]
            starter.trophies = max(starter.trophies, config.starting_brawler_trophies)
            starter.highest_trophies = max(
                starter.highest_trophies, config.starting_brawler_trophies
            )
            account.experience = max(account.experience, 1488)
            account.trophy_road_tier = max(account.trophy_road_tier, 454)
            account.player_level = max(account.player_level, 100)
            account.coins = max(account.coins, config.starting_coins)
            account.gems = max(account.gems, config.starting_gems)
            account.power_points = max(account.power_points, config.starting_power_points)
            account.schema_version = 2
        if str(account.selected_brawler) not in account.brawlers:
            account.selected_brawler = 0
        account.name = (account.name or config.initial_name or "Player")[:60]
        account.region = (account.region or config.region or "RU").strip()[:8]
        # Legacy profiles may have no token. Generate one once and persist it;
        # it is intentionally not logged (plaintext is retained for protocol
        # compatibility in this educational local server).
        account.pass_token = (account.pass_token or secrets.token_hex(13))[:1024]
        account.coins = max(0, account.coins)
        account.gems = max(0, account.gems)
        account.credits = max(0, account.credits)
        account.bling = max(0, account.bling)
        account.token_doubler = max(0, account.token_doubler)
        raw_skins = getattr(account, "owned_skins", [])
        account.owned_skins = sorted({
            value for value in raw_skins
            if isinstance(value, int) and not isinstance(value, bool) and value in SKIN_IDS
        })
        account.selected_skins = {
            str(character_id): skin_id
            for character_id, skin_id in account.selected_skins.items()
            if str(character_id) in account.brawlers
            and isinstance(skin_id, int)
            and skin_id in account.owned_skins
        }
        if account.thumbnail != 0 and account.thumbnail not in PLAYER_THUMBNAIL_IDS:
            account.thumbnail = 0
        if account.name_color not in NAME_COLOR_IDS:
            account.name_color = 0
        account.profile_vanity = {
            str(key): value
            for key, value in account.profile_vanity.items()
            if isinstance(key, str)
            and isinstance(value, int)
            and (
                (":" in key and key.split(":", 1)[0].isdigit()
                 and int(key.split(":", 1)[0]) in VANITY_IDS
                 and value in VANITY_IDS[int(key.split(":", 1)[0])])
                or (":" not in key and value >= 0)
            )
        }
        if "power_points" not in raw:
            account.power_points = config.starting_power_points
        account.power_points = max(0, account.power_points)
        return account


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    account_high: int
    account_low: int
    name: str
    trophies: int
    thumbnail: int = 0
    name_color: int = 0


class AccountRepository:
    def __init__(
        self,
        path: Path | None,
        config: ServerConfig,
        account_id: tuple[int, int] = (0, 1),
    ) -> None:
        self.path = path
        self.config = config
        self.account_id = account_id
        self._lock = threading.RLock()
        self._account: PlayerAccount | None = None

    def load(self) -> PlayerAccount:
        with self._lock:
            if self._account is not None:
                return self._account
            if self.path is not None and self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    self._account = PlayerAccount.from_dict(raw, self.config)
                except (
                    OSError,
                    json.JSONDecodeError,
                    TypeError,
                    ValueError,
                    KeyError,
                    AttributeError,
                ):
                    self._account = PlayerAccount.fresh(self.config)
                    self._account.account_high, self._account.account_low = self.account_id
            else:
                self._account = PlayerAccount.fresh(self.config)
                self._account.account_high, self._account.account_low = self.account_id
            self.save(self._account)
            return self._account

    def save(self, account: PlayerAccount) -> None:
        with self._lock:
            self._account = account
            if self.path is None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(account.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            for attempt in range(5):
                try:
                    temporary.replace(self.path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.01 * (attempt + 1))

    def reset(self) -> PlayerAccount:
        with self._lock:
            self._account = PlayerAccount.fresh(self.config)
            self._account.account_high, self._account.account_low = self.account_id
            self.save(self._account)
            return self._account

    def leaderboard(self, account: PlayerAccount, count: int = 50) -> tuple[LeaderboardEntry, ...]:
        bot_names = (
            "ShellyBot", "ColtBot", "BullBot", "BrockBot", "RicoBot", "SpikeBot",
            "Барли-Бот", "Джесси-Бот", "Нита-Бот", "Динамайк-Бот", "Эль Примо",
            "Mortis AI", "Crow AI", "Poco AI", "Бо-Бот", "Piper AI", "Pam AI",
            "Tara AI", "Darryl AI", "Penny AI", "Frank AI", "Gene AI", "Tick AI",
            "Leon AI", "Rosa AI", "Carl AI", "Bibi AI", "8-BIT AI", "Sandy AI",
            "Bea AI", "Emz AI", "Mr.P AI", "Max AI", "Jacky AI", "Gale AI",
            "Nani AI", "Sprout AI", "Surge AI", "Colette AI", "Amber AI",
            "Lou AI", "Byron AI", "Edgar AI", "Ruffs AI", "Stu AI", "Belle AI",
            "Squeak AI", "Grom AI", "Buzz AI", "Griff AI", "Ash AI", "Meg AI",
        )
        entries = [
            LeaderboardEntry(1, index + 100, name, 75 + index * 37, index % 20, index % 12)
            for index, name in enumerate(bot_names)
        ]
        player_entry = LeaderboardEntry(
            account.account_high, account.account_low, account.name,
            account.total_trophies, account.thumbnail, account.name_color,
        )
        entries.sort(key=lambda value: (-value.trophies, value.account_low))
        # Keep the real local player visible even with zero trophies. The APK
        # can then open the player's profile directly from the ranking.
        top = entries[:max(0, count - 1)]
        top.append(player_entry)
        top.sort(key=lambda value: (-value.trophies, value.account_low))
        return tuple(top[:count])

    def profile(self, account_high: int, account_low: int) -> PlayerAccount:
        account = self.load()
        if (account_high, account_low) == account.account_id:
            return account
        for entry in self.leaderboard(account, 50):
            if (entry.account_high, entry.account_low) != (account_high, account_low):
                continue
            bot = PlayerAccount.fresh(self.config)
            bot.account_high = entry.account_high
            bot.account_low = entry.account_low
            bot.name = entry.name
            bot.thumbnail = entry.thumbnail
            bot.name_color = entry.name_color
            bot.brawlers["0"].trophies = entry.trophies
            bot.brawlers["0"].highest_trophies = entry.trophies
            bot.battle_count = max(1, entry.trophies // 8)
            bot.solo_wins = bot.battle_count
            return bot
        return account


class AccountStore:
    """Owns independent on-disk profiles identified by login id and token."""

    def __init__(self, directory: Path | None, config: ServerConfig) -> None:
        self.directory = directory
        self.config = config
        self._repositories: dict[str, AccountRepository] = {}
        self._lock = threading.RLock()

    @property
    def _active_profile_path(self) -> Path | None:
        return self.directory / "active_profile.json" if self.directory is not None else None

    def _active_repository(self) -> AccountRepository | None:
        """Return the local profile used when this APK sends a zero id."""
        path = self._active_profile_path
        if path is None or not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            account_id = (int(raw["account_high"]), int(raw["account_low"]))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        return self._repository_for_account_id(account_id)

    def _set_active_repository(self, repository: AccountRepository) -> None:
        path = self._active_profile_path
        if path is None:
            return
        account = repository.load()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"account_high": account.account_high, "account_low": account.account_low}),
            encoding="utf-8",
        )

    @staticmethod
    def _identity(public_key: bytes) -> tuple[str, tuple[int, int]]:
        digest = hashlib.sha256(public_key).digest()
        key = digest.hex()
        high = int.from_bytes(digest[:4], "big", signed=True)
        low = int.from_bytes(digest[4:8], "big", signed=True)
        if high == 0 and low == 0:
            low = 1
        return key, (high, low)

    def repository_for_client(self, public_key: bytes) -> AccountRepository:
        key, account_id = self._identity(public_key)
        with self._lock:
            repository = self._repositories.get(key)
            if repository is None:
                path = self.directory / f"{key}.json" if self.directory is not None else None
                repository = AccountRepository(path, self.config, account_id)
                self._repositories[key] = repository
            return repository

    def _repository_for_account_id(
        self, account_id: tuple[int, int]
    ) -> AccountRepository | None:
        for repository in self._repositories.values():
            if repository.load().account_id == account_id:
                return repository
        if self.directory is None or not self.directory.exists():
            return None
        for path in self.directory.glob("*.json"):
            if path.name == "active_profile.json":
                continue
            repository = AccountRepository(path, self.config)
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    continue
                raw_id = (raw.get("account_high"), raw.get("account_low"))
                if raw_id != account_id:
                    continue
                account = repository.load()
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
            if account.account_id == account_id:
                self._repositories[path.stem] = repository
                return repository
        return None

    def repository_for_login(
        self, account_high: int, account_low: int, pass_token: str
    ) -> tuple[AccountRepository, bool]:
        """Restore a saved login or create an independent fresh account.

        The Pepper public key is compiled into this APK and is identical on
        every installation, so it cannot identify a player. The account id
        and token stored by the game are the persistent identity instead.
        """

        requested_id = (account_high, account_low)
        with self._lock:
            if requested_id in ((0, 0), (0, 1)):
                repository = self._active_repository()
                if repository is not None:
                    return repository, False
            if requested_id not in ((0, 0), (0, 1)):
                repository = self._repository_for_account_id(requested_id)
                if repository is not None:
                    if secrets.compare_digest(repository.load().pass_token, pass_token):
                        self._set_active_repository(repository)
                        return repository, False
                    # A known account with a bad token must never be replaced.
                    raise PermissionError("invalid account pass token")

            while True:
                # The v68 client renders the public player tag from the low
                # LogicLong part as an unsigned base-14 value.  Generating a
                # signed random low part produced negative ids; this build's
                # client then displayed only "#".  Keep the public low part
                # positive while retaining the full 32-bit signed wire type.
                account_id = (0, secrets.randbelow(0x7FFFFFFE) + 2)
                if self._repository_for_account_id(account_id) is None:
                    break
            key = f"{account_id[0] & 0xFFFFFFFF:08x}{account_id[1] & 0xFFFFFFFF:08x}"
            path = self.directory / f"{key}.json" if self.directory is not None else None
            repository = AccountRepository(path, self.config, account_id)
            self._repositories[key] = repository
            repository.load()
            self._set_active_repository(repository)
            return repository, True

    def reset_all(self) -> None:
        """Delete only explicit per-player JSON profiles after --reset."""

        with self._lock:
            self._repositories.clear()
            active_profile = self._active_profile_path
            if active_profile is not None:
                active_profile.unlink(missing_ok=True)
            if self.directory is None or not self.directory.exists():
                return
            for path in self.directory.glob("*.json"):
                path.unlink()

    def _real_accounts(self) -> list[PlayerAccount]:
        with self._lock:
            repositories = list(self._repositories.values())
            if self.directory is not None and self.directory.exists():
                known_paths = {repository.path for repository in repositories}
                for path in self.directory.glob("*.json"):
                    if path.name == "active_profile.json":
                        continue
                    if path not in known_paths:
                        repositories.append(AccountRepository(path, self.config))
            return [repository.load() for repository in repositories]

    def leaderboard(self, account: PlayerAccount, count: int = 50) -> tuple[LeaderboardEntry, ...]:
        entries = list(AccountRepository(None, self.config).leaderboard(account, count))
        by_id = {(entry.account_high, entry.account_low): entry for entry in entries}
        for other in self._real_accounts():
            by_id[other.account_id] = LeaderboardEntry(
                other.account_high,
                other.account_low,
                other.name,
                other.total_trophies,
                other.thumbnail,
                other.name_color,
            )
        ordered = sorted(by_id.values(), key=lambda entry: (-entry.trophies, entry.account_low))
        if account.account_id not in {(entry.account_high, entry.account_low) for entry in ordered[:count]}:
            ordered = ordered[: max(0, count - 1)] + [by_id[account.account_id]]
            ordered.sort(key=lambda entry: (-entry.trophies, entry.account_low))
        return tuple(ordered[:count])

    def profile(self, account_high: int, account_low: int, fallback: AccountRepository) -> PlayerAccount:
        for account in self._real_accounts():
            if account.account_id == (account_high, account_low):
                return account
        return fallback.profile(account_high, account_low)
