from __future__ import annotations

from collections.abc import Iterable

from ..account import LeaderboardEntry, PlayerAccount, ServerConfig
from ..stream import LogicLong, write_data_reference
from .base import PiranhaMessage

_ALPHABET = "0289PYLQGRJCUV"
_BASE = 14


def _player_tag(account_low: int) -> str:
    """Encode an account low as a Brawl-Stars-style player tag like \"#2PP\"."""
    # LogicLong parts are signed, but the public tag encodes the low part as
    # an unsigned 32-bit value. Negative ids must not become an empty '#'.
    account_low &= 0xFFFFFFFF
    chars: list[str] = []
    value = account_low
    if value == 0:
        chars.append(_ALPHABET[0])
    while value > 0:
        chars.append(_ALPHABET[value % _BASE])
        value //= _BASE
    return "#" + "".join(reversed(chars))


def _write_player_display(stream, name: str, thumbnail: int, name_color: int) -> None:
    stream.write_string(name)
    stream.write_vint(100)
    stream.write_vint(28_000_000 + thumbnail)
    stream.write_vint(43_000_000 + name_color)
    stream.write_vint(0)
    stream.write_boolean(False)
    stream.write_vint(0)
    stream.write_vint(0)


class ServerHelloMessage(PiranhaMessage):
    message_type = 20100
    service_node_type = 1

    def __init__(self, token: bytes = b"") -> None:
        super().__init__()
        self.token = token

    def encode(self) -> None:
        self.byte_stream.write_bytes(self.token)


class KeepAliveServerMessage(PiranhaMessage):
    message_type = 20108
    service_node_type = 1


class LoginFailedMessage(PiranhaMessage):
    """Graceful v68 login rejection instead of dropping the TCP session."""

    message_type = 20103
    service_node_type = 1

    def __init__(self, error_code: int = 1, reason: str = "Login failed") -> None:
        super().__init__()
        self.error_code = error_code
        self.reason = reason[:255]

    def encode(self) -> None:
        s = self.byte_stream
        s.write_int(self.error_code)
        s.write_string("")  # resource fingerprint
        s.write_string("")  # redirect domain
        s.write_string("")  # content URL
        s.write_string("")  # update URL
        s.write_string(self.reason)
        s.write_int(0)  # maintenance seconds
        s.write_boolean(False)
        s.write_int(0)  # compressed fingerprint length
        s.write_int(0)  # content URL list count
        s.write_int(0)  # app store
        s.write_int(0)  # maintenance type
        s.write_string("")
        s.write_int(0)
        s.write_boolean(True)
        s.write_boolean(True)
        s.write_string("")
        s.write_vint(0)
        s.write_string("")
        s.write_boolean(False)


class LobbyInfoMessage(PiranhaMessage):
    message_type = 23457
    service_node_type = 9

    def __init__(self, player_count: int = 1, text: str = "BSL.v68 Python") -> None:
        super().__init__()
        self.player_count = max(0, player_count)
        self.text = text[:255]

    def encode(self) -> None:
        self.byte_stream.write_vint(self.player_count)
        self.byte_stream.write_string(self.text)
        self.byte_stream.write_vint(0)  # event count
        self.byte_stream.write_vint(0)  # v51+ timer


class MyAllianceMessage(PiranhaMessage):
    message_type = 24399
    service_node_type = 9

    def __init__(self, club=None, account=None) -> None:
        super().__init__()
        self.club = club
        self.account = account

    def encode(self) -> None:
        s = self.byte_stream
        if self.club is None:
            # AllianceHeader in the v51-v54 implementations is optional,
            # followed by the common trailer flag.  A second VInt here
            # shifts the next server message when the player has no club.
            s.write_vint(0); s.write_boolean(False); return
        member_role = self.club.members.get(f"{self.account.account_high}:{self.account.account_low}", 0)
        s.write_vint(1); s.write_boolean(True)
        write_data_reference(s, 25, member_role)
        _write_club_header(s, self.club)
        s.write_boolean(False)


def _write_club_header(s, club) -> None:
    # Alliance headers use fixed-width LogicLongs (not VLongs).
    # AllianceHeaderEntry — verified against BSDS-V44
    s.write_int(0); s.write_int(club.club_id); s.write_string(club.name)
    write_data_reference(s, 8, club.badge); s.write_vint(club.club_type)
    s.write_vint(len(club.members))  # member count
    s.write_vint(0)  # total trophies (not tracked)
    s.write_vint(club.required_trophies)
    write_data_reference(s, 0)  # empty data reference
    s.write_string(club.region); s.write_vint(0); s.write_boolean(club.family_friendly)
    s.write_vint(0)


