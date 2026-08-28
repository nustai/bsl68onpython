from __future__ import annotations


def _u32(value: int) -> int:
    return value & 0xFFFFFFFF


def _rotate_left_one(value: int) -> int:
    value &= 0xFFFFFFFF
    return ((value >> 31) | (value << 1)) & 0xFFFFFFFF


class ChecksumEncoder:
    """Python counterpart of TitanEngine's checksum-only encoder."""

    def __init__(self) -> None:
        self._checksum = 0
        self._enabled = True
        self._snapshot_checksum = 0

    def enable_checksum(self, enabled: bool) -> None:
        if not self._enabled or enabled:
            if not self._enabled and enabled:
                self._checksum = self._snapshot_checksum
            self._enabled = enabled
        else:
            self._snapshot_checksum = self._checksum
            self._enabled = False

    def _add(self, value: int, salt: int) -> None:
        self._checksum = _u32(value + _rotate_left_one(self._checksum) + salt)

    def _add_collection(self, value: int) -> None:
        self._checksum = _u32((value + (self._checksum >> 31)) | (self._checksum << 1))

    def write_short(self, value: int) -> None:
        self._add(value, 19)

    def write_int(self, value: int) -> None:
        self._add(value, 9)

    def write_vint(self, value: int) -> int:
        self._add(value, 33)
        return value

    def write_long_long(self, value: int) -> None:
        self._add(value, 67)

    def write_byte(self, value: int) -> int:
        self._add(value, 11)
        return value

    def write_bytes(self, value: bytes | None, length: int) -> None:
        self._add_collection(length + 28 if value is not None else 27)

    def write_boolean(self, value: bool) -> bool:
        self._add(13 if value else 7, 0)
        return value

    def write_string(self, value: str | None) -> None:
        self._add_collection(len(value) + 28 if value is not None else 27)

    def write_string_reference(self, value: str) -> None:
        self._add(len(value), 38)

    @property
    def checksum(self) -> int:
        value = self._checksum
        return value - 0x100000000 if value & 0x80000000 else value

    def reset_checksum(self) -> None:
        self._checksum = 0
