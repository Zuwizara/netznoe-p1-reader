from __future__ import annotations

from netznoe_p1_reader.dlms import DlmsDecoder
from netznoe_p1_reader.mbus import MBusFramer

from .fixtures import PUBLIC_GUEK, PUBLIC_MBUS_PUSH


def test_official_net_noe_example_frame() -> None:
    frames = MBusFramer().feed(PUBLIC_MBUS_PUSH)
    assert [len(frame) for frame in frames] == [256, 26]

    decoder = DlmsDecoder(PUBLIC_GUEK)
    assert decoder.decode_frame(frames[0]) is None
    measurement = decoder.decode_frame(frames[1])
    assert measurement is not None
    assert measurement.timestamp == "2021-09-27T09:47:15+02:00"
    assert measurement.energy_import_wh == 12937
    assert measurement.energy_export_wh == 0
    assert measurement.voltage_l1_v == 233.7
    assert measurement.power_factor == 1
    assert measurement.meter_number == "181220000009"
    assert decoder.last_metadata.system_title == "4B464D6750000009"
    assert decoder.last_metadata.frame_counter == 35
    assert decoder.last_metadata.security_control == 0x20