def _write_club_members(s, club, account_lookup) -> None:
    # The client allocates a fixed member-row structure. Never advertise more
    # than 30 rows, even if an old JSON file contains stale members.
    members = tuple(club.members.items())[:30]
    s.write_vint(len(members))
    for key, role in members:
        high, low = (int(v) for v in key.split(":", 1))
        account = account_lookup((high, low))
        s.write_int(high); s.write_int(low)
        s.write_vint(role)
        s.write_vint(account.total_trophies if account else 0)
        s.write_vint(0); s.write_vint(0); s.write_vint(0)
        s.write_boolean(False)
        s.write_string(account.name if account else "Player")
        s.write_vint(100)
        s.write_vint(28_000_000 + (account.thumbnail if account else 0))
        s.write_vint(43_000_000 + (account.name_color if account else 0))
        s.write_vint(46_000_000)
        s.write_vint(-1)
        s.write_boolean(False)
        s.write_vint(0)
        s.write_vint(200)


class AllianceDataMessage(PiranhaMessage):
    """AllianceDataMessage — verified against BSDS-V44 / Power-Brawl-v57."""

    message_type = 24301
    service_node_type = 9

    def __init__(self, club=None, account_lookup=None) -> None:
        super().__init__()
        self.club = club
        self.account_lookup = account_lookup or (lambda _: None)

    def encode(self) -> None:
        s = self.byte_stream
        s.write_boolean(False)  # isShortData
        _write_club_header(s, self.club)
        s.write_string(self.club.description)
        _write_club_members(s, self.club, self.account_lookup)


class ChangeAllianceSettingsOkMessage(PiranhaMessage):
    """Full refreshed alliance state returned after message 14316."""

    message_type = 24313
    service_node_type = 9

    def __init__(self, club=None, account_lookup=None) -> None:
        super().__init__()
        self.club = club
        self.account_lookup = account_lookup or (lambda _: None)

    def encode(self) -> None:
        _write_club_header(self.byte_stream, self.club)
        self.byte_stream.write_string(self.club.description)
        _write_club_members(self.byte_stream, self.club, self.account_lookup)


class AllianceStreamMessage(PiranhaMessage):
    """AllianceStreamMessage — verified against BSDS-V44 StreamEntry + ChatStreamEntry.

    Layout per entry:
      - stream_type (vint, always 2 for chat)
      - StreamEntry base:
          - stream_id: LogicLong (fixed write_int pair)
          - player_id: LogicLong (fixed write_int pair)
          - player_name: string
          - player_role: vint
          - unknown vint (0)
          - boolean (False)
      - message text: string
    """

    message_type = 24311
    service_node_type = 9

    def __init__(self, club=None) -> None:
        super().__init__(); self.club = club

    def encode(self) -> None:
        s = self.byte_stream
        # Only complete, bounded records are sent. A malformed persisted entry
        # must never shift the following stream entry and crash the client.
        entries = []
        if self.club is not None:
            for item in self.club.messages[-100:]:
                if (
                    isinstance(item.account_high, int)
                    and isinstance(item.account_low, int)
                    and isinstance(item.timestamp, int)
                    and isinstance(item.name, str)
                    and isinstance(item.text, str)
                    and item.name
                    and item.text
                    and len(item.name.encode("utf-8")) <= 60
                    and len(item.text.encode("utf-8")) <= 255
                ):
                    entries.append(item)
        s.write_vint(len(entries))
        for item in entries:
            role = self.club.members.get(f"{item.account_high}:{item.account_low}", 0)
            s.write_vint(2)  # ChatStreamEntry type
            # StreamEntry base fields: both IDs are fixed LogicLong values.
            s.write_int(0); s.write_int(item.timestamp)
            s.write_int(item.account_high); s.write_int(item.account_low)
            s.write_string(item.name)
            s.write_vint(role)
            s.write_vint(0)
            s.write_boolean(False)
            s.write_string(item.text)


