"""OBIS-based interpretation of Gurux Simple XML output."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .models import Measurement

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ObisDefinition:
    field: str
    expected_unit_code: int | None


OBIS: dict[str, ObisDefinition] = {
    "1.0.1.8.0.255": ObisDefinition("energy_import_wh", 30),
    "1.0.2.8.0.255": ObisDefinition("energy_export_wh", 30),
    "1.0.1.7.0.255": ObisDefinition("power_import_w", 27),
    "1.0.2.7.0.255": ObisDefinition("power_export_w", 27),
    "1.0.32.7.0.255": ObisDefinition("voltage_l1_v", 35),
    "1.0.52.7.0.255": ObisDefinition("voltage_l2_v", 35),
    "1.0.72.7.0.255": ObisDefinition("voltage_l3_v", 35),
    "1.0.31.7.0.255": ObisDefinition("current_l1_a", 33),
    "1.0.51.7.0.255": ObisDefinition("current_l2_a", 33),
    "1.0.71.7.0.255": ObisDefinition("current_l3_a", 33),
    "1.0.13.7.0.255": ObisDefinition("power_factor", 255),
}

_DATA_NOTIFICATION = re.compile(r"<DataNotification>.*?</DataNotification>", re.DOTALL)
_SYSTEM_TITLE = re.compile(r'<SystemTitle Value="([0-9A-Fa-f]+)"')
_CIPHERED_SERVICE = re.compile(r'<CipheredService Value="([0-9A-Fa-f]+)"')
_INTEGER_TAGS = {
    "Int8": (1, True),
    "Int16": (2, True),
    "Int32": (4, True),
    "Int64": (8, True),
    "UInt8": (1, False),
    "UInt16": (2, False),
    "UInt32": (4, False),
    "UInt64": (8, False),
    "Enum": (1, False),
}


class DlmsDataError(ValueError):
    """Raised when decrypted DLMS data cannot be interpreted."""


@dataclass(frozen=True, slots=True)
class DlmsMetadata:
    system_title: str | None
    frame_counter: int | None
    security_control: int | None


def obis_from_bytes(value: bytes) -> str:
    if len(value) != 6:
        raise DlmsDataError("an OBIS logical name must contain six bytes")
    return ".".join(str(part) for part in value)


def _integer(node: ET.Element) -> int:
    try:
        size, signed = _INTEGER_TAGS[node.tag]
        raw = bytes.fromhex(node.attrib["Value"])
    except (KeyError, ValueError) as exc:
        raise DlmsDataError(f"unsupported or invalid DLMS integer {node.tag}") from exc
    if len(raw) > size:
        raise DlmsDataError(f"invalid width for {node.tag}")
    raw = raw.rjust(size, b"\x00")
    return int.from_bytes(raw, "big", signed=signed)


def _scaled(value: int, scaler: int) -> int | float:
    result = Decimal(value) * (Decimal(10) ** scaler)
    if result == result.to_integral_value():
        return int(result)
    return float(result)


def _decode_datetime(raw: bytes) -> str | None:
    required_indexes = (0, 1, 2, 3, 5, 6, 7)
    if len(raw) != 12 or any(raw[index] == 0xFF for index in required_indexes):
        return None
    year = int.from_bytes(raw[0:2], "big")
    hundredths = 0 if raw[8] == 0xFF else raw[8]
    deviation_raw = int.from_bytes(raw[9:11], "big", signed=True)
    tz = None if deviation_raw == -32768 else timezone(timedelta(minutes=-deviation_raw))
    try:
        value = datetime(
            year,
            raw[2],
            raw[3],
            raw[5],
            raw[6],
            raw[7],
            hundredths * 10_000,
            tz,
        )
    except ValueError:
        return None
    return value.isoformat()


def extract_metadata(xml: str) -> DlmsMetadata:
    title_match = _SYSTEM_TITLE.search(xml)
    cipher_match = _CIPHERED_SERVICE.search(xml)
    security_control: int | None = None
    frame_counter: int | None = None
    if cipher_match:
        ciphered = bytes.fromhex(cipher_match.group(1))
        if len(ciphered) >= 5:
            security_control = ciphered[0]
            frame_counter = int.from_bytes(ciphered[1:5], "big")
    return DlmsMetadata(
        system_title=title_match.group(1).upper() if title_match else None,
        frame_counter=frame_counter,
        security_control=security_control,
    )


def parse_gurux_xml(xml: str) -> Measurement | None:
    """Parse a decrypted notification by OBIS name, not element position."""
    match = _DATA_NOTIFICATION.search(xml)
    if not match:
        return None
    try:
        root = ET.fromstring(match.group(0))
    except ET.ParseError as exc:
        raise DlmsDataError("Gurux returned malformed decrypted XML") from exc
    structure = root.find("./NotificationBody/DataValue/Structure")
    if structure is None:
        raise DlmsDataError("DLMS notification contains no data structure")

    values: dict[str, object] = {}
    children = list(structure)
    for index, node in enumerate(children):
        if node.tag != "OctetString":
            continue
        try:
            raw = bytes.fromhex(node.attrib["Value"])
        except (KeyError, ValueError):
            continue

        if len(raw) == 12 and "timestamp" not in values:
            values["timestamp"] = _decode_datetime(raw)
            continue
        if len(raw) == 6 and index + 2 < len(children):
            obis = obis_from_bytes(raw)
            definition = OBIS.get(obis)
            if definition is None:
                LOGGER.debug("Ignoring unsupported OBIS %s", obis)
                continue
            value_node = children[index + 1]
            scaler_unit = children[index + 2]
            if value_node.tag not in _INTEGER_TAGS or scaler_unit.tag != "Structure":
                LOGGER.warning("Ignoring malformed value for OBIS %s", obis)
                continue
            parts = list(scaler_unit)
            if len(parts) < 2 or parts[0].tag != "Int8" or parts[1].tag != "Enum":
                LOGGER.warning("Ignoring missing scaler/unit for OBIS %s", obis)
                continue
            scaler = _integer(parts[0])
            unit_code = _integer(parts[1])
            if (
                definition.expected_unit_code is not None
                and unit_code != definition.expected_unit_code
            ):
                LOGGER.warning(
                    "OBIS %s uses unit code %d, expected %d",
                    obis,
                    unit_code,
                    definition.expected_unit_code,
                )
            values[definition.field] = _scaled(_integer(value_node), scaler)
            continue
        if raw and all(0x20 <= char <= 0x7E for char in raw):
            values["meter_number"] = raw.decode("ascii")

    return Measurement(**values)  # type: ignore[arg-type]
