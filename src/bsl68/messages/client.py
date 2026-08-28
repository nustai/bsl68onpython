from __future__ import annotations

import logging
from dataclasses import dataclass

from ..stream import read_data_reference
from .base import PiranhaMessage


class ClientHelloMessage(PiranhaMessage):
    message_type = 10100
    service_node_type = 1

    def __init__(self) -> None:
        super().__init__()
        self.key_version = 0
        self.major_version = 0
        self.client_seed = 0
        self.values = (0, 0, 0, 0)
        self.reference = ""

    def decode(self) -> None:
        stream = self.byte_stream
        # Match the C# reference exactly: read 6 ints, a string reference
        # (which returns "" without advancing when the "length" field exceeds
        # maxCapacity — this is how the C# engine handles unknown layouts),
        # then 2 more ints.  No length pre-checks.
        values = tuple(stream.read_int() for _ in range(6))
        self.reference = stream.read_string_reference()
        values += (stream.read_int(), stream.read_int())
        self.values = values
        self.key_version = values[1]
        self.major_version = values[2]
        self.client_seed = values[3]


class LoginMessage(PiranhaMessage):
    message_type = 10101
    service_node_type = 1

    def __init__(self) -> None:
        super().__init__()
        self.account_high = 0
        self.account_id = 0
        self.pass_token = ""
        self.client_major_version = 0
        self.client_minor = 0
        self.client_build = 0
        self.resource_sha = ""

    def decode(self) -> None:
        stream = self.byte_stream
        self.account_high = stream.read_int()
        self.account_id = stream.read_int()
        self.pass_token = stream.read_string(1024) or ""
        self.client_major_version = stream.read_int()
        self.client_minor = stream.read_int()
        self.client_build = stream.read_int()
        self.resource_sha = stream.read_string(1024) or ""


class KeepAliveMessage(PiranhaMessage):
    message_type = 10108
    service_node_type = 1


class IgnoredClientMessage(PiranhaMessage):
    """Auxiliary client telemetry/status message that requires no reply."""


class GenericClientMessage(IgnoredClientMessage):
    """A known-safe envelope for optional v68 features not hosted locally."""


class BattleDisabledMessage(IgnoredClientMessage):
    """Any battle, replay, spectate, practice, or matchmaking request."""


class AnalyticsEventMessage(IgnoredClientMessage):
    message_type = 10110
    service_node_type = 1


class SetDeviceTokenMessage(IgnoredClientMessage):
    message_type = 10113
    service_node_type = 1


class AuxiliaryHomeMessage13654(IgnoredClientMessage):
    message_type = 13654
    service_node_type = 9


class PlayerStatusMessage(IgnoredClientMessage):
    message_type = 14366
    service_node_type = 9


class AuxiliaryMessage17502(IgnoredClientMessage):
    message_type = 17502
    service_node_type = 9


class AuxiliaryMessage18977(IgnoredClientMessage):
    message_type = 18977
    service_node_type = 9


class AuxiliaryMessage38101(IgnoredClientMessage):
    message_type = 38101


class AuxiliaryMessage38102(IgnoredClientMessage):
    message_type = 38102


class AuxiliaryMessage38103(IgnoredClientMessage):
    message_type = 38103


class AuxiliaryMessage38104(IgnoredClientMessage):
    message_type = 38104


class AuxiliaryMessage39004(IgnoredClientMessage):
    message_type = 39004


class AuxiliaryPostBattleMessage16650(BattleDisabledMessage):
    # Sent by the v68 client while dismissing the offline battle result.
    message_type = 16650


class ClientCapabilitiesMessage(PiranhaMessage):
    message_type = 10107
    service_node_type = 1

    def __init__(self) -> None:
        super().__init__()
        self.capabilities = 0

    def decode(self) -> None:
        if not self.byte_stream.is_at_end():
            self.capabilities = self.byte_stream.read_vint()


class ChangeAvatarNameMessage(PiranhaMessage):
    message_type = 10212
    service_node_type = 9

    def __init__(self) -> None:
        super().__init__()
        self.name = ""
        self.name_set_by_user = True

    def decode(self) -> None:
        self.name = self.byte_stream.read_string(60) or ""
        self.name_set_by_user = self.byte_stream.read_boolean()


