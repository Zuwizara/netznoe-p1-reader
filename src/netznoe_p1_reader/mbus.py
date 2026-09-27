"""Streaming parser for wired M-Bus long frames."""

from __future__ import annotations

import logging
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)
START = 0x68
STOP = 0x16


@dataclass(slots=True)
class FramerStats:
    discarded_bytes: int = 0
    invalid_headers: int = 0
    invalid_checksums: int = 0
    invalid_end_bytes: int = 0
    timed_out_frames: int = 0


class MBusFramer:
    """Recover validated M-Bus long frames from arbitrary serial chunks."""

    def __init__(self, *, minimum_length: int = 5) -> None:
        self._buffer = bytearray()
        self._minimum_length = minimum_length
        self.stats = FramerStats()

    def feed(self, data: bytes) -> list[bytes]:
        if data:
            self._buffer.extend(data)
        frames: list[bytes] = []

        while True:
            start = self._buffer.find(START)
            if start < 0:
                self.stats.discarded_bytes += len(self._buffer)
                self._buffer.clear()
                break
            if start:
                self.stats.discarded_bytes += start
                del self._buffer[:start]
            if len(self._buffer) < 4:
                break

            length = self._buffer[1]
            if (
                self._buffer[2] != length
                or self._buffer[3] != START
                or length < self._minimum_length
            ):
                self.stats.invalid_headers += 1
                del self._buffer[0]
                continue

            frame_size = length + 6
            if len(self._buffer) < frame_size:
                later = self._find_complete_frame_start()
                if later is not None:
                    self.stats.discarded_bytes += later
                    self.stats.invalid_headers += 1
                    del self._buffer[:later]
                    continue
                break

            candidate = bytes(self._buffer[:frame_size])
            if candidate[-1] != STOP:
                self.stats.invalid_end_bytes += 1
                LOGGER.warning("Discarding M-Bus frame with invalid end byte")
                del self._buffer[0]
                continue
            checksum = sum(candidate[4:-2]) & 0xFF
            if checksum != candidate[-2]:
                self.stats.invalid_checksums += 1
                LOGGER.warning("Discarding M-Bus frame with invalid checksum")
                del self._buffer[0]
                continue

            frames.append(candidate)
            del self._buffer[:frame_size]

        return frames

    def _find_complete_frame_start(self) -> int | None:
        """Find a later fully validated frame behind a bogus partial header."""
        for start in range(1, max(1, len(self._buffer) - 3)):
            if self._buffer[start] != START or start + 4 > len(self._buffer):
                continue
            length = self._buffer[start + 1]
            if (
                length < self._minimum_length
                or self._buffer[start + 2] != length
                or self._buffer[start + 3] != START
            ):
                continue
            end = start + length + 6
            if end > len(self._buffer):
                continue
            candidate = self._buffer[start:end]
            if candidate[-1] == STOP and (sum(candidate[4:-2]) & 0xFF) == candidate[-2]:
                return start
        return None

    def on_timeout(self) -> None:
        """Drop a partial candidate after an idle serial timeout."""
        if self._buffer:
            self.stats.timed_out_frames += 1
            LOGGER.warning("Discarding %d buffered serial bytes after timeout", len(self._buffer))
            self._buffer.clear()

    def clear(self) -> None:
        self._buffer.clear()
