from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from .account import AccountStore, ServerConfig
from .club import ClubStore
from .messaging import Messaging, ProtocolError

LOGGER = logging.getLogger(__name__)


class LaserTcpCentralGateway:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9339,
        config: ServerConfig | None = None,
        data_path: Path | None = None,
        reset: bool = False,
    ) -> None:
        if not 1000 <= port <= 65535:
            raise ValueError("port must be between 1000 and 65535")
        self.host = host
        self.port = port
        self.config = config or ServerConfig()
        profile_directory = data_path.parent / "players" if data_path is not None else None
        self.account_store = AccountStore(profile_directory, self.config)
        club_path = data_path.parent / "clubs.json" if data_path is not None else None
        self.club_store = ClubStore(club_path)
        self._sessions: set[uuid.UUID] = set()
        if reset:
            self.account_store.reset_all()
            self.club_store.reset()

    async def serve_forever(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        server = await asyncio.start_server(self._handle_client, self.host, self.port)
        addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or ())
        LOGGER.info("LaserTcpCentralGateway started on %s", addresses)
        LOGGER.info("Profiles directory: %s", self.account_store.directory or "memory")
        async with server:
            await server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        session_id = uuid.uuid4()
        self._sessions.add(session_id)
        remote = writer.get_extra_info("peername")
        LOGGER.info("User connected: id=%s remote=%s", session_id, remote)

        async def send_bytes(value: bytes) -> None:
            writer.write(value)
            await writer.drain()

        messaging = Messaging(
            send_bytes,
            config=self.config,
            account_store=self.account_store,
            club_store=self.club_store,
            online_count=lambda: len(self._sessions),
        )
        try:
            while data := await reader.read(4096):
                results = await messaging.feed_data(data)
                for result in results:
                    if result < 0:
                        raise ProtocolError(result, f"protocol error: {result}")
        except (ConnectionError, ProtocolError, ValueError, PermissionError) as error:
            LOGGER.warning("Session %s closed after protocol/network error: %s", session_id, error)
        except Exception:
            # An individual client must never terminate the gateway process.
            LOGGER.exception("Unexpected session error: id=%s", session_id)
        finally:
            self._sessions.discard(session_id)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            LOGGER.info("User disconnected: id=%s", session_id)