class AvatarNameCheckRequestMessage(PiranhaMessage):
    """Name-dialog validation request sent before ChangeAvatarNameMessage."""

    message_type = 14600
    service_node_type = 9

    def __init__(self) -> None:
        super().__init__()
        self.name = ""

    def decode(self) -> None:
        # This is the general filtered-string limit used by v68's libg.so.
        self.name = self.byte_stream.read_string(900_000) or ""


class GoHomeMessage(PiranhaMessage):
    message_type = 14456
    service_node_type = 9


class LegacyGoHomeMessage(GoHomeMessage):
    """Legacy 2022 id accepted alongside the v62+ GoHome id."""

    message_type = 14101


class GoHomeFromOfflinePracticeMessage(PiranhaMessage):
    """Return home after a client-side practice battle (v50+)."""

    message_type = 17750
    service_node_type = 9

    def __init__(self) -> None:
        super().__init__()
        self.unknown = False

    def decode(self) -> None:
        if not self.byte_stream.is_at_end():
            self.unknown = self.byte_stream.read_boolean()


class LegacyGoHomeFromOfflinePracticeMessage(GoHomeFromOfflinePracticeMessage):
    """Pre-v50 id retained because some modified clients still emit it."""

    message_type = 14109


class StartGameMessage(BattleDisabledMessage):
    """Requests normal server matchmaking from the home-screen battle button."""

    message_type = 14103
    service_node_type = 9


class CancelMatchmakingMessage(BattleDisabledMessage):
    """Cancels an active matchmaking request from the battle loading screen."""

    message_type = 14106
    service_node_type = 9


class LogicCommandData:
    def __init__(self, command_type: int) -> None:
        self.command_type = command_type
        self.tick_when_given = 0
        self.execute_tick = 0
        self.executor_high = 0
        self.executor_low = 0
        self.offer_index = -1
        self.data_reference: tuple[int, ...] = (0,)
        self.currency_slot = 0
        self.brawler_slot = 0
        self.unknown = 0
        self.skin_reference: tuple[int, ...] = (0,)
        self.emote_reference: tuple[int, ...] = (0,)
        self.emote_slot = 0
        self.level_up_reference: tuple[int, ...] = (0,)
        self.level_up_value = 0
        self.level_up_unknown = 0
        self.vanity_csv_id = 0
        self.vanity_id = 0
        self.vanity_slot_id = 0
        self.vanity_slot_index = 0


