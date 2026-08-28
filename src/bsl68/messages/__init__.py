from .base import PiranhaMessage
from .client import (
    AnalyticsEventMessage,
    AskForAllianceDataMessage,
    AskForAllianceStreamMessage,
    AskForBattleEndMessage,
    AskForJoinableAlliancesListMessage,
    AuxiliaryHomeMessage13654,
    AuxiliaryMessage17502,
    AuxiliaryMessage18977,
    AuxiliaryMessage38101,
    AuxiliaryMessage38102,
    AuxiliaryMessage38103,
    AuxiliaryMessage38104,
    AuxiliaryMessage39004,
    AuxiliaryPostBattleMessage16650,
    AvatarNameCheckRequestMessage,
    BattleDisabledMessage,
    CancelMatchmakingMessage,
    ChangeAllianceMemberRoleMessage,
    ChangeAllianceSettingsMessage,
    ChangeAvatarNameMessage,
    ChatToAllianceStreamMessage,
    ClientCapabilitiesMessage,
    ClientHelloMessage,
    CreateAllianceMessage,
    EndClientTurnMessage,
    GenericClientMessage,
    GetLeaderboardMessage,
    GetPlayerProfileMessage,
    GoHomeFromOfflinePracticeMessage,
    GoHomeMessage,
    IgnoredClientMessage,
    JoinAllianceMessage,
    KeepAliveMessage,
    KickAllianceMemberMessage,
    LeaveAllianceMessage,
    LegacyGoHomeFromOfflinePracticeMessage,
    LegacyGoHomeMessage,
    LoginMessage,
    PlayerStatusMessage,
    SearchAlliancesMessage,
    SetDeviceTokenMessage,
    SinglePlayerMatchRequestMessage,
    StartGameMessage,
)
from .server import (
    AllianceDataMessage,
    AllianceResponseMessage,
    AllianceSearchResultMessage,
    AllianceStreamMessage,
    AvailableServerCommandMessage,
    AvatarNameCheckResponseMessage,
    BattleEndMessage,
    ChangeAllianceSettingsOkMessage,
    JoinableAllianceListMessage,
    KeepAliveServerMessage,
    LeaderboardMessage,
    LobbyInfoMessage,
    LoginFailedMessage,
    LoginOkMessage,
    MyAllianceMessage,
    OutOfSyncMessage,
    OwnHomeDataMessage,
    PlayerProfileMessage,
    ServerHelloMessage,
)

_MESSAGE_CLASSES: tuple[type[PiranhaMessage], ...] = (
    ClientHelloMessage, LoginMessage, ClientCapabilitiesMessage, KeepAliveMessage,
    AnalyticsEventMessage, SetDeviceTokenMessage, AuxiliaryHomeMessage13654,
    PlayerStatusMessage, AuxiliaryMessage17502, AuxiliaryMessage18977,
    AuxiliaryMessage38101, AuxiliaryMessage38102, AuxiliaryMessage38103,
    AuxiliaryMessage38104, AuxiliaryMessage39004, AuxiliaryPostBattleMessage16650,
    AvatarNameCheckRequestMessage, ChangeAvatarNameMessage, CancelMatchmakingMessage,
    GoHomeMessage, LegacyGoHomeMessage, GoHomeFromOfflinePracticeMessage,
    LegacyGoHomeFromOfflinePracticeMessage, EndClientTurnMessage, AskForBattleEndMessage,
    SinglePlayerMatchRequestMessage, StartGameMessage, GetLeaderboardMessage,
    GetPlayerProfileMessage, ChangeAllianceMemberRoleMessage, KickAllianceMemberMessage,
    ChangeAllianceSettingsMessage, SearchAlliancesMessage, ServerHelloMessage,
    AvatarNameCheckResponseMessage, BattleEndMessage, LoginFailedMessage,
    LoginOkMessage, KeepAliveServerMessage, LobbyInfoMessage, OutOfSyncMessage,
    OwnHomeDataMessage, AvailableServerCommandMessage, PlayerProfileMessage,
    LeaderboardMessage, AskForAllianceDataMessage, CreateAllianceMessage,
    AskForJoinableAlliancesListMessage, JoinAllianceMessage, LeaveAllianceMessage,
    ChatToAllianceStreamMessage, AskForAllianceStreamMessage, MyAllianceMessage,
    AllianceDataMessage, AllianceStreamMessage, JoinableAllianceListMessage,
    AllianceSearchResultMessage, ChangeAllianceSettingsOkMessage,
    AllianceResponseMessage,
)
MESSAGE_TYPES: dict[int, type[PiranhaMessage]] = {}
for _message_class in _MESSAGE_CLASSES:
    _message_type = _message_class.message_type
    if _message_type in MESSAGE_TYPES:
        raise RuntimeError(
            f"duplicate message_type {_message_type}: "
            f"{MESSAGE_TYPES[_message_type].__name__} and {_message_class.__name__}"
        )
    MESSAGE_TYPES[_message_type] = _message_class


