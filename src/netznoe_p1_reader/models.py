"""Domain models shared by decoder and publishers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class Measurement:
    timestamp: str | None = None
    energy_import_wh: int | float | None = None
    energy_export_wh: int | float | None = None
    power_import_w: int | float | None = None
    power_export_w: int | float | None = None
    voltage_l1_v: int | float | None = None
    voltage_l2_v: int | float | None = None
    voltage_l3_v: int | float | None = None
    current_l1_a: int | float | None = None
    current_l2_a: int | float | None = None
    current_l3_a: int | float | None = None
    power_factor: int | float | None = None
    meter_number: str | None = None
    received_at: str = ""

    def __post_init__(self) -> None:
        if not self.received_at:
            self.received_at = datetime.now(UTC).isoformat()

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)