class EndClientTurnMessage(PiranhaMessage):
    message_type = 14102
    service_node_type = 9

    def __init__(self) -> None:
        super().__init__()
        self.tick = 0
        self.checksum = 0
        self.command_count = 0
        self.commands: list[LogicCommandData] = []
        self.raw_payload = b""

    def _read_command_header(self, command: LogicCommandData) -> None:
        stream = self.byte_stream
        command.tick_when_given = stream.read_vint()
        command.execute_tick = stream.read_vint()
        command.executor_high = stream.read_vint()
        command.executor_low = stream.read_vint()

    def decode(self) -> None:
        stream = self.byte_stream
        self.raw_payload = stream.getvalue()
        try:
            stream.read_boolean()
            self.tick = stream.read_vint()
            # v68 removed the separate checksum field from EndClientTurn.
            # The byte immediately after tick is the command count. Reading
            # an extra VInt here shifted command 505 into bogus ids (0, 86,
            # 117, ...), which broke avatar selection and every newer logic
            # command.
            self.checksum = 0
            self.command_count = stream.read_vint()
        except EOFError:
            self.command_count = 0
            return
        if self.command_count < 0 or self.command_count > 512:
            # Command layouts change between client versions and commands do
            # not have an encoded length.  Keep the turn envelope usable even
            # when a v68 field was interpreted as an implausible count.
            self.command_count = 0
            return

        for _ in range(self.command_count):
            # Some client builds append a truncated command block (most often
            # for an empty/offline turn).  It is safe to retain the envelope
            # and ignore the incomplete command; rejecting the whole message
            # only causes a warning and prevents the normal heartbeat/menu
            # flow from continuing.
            try:
                command = LogicCommandData(stream.read_vint())
                self.commands.append(command)
            except EOFError:
                break
            if command.command_type not in (500, 505, 506, 519, 520, 522, 525, 527, 538, 568, 571):
                # All v68 logic commands start with the common four-field
                # header. Keep the command in the decoded turn and continue;
                # this lets later header-only commands in a multi-command
                # 14102 packet still be handled instead of dropping the turn.
                logging.getLogger(__name__).warning(
                    "Unknown logic command %d in 14102", command.command_type
                )
                self._read_command_header(command)
                continue
            try:
                self._read_command_header(command)
                if command.command_type == 519:
                    command.offer_index = stream.read_vint()
                    command.data_reference = read_data_reference(stream)
                    read_data_reference(stream)
                    command.currency_slot = stream.read_vint()
                elif command.command_type in (505, 522, 525, 527):
                    command.data_reference = read_data_reference(stream)
                    if command.command_type in (522, 525):
                        command.brawler_slot = stream.read_vint()
                elif command.command_type == 506:
                    command.skin_reference = read_data_reference(stream)
                    command.unknown = stream.read_vint()
                elif command.command_type == 520:
                    # LevelUpCommand: brawler reference followed by target
                    # level. Do not consume a speculative trailing field: the
                    # command has no length prefix and that would eat the next
                    # command in a multi-command turn.
                    command.level_up_reference = read_data_reference(stream)
                    command.level_up_value = stream.read_vint()
                elif command.command_type == 538:
                    command.emote_reference = read_data_reference(stream)
                    command.emote_slot = stream.read_vint()
                elif command.command_type == 571:
                    command.unknown = stream.read_vint()
                elif command.command_type == 568:
                    # The complete v68 vanity layout is not confirmed. Read
                    # only the observed fixed fields; a malformed/truncated
                    # command stops this turn rather than desynchronising it.
                    command.unknown = stream.read_vint()
                    command.vanity_csv_id = stream.read_vint()
                    command.vanity_id = stream.read_vint()
                    command.vanity_slot_id = stream.read_vint()
                    if command.vanity_csv_id:
                        command.vanity_slot_index = stream.read_vint()
                    else:
                        command.vanity_slot_index = int(stream.read_boolean())
            except (EOFError, ValueError):
                break

        # Keep a compact trace for APK-specific layouts.  The command has no
        # length prefix, so this is essential when a newer client shifts one
        # of the vanity/map fields.
        logging.getLogger(__name__).info(
            "14102 decoded: tick=%d count=%d commands=%s raw=%s",
            self.tick,
            self.command_count,
            [
                (c.command_type, c.data_reference, c.vanity_csv_id,
                 c.vanity_id, c.vanity_slot_id, c.vanity_slot_index)
                for c in self.commands
            ],
            self.raw_payload[:256].hex(),
        )


@dataclass(slots=True)
class BattleHero:
    brawler_reference: tuple[int, ...]
    skin_reference: tuple[int, ...]
    team: int
    is_player: bool
    player_name: str


class AskForBattleEndMessage(PiranhaMessage):
    message_type = 14110
    service_node_type = 9

    def __init__(self) -> None:
        super().__init__()
        self.unknown = 0
        self.result = 0
        self.rank = 0
        self.map_reference: tuple[int, ...] = (0,)
        self.heroes: list[BattleHero] = []

    def decode(self) -> None:
        stream = self.byte_stream
        self.unknown = stream.read_vint()
        self.result = stream.read_vint()
        self.rank = stream.read_vint()
        self.map_reference = read_data_reference(stream)
        hero_count = stream.read_vint()
        if hero_count < 0 or hero_count > 64:
            raise ValueError("invalid offline battle hero count")
        for _ in range(hero_count):
            self.heroes.append(
                BattleHero(
                    read_data_reference(stream),
                    read_data_reference(stream),
                    stream.read_vint(),
                    stream.read_boolean(),
                    stream.read_string(60) or "",
                )
            )


