from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable

from nacl.exceptions import CryptoError

from .account import AccountRepository, AccountStore, ServerConfig
from .catalog import (
    BRAWLER_BY_ID,
    EMOTE_IDS,
    NAME_COLOR_IDS,
    PLAYER_THUMBNAIL_IDS,
    SKIN_IDS,
    VANITY_IDS,
)
from .club import ClubStore
from .crypto import PepperEncrypter, box_decrypt, box_encrypt, pepper_hash
from .messages import (
    AllianceDataMessage,
    AllianceResponseMessage,
    AllianceSearchResultMessage,
    AllianceStreamMessage,
    AskForAllianceDataMessage,
    AskForAllianceStreamMessage,
    AskForBattleEndMessage,
    AskForJoinableAlliancesListMessage,
    AvailableServerCommandMessage,
    AvatarNameCheckRequestMessage,
    AvatarNameCheckResponseMessage,
    BattleDisabledMessage,
    BattleEndMessage,
    ChangeAllianceMemberRoleMessage,
    ChangeAllianceSettingsMessage,
    ChangeAllianceSettingsOkMessage,
    ChangeAvatarNameMessage,
    ChatToAllianceStreamMessage,
    ClientCapabilitiesMessage,
    CreateAllianceMessage,
    EndClientTurnMessage,
    GenericClientMessage,
    GetLeaderboardMessage,
    GetPlayerProfileMessage,
    GoHomeFromOfflinePracticeMessage,
    GoHomeMessage,
    IgnoredClientMessage,
    JoinableAllianceListMessage,
    JoinAllianceMessage,
    KeepAliveMessage,
    KeepAliveServerMessage,
    KickAllianceMemberMessage,
    LeaderboardMessage,
    LeaveAllianceMessage,
    LobbyInfoMessage,
    LoginFailedMessage,
    LoginMessage,
    LoginOkMessage,
    MyAllianceMessage,
    OwnHomeDataMessage,
    PiranhaMessage,
    PlayerProfileMessage,
    SearchAlliancesMessage,
    ServerHelloMessage,
    SinglePlayerMatchRequestMessage,
    create_message,
)

LOGGER = logging.getLogger(__name__)
HEADER_SIZE = 7
MAX_INBOUND_PAYLOAD = 1024 * 1024