class JoinableAllianceListMessage(PiranhaMessage):
    message_type = 24304
    service_node_type = 9

    def __init__(self, clubs=()) -> None:
        super().__init__(); self.clubs = tuple(clubs)

    def encode(self) -> None:
        s = self.byte_stream; s.write_vint(len(self.clubs))
        for club in self.clubs:
            _write_club_header(s, club); s.write_string(club.description)


class AllianceSearchResultMessage(JoinableAllianceListMessage):
    message_type = 24324


class AllianceResponseMessage(PiranhaMessage):
    message_type = 24333
    service_node_type = 9

    def __init__(self, response: int = 0) -> None:
        super().__init__(); self.response = response

    def encode(self) -> None:
        self.byte_stream.write_vint(self.response)


class BattleEndMessage(PiranhaMessage):
    """Acknowledge the result calculated by the client's offline battle."""

    message_type = 23456
    service_node_type = 9

    def __init__(
        self,
        rank: int = 0,
        heroes: Iterable[object] = (),
        account: PlayerAccount | None = None,
    ) -> None:
        super().__init__()
        self.rank = rank
        self.heroes = tuple(heroes)
        self.account = account or PlayerAccount.fresh(ServerConfig())

    def encode(self) -> None:
        s = self.byte_stream
        wv, wb = s.write_vint, s.write_boolean
        wr = lambda reference: write_data_reference(s, *reference)

        for _ in range(4):
            s.write_int(0)  # two fixed-width LogicLong battle UUID values
        wv(2)  # offline/practice result
        wv(self.rank)
        for _ in range(9):
            wv(0)  # rewards, duration and championship fields
        wb(False); wv(0); wv(0); wb(False); wb(False)
        for _ in range(6):
            wv(0)
        wb(False); wb(False); wb(False); wb(True)
        wb(False); wb(False); wb(False); wv(-1); wb(False)

        wv(len(self.heroes))
        for hero in self.heroes:
            is_player = bool(getattr(hero, "is_player", False))
            team = bool(getattr(hero, "team", 0))
            wb(is_player); wb(team); wb(team)
            s.write_byte(1); wr(getattr(hero, "brawler_reference", (16, 0)))
            s.write_byte(1); wr(getattr(hero, "skin_reference", (0,)))
            s.write_byte(1); wv(1250)
            s.write_byte(1); wv(11)
            s.write_byte(1); wv(0)
            wv(0); wv(0)
            wb(is_player)
            if is_player:
                LogicLong(self.account.account_high, self.account.account_low).encode(s)
            s.write_string(getattr(hero, "player_name", "") or self.account.name)
            wv(100); wv(28_000_000 + self.account.thumbnail)
            wv(43_000_000 + self.account.name_color); wv(-2)
            wb(False)  # no club block
            s.write_int8(1); wv(5978); s.write_int8(1); wv(0)
            s.write_int16(5); s.write_int16(3)
            s.write_int(27328); s.write_int(25659)
            write_data_reference(s, 0)

        for value in (0, 1, 0, 0, 0, 0, 0):
            wv(value)
        for _ in range(4):
            wb(False)
        wv(0); wv(0); wv(0); wb(False); wv(0); wb(False); wv(0)
        wb(False); wb(False); wv(0); wv(0)
        wb(False); wb(False); wb(False)


class AvatarNameCheckResponseMessage(PiranhaMessage):
    message_type = 20300
    service_node_type = 9

    def __init__(self, name: str = "", rejected: bool = False, error_code: int = 0) -> None:
        super().__init__()
        self.name = name
        self.rejected = rejected
        self.error_code = error_code

    def encode(self) -> None:
        # Verified against v68 libg.so: boolean, fixed-width int, string.
        self.byte_stream.write_boolean(self.rejected)
        self.byte_stream.write_int(self.error_code)
        self.byte_stream.write_string(self.name)