class SinglePlayerMatchRequestMessage(PiranhaMessage):
    """Client-side battle request; no loading packet is needed in offline mode."""

    message_type = 14118
    service_node_type = 9


class GetLeaderboardMessage(PiranhaMessage):
    message_type = 14403
    service_node_type = 13

    def __init__(self) -> None:
        super().__init__()
        self.regional = False
        self.unknown = 0
        self.brawler_reference: tuple[int, ...] = (0,)
        self.leaderboard_type = 1

    def decode(self) -> None:
        stream = self.byte_stream
        self.regional = stream.read_boolean()
        self.unknown = stream.read_vint()
        self.brawler_reference = read_data_reference(stream)
        self.leaderboard_type = stream.read_vint()


class GetPlayerProfileMessage(PiranhaMessage):
    message_type = 15081
    service_node_type = 9

    def __init__(self) -> None:
        super().__init__()
        self.account_high = 0
        self.account_low = 1

    def decode(self) -> None:
        stream = self.byte_stream
        has_battle_info = stream.read_boolean()
        if has_battle_info:
            # TODO: the optional battle-card block is not fully documented.
            # Do not guess its length: retaining the default id is safer than
            # consuming bytes belonging to another field.
            return
        stream.read_vint()
        self.account_high = stream.read_int()
        self.account_low = stream.read_int()


class AskForAllianceDataMessage(PiranhaMessage):
    message_type = 14302
    service_node_type = 9

    def decode(self) -> None:
        self.club_high = self.byte_stream.read_int()
        self.club_low = self.byte_stream.read_int()
        self.unknown = self.byte_stream.read_boolean()


class CreateAllianceMessage(PiranhaMessage):
    message_type = 14301
    service_node_type = 9

    def decode(self) -> None:
        s = self.byte_stream
        self.name = s.read_string(60) or "Club"
        self.description = s.read_string(255) or ""
        self.badge = read_data_reference(s)
        self.region = read_data_reference(s)
        self.club_type = s.read_vint()
        self.required_trophies = s.read_vint()
        self.family_friendly = s.read_boolean()


class AskForJoinableAlliancesListMessage(PiranhaMessage):
    message_type = 14303
    service_node_type = 9


class JoinAllianceMessage(PiranhaMessage):
    message_type = 14305
    service_node_type = 9

    def decode(self) -> None:
        self.club_high = self.byte_stream.read_int()
        self.club_low = self.byte_stream.read_int()


class ChangeAllianceMemberRoleMessage(PiranhaMessage):
    message_type = 14306
    service_node_type = 9

    def decode(self) -> None:
        self.account_high = self.byte_stream.read_int()
        self.account_low = self.byte_stream.read_int()
        self.role = self.byte_stream.read_vint()


class KickAllianceMemberMessage(PiranhaMessage):
    message_type = 14307
    service_node_type = 9

    def decode(self) -> None:
        self.account_high = self.byte_stream.read_int()
        self.account_low = self.byte_stream.read_int()


class LeaveAllianceMessage(PiranhaMessage):
    message_type = 14308
    service_node_type = 9


class ChatToAllianceStreamMessage(PiranhaMessage):
    message_type = 14315
    service_node_type = 9

    def decode(self) -> None:
        self.text = self.byte_stream.read_string(255) or ""


class AskForAllianceStreamMessage(PiranhaMessage):
    """Client requests alliance stream (chat) entries."""

    message_type = 14304
    service_node_type = 9


class ChangeAllianceSettingsMessage(PiranhaMessage):
    """v44-v68 alliance settings layout shared by the reference servers."""

    message_type = 14316
    service_node_type = 9

    def decode(self) -> None:
        stream = self.byte_stream
        self.description = stream.read_string(255) or ""
        self.badge = read_data_reference(stream)
        self.region = read_data_reference(stream)
        self.club_type = stream.read_vint()
        self.required_trophies = stream.read_vint()
        self.family_friendly = stream.read_boolean()


class SearchAlliancesMessage(PiranhaMessage):
    message_type = 14324
    service_node_type = 9

    def decode(self) -> None:
        self.query = self.byte_stream.read_string(60) or ""