# Online matchmaking, replay and spectate routes remain blocked. Offline
# practice has its own registered request/result/home packets and is excluded.
BATTLE_MESSAGE_TYPES = frozenset(
    {
        10401, 12107, 12108, 12110, 12111, 12152, 12155, 12157, 12905,
        14103, 14104, 14105, 14106, 14107, 14108,
        14114, 14115, 14116, 14117, 14177, 14199,
        14350, 14351, 14352, 14353, 14354, 14355, 14356, 14357, 14358,
        14359, 14360, 14361, 14362, 14363, 14364, 14365, 14367, 14368,
        14369, 14370, 14371, 14372, 14373, 14406, 14700, 14701, 16650,
    }
)


def create_message(message_type: int) -> PiranhaMessage | None:
    if message_type in BATTLE_MESSAGE_TYPES:
        message = BattleDisabledMessage()
        message.message_type = message_type
        return message
    message_class = MESSAGE_TYPES.get(message_type)
    if message_class is not None:
        return message_class()
    # Optional client features (friends, clubs, telemetry, map editor and
    # account linking) must not break the home session merely because this
    # local server does not provide their backend.
    if 10000 <= message_type < 20000 or 30000 <= message_type < 40000:
        message = GenericClientMessage()
        message.message_type = message_type
        return message
    return None


__all__ = [
    "AllianceDataMessage",
    "AllianceResponseMessage",
    "AllianceSearchResultMessage",
    "AllianceStreamMessage",
    "AnalyticsEventMessage",
    "AskForAllianceDataMessage",
    "AskForAllianceStreamMessage",
    "AskForBattleEndMessage",
    "AuxiliaryHomeMessage13654",
    "AuxiliaryMessage17502",
    "AuxiliaryMessage18977",
    "AuxiliaryMessage38101",
    "AuxiliaryMessage38102",
    "AuxiliaryMessage38103",
    "AuxiliaryMessage38104",
    "AuxiliaryMessage39004",
    "AvailableServerCommandMessage",
    "AvatarNameCheckRequestMessage",
    "AvatarNameCheckResponseMessage",
    "BattleDisabledMessage",
    "BattleEndMessage",
    "CancelMatchmakingMessage",
    "ChangeAllianceMemberRoleMessage",
    "ChangeAllianceSettingsMessage",
    "ChangeAllianceSettingsOkMessage",
    "ChangeAvatarNameMessage",
    "ChatToAllianceStreamMessage",
    "ClientCapabilitiesMessage",
    "ClientHelloMessage",
    "CreateAllianceMessage",
    "EndClientTurnMessage",
    "GenericClientMessage",
    "GetLeaderboardMessage",
    "GetPlayerProfileMessage",
    "GoHomeFromOfflinePracticeMessage",
    "GoHomeMessage",
    "IgnoredClientMessage",
    "JoinAllianceMessage",
    "JoinableAllianceListMessage",
    "KeepAliveMessage",
    "KeepAliveServerMessage",
    "KickAllianceMemberMessage",
    "LeaderboardMessage",
    "LeaveAllianceMessage",
    "LegacyGoHomeFromOfflinePracticeMessage",
    "LegacyGoHomeMessage",
    "LobbyInfoMessage",
    "LoginFailedMessage",
    "LoginMessage",
    "LoginOkMessage",
    "MyAllianceMessage",
    "OutOfSyncMessage",
    "OwnHomeDataMessage",
    "PiranhaMessage",
    "PlayerProfileMessage",
    "PlayerStatusMessage",
    "SearchAlliancesMessage",
    "ServerHelloMessage",
    "SetDeviceTokenMessage",
    "SinglePlayerMatchRequestMessage",
    "StartGameMessage",
    "create_message",
]