class LoginOkMessage(PiranhaMessage):
    message_type = 20104
    service_node_type = 1

    def __init__(self, account: PlayerAccount | None = None) -> None:
        super().__init__()
        self.account = account or PlayerAccount.fresh(ServerConfig())

    def encode(self) -> None:
        s = self.byte_stream
        s.write_int(self.account.account_high)
        s.write_int(self.account.account_low)
        s.write_int(self.account.account_high)
        s.write_int(self.account.account_low)
        s.write_string(self.account.pass_token)
        s.write_string("")
        s.write_string("")
        s.write_int(68)
        s.write_int(250)
        s.write_int(1)
        s.write_string("dev")
        for _ in range(3):
            s.write_int(0)
        for _ in range(3):
            s.write_string("")
        s.write_int(0)
        s.write_string("")
        s.write_string(self.account.region)
        s.write_string("")
        s.write_int(0)
        s.write_string("")
        s.write_int(2)
        s.write_string("https://game-assets.brawlstarsgame.com")
        s.write_string("http://a678dbc1c015a893c9fd-4e8cc3b1ad3a3c940c504815caefa967.r87.cf2.rackcdn.com")
        s.write_int(2)
        s.write_string("https://event-assets.brawlstars.com")
        s.write_string("https://24b999e6da07674e22b0-8209975788a0f2469e68e84405ae4fcf.ssl.cf2.rackcdn.com/event-assets")
        s.write_vint(0)
        s.write_string("")
        s.write_boolean(True)
        s.write_boolean(False)
        for _ in range(5):
            s.write_string("")
        for _ in range(5):
            s.write_boolean(False)


