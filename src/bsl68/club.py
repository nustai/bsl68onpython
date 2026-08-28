from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .catalog import ALLIANCE_BADGE_IDS

MAX_CLUB_MEMBERS = 30
MAX_CLUB_MESSAGES = 100

@dataclass
class ClubMessage:
    account_high: int
    account_low: int
    name: str
    text: str
    timestamp: int


@dataclass
class Club:
    club_id: int
    name: str
    description: str = ""
    badge: int = 0
    region: str = "RU"
    club_type: int = 1
    required_trophies: int = 0
    family_friendly: bool = True
    members: dict[str, int] = field(default_factory=dict)
    messages: list[ClubMessage] = field(default_factory=list)


class ClubStore:
    """Small JSON-backed club store used by the v68 social packets."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._clubs: dict[int, Club] = {}
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(raw, list):
            return
        # A single damaged record must not hide all clubs after a restart.
        allowed = {"club_id", "name", "description", "badge", "region",
                   "club_type", "required_trophies", "family_friendly",
                   "members", "messages"}
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                values = {key: value for key, value in item.items() if key in allowed}
                messages = []
                for message in values.get("messages", []):
                    if isinstance(message, dict):
                        message_values = {key: message[key] for key in
                                          ("account_high", "account_low", "name", "text", "timestamp")
                                          if key in message}
                        if len(message_values) == 5:
                            messages.append(ClubMessage(**message_values))
                values["messages"] = messages
                values["members"] = {
                    str(key): int(role)
                    for key, role in dict(values.get("members", {})).items()
                    if isinstance(key, str) and isinstance(role, int)
                }
                club = Club(**values)
            except (TypeError, ValueError, KeyError):
                continue
            self._clubs[club.club_id] = club

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps([asdict(c) for c in self._clubs.values()], ensure_ascii=False),
            encoding="utf-8",
        )
        # Windows file scanners can briefly hold the destination after the
        # write. Retry the atomic swap without falling back to a partial JSON
        # write, which would risk losing the club roster on restart.
        for attempt in range(5):
            try:
                temporary.replace(self.path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.01 * (attempt + 1))

    @staticmethod
    def key(account_id: tuple[int, int]) -> str:
        return f"{account_id[0]}:{account_id[1]}"

    def for_account(self, account_id: tuple[int, int]) -> Club | None:
        with self._lock:
            key = self.key(account_id)
            return next((c for c in self._clubs.values() if key in c.members), None)

    def all(self) -> tuple[Club, ...]:
        with self._lock:
            return tuple(sorted(self._clubs.values(), key=lambda club: club.club_id))

    def get(self, club_id: int) -> Club | None:
        with self._lock:
            return self._clubs.get(club_id)

    def reset(self) -> None:
        with self._lock:
            self._clubs.clear()
            self._save()

    def search(
        self,
        query: str = "",
        region: str | None = None,
        player_trophies: int = 0,
        limit: int = 50,
    ) -> tuple[Club, ...]:
        """Return clubs suitable for the stock join/search screens."""
        needle = " ".join(str(query).casefold().split())[:30]
        safe_region = str(region).strip().casefold() if region else ""
        with self._lock:
            clubs = (
                club for club in self._clubs.values()
                if len(club.members) < MAX_CLUB_MEMBERS
                and club.required_trophies <= max(0, int(player_trophies))
                and (not needle or needle in club.name.casefold())
                and (not safe_region or club.region.casefold() == safe_region)
            )
            ordered = sorted(clubs, key=lambda club: (-len(club.members), club.name.casefold(), club.club_id))
            return tuple(ordered[:max(0, min(int(limit), 50))])

    def create(self, account_id: tuple[int, int], player_name: str, name: str, description: str, badge: int, region: str, club_type: int, required: int, family: bool) -> Club:
        with self._lock:
            existing = self.for_account(account_id)
            if existing:
                return existing
            safe_name = " ".join(str(name).strip().split())[:30] or "Club"
            safe_description = str(description).strip()[:255]
            safe_region = str(region).strip()[:8] or "RU"
            safe_badge = int(badge) if int(badge) in ALLIANCE_BADGE_IDS else 0
            safe_type = max(0, min(int(club_type), 3))
            safe_required = max(0, min(int(required), 2**31 - 1))
            club = Club(max(self._clubs.keys(), default=100000) + 1, safe_name, safe_description, safe_badge, safe_region, safe_type, safe_required, bool(family))
            club.members[self.key(account_id)] = 2
            self._clubs[club.club_id] = club
            self._save()
            return club

    def join(
        self,
        club_id: int,
        account_id: tuple[int, int],
        player_trophies: int = 0,
    ) -> Club | None:
        with self._lock:
            # A player may belong to at most one club.
            if self.for_account(account_id) is not None:
                return None
            club = self._clubs.get(club_id)
            if (
                club is None
                or len(club.members) >= MAX_CLUB_MEMBERS
                or club.club_type >= 2
                or max(0, int(player_trophies)) < club.required_trophies
            ):
                return None
            club.members[self.key(account_id)] = 0
            self._save()
            return club

    def leave(self, account_id: tuple[int, int]) -> None:
        with self._lock:
            club = self.for_account(account_id)
            if club:
                removed_role = club.members.pop(self.key(account_id), None)
                if not club.members:
                    self._clubs.pop(club.club_id, None)
                elif removed_role == 2:
                    # A persisted club must always retain one president.
                    successor = min(
                        club.members,
                        key=lambda key: (-club.members[key], key),
                    )
                    club.members[successor] = 2
                self._save()

    def update_settings(
        self,
        actor_id: tuple[int, int],
        description: str,
        badge: int,
        region: str,
        club_type: int,
        required_trophies: int,
        family_friendly: bool,
    ) -> Club | None:
        with self._lock:
            club = self.for_account(actor_id)
            if club is None or club.members.get(self.key(actor_id)) != 2:
                return None
            club.description = str(description).strip()[:255]
            club.badge = int(badge) if int(badge) in ALLIANCE_BADGE_IDS else 0
            club.region = str(region).strip()[:8] or club.region
            club.club_type = max(0, min(int(club_type), 3))
            club.required_trophies = max(0, min(int(required_trophies), 2**31 - 1))
            club.family_friendly = bool(family_friendly)
            self._save()
            return club

    def change_role(
        self,
        actor_id: tuple[int, int],
        target_id: tuple[int, int],
        role: int,
    ) -> Club | None:
        with self._lock:
            club = self.for_account(actor_id)
            actor_key, target_key = self.key(actor_id), self.key(target_id)
            if (
                club is None
                or club.members.get(actor_key) != 2
                or target_key not in club.members
                or target_key == actor_key
                or role not in (0, 1, 2)
            ):
                return None
            if role == 2:
                club.members[actor_key] = 1
            club.members[target_key] = role
            self._save()
            return club

    def kick(
        self,
        actor_id: tuple[int, int],
        target_id: tuple[int, int],
    ) -> Club | None:
        with self._lock:
            club = self.for_account(actor_id)
            actor_key, target_key = self.key(actor_id), self.key(target_id)
            if club is None or actor_key == target_key or target_key not in club.members:
                return None
            actor_role = club.members.get(actor_key, 0)
            target_role = club.members[target_key]
            if actor_role < 1 or actor_role <= target_role:
                return None
            club.members.pop(target_key)
            self._save()
            return club

    def add_message(self, club: Club, account_id: tuple[int, int], name: str, text: str, timestamp: int) -> ClubMessage | None:
        with self._lock:
            safe_name = " ".join(str(name).strip().split())[:60] or "Player"
            safe_text = str(text).strip()[:255]
            if not safe_text or club is None or self.for_account(account_id) is not club:
                return None
            message = ClubMessage(account_id[0], account_id[1], safe_name, safe_text, int(timestamp))
            club.messages.append(message)
            del club.messages[:-MAX_CLUB_MESSAGES]
            self._save()
            return message