# Logic command identifiers used by the v68 client.  Most of these commands
# are client UI/economy notifications and have no server-side effect in this
# offline implementation.  Keeping their names here prevents harmless known
# commands from being reported as protocol errors, without guessing payload
# layouts (logic commands do not contain a length field).
LOGIC_COMMAND_NAMES: dict[int, str] = {
    201: "LogicChangeAvatarNameCommand",
    202: "LogicDiamondsAddedCommand",
    203: "LogicGiveDeliveryItemsCommand",
    204: "LogicDayChangedCommand",
    205: "LogicDecreaseHeroScoreCommand",
    206: "LogicAddNotificationCommand",
    207: "LogicChangeResourcesCommand",
    208: "LogicTransactionsRevokedCommand",
    209: "LogicKeyPoolChangedCommand",
    210: "LogicIAPChangedCommand",
    211: "LogicOffersChangedCommand",
    212: "LogicPlayerDataChangedCommand",
    213: "LogicInviteBlockingChangedCommand",
    214: "LogicGemNameChangeStateChangedCommand",
    215: "LogicSetSupportedCreatorCommand",
    216: "LogicCooldownExpiredCommand",
    217: "LogicProLeagueSeasonChangedCommand",
    218: "LogicBrawlPassSeasonChangedCommand",
    219: "LogicBrawlPassUnlockedCommand",
    220: "LogicHerowinQuestsChangedCommand",
    221: "LogicTeamChatMuteStateChangedCommand",
    222: "LogicRankedSeasonChangedCommand",
    223: "LogicCooldownAddedCommand",
    224: "LogicSetESportsHubNotificationCommand",
    500: "LogicGatchaCommand",
    503: "LogicClaimDailyRewardCommand",
    504: "LogicSendAllianceMailCommand",
    505: "LogicSetPlayerThumbnailCommand",
    506: "LogicSelectSkinCommand",
    507: "LogicUnlockSkinCommand",
    508: "LogicChangeControlModeCommand",
    509: "LogicPurchaseDoubleCoinsCommand",
    511: "LogicHelpOpenedCommand",
    512: "LogicToggleInGameHintsCommand",
    514: "LogicDeleteNotificationCommand",
    515: "LogicClearShopTickersCommand",
    517: "LogicClaimRankUpRewardCommand",
    518: "LogicPurchaseTicketsCommand",
    519: "LogicPurchaseOfferCommand",
    520: "LogicLevelUpCommand",
    521: "LogicPurchaseHeroLvlUpMaterialCommand",
    522: "LogicHeroSeenCommand",
    523: "LogicClaimAdRewardCommand",
    524: "LogicVideoStartedCommand",
    525: "LogicSelectCharacterCommand",
    526: "LogicUnlockFreeSkinsCommand",
    527: "LogicSetPlayerNameColorCommand",
    528: "LogicViewInboxNotificationCommand",
    529: "LogicSelectStarPowerCommand",
    530: "LogicSetPlayerAgeCommand",
    531: "LogicCancelPurchaseOfferCommand",
    532: "LogicItemSeenCommand",
    533: "LogicQuestSeenCommand",
    534: "LogicPurchaseBrawlPassCommand",
    535: "LogicClaimTailRewardCommand",
    536: "LogicPurchaseBrawlpassProgressCommand",
    537: "LogicVanityItemSeenCommand",
    538: "LogicSelectEmoteCommand",
    539: "LogicBrawlPassAutoCollectWarningSeenCommand",
    540: "LogicPurchaseChallengeLivesCommand",
    541: "LogicClearESportsHubNotificationCommand",
    542: "LogicSelectGroupSkinCommand",
    568: "LogicSetPlayerProfileVanityCommand",
    571: "LogicOpenRandomCommand",
}


