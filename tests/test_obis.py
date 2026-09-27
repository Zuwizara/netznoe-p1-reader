from __future__ import annotations

from netznoe_p1_reader.obis import obis_from_bytes, parse_gurux_xml


def test_obis_mapping_scaling_unknown_and_missing_values() -> None:
    xml = """
    <DataNotification><NotificationBody><DataValue><Structure Qty="9">
      <OctetString Value="07E5091B01092F0F00FF8880" />
      <OctetString Value="0100200700FF" /><UInt16 Value="0921" />
      <Structure Qty="02"><Int8 Value="FF" /><Enum Value="23" /></Structure>
      <OctetString Value="01001F0700FF" /><UInt16 Value="007B" />
      <Structure Qty="02"><Int8 Value="FE" /><Enum Value="21" /></Structure>
      <OctetString Value="0100630100FF" /><UInt16 Value="1234" />
      <Structure Qty="02"><Int8 Value="00" /><Enum Value="FF" /></Structure>
      <OctetString Value="313831323230303030303039" />
    </Structure></DataValue></NotificationBody></DataNotification>
    """
    measurement = parse_gurux_xml(xml)
    assert measurement is not None
    assert measurement.timestamp == "2021-09-27T09:47:15+02:00"
    assert measurement.voltage_l1_v == 233.7
    assert measurement.current_l1_a == 1.23
    assert measurement.meter_number == "181220000009"
    assert measurement.energy_import_wh is None


def test_obis_is_derived_from_six_bytes() -> None:
    assert obis_from_bytes(bytes.fromhex("0100010800FF")) == "1.0.1.8.0.255"
