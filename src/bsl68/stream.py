from __future__ import annotations

import zlib
from collections.abc import Iterable
from dataclasses import dataclass


def _i32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


class ByteStream:
    """Supercell-compatible byte and bit stream used by the v68 protocol."""

    def __init__(self, value: int | bytes | bytearray = 5):
        self._buffer = bytearray(value)
        self._length = 0 if isinstance(value, int) else len(value)
        self._offset = 0
        self._bit_idx = 0

    def _ensure(self, count: int) -> None:
        missing = self._offset + count - len(self._buffer)
        if missing > 0:
            self._buffer.extend(b"\0" * missing)

    def _align(self) -> None:
        self._bit_idx = 0

    def _take(self, count: int) -> bytes:
        self._align()
        end = self._offset + count
        if end > self._length:
            raise EOFError("not enough bytes in stream")
        value = bytes(self._buffer[self._offset:end])
        self._offset = end
        return value

    def read_boolean(self) -> bool:
        if self._bit_idx == 0:
            if self._offset >= self._length:
                raise EOFError("not enough bits in stream")
            self._offset += 1
        value = bool(self._buffer[self._offset - 1] & (1 << self._bit_idx))
        self._bit_idx = (self._bit_idx + 1) & 7
        return value

    def read_byte(self) -> int:
        return self._take(1)[0]

    def read_short(self) -> int:
        return int.from_bytes(self._take(2), "big", signed=True)

    def read_int8(self) -> int:
        return self.read_byte()

    def read_int16(self) -> int:
        return int.from_bytes(self._take(2), "big")

    def read_int24(self) -> int:
        return int.from_bytes(self._take(3), "big")

    def read_int(self) -> int:
        return int.from_bytes(self._take(4), "big", signed=True)

    def read_int_little_endian(self) -> int:
        return int.from_bytes(self._take(4), "little", signed=True)

    def read_vlong(self) -> LogicLong:
        return LogicLong(self.read_vint(), self.read_vint())

    def read_vint(self) -> int:
        self._align()
        first = self.read_byte()
        negative = bool(first & 0x40)
        value = first & 0x3F
        shift = 6
        current = first
        while current & 0x80 and shift < 34:
            current = self.read_byte()
            value |= (current & 0x7F) << shift
            shift += 7
        if current & 0x80 or (shift >= 34 and current & 0x70):
            raise ValueError("invalid 32-bit VInt")
        if negative:
            value |= 0x80000000 if shift >= 34 else -(1 << shift)
        return _i32(value)

    def read_bytes_length(self) -> int:
        return self.read_int()

    def read_bytes(self, length: int | None = None, max_capacity: int = 2**31 - 1) -> bytes | None:
        if length is None:
            length = self.read_bytes_length()
        if length == -1:
            return None
        if length < -1:
            raise ValueError(f"invalid negative byte length: {length}")
        if length > max_capacity:
            raise ValueError(f"byte length exceeds capacity: {length}")
        return self._take(length)

    def read_string(self, max_capacity: int = 2048) -> str | None:
        length = self.read_bytes_length()
        if length <= -1:
            return None
        if length > max_capacity:
            # C# engine returns null without advancing offset when length
            # exceeds maxCapacity — match that behaviour.
            return None
        return self._take(length).decode("utf-8")

    def read_string_reference(self, max_capacity: int = 2048) -> str:
        length = self.read_bytes_length()
        # String references use the engine's null/invalid sentinel semantics:
        # any negative length is represented to callers as an empty reference.
        # When length exceeds max_capacity the C# engine returns "" without
        # advancing the offset — match that behaviour instead of raising.
        if length < 0 or length > max_capacity:
            return ""
        return self._take(length).decode("utf-8")

    def write_boolean(self, value: bool | int) -> bool:
        result = bool(value)
        if self._bit_idx == 0:
            self._ensure(1)
            self._buffer[self._offset] = 0
            self._offset += 1
        if result:
            self._buffer[self._offset - 1] |= 1 << self._bit_idx
        self._bit_idx = (self._bit_idx + 1) & 7
        return result

    def write_byte(self, value: int) -> int:
        self._align()
        self._ensure(1)
        self._buffer[self._offset] = value & 0xFF
        self._offset += 1
        return value

    def _write_fixed(self, value: int, size: int, byteorder: str = "big") -> None:
        self._align()
        self._ensure(size)
        mask = (1 << (size * 8)) - 1
        self._buffer[self._offset:self._offset + size] = (value & mask).to_bytes(size, byteorder)
        self._offset += size

    def write_short(self, value: int) -> None:
        self._write_fixed(value, 2)

    def write_int8(self, value: int) -> None:
        self._write_fixed(value, 1)

    def write_int16(self, value: int) -> None:
        self._write_fixed(value, 2)

    def write_int24(self, value: int) -> None:
        self._write_fixed(value, 3)

    def write_int(self, value: int | bool) -> None:
        self._write_fixed(int(value), 4)

    def write_int_little_endian(self, value: int) -> None:
        self._write_fixed(value, 4, "little")

    def write_vint(self, value: int | bool) -> int:
        value = int(value)
        if not -(1 << 31) <= value < (1 << 31):
            raise ValueError("VInt is outside the signed 32-bit range")
        self._align()
        negative = value < 0
        if value >= 0:
            length = 1 if value < 0x40 else 2 if value < 0x2000 else 3 if value < 0x100000 else 4 if value < 0x8000000 else 5
        else:
            length = 1 if value > -0x40 else 2 if value > -0x2000 else 3 if value > -0x100000 else 4 if value > -0x8000000 else 5
        self.write_byte((value & 0x3F) | (0x40 if negative else 0) | (0x80 if length > 1 else 0))
        for index in range(1, length):
            byte = (value >> (6 + 7 * (index - 1))) & (0x0F if index == 4 else 0x7F)
            if index < length - 1:
                byte |= 0x80
            self.write_byte(byte)
        return value

    def write_bytes(self, value: bytes | bytearray | None, length: int | None = None) -> None:
        if value is None:
            self.write_int(-1)
            return
        length = len(value) if length is None else length
        self.write_int(length)
        self.write_bytes_without_length(value, length)

    def write_bytes_without_length(self, value: bytes | bytearray, length: int | None = None) -> None:
        self._align()
        length = len(value) if length is None else length
        if length < 0 or length > len(value):
            raise ValueError("byte length is outside the source buffer")
        self._ensure(length)
        self._buffer[self._offset:self._offset + length] = value[:length]
        self._offset += length

    def write_string(self, value: str | None) -> None:
        self.write_bytes(None if value is None else value.encode("utf-8"))

    def write_string_reference(self, value: str | None) -> None:
        self.write_bytes(b"" if value is None else value.encode("utf-8"))

    write_filtered_string = write_string_reference

    def write_vlong(self, value: LogicLong) -> None:
        self.write_vint(value.high)
        self.write_vint(value.low)

    def read_int_list(self, max_items: int = 4096) -> list[int]:
        count = self.read_vint()
        if count < 0 or count > max_items:
            raise ValueError(f"invalid integer list length: {count}")
        return [self.read_vint() for _ in range(count)]

    def write_int_list(self, values: Iterable[int]) -> None:
        items = tuple(values)
        self.write_vint(len(items))
        for value in items:
            self.write_vint(value)

    def read_logic_long_list(self, max_items: int = 4096) -> list[LogicLong]:
        count = self.read_vint()
        if count < 0 or count > max_items:
            raise ValueError(f"invalid LogicLong list length: {count}")
        return [self.read_vlong() for _ in range(count)]

    def write_logic_long_list(self, values: Iterable[LogicLong]) -> None:
        items = tuple(values)
        self.write_vint(len(items))
        for value in items:
            self.write_vlong(value)

    def write_compressed(self, value: bytes, level: int = 6) -> None:
        """Write the zlib block used by Titan's ByteStreamHelper."""
        compressed = zlib.compress(value, level)
        self.write_int(len(compressed) + 4)
        self.write_int_little_endian(len(value))
        self.write_bytes_without_length(compressed)

    def read_compressed(
        self,
        max_compressed: int = 16 * 1024 * 1024,
        max_uncompressed: int = 64 * 1024 * 1024,
    ) -> bytes:
        block_length = self.read_int()
        expected_length = self.read_int_little_endian()
        compressed_length = block_length - 4
        if compressed_length < 0 or compressed_length > max_compressed:
            raise ValueError("invalid compressed block length")
        if expected_length < 0 or expected_length > max_uncompressed:
            raise ValueError("invalid uncompressed block length")
        try:
            value = zlib.decompress(self._take(compressed_length))
        except zlib.error as error:
            raise ValueError("invalid zlib block") from error
        if len(value) != expected_length:
            raise ValueError("uncompressed length does not match header")
        return value

    def is_at_end(self) -> bool:
        return self._offset >= self._length

    @property
    def remaining(self) -> int:
        return max(0, self._length - self._offset)

    def skip(self, count: int) -> None:
        if count < 0:
            raise ValueError("skip count cannot be negative")
        self._take(count)

    @property
    def length(self) -> int:
        return max(self._length, self._offset)

    @property
    def offset(self) -> int:
        return self._offset

    @offset.setter
    def offset(self, value: int) -> None:
        if value < 0 or value > self.length:
            raise ValueError("offset outside stream")
        self._offset = value
        self._align()

    def reset_offset(self) -> None:
        self.offset = 0

    def set_byte_array(self, buffer: bytes | bytearray, length: int | None = None) -> None:
        if length is not None and (length < 0 or length > len(buffer)):
            raise ValueError("stream length is outside the supplied buffer")
        self._buffer = bytearray(buffer)
        self._length = len(buffer) if length is None else length
        self._offset = 0
        self._align()

    def getvalue(self) -> bytes:
        return bytes(self._buffer[:self.length])

    def clear(self, capacity: int = 5) -> None:
        self._buffer = bytearray(capacity)
        self._length = self._offset = self._bit_idx = 0


