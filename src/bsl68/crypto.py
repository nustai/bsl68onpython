from __future__ import annotations

from hashlib import blake2b
from secrets import compare_digest

from nacl.bindings import crypto_scalarmult
from nacl.exceptions import CryptoError

CLIENT_SECRET_KEY = bytes.fromhex(
    "36abd74b2db5faa4d5a7977a1bc8be137ad7330efc934dfba36600ecd6871476"
)
SERVER_PUBLIC_KEY = bytes.fromhex(
    "46cb575cd747a84045647b8f59473ffafbcd302093c73fd5f8233d779bea886b"
)


def pepper_hash(*parts: bytes) -> bytes:
    digest = blake2b(digest_size=24)
    for part in parts:
        digest.update(part)
    return digest.digest()


_SIGMA = b"expand 32-byte k"
_U32_MASK = 0xFFFFFFFF


def _load_u32(value: bytes, offset: int) -> int:
    return int.from_bytes(value[offset:offset + 4], "little")


def _rotate_left(value: int, count: int) -> int:
    value &= _U32_MASK
    return ((value << count) | (value >> (32 - count))) & _U32_MASK


def _salsa_core(pin: bytes, key: bytes, hsalsa: bool) -> bytes:
    """The source project's Salsa core, including its intentional 19 rounds."""
    if len(pin) < 16 or len(key) != 32:
        raise ValueError("invalid Salsa input or key size")
    x = [0] * 16
    for index in range(4):
        x[5 * index] = _load_u32(_SIGMA, 4 * index)
        x[1 + index] = _load_u32(key, 4 * index)
        x[6 + index] = _load_u32(pin, 4 * index)
        x[11 + index] = _load_u32(key, 16 + 4 * index)
    original = x.copy()

    # TweetNaCl normally performs 20 iterations here. BSL.v68's C# source
    # performs 19, and the patched v68 client uses that exact variant.
    for _ in range(19):
        work = [0] * 16
        for column in range(4):
            values = [x[(5 * column + 4 * row) % 16] for row in range(4)]
            values[1] ^= _rotate_left(values[0] + values[3], 7)
            values[2] ^= _rotate_left(values[1] + values[0], 9)
            values[3] ^= _rotate_left(values[2] + values[1], 13)
            values[0] ^= _rotate_left(values[3] + values[2], 18)
            for row, value in enumerate(values):
                work[4 * column + (column + row) % 4] = value & _U32_MASK
        x = work

    x = [(value + original[index]) & _U32_MASK for index, value in enumerate(x)]
    if hsalsa:
        for index in range(4):
            x[5 * index] = (x[5 * index] - _load_u32(_SIGMA, 4 * index)) & _U32_MASK
            x[6 + index] = (x[6 + index] - _load_u32(pin, 4 * index)) & _U32_MASK
        words = (x[0], x[5], x[10], x[15], x[6], x[7], x[8], x[9])
    else:
        words = tuple(x)
    return b"".join(word.to_bytes(4, "little") for word in words)


def _hsalsa19(pin: bytes, key: bytes) -> bytes:
    return _salsa_core(pin, key, True)


def _salsa19_stream(length: int, nonce_tail: bytes, key: bytes) -> bytes:
    if len(nonce_tail) != 8:
        raise ValueError("Salsa nonce tail must be eight bytes")
    counter = bytearray(nonce_tail + b"\0" * 8)
    output = bytearray()
    while len(output) < length:
        output.extend(_salsa_core(bytes(counter), key, False))
        carry = 1
        for index in range(8, 16):
            total = counter[index] + carry
            counter[index] = total & 0xFF
            carry = total >> 8
    return bytes(output[:length])


def _xsalsa19_stream(length: int, nonce: bytes, key: bytes) -> bytes:
    if len(nonce) != 24 or len(key) != 32:
        raise ValueError("XSalsa requires a 24-byte nonce and 32-byte key")
    return _salsa19_stream(length, nonce[16:], _hsalsa19(nonce[:16], key))


def _poly1305(message: bytes, key: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("Poly1305 requires a 32-byte one-time key")
    r = int.from_bytes(key[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    pad = int.from_bytes(key[16:], "little")
    accumulator = 0
    modulus = (1 << 130) - 5
    for offset in range(0, len(message), 16):
        block = message[offset:offset + 16]
        accumulator = (accumulator + int.from_bytes(block + b"\x01", "little")) * r % modulus
    return ((accumulator + pad) & ((1 << 128) - 1)).to_bytes(16, "little")


def secretbox_encrypt(message: bytes, nonce: bytes, key: bytes) -> bytes:
    key_stream = _xsalsa19_stream(32 + len(message), nonce, key)
    ciphertext = bytes(value ^ key_stream[index + 32] for index, value in enumerate(message))
    return _poly1305(ciphertext, key_stream[:32]) + ciphertext


def secretbox_decrypt(ciphertext: bytes, nonce: bytes, key: bytes) -> bytes:
    if len(ciphertext) < 16:
        raise CryptoError("ciphertext is too short")
    tag, encrypted = ciphertext[:16], ciphertext[16:]
    key_stream = _xsalsa19_stream(32 + len(encrypted), nonce, key)
    if not compare_digest(tag, _poly1305(encrypted, key_stream[:32])):
        raise CryptoError("ciphertext authentication failed")
    return bytes(value ^ key_stream[index + 32] for index, value in enumerate(encrypted))


def _box_key() -> bytes:
    shared = crypto_scalarmult(CLIENT_SECRET_KEY, SERVER_PUBLIC_KEY)
    return _hsalsa19(bytes(16), shared)


def box_encrypt(message: bytes, nonce: bytes) -> bytes:
    return secretbox_encrypt(message, nonce, _box_key())


def box_decrypt(ciphertext: bytes, nonce: bytes) -> bytes:
    return secretbox_decrypt(ciphertext, nonce, _box_key())


class PepperEncrypter:
    def __init__(self, key: bytes, nonce: bytes):
        if len(key) != 32 or len(nonce) != 24:
            raise ValueError("Pepper requires a 32-byte key and 24-byte nonce")
        self.key = key
        self.nonce = bytearray(nonce)

    def _next_nonce(self) -> bytes:
        carry = 2
        for index, value in enumerate(self.nonce):
            total = carry + value
            self.nonce[index] = total & 0xFF
            carry = total >> 8
            if carry == 0:
                break
        return bytes(self.nonce)

    def encrypt(self, value: bytes) -> bytes:
        return secretbox_encrypt(value, self._next_nonce(), self.key)

    def decrypt(self, value: bytes) -> bytes:
        return secretbox_decrypt(value, self._next_nonce(), self.key)

    @staticmethod
    def get_encryption_overhead() -> int:
        return 16


__all__ = [
    "CLIENT_SECRET_KEY", "SERVER_PUBLIC_KEY", "CryptoError", "PepperEncrypter",
    "box_decrypt", "box_encrypt", "pepper_hash", "secretbox_decrypt", "secretbox_encrypt",
]
