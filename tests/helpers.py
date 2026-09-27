from __future__ import annotations


def mbus_frame(body: bytes) -> bytes:
    if not 5 <= len(body) <= 255:
        raise ValueError("body length must fit an M-Bus long frame")
    length = len(body)
    return bytes((0x68, length, length, 0x68)) + body + bytes((sum(body) & 0xFF, 0x16))