class OwnHomeDataMessage(PiranhaMessage):
    message_type = 24101
    service_node_type = 9

    def __init__(
        self,
        account: PlayerAccount | None = None,
        config: ServerConfig | None = None,
    ) -> None:
        super().__init__()
        self.config = config or ServerConfig()
        self.account = account or PlayerAccount.fresh(self.config)

    def _encode_avatar_slot(self, class_id: int, instance_id: int, value: int) -> None:
        write_data_reference(self.byte_stream, class_id, instance_id)
        self.byte_stream.write_vint(-1)
        self.byte_stream.write_vint(value)

    def _avatar_groups(self) -> dict[int, list[tuple[int, int, int]]]:
        account = self.account
        groups: dict[int, list[tuple[int, int, int]]] = {0: []}
        for brawler in account.unlocked_brawlers:
            groups[0].append((23, brawler.unlock_card_id, 1))
        # This APK keeps the legacy private-server currency mapping: resource
        # 5:8 is localized as Coins, while its new global Power Points balance
        # is resource 5:22. Resource 5:1 is labelled Tokens in this client.
        groups[0].append((5, 8, account.coins))
        groups[0].append((5, 22, account.power_points))
        groups[1] = [(16, b.character_id, b.trophies) for b in account.unlocked_brawlers]
        groups[2] = [(16, b.character_id, b.highest_trophies) for b in account.unlocked_brawlers]
        groups[5] = [(16, b.character_id, max(0, b.power_level - 1)) for b in account.unlocked_brawlers]
        groups[7] = [(16, b.character_id, b.seen_state) for b in account.unlocked_brawlers]
        return groups

    def encode(self) -> None:
        s, account, config = self.byte_stream, self.account, self.config
        wv, wi, wb, wy, ws = s.write_vint, s.write_int, s.write_boolean, s.write_byte, s.write_string
        wr = lambda class_id, instance_id=None: write_data_reference(s, class_id, instance_id)
        wvl = lambda high, low: s.write_vlong(LogicLong(high, low))

        wv(0); wv(-1)
        wv(0); wv(0)
        for value in (
            account.total_trophies,
            account.highest_trophies,
            account.highest_trophies,
            account.trophy_road_tier,
            account.experience,
        ):
            wv(value)
        wr(28, account.thumbnail); wr(43, account.name_color)
        for _ in range(8):
            wv(0)
        for value in (account.highest_trophies, 0, 1):
            wv(value)
        wb(True)
        for value in (19500, 111111, 1375134, 0, 1375134, 0, 0, 0):
            wv(value)
        wb(True)
        for value in (2, 2, 2, 0, 0, 0):
            wv(value)

        # Keep the stock v68 shop block byte-compatible with the working C#
        # server. The previous custom offers used an incorrect v68 layout and
        # shifted every following field, which made the client believe it was
        # already matchmaking and hid currencies/the shop.
        wv(0)

        for value in (200, -1, 0, 0, -1):
            wv(value)
        wy(1); wr(16, account.selected_brawler)
        ws(account.region or config.region); ws("BSL.v68 Python")
        wv(8)
        for high, low in ((1, 9), (1, 22), (3, 25), (1, 24), (2, 15), (32447, 28), (100, 46), (1, 52)):
            wvl(high, low)
        wv(0)
        wv(1)
        for value in (52, 0):
            wv(value)
        wb(False); wv(0)
        wb(False); wb(False); wb(True)
        for _ in range(4): wi(0)
        wb(True)
        for _ in range(4): wi(0)
        wb(False); wb(True)
        for _ in range(4): wi(0)
        wr(0); wv(0)
        if wb(True):
            for _ in range(6): wv(0)
            ws("")
        if wb(True):
            # v68 expects the vanity collection here. Sending the entire
            # 1325-entry thumbnail catalogue (as the old experiment did)
            # shifts the following LogicClientHome fields in some builds and
            # causes libg.so to segfault. Report only the active item until
            # the complete v68 vanity layout is implemented.
            wv(1)
            wr(28, account.thumbnail)
            wv(0)
        wb(False)
        wi(0); wv(0); wr(16, 0); wb(False)
        for value in (-1, 0, 0, 0, 0, 0, 0, 0): wv(value)
        for _ in range(4): wr(2, 0)
        wb(False); wr(2, 0); wv(770); wb(False); wb(False)

        wv(38)
        for value in range(1, 39): wv(value)
        wv(1)
        for value in (-1, 1, 0, 0, 85926, 5): wv(value)
        wr(15, 13); wr(0); wv(0); ws(None)
        for _ in range(6): wv(0)
        wb(False); wb(False); wv(0); wb(False); wv(0); wv(0)
        for _ in range(4): wb(False)
        wv(-1); wb(False); wr(0); wb(False)
        for _ in range(4): wv(-1)
        for _ in range(8): wb(False)
        wv(0); wv(0)
        wv(10)
        for value in (20, 35, 75, 140, 290, 480, 800, 1250, 1875, 2800): wv(value)
        wv(4)
        for value in (30, 80, 170, 360): wv(value)
        wv(4)
        for value in (300, 880, 2040, 4680): wv(value)
        wv(0)
        wv(21)
        for high, low in (
            (501, 10008), (0, 10046), (30, 10050), (0, 10051), (5600, 10060),
            (200, 117), (1, 128), (0, 65), (41000174, 1), (99999999, 131),
            (100000, 138), (1, 95), (55598, 47), (1, 123), (200, 124),
            (55598, 48), (3, 50), (500, 1100), (500, 1101), (1, 1002), (500, 1102),
        ):
            wvl(high, low)
        for _ in range(9): wv(0)
        wv(6)
        for value in (0, 29, 79, 169, 349, 699): wv(value)
        wv(6)
        for value in (0, 160, 450, 500, 1250, 2500): wv(value)
        wv(5)
        for value in (0, 100, 400, 1000, 3000): wv(value)
        for _ in range(7): wv(0)

        LogicLong(account.account_high, account.account_low).encode(s)
        wv(0); wv(-1); wb(False)
        for _ in range(3): wv(0)
        for _ in range(4): wb(False)
        wv(0); wb(True)
        for _ in range(3): wv(0)
        wv(1); wr(16, account.selected_brawler)
        for value in (1900, 349, 0, 0, 0, 0, 0, 0, 0, 0): wv(value)
        for _ in range(6): wr(0)
        for _ in range(5): wb(False)
        wv(0); wv(0); wv(0); wi(-1488); wb(False)
        for value in (0, 0, 51998, 0, 0, 0, 0, 0, 0): wv(value)
        wb(False)
        for _ in range(3): wv(0)
        wb(False); wb(False); wb(False)
        wv(2); wr(95, 0); wv(1); wr(95, 1); wv(1)
        for _ in range(4): wb(False)
        wv(0); wv(0); wb(False); wb(False)

        LogicLong(account.account_high, account.account_low).encode_v(s)
        LogicLong(account.account_high, account.account_low).encode_v(s)
        LogicLong.from_int(0).encode_v(s)
        s.write_string_reference(account.name)
        wb(account.name_set); wi(-1)

        groups = self._avatar_groups()
        wv(35)
        for index in range(35):
            wv(0)  # transient slots
            slots = groups.get(index, ())
            wv(len(slots))
            for class_id, instance_id, value in slots:
                self._encode_avatar_slot(class_id, instance_id, value)

        for value in (
            account.gems, account.gems, 0, account.player_level, 0, account.battle_count,
            account.solo_wins, account.losses, 0, account.solo_wins, 0, 2, 1, 0, 0,
        ):
            wv(value)
        ws(None)
        for value in (0, 0, 2, 0): wv(value)
        wb(False)


