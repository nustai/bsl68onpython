from __future__ import annotations

from abc import ABC

from ..stream import ByteStream


class PiranhaMessage(ABC):
    message_type = 0
    service_node_type = 0

    def __init__(self) -> None:
        self.byte_stream = ByteStream(5)
        self.message_version = -1
        self.proxy_session_id = 0

    @property
    def encoding_length(self) -> int:
        return self.byte_stream.length

    @property
    def message_bytes(self) -> bytes:
        return self.byte_stream.getvalue()

    @property
    def version(self) -> int:
        if self.message_version >= 1:
            return self.message_version
        return 1 if self.message_type == 20104 else 0

    @property
    def is_client_to_server(self) -> bool:
        return 10000 <= self.message_type < 20000 or self.message_type == 30000

    @property
    def is_server_to_client(self) -> bool:
        return 20000 <= self.message_type < 30000 or self.message_type == 40000

    def encode(self) -> None:
        pass

    def decode(self) -> None:
        pass

    def clear(self) -> None:
        self.byte_stream.clear(self.encoding_length)