class ProtocolError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class MessageManager:
    def __init__(
        self,
        messaging: Messaging,
        repository: AccountRepository,
        config: ServerConfig,
        account_store: AccountStore | None = None,
        club_store: ClubStore | None = None,
        client_public_key: bytes = b"",
    ) -> None:
        self.messaging = messaging
        self.repository = repository
        self.config = config
        self.account_store = account_store
        self.club_store = club_store
        self.client_public_key = client_public_key
        self.account = repository.load()
        self._logged_optional_payloads: set[int] = set()

    async def _send_home(self) -> None:
        # The v68 login flow expects LoginOk followed by OwnHomeData.  An empty
        # MyAllianceMessage is not part of that flow; sending it immediately
        # after home shifts the client's social-state reader and can terminate
        # the session before the menu is shown.  Send 24399 only when the
        # account actually belongs to a club.
        await self.messaging.send(OwnHomeDataMessage(self.account, self.config))
        if self.club_store is not None:
            club = self.club_store.for_account(self.account.account_id)
            if club is not None:
                await self.messaging.send(MyAllianceMessage(club, self.account))
        if self.config.motd:
            await self.messaging.send(
                LobbyInfoMessage(self.messaging.online_count, self.config.motd)
            )

    @staticmethod
    def _validated_name(value: str) -> str | None:
        name = " ".join(value.strip().split())
        encoded = name.encode("utf-8")
        if 2 <= len(name) and len(encoded) <= 60 and not any(ord(char) < 32 for char in name):
            return name
        return None

    async def _handle_command(self, command) -> None:
        command_type = command.command_type
        if command_type == 519:
            reference = command.data_reference
            # Skin references must be handled before offer/brawler fallback.
            if len(reference) == 2 and reference[0] == 29:
                skin_id = reference[1]
                if skin_id < 0 or (SKIN_IDS and skin_id not in SKIN_IDS):
                    LOGGER.warning("Shop skin rejected: %s", reference)
                    # Complete the client transaction lifecycle even for a
                    # stale catalogue id.  Leaving 519 without a home
                    # snapshot keeps the stock client on its loading spinner.
                    await self._send_home()
                    return
                if self.account.unlock_skin(skin_id, 1):
                    self.account.selected_skins[str(self.account.selected_brawler)] = skin_id
                    self.repository.save(self.account)
                    LOGGER.info("Shop purchase: skin=%d currency=gems price=1 gems_left=%d", skin_id, self.account.gems)
                    await self._send_home()
                else:
                    LOGGER.warning("Shop skin rejected: already owned or not enough gems: %s", reference)
                    # 519 is a client-side transaction envelope.  Always
                    # return a coherent home snapshot, including rejection,
                    # otherwise the stock client remains on its spinner.
                    await self._send_home()
                return
            character_id: int | None = None
            if len(reference) == 2 and reference[0] == 16:
                character_id = reference[1]
            elif 0 <= command.offer_index < len(self.account.locked_brawler_ids):
                character_id = self.account.locked_brawler_ids[command.offer_index]
            if character_id not in BRAWLER_BY_ID:
                LOGGER.warning("Shop brawler rejected: unknown character=%s", character_id)
                await self._send_home()
                return
            # The v68 shop uses gems for the Colt offer in this test server.
            # Prefer the explicit character reference; offer indexes are kept
            # as a compatibility fallback for older clients.
            currency = "gems" if character_id == 1 else "coins"
            price = self.config.colt_gem_price if character_id == 1 else self.config.brawler_price
            if character_id is not None and self.account.unlock_brawler(
                character_id, price, self.config.starting_power_points, currency
            ):
                self.repository.save(self.account)
                LOGGER.info(
                    "Shop purchase: brawler=%d currency=%s price=%d coins=%d gems=%d",
                    character_id,
                    currency, price, self.account.coins, self.account.gems,
                )
            else:
                LOGGER.warning(
                    "Shop purchase rejected: offer=%d data_reference=%s coins=%d",
                    command.offer_index,
                    command.data_reference,
                    self.account.coins,
                )
            # Refresh the live home state so the client immediately sees the
            # newly owned brawler and the deducted currency.
            if str(character_id) in self.account.brawlers:
                await self._send_home()
            else:
                # Keep the transaction lifecycle complete when the offer is
                # stale, already bought, or unaffordable.
                await self._send_home()
            return

        changed = False
        if command_type == 520:
            # LevelUpCommand is a client request to spend the already granted
            # upgrade materials. In this server materials are unlimited, but
            # the target must still reference an owned brawler and remain in
            # the v68 level range. Do not modify an arbitrary DataReference.
            reference = command.level_up_reference
            if len(reference) == 2 and reference[0] == 16:
                progress = self.account.brawlers.get(str(reference[1]))
                raw_target = command.level_up_value
                # v68 stores the power level in the avatar group as
                # power_level - 1 and sends that zero-based value back in
                # LevelUpCommand. Accept the legacy one-based form as well.
                target = raw_target + 1 if 0 <= raw_target <= 10 else raw_target
                if progress is not None and 1 <= target <= 11 and target > progress.power_level:
                    progress.power_level = target
                    progress.power_points = max(progress.power_points, self.config.starting_power_points)
                    changed = True
                    LOGGER.info("Brawler upgraded: brawler=%d level=%d", reference[1], target)
            if not changed:
                LOGGER.warning("Brawler upgrade rejected: reference=%s level=%d", reference, command.level_up_value)
        elif command_type == 506 and len(command.skin_reference) == 2 and command.skin_reference[0] == 29:
            skin_id = command.skin_reference[1]
            if skin_id >= 0 and skin_id in self.account.owned_skins and (not SKIN_IDS or skin_id in SKIN_IDS):
                self.account.selected_skins[str(self.account.selected_brawler)] = skin_id
                changed = True
            else:
                LOGGER.warning("Skin selection rejected: %s", command.skin_reference)
        elif command_type == 538 and len(command.emote_reference) == 2 and command.emote_reference[0] == 23:
            if 0 <= command.emote_slot <= 20 and command.emote_reference[1] >= 0 and (not EMOTE_IDS or command.emote_reference[1] in EMOTE_IDS):
                self.account.emote_slots[str(command.emote_slot)] = command.emote_reference[1]
                changed = True
        elif command_type == 568:
            valid_ids = VANITY_IDS.get(command.vanity_csv_id)
            if (
                0 <= command.vanity_slot_id <= 20
                and valid_ids is not None
                and command.vanity_id in valid_ids
            ):
                # v68 sends the selected battle-card item as
                # (vanity_csv_id, vanity_id, slot). Keep the composite item
                # instead of only the id: 28:22 and 52:156 are different
                # catalogues and may share numeric ids.
                key = f"{command.vanity_csv_id}:{command.vanity_slot_id}"
                self.account.profile_vanity[key] = command.vanity_id
                # CSV 28 is the player thumbnail catalogue. Older code saved
                # the command but continued sending the previous thumbnail
                # in OwnHomeData, making the change disappear after restart.
                if command.vanity_csv_id == 28:
                    self.account.thumbnail = command.vanity_id
                changed = True
            else:
                LOGGER.warning(
                    "Profile vanity rejected: csv=%d id=%d slot=%d",
                    command.vanity_csv_id, command.vanity_id, command.vanity_slot_id,
                )
        elif len(command.data_reference) == 2:
            class_id, instance_id = command.data_reference
            if command_type == 525 and class_id == 16 and str(instance_id) in self.account.brawlers:
                self.account.selected_brawler = instance_id
                changed = True
            elif command_type == 505 and class_id == 28 and instance_id in PLAYER_THUMBNAIL_IDS:
                self.account.thumbnail = instance_id
                changed = True
            elif command_type == 527 and class_id == 43:
                if instance_id in NAME_COLOR_IDS:
                    self.account.name_color = instance_id
                    changed = True
            elif command_type == 522 and class_id == 16:
                progress = self.account.brawlers.get(str(instance_id))
                if progress is not None:
                    progress.seen_state = 2
                    changed = True
        if changed:
            self.repository.save(self.account)

    async def receive_message(self, message: PiranhaMessage) -> int:
        if isinstance(message, KeepAliveMessage):
            await self.messaging.send(KeepAliveServerMessage())
            return 1
        if isinstance(message, ClientCapabilitiesMessage):
            LOGGER.debug("Client capabilities: %d", message.capabilities)
            return 1
        if isinstance(message, AskForBattleEndMessage):
            self.account.apply_offline_battle_result(
                message.result,
                message.rank,
                message.heroes,
            )
            self.repository.save(self.account)
            await self.messaging.send(
                BattleEndMessage(message.rank, message.heroes, self.account)
            )
            LOGGER.info(
                "Offline battle completed: result=%d rank=%d heroes=%d",
                message.result,
                message.rank,
                len(message.heroes),
            )
            return 1
        if isinstance(message, GoHomeFromOfflinePracticeMessage):
            await self._send_home()
            return 1
        if isinstance(message, SinglePlayerMatchRequestMessage):
            # With offlineBattles enabled in libBSL.c.so the client owns the
            # loading/battle simulation. A server loading packet would switch
            # it back to online matchmaking.
            LOGGER.info("Accepted client-side single-player battle request")
            return 1
        if self.club_store is not None and isinstance(message, AskForJoinableAlliancesListMessage):
            clubs = self.club_store.search(player_trophies=self.account.total_trophies)
            await self.messaging.send(JoinableAllianceListMessage(clubs))
            return 1
        if self.club_store is not None and isinstance(message, SearchAlliancesMessage):
            clubs = self.club_store.search(
                message.query,
                player_trophies=self.account.total_trophies,
            )
            await self.messaging.send(AllianceSearchResultMessage(clubs))
            return 1
        if self.club_store is not None and isinstance(message, CreateAllianceMessage):
            club = self.club_store.create(
                self.account.account_id, self.account.name, message.name,
                message.description, message.badge[-1] if len(message.badge) > 1 else 0,
                self.config.region, message.club_type, message.required_trophies,
                message.family_friendly,
            )
            # 24333 is the response to the create request.  The client then
            # requests/consumes the club state; keep the state packets grouped
            # and never put an empty club packet in the login/home sequence.
            await self.messaging.send(AllianceResponseMessage(20))
            await self.messaging.send(MyAllianceMessage(club, self.account))
            await self.messaging.send(AllianceDataMessage(club, self._lookup_account))
            await self.messaging.send(AllianceStreamMessage(club))
            return 1
        if self.club_store is not None and isinstance(message, JoinAllianceMessage):
            club = self.club_store.join(
                message.club_low,
                self.account.account_id,
                self.account.total_trophies,
            )
            await self.messaging.send(AllianceResponseMessage(20 if club else 95))
            if club:
                await self.messaging.send(MyAllianceMessage(club, self.account))
                await self.messaging.send(AllianceDataMessage(club, self._lookup_account))
                await self.messaging.send(AllianceStreamMessage(club))
            return 1
        if self.club_store is not None and isinstance(message, ChangeAllianceSettingsMessage):
            current = self.club_store.for_account(self.account.account_id)
            club = self.club_store.update_settings(
                self.account.account_id,
                message.description,
                message.badge[-1] if len(message.badge) == 2 else 0,
                current.region if current else self.account.region,
                message.club_type,
                message.required_trophies,
                message.family_friendly,
            )
            await self.messaging.send(AllianceResponseMessage(10 if club else 95))
            if club:
                await self.messaging.send(
                    ChangeAllianceSettingsOkMessage(club, self._lookup_account)
                )
                await self.messaging.send(MyAllianceMessage(club, self.account))
            return 1
        if self.club_store is not None and isinstance(message, ChangeAllianceMemberRoleMessage):
            club = self.club_store.change_role(
                self.account.account_id,
                (message.account_high, message.account_low),
                message.role,
            )
            await self.messaging.send(AllianceResponseMessage(10 if club else 95))
            if club:
                await self.messaging.send(AllianceDataMessage(club, self._lookup_account))
            return 1
        if self.club_store is not None and isinstance(message, KickAllianceMemberMessage):
            club = self.club_store.kick(
                self.account.account_id,
                (message.account_high, message.account_low),
            )
            await self.messaging.send(AllianceResponseMessage(10 if club else 95))
            if club:
                await self.messaging.send(AllianceDataMessage(club, self._lookup_account))
            return 1
        if self.club_store is not None and isinstance(message, LeaveAllianceMessage):
            self.club_store.leave(self.account.account_id); await self.messaging.send(MyAllianceMessage()); return 1
        if self.club_store is not None and isinstance(message, AskForAllianceDataMessage):
            club = next((c for c in self.club_store.all() if c.club_id == message.club_low), None)
            if club is None and message.club_high == 0:
                club = self.club_store.for_account(self.account.account_id)
            if club: await self.messaging.send(AllianceDataMessage(club, self._lookup_account))
            return 1
        if self.club_store is not None and isinstance(message, AskForAllianceStreamMessage):
            club = self.club_store.for_account(self.account.account_id)
            if club: await self.messaging.send(AllianceStreamMessage(club))
            return 1
        if self.club_store is not None and isinstance(message, ChatToAllianceStreamMessage):
            club = self.club_store.for_account(self.account.account_id)
            text = message.text.strip()
            if club and text and len(text.encode("utf-8")) <= 255:
                import time
                self.club_store.add_message(club, self.account.account_id, self.account.name, text, int(time.time()))
                await self.messaging.send(AllianceStreamMessage(club))
            return 1
        if isinstance(message, IgnoredClientMessage):
            if isinstance(message, BattleDisabledMessage):
                LOGGER.info("Battle feature blocked: message=%d", message.message_type)
                await self._send_home()
                return 1
            if (
                message.message_type in (38101, 38102, 38103, 38104)
                and message.message_type not in self._logged_optional_payloads
            ):
                self._logged_optional_payloads.add(message.message_type)
                LOGGER.debug(
                    "Auxiliary client message sample: message=%d payload=%s",
                    message.message_type,
                    message.byte_stream.getvalue()[:128].hex(),
                )
                return 1
            if isinstance(message, GenericClientMessage):
                if message.message_type not in self._logged_optional_payloads:
                    self._logged_optional_payloads.add(message.message_type)
                    LOGGER.debug(
                        "Optional client message sample: message=%d payload=%s",
                        message.message_type,
                        message.byte_stream.getvalue()[:128].hex(),
                    )
                else:
                    LOGGER.debug("Optional client message ignored: %d", message.message_type)
                return 1
            LOGGER.debug("Auxiliary client message ignored: %d", message.message_type)
            return 1
        if isinstance(message, LoginMessage):
            if message.client_major_version != 68:
                await self.messaging.send(
                    LoginFailedMessage(8, "This server requires client 68.250")
                )
                return 1
            if self.account_store is not None:
                try:
                    self.repository, created = self.account_store.repository_for_login(
                        message.account_high, message.account_id, message.pass_token
                    )
                except PermissionError:
                    await self.messaging.send(LoginFailedMessage(1, "Invalid account token"))
                    return 1
                self.account = self.repository.load()
                LOGGER.info(
                    "%s account: id=(%d, %d)",
                    "Created" if created else "Restored",
                    self.account.account_high,
                    self.account.account_low,
                )
            await self.messaging.send(LoginOkMessage(self.account))
            await self._send_home()
            return 1
        if isinstance(message, GoHomeMessage):
            await self._send_home()
            return 1
        if isinstance(message, AvatarNameCheckRequestMessage):
            name = self._validated_name(message.name)
            if name is None:
                await self.messaging.send(AvatarNameCheckResponseMessage("", True, 1))
                LOGGER.warning("Rejected invalid player name during availability check")
            else:
                await self.messaging.send(AvatarNameCheckResponseMessage(name))
                LOGGER.info("Player name is available: %r", name)
            return 1
        if isinstance(message, ChangeAvatarNameMessage):
            name = self._validated_name(message.name)
            if name is not None:
                self.account.name = name
                # Receiving 10212 means the user confirmed the dialog. Some
                # v68 builds send the trailing flag as false on the first
                # attempt; persisting that value makes the dialog reappear on
                # every login even though the name itself was saved.
                self.account.name_set = True
                self.repository.save(self.account)
                await self.messaging.send(
                    AvailableServerCommandMessage(name, True)
                )
                # Do not send another OwnHomeData here. The 24111 command
                # applies the name to the live home state; recreating the home
                # during the registration transition races the dialog and is
                # why OK used to work only every other press.
                LOGGER.info("Player name changed to %r", name)
            else:
                LOGGER.warning("Rejected invalid player name")
            return 1
        if isinstance(message, GetPlayerProfileMessage):
            profile = (
                self.account_store.profile(message.account_high, message.account_low, self.repository)
                if self.account_store is not None
                else self.repository.profile(message.account_high, message.account_low)
            )
            club = self.club_store.for_account(profile.account_id) if self.club_store else None
            await self.messaging.send(PlayerProfileMessage(profile, club))
            return 1
        if isinstance(message, GetLeaderboardMessage):
            entries = (
                self.account_store.leaderboard(self.account)
                if self.account_store is not None
                else self.repository.leaderboard(self.account)
            )
            await self.messaging.send(
                LeaderboardMessage(
                    message.leaderboard_type,
                    message.brawler_reference,
                    entries,
                    self.config.region,
                )
            )
            return 1
        if isinstance(message, EndClientTurnMessage):
            for command in message.commands:
                command_name = LOGIC_COMMAND_NAMES.get(
                    command.command_type, "UnknownLogicCommand"
                )
                LOGGER.info(
                    "Logic command received: type=%d name=%s",
                    command.command_type,
                    command_name,
                )
                if command.command_type not in (505, 506, 519, 520, 522, 525, 527, 538, 568, 571):
                    if command.command_type in LOGIC_COMMAND_NAMES:
                        LOGGER.debug(
                            "Known logic command has no local effect: type=%d name=%s",
                            command.command_type,
                            command_name,
                        )
                    else:
                        LOGGER.warning(
                            "Unknown logic command: type=%d turn_payload=%s",
                            command.command_type,
                            message.raw_payload[:256].hex(),
                        )
                try:
                    await self._handle_command(command)
                except (EOFError, ValueError, TypeError, KeyError):
                    LOGGER.warning("Logic command rejected: type=%d", command.command_type)
                except Exception:
                    LOGGER.exception("Unexpected logic command error: type=%d", command.command_type)
            return 1
        return 1

    def _lookup_account(self, account_id: tuple[int, int]):
        if self.account_store is None:
            return None
        return self.account_store.profile(account_id[0], account_id[1], self.repository)


