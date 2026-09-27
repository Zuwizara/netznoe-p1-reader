"""Resilient serial input loop."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import serial

from .config import SerialConfig
from .mbus import MBusFramer

LOGGER = logging.getLogger(__name__)


class SerialCheckError(RuntimeError):
    """Raised when the serial adapter check cannot find a valid frame."""


@dataclass(frozen=True, slots=True)
class SerialCheckResult:
    frame_length: int
    bytes_received: int


def check_serial_port(config: SerialConfig, timeout_seconds: float = 15.0) -> SerialCheckResult:
    """Wait for one valid M-Bus frame without decrypting or logging its contents."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    framer = MBusFramer()
    received = 0
    deadline = time.monotonic() + timeout_seconds
    try:
        with serial.Serial(
            port=config.port,
            baudrate=config.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=min(config.timeout, timeout_seconds),
        ) as connection:
            while time.monotonic() < deadline:
                chunk = connection.read(512)
                if not chunk:
                    framer.on_timeout()
                    continue
                received += len(chunk)
                frames = framer.feed(chunk)
                if frames:
                    return SerialCheckResult(len(frames[0]), received)
    except (OSError, serial.SerialException) as exc:
        raise SerialCheckError(f"cannot open or read {config.port}: {exc}") from exc
    raise SerialCheckError(
        f"no valid M-Bus frame received from {config.port} within {timeout_seconds:g} seconds "
        f"({received} bytes received)"
    )


class SerialReader:
    def __init__(self, config: SerialConfig, *, read_size: int = 512) -> None:
        self._config = config
        self._read_size = read_size
        self._framer = MBusFramer()

    def frames(self, stop_event: threading.Event) -> Iterator[bytes]:
        delay = self._config.reconnect_min_seconds
        while not stop_event.is_set():
            try:
                LOGGER.info(
                    "Opening serial port %s at %d baud (8N1)",
                    self._config.port,
                    self._config.baudrate,
                )
                with serial.Serial(
                    port=self._config.port,
                    baudrate=self._config.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self._config.timeout,
                ) as connection:
                    delay = self._config.reconnect_min_seconds
                    while not stop_event.is_set():
                        chunk = connection.read(self._read_size)
                        if not chunk:
                            self._framer.on_timeout()
                            continue
                        yield from self._framer.feed(chunk)
            except (OSError, serial.SerialException) as exc:
                self._framer.clear()
                LOGGER.error("Serial connection failed: %s; retrying in %.1fs", exc, delay)
                if stop_event.wait(delay):
                    return
                delay = min(delay * 2, self._config.reconnect_max_seconds)
