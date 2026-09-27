from __future__ import annotations

from typing import Any

import pytest

from netznoe_p1_reader.config import SerialConfig
from netznoe_p1_reader.serial_reader import SerialCheckError, check_serial_port

from .helpers import mbus_frame


class FakeSerial:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = iter(chunks)

    def __enter__(self) -> FakeSerial:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return next(self._chunks, b"")


def test_serial_check_accepts_fragmented_valid_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = mbus_frame(b"\x53\xff\x11\x01\x67payload")
    connection = FakeSerial([frame[:4], frame[4:]])
    monkeypatch.setattr("netznoe_p1_reader.serial_reader.serial.Serial", lambda **_kw: connection)
    monkeypatch.setattr("netznoe_p1_reader.serial_reader.time.monotonic", lambda: 0.0)

    result = check_serial_port(SerialConfig("/dev/test"))

    assert result.frame_length == len(frame)
    assert result.bytes_received == len(frame)


def test_serial_check_reports_timeout_without_printing_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeSerial([b"noise", b""])
    ticks = iter((0.0, 0.0, 1.0))
    monkeypatch.setattr("netznoe_p1_reader.serial_reader.serial.Serial", lambda **_kw: connection)
    monkeypatch.setattr(
        "netznoe_p1_reader.serial_reader.time.monotonic", lambda: next(ticks, 2.0)
    )

    with pytest.raises(SerialCheckError, match=r"5 bytes received"):
        check_serial_port(SerialConfig("/dev/test"), timeout_seconds=1)
