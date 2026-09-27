"""Resilient serial input loop."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator

import serial

from .config import SerialConfig
from .mbus import MBusFramer

LOGGER = logging.getLogger(__name__)


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