@dataclass(slots=True)
class LogicLong:
    high: int = 0
    low: int = 0

    @classmethod
    def from_int(cls, value: int) -> LogicLong:
        return cls(_i32(value >> 32), _i32(value))

    def to_int(self) -> int:
        return (self.high << 32) | (self.low & 0xFFFFFFFF)

    def encode(self, stream: ByteStream) -> LogicLong:
        stream.write_int(self.high)
        stream.write_int(self.low)
        return self

    def encode_v(self, stream: ByteStream) -> LogicLong:
        stream.write_vlong(self)
        return self

    @classmethod
    def decode(cls, stream: ByteStream) -> LogicLong:
        return cls(stream.read_int(), stream.read_int())


def write_data_reference(stream: ByteStream, class_id: int, instance_id: int | None = None) -> int:
    if instance_id is None or class_id <= 0:
        stream.write_vint(0)
        return class_id if instance_id is None else instance_id
    stream.write_vint(class_id)
    stream.write_vint(instance_id)
    return instance_id


def read_data_reference(stream: ByteStream) -> tuple[int, ...]:
    class_id = stream.read_vint()
    return (0,) if class_id == 0 else (class_id, stream.read_vint())


def write_int_list(stream: ByteStream, values: Iterable[int]) -> None:
    stream.write_int_list(values)