class PlayerProfileMessage(PiranhaMessage):
    message_type = 24113
    service_node_type = 9

    def __init__(self, account: PlayerAccount | None = None, club=None) -> None:
        super().__init__()
        self.account = account or PlayerAccount.fresh(ServerConfig())
        self.club = club

    def encode(self) -> None:
        s, account = self.byte_stream, self.account
        wv, wb = s.write_vint, s.write_boolean
        wr = lambda class_id, instance_id=None: write_data_reference(s, class_id, instance_id)

        s.write_vlong(LogicLong(account.account_high, account.account_low))
        wr(16, account.selected_brawler)
        wr(0)
        wv(len(account.unlocked_brawlers))
        for brawler in account.unlocked_brawlers:
            wr(16, brawler.character_id)
            selected_skin = account.selected_skins.get(str(brawler.character_id))
            wr(29, selected_skin) if isinstance(selected_skin, int) else wr(0)
            wv(brawler.trophies)
            wv(brawler.highest_trophies)
            wv(brawler.power_level)
            wv(0)
            wv(0)

        stats = (
            (1, account.wins_3v3), (2, account.experience),
            (3, account.total_trophies), (4, account.highest_trophies),
            (5, len(account.brawlers)), (8, account.solo_wins),
            (11, account.duo_wins), (9, 0), (12, 0), (13, 0),
            (14, 0), (15, 0), (16, 0), (18, 0), (17, 0),
            (19, 0), (20, 0), (21, 0),
        )
        wv(len(stats))
        for stat_id, value in stats:
            wv(stat_id); wv(value)

        _write_player_display(s, account.name, account.thumbnail, account.name_color)
        # The working v51-v54 profile wrapper has one common trailer after
        # the optional alliance header: role data-reference, then one VInt.
        # The old port omitted that VInt for players without a club and sent
        # a literal 16 for club members, shifting the following profile data.
        if self.club is None:
            wb(False)
            wr(0)
        else:
            wb(True)
            _write_club_header(s, self.club)
            role = self.club.members.get(
                f"{account.account_high}:{account.account_low}", 0
            )
            wr(25, role) if role > 0 else wr(0)
        wv(0)


class LeaderboardMessage(PiranhaMessage):
    message_type = 24403
    service_node_type = 13

    def __init__(
        self,
        leaderboard_type: int = 1,
        brawler_reference: tuple[int, ...] = (0,),
        entries: Iterable[LeaderboardEntry] = (),
        region: str = "RU",
    ) -> None:
        super().__init__()
        self.leaderboard_type = leaderboard_type
        self.brawler_reference = brawler_reference
        self.entries = tuple(entries)
        self.region = region

    def encode(self) -> None:
        s = self.byte_stream
        wv, wb = s.write_vint, s.write_boolean
        wv(self.leaderboard_type)
        wv(0)
        if len(self.brawler_reference) == 2:
            write_data_reference(s, self.brawler_reference[0], self.brawler_reference[1])
        else:
            write_data_reference(s, 0)
        s.write_string(self.region)
        wv(len(self.entries))
        for rank, entry in enumerate(self.entries, 1):
            wb(False)  # optional alliance display
            wv(rank)
            wv(entry.trophies)
            wb(True)
            s.write_string("")
            _write_player_display(s, entry.name, entry.thumbnail, entry.name_color)
            wv(0)
            wb(True)
            LogicLong(entry.account_high, entry.account_low).encode(s)
            wv(0)
        wv(0); wv(0); wv(0); wv(0)
        s.write_string(self.region)


class AvailableServerCommandMessage(PiranhaMessage):
    message_type = 24111
    service_node_type = 9

    def __init__(self, name: str = "Player", name_set_by_user: bool = True) -> None:
        super().__init__()
        self.name = name
        self.name_set_by_user = name_set_by_user

    def encode(self) -> None:
        s = self.byte_stream
        s.write_vint(201)
        s.write_string(self.name)
        s.write_vint(self.name_set_by_user)
        # v68 added a second string before the LogicServerCommand base data.
        s.write_string("")
        for value in (-1, -1, -1, 0, 0):
            s.write_vint(value)


class OutOfSyncMessage(PiranhaMessage):
    message_type = 24104
    service_node_type = 9

    def encode(self) -> None:
        self.byte_stream.write_vint(0)
        self.byte_stream.write_vint(0)
        self.byte_stream.write_vint(0)
