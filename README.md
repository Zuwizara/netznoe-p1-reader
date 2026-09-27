# netznoe-p1-reader

[Deutsch](README.de.md) | English

[![CI](https://github.com/Zuwizara/netznoe-p1-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/Zuwizara/netznoe-p1-reader/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/tag/Zuwizara/netznoe-p1-reader)](https://github.com/Zuwizara/netznoe-p1-reader/tags)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/github/license/Zuwizara/netznoe-p1-reader)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-C51A4A?logo=raspberrypi)](https://www.raspberrypi.com/)

A long-running Python service for Raspberry Pi. It reads the encrypted P1
customer interface of a Netz NÖ smart meter, decrypts its DLMS/COSEM data and
publishes all measurements over MQTT. Home Assistant MQTT Discovery is built
in.

The first release supports the Netz NÖ Kaifa MA309. The service runs without
root privileges and never logs the personal GUEK or complete frames.

## Requirements

- Raspberry Pi with Raspberry Pi OS or a comparable Debian system
- Python 3.11 or newer
- Kaifa MA309 with its P1 customer interface enabled
- personal 32-character GUEK from Netz NÖ
- a genuine wired M-Bus-to-USB converter; a USB UART adapter is not sufficient
- an accessible MQTT broker
- optionally, Home Assistant with the MQTT integration configured

According to the Netz NÖ documentation, the RJ12 connector uses pin 3 for
`MBUS1 (+)` and pin 4 for `MBUS2 (-)`. Follow the instructions from Netz NÖ and
the adapter manufacturer.

### Tested M-Bus adapter

Hardware testing used the
[Tedbear USB M-Bus Master/Slave adapter, ASIN B0827DSGTD](https://www.amazon.de/dp/B0827DSGTD).
This is a test reference, not a purchase recommendation or a guarantee for
later product revisions.

## Installation

The commands below are not executed automatically.

### 1. Prepare the system

```console
sudo apt update
sudo apt install --yes git python3 python3-venv
python3 --version
```

Python must be version `3.11` or newer.

### 2. Create the service account and install the application

```console
sudo useradd --system --user-group \
  --home /opt/netznoe-p1-reader \
  --shell /usr/sbin/nologin netznoe-p1-reader
sudo usermod -aG dialout netznoe-p1-reader
sudo mkdir -p /opt/netznoe-p1-reader
sudo chown netznoe-p1-reader:netznoe-p1-reader /opt/netznoe-p1-reader
sudo -u netznoe-p1-reader git clone \
  https://github.com/Zuwizara/netznoe-p1-reader.git \
  /opt/netznoe-p1-reader/src
sudo -u netznoe-p1-reader python3 -m venv \
  /opt/netznoe-p1-reader/.venv
sudo -u netznoe-p1-reader \
  /opt/netznoe-p1-reader/.venv/bin/pip install \
  /opt/netznoe-p1-reader/src
```

Run `id netznoe-p1-reader` and verify that both `netznoe-p1-reader` and
`dialout` are listed as groups.

### 3. Find the serial adapter

Plug in the adapter and list stable device names:

```console
ls -l /dev/serial/by-id/
```

Example:

```text
/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A10XYZ-if00-port0
```

Check its permissions and device group:

```console
stat -Lc 'Device: %n  Group: %G  Permissions: %A' \
  /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A10XYZ-if00-port0
```

A path below `/dev/serial/by-id/` normally remains stable across reboots. If
there is no such entry, `/dev/ttyUSB0` can be used temporarily. If the device
group is not `dialout`, add the service account to the group shown instead.

### 4. Create the configuration

```console
sudo install -o root -g netznoe-p1-reader -m 0640 \
  /opt/netznoe-p1-reader/src/.env.example \
  /etc/netznoe-p1-reader.env
sudoedit /etc/netznoe-p1-reader.env
```

Replace at least these placeholders:

- `NETZNOE_P1_GUEK`: personal GUEK, exactly 32 hexadecimal characters
- `NETZNOE_P1_SERIAL_PORT`: the adapter path found above
- `NETZNOE_P1_MQTT_HOST`, username and password: MQTT access details
- `NETZNOE_P1_DEVICE_ID`: a stable ID, for example `meter_basement`

Do not change `DEVICE_ID` later or Home Assistant will create new entities.
Never put the real GUEK in Git, screenshots, tickets or logs.

### 5. Check the configuration and adapter

Validate the configuration without opening the port or network:

```console
sudo -u netznoe-p1-reader sh -c \
  'set -a; . /etc/netznoe-p1-reader.env; exec /opt/netznoe-p1-reader/.venv/bin/netznoe-p1-reader --check-config'
```

The expected output is `Configuration is valid`.

Then wait up to 20 seconds for a valid M-Bus frame:

```console
sudo -u netznoe-p1-reader sh -c \
  'set -a; . /etc/netznoe-p1-reader.env; exec /opt/netznoe-p1-reader/.venv/bin/netznoe-p1-reader --check-serial --check-serial-seconds 20'
```

Example success output:

```text
serial check passed: valid 256-byte M-Bus frame received on /dev/serial/by-id/...
```

This check needs neither the GUEK nor MQTT and does not print frame contents.
It validates the M-Bus header, duplicate length, checksum and end byte.

### 6. Start the systemd service

```console
sudo install -o root -g root -m 0644 \
  /opt/netznoe-p1-reader/src/contrib/netznoe-p1-reader.service \
  /etc/systemd/system/netznoe-p1-reader.service
sudo systemctl daemon-reload
sudo systemctl enable --now netznoe-p1-reader.service
```

The service runs as `netznoe-p1-reader`, gets serial access through `dialout`,
starts at boot and restarts after failures.

### 7. Verify operation

```console
systemctl status netznoe-p1-reader.service
journalctl -u netznoe-p1-reader.service -f
```

`Active: active (running)` indicates a running service. During normal operation,
the log reports the open serial port, MQTT connection and decrypted
measurements.

The MQTT broker should receive:

- `<topic-prefix>/availability`: retained value `online`
- `<topic-prefix>/state`: a JSON data set about every five seconds
- `<discovery-prefix>/sensor/...`: retained Home Assistant configuration

Home Assistant automatically creates one device containing all sensors.

## Updating

```console
sudo systemctl stop netznoe-p1-reader.service
sudo -u netznoe-p1-reader git -C \
  /opt/netznoe-p1-reader/src pull --ff-only
sudo -u netznoe-p1-reader \
  /opt/netznoe-p1-reader/.venv/bin/pip install --upgrade \
  /opt/netznoe-p1-reader/src
sudo systemctl start netznoe-p1-reader.service
systemctl status netznoe-p1-reader.service
```

## Troubleshooting

- **Adapter is not shown:** check the USB connection and run
  `ls -l /dev/serial/by-id/` again.
- **`cannot open or read`:** check the device path, group and output of
  `id netznoe-p1-reader`.
- **`0 bytes received`:** check P1 activation, RJ12 wiring and the M-Bus level
  converter.
- **Bytes arrive, but no valid frame:** check 2400 baud, 8N1, signal levels and
  wiring.
- **Decryption fails:** ensure the GUEK has exactly 32 hexadecimal characters
  and belongs to this meter.
- **No MQTT data:** check broker address, credentials and ACLs; for TLS also
  check time, hostname and CA chain.
- **No Home Assistant sensors:** check the MQTT integration, discovery prefix
  and permission to publish retained discovery messages.

Do not paste real keys or frames into public issues.

## Configuration reference

All variables start with `NETZNOE_P1_`.

| Variable | Default | Description |
| --- | --- | --- |
| `GUEK` | required | 32 hexadecimal characters / 16 bytes |
| `SERIAL_PORT` | `/dev/ttyUSB0` | serial M-Bus converter |
| `SERIAL_BAUDRATE` | `2400` | baud rate; 8N1 is fixed |
| `SERIAL_TIMEOUT_MS` | `1000` | timeout for partial frames |
| `MQTT_HOST` | `localhost` | broker hostname or address |
| `MQTT_PORT` | `1883`, with TLS `8883` | broker port |
| `MQTT_USERNAME` | empty | optional username |
| `MQTT_PASSWORD` | empty | optional password |
| `MQTT_TOPIC_PREFIX` | `netznoe/p1` | state/availability base |
| `DEVICE_ID` | based on hostname | stable, unique ID |
| `DEVICE_NAME` | `Netz NÖ Smart Meter` | display name |
| `HA_DISCOVERY_PREFIX` | `homeassistant` | discovery prefix |
| `MQTT_TLS` | `false` | enable TLS |
| `MQTT_TLS_CA_CERT` | system CAs | optional private CA |
| `LOG_LEVEL` | `INFO` | Python log level |

TLS always verifies certificates; there is no insecure mode.

## MQTT and Home Assistant

The service maintains exactly one Paho connection with its own network loop
and automatic reconnect. A broker outage does not block serial reading; at
most the most recent measurement remains queued for publishing.

- State: `<topic-prefix>/state`, QoS 1, not retained
- Availability: `<topic-prefix>/availability`, QoS 1, retained Last Will
- Discovery: `<discovery-prefix>/sensor/<device-id>/<sensor>/config`, QoS 1,
  retained
- Home Assistant birth: `<discovery-prefix>/status`
- Sensor timeout: `expire_after` 30 seconds

Example state message:

```json
{
  "timestamp": "2021-09-27T09:47:15+02:00",
  "energy_import_wh": 12937,
  "energy_export_wh": 0,
  "power_import_w": 0,
  "power_export_w": 0,
  "voltage_l1_v": 233.7,
  "voltage_l2_v": 0,
  "voltage_l3_v": 0,
  "current_l1_a": 0,
  "current_l2_a": 0,
  "current_l3_a": 0,
  "power_factor": 1,
  "meter_number": "181220000009",
  "received_at": "2026-01-01T12:00:00+00:00"
}
```

## Development

```console
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

Tests need neither hardware nor network services. They cover framing, OBIS,
scaling, MQTT and discovery, and decrypt the public Netz NÖ sample frame.
GitHub Actions runs them on Python 3.11 through 3.14.

## Technical details

### Protocol and resilience

- wired M-Bus, 2400 baud, 8N1, unidirectional
- M-Bus long frames `68 LL LL 68 ... checksum 16`
- DLMS/COSEM Security Suite 0 with the individual 16-byte GUEK
- push interval of approximately five seconds
- decryption and fragment assembly using `gurux-dlms`
- interpretation by OBIS code instead of fixed XML positions

The streaming framer handles fragmented reads, multiple frames per read, noise
and corrupt frames. It validates length, checksum and end byte, and reopens the
port with exponential backoff after connection failures.

### Supported OBIS values

| JSON field | OBIS | Unit |
| --- | --- | --- |
| `energy_import_wh` | `1.0.1.8.0.255` | Wh |
| `energy_export_wh` | `1.0.2.8.0.255` | Wh |
| `power_import_w` | `1.0.1.7.0.255` | W |
| `power_export_w` | `1.0.2.7.0.255` | W |
| `voltage_l1_v` | `1.0.32.7.0.255` | V |
| `voltage_l2_v` | `1.0.52.7.0.255` | V |
| `voltage_l3_v` | `1.0.72.7.0.255` | V |
| `current_l1_a` | `1.0.31.7.0.255` | A |
| `current_l2_a` | `1.0.51.7.0.255` | A |
| `current_l3_a` | `1.0.71.7.0.255` | A |
| `power_factor` | `1.0.13.7.0.255` | - |

The timestamp and meter number are read as well. The scaler and unit come from
the COSEM data set. Missing or unknown OBIS values do not stop the service.

### Kaifa frame assumptions

The public Netz NÖ sample push is 282 bytes long and consists of two M-Bus
long frames: `68 FA FA 68` with 256 bytes and `68 14 14 68` with 26 bytes. The
assembled PDU contains an 8-byte system title, Security Control `0x20` for
Security Suite 0, a big-endian 32-bit frame counter and the encrypted data.
Netz NÖ does not use an authentication key for this format.

These assumptions are tested against the public sample. Real meter readings,
system titles and frame counters are not hard-coded.

## Sources

- [Netz NÖ: Smart Meter customer interface P1, 6th edition, March 2026](https://netz-noe.at/getContentAsset/568bef9a-3bd1-4f2e-a710-6ba7e71cb746/0ee16eb8-9692-4f25-b8a4-d007b35915a4/218_20_SM_Kundenschnittstelle_WCAG.pdf?language=de)
- [Gurux DLMS Python](https://github.com/Gurux/Gurux.DLMS.Python)
- [Paho MQTT Python Client](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
- [Home Assistant MQTT](https://www.home-assistant.io/integrations/mqtt/)

## License

GPL-2.0-only, see [LICENSE](LICENSE).