class Messaging:
    """One v68 connection's framing, handshake, and message dispatch state."""

    def __init__(
        self,
        send_bytes: Callable[[bytes], Awaitable[None]],
        repository: AccountRepository | None = None,
        config: ServerConfig | None = None,
        account_store: AccountStore | None = None,
        club_store: ClubStore | None = None,
        online_count: Callable[[], int] | None = None,
    ) -> None:
        self._send_bytes = send_bytes
        self._buffer = bytearray()
        self.config = config or ServerConfig()
        self.repository = repository or AccountRepository(None, self.config)
        self.account_store = account_store
        self.club_store = club_store
        self._online_count = online_count or (lambda: 1)
        self._secret_key = secrets.token_bytes(32)
        self._session_token = secrets.token_bytes(24)
        self._server_nonce = secrets.token_bytes(24)
        self._client_public_key = b""
        self._remote_nonce = b""
        self._decrypt_stream: PepperEncrypter | None = None
        self._encrypt_stream: PepperEncrypter | None = None
        self._message_manager: MessageManager | None = None
        self._pepper_state = 2

    @property
    def online_count(self) -> int:
        try:
            return max(0, int(self._online_count()))
        except (TypeError, ValueError):
            return 1

    async def feed_data(self, data: bytes) -> list[int]:
        self._buffer.extend(data)
        results: list[int] = []
        while len(self._buffer) >= HEADER_SIZE:
            message_type, length, version = self.read_header(self._buffer)
            if length > MAX_INBOUND_PAYLOAD:
                self._buffer.clear()
                raise ProtocolError(-601, f"payload is too large: {length}")
            frame_length = HEADER_SIZE + length
            if len(self._buffer) < frame_length:
                break
            payload = bytes(self._buffer[HEADER_SIZE:frame_length])
            del self._buffer[:frame_length]
            results.append(await self.read_new_message(message_type, version, payload))
        return results

    async def read_new_message(self, message_type: int, version: int, payload: bytes) -> int:
        if self._pepper_state == 2:
            if message_type != 10100:
                return -602
            self._pepper_state = 3
        elif self._pepper_state == 3:
            if message_type != 10101:
                return -603
            try:
                payload = self._handle_pepper_login(payload)
            except (CryptoError, ValueError, IndexError) as error:
                LOGGER.warning("Pepper login failed: %s", error)
                return -604
        elif self._pepper_state == 5:
            if self._decrypt_stream is None:
                return -605
            try:
                payload = self._decrypt_stream.decrypt(payload)
            except CryptoError:
                LOGGER.warning("Invalid encrypted message %d", message_type)
                return -605

        message = create_message(message_type)
        if message is None:
            LOGGER.info(
                "Unknown message received: %d (payload=%d bytes, version=%d)",
                message_type,
                len(payload),
                version,
            )
            return 0
        message.message_version = version
        if payload:
            message.byte_stream.set_byte_array(payload)
            try:
                message.decode()
            except (EOFError, UnicodeError, ValueError) as error:
                LOGGER.warning("Could not decode message %d: %s", message_type, error)
                return -606

        LOGGER.info("Message received: %d", message_type)
        if message_type == 10100:
            await self.send(ServerHelloMessage(self._session_token))
            return 0
        if self._message_manager is None:
            return -666
        return await self._message_manager.receive_message(message)

    def _handle_pepper_login(self, payload: bytes) -> bytes:
        if len(payload) < 48:
            raise ValueError("Pepper login payload is too short")
        self._client_public_key = payload[:32]
        nonce = pepper_hash(self._client_public_key, self.server_public_key)
        decrypted = box_decrypt(payload[32:], nonce)
        if len(decrypted) < 25:
            raise ValueError("decrypted login payload is too short")
        self._remote_nonce = decrypted[1:25]
        self._pepper_state = 4
        # The APK's Pepper key is shared by every installation. Select the
        # actual profile only after decoding LoginMessage's id and token.
        repository = self.repository
        self._message_manager = MessageManager(
            self,
            repository,
            self.config,
            self.account_store,
            self.club_store,
            self._client_public_key,
        )
        return decrypted[25:]

    def _pepper_login_response(self, payload: bytes) -> bytes:
        packet = self._server_nonce + self._secret_key + payload
        nonce = pepper_hash(self._remote_nonce, self._client_public_key, self.server_public_key)
        self._decrypt_stream = PepperEncrypter(self._secret_key, self._remote_nonce)
        self._encrypt_stream = PepperEncrypter(self._secret_key, self._server_nonce)
        self._pepper_state = 5
        return box_encrypt(packet, nonce)

    @property
    def server_public_key(self) -> bytes:
        from .crypto import SERVER_PUBLIC_KEY
        return SERVER_PUBLIC_KEY

    async def send(self, message: PiranhaMessage) -> int:
        if not message.is_server_to_client:
            return -1
        if message.encoding_length == 0:
            message.encode()
        payload = message.message_bytes
        if self._pepper_state == 4:
            payload = self._pepper_login_response(payload)
        elif self._pepper_state == 5:
            if self._encrypt_stream is None:
                return -1
            payload = self._encrypt_stream.encrypt(payload)
        frame = self.write_header(payload, message.message_type, message.version) + payload
        await self._send_bytes(frame)
        LOGGER.info("Message sent: %d", message.message_type)
        return 0

    @staticmethod
    def read_header(value: bytes | bytearray) -> tuple[int, int, int]:
        if len(value) < HEADER_SIZE:
            raise ValueError("a message header is seven bytes")
        return (
            int.from_bytes(value[0:2], "big"),
            int.from_bytes(value[2:5], "big"),
            int.from_bytes(value[5:7], "big"),
        )

    @staticmethod
    def write_header(payload: bytes, message_type: int, version: int) -> bytes:
        if len(payload) > 0xFFFFFF:
            raise ValueError("payload does not fit the 24-bit length field")
        return (
            message_type.to_bytes(2, "big")
            + len(payload).to_bytes(3, "big")
            + version.to_bytes(2, "big")
        )
