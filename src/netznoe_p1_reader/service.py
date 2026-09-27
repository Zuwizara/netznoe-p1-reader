"""Application orchestration."""

from __future__ import annotations

import logging
import threading

from .config import AppConfig
from .dlms import DlmsDecoder
from .mqtt import MqttPublisher
from .obis import DlmsDataError
from .serial_reader import SerialReader

LOGGER = logging.getLogger(__name__)


def run(config: AppConfig, stop_event: threading.Event) -> None:
    decoder = DlmsDecoder(config.guek)
    publisher = MqttPublisher(config.mqtt)
    reader = SerialReader(config.serial)
    publisher.start()
    try:
        for frame in reader.frames(stop_event):
            try:
                measurement = decoder.decode_frame(frame)
            except DlmsDataError as exc:
                LOGGER.warning("Discarding undecodable DLMS push: %s", exc)
                continue
            if measurement is not None:
                LOGGER.info("Decoded meter measurement")
                publisher.submit(measurement)
    finally:
        publisher.stop()
