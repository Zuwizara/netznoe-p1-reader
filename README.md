# netznoe-p1-reader

Deutsch | [English](README.en.md)

[![CI](https://github.com/Zuwizara/netznoe-p1-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/Zuwizara/netznoe-p1-reader/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/tag/Zuwizara/netznoe-p1-reader)](https://github.com/Zuwizara/netznoe-p1-reader/tags)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/github/license/Zuwizara/netznoe-p1-reader)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-C51A4A?logo=raspberrypi)](https://www.raspberrypi.com/)

Ein dauerhaft laufender Python-Dienst für den Raspberry Pi. Er liest die
verschlüsselte P1-Kundenschnittstelle eines Netz-NÖ-Smart-Meters, entschlüsselt
DLMS/COSEM-Daten und veröffentlicht alle Messwerte über MQTT. Home Assistant
MQTT Discovery ist integriert.

Der erste Release unterstützt den Kaifa MA309 von Netz NÖ. Der Dienst läuft
ohne Root-Rechte und gibt weder den persönlichen GUEK noch vollständige Frames
im Log aus.

## Voraussetzungen

- Raspberry Pi mit Raspberry Pi OS oder einem vergleichbaren Debian-System
- Python 3.11 oder neuer
- Kaifa MA309 mit aktivierter P1-Kundenschnittstelle
- persönlicher 32-stelliger GUEK von Netz NÖ
- echter wired-M-Bus-zu-USB-Konverter; ein USB-UART-Adapter genügt nicht
- erreichbarer MQTT-Broker
- optional Home Assistant mit eingerichteter MQTT-Integration

Laut Netz-NÖ-Dokumentation liegen am RJ12-Anschluss `MBUS1 (+)` auf Pin 3 und
`MBUS2 (-)` auf Pin 4. Die Vorgaben von Netz NÖ und des Adapterherstellers sind
zu beachten.

### Getesteter M-Bus-Adapter

Der Hardwaretest erfolgte mit dem
[Tedbear USB-M-Bus-Master/Slave-Adapter, ASIN B0827DSGTD](https://www.amazon.de/dp/B0827DSGTD).
Das ist ein Erfahrungswert, keine Kaufempfehlung oder Garantie für spätere
Produktrevisionen.

## Installation

Die folgenden Befehle werden nicht automatisch ausgeführt.

### 1. System vorbereiten

```console
sudo apt update
sudo apt install --yes git python3 python3-venv
python3 --version
```

Die Python-Version muss mindestens `3.11` sein.

### 2. Dienstkonto und Anwendung anlegen

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

Mit `id netznoe-p1-reader` prüfen, ob die Gruppen
`netznoe-p1-reader` und `dialout` eingetragen sind.

### 3. Seriellen Adapter finden

Adapter einstecken und stabile Gerätenamen anzeigen:

```console
ls -l /dev/serial/by-id/
```

Beispiel:

```text
/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A10XYZ-if00-port0
```

Rechte und Geräte-Gruppe prüfen:

```console
stat -Lc 'Gerät: %n  Gruppe: %G  Rechte: %A' \
  /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A10XYZ-if00-port0
```

Ein Pfad unter `/dev/serial/by-id/` bleibt normalerweise auch nach Neustarts
stabil. Falls kein solcher Eintrag existiert, kann vorläufig `/dev/ttyUSB0`
verwendet werden. Weicht die Geräte-Gruppe von `dialout` ab, muss stattdessen
diese Gruppe beim Dienstkonto ergänzt werden.

### 4. Konfiguration anlegen

```console
sudo install -o root -g netznoe-p1-reader -m 0640 \
  /opt/netznoe-p1-reader/src/.env.example \
  /etc/netznoe-p1-reader.env
sudoedit /etc/netznoe-p1-reader.env
```

Mindestens diese Platzhalter ersetzen:

- `NETZNOE_P1_GUEK`: persönlicher GUEK, exakt 32 Hex-Zeichen
- `NETZNOE_P1_SERIAL_PORT`: zuvor ermittelter Adapterpfad
- `NETZNOE_P1_MQTT_HOST`, Benutzer und Passwort: MQTT-Zugang
- `NETZNOE_P1_DEVICE_ID`: stabile ID, beispielsweise `zaehler_keller`

Die `DEVICE_ID` später nicht ändern, sonst legt Home Assistant neue Entitäten
an. Der echte GUEK gehört niemals in Git, Screenshots, Tickets oder Logs.

### 5. Konfiguration und Adapter prüfen

Konfiguration prüfen, ohne Port oder Netzwerk zu öffnen:

```console
sudo -u netznoe-p1-reader sh -c \
  'set -a; . /etc/netznoe-p1-reader.env; exec /opt/netznoe-p1-reader/.venv/bin/netznoe-p1-reader --check-config'
```

Erwartet wird `Configuration is valid`.

Anschließend bis zu 20 Sekunden auf einen gültigen M-Bus-Frame warten:

```console
sudo -u netznoe-p1-reader sh -c \
  'set -a; . /etc/netznoe-p1-reader.env; exec /opt/netznoe-p1-reader/.venv/bin/netznoe-p1-reader --check-serial --check-serial-seconds 20'
```

Erfolgreiche Beispielausgabe:

```text
serial check passed: valid 256-byte M-Bus frame received on /dev/serial/by-id/...
```

Der Selbsttest benötigt weder GUEK noch MQTT und gibt keine Frameinhalte aus.
Er prüft M-Bus-Header, doppelte Länge, Prüfsumme und Endbyte.

### 6. systemd-Dienst starten

```console
sudo install -o root -g root -m 0644 \
  /opt/netznoe-p1-reader/src/contrib/netznoe-p1-reader.service \
  /etc/systemd/system/netznoe-p1-reader.service
sudo systemctl daemon-reload
sudo systemctl enable --now netznoe-p1-reader.service
```

Der Dienst läuft als `netznoe-p1-reader`, erhält seriellen Zugriff über
`dialout`, startet beim Boot und wird nach Fehlern neu gestartet.

### 7. Betrieb prüfen

```console
systemctl status netznoe-p1-reader.service
journalctl -u netznoe-p1-reader.service -f
```

`Active: active (running)` zeigt einen laufenden Dienst. Im Normalbetrieb
meldet das Log den geöffneten seriellen Port, die MQTT-Verbindung und
entschlüsselte Messungen.

Im MQTT-Broker sollten folgende Daten erscheinen:

- `<topic-prefix>/availability`: retained Wert `online`
- `<topic-prefix>/state`: ungefähr alle fünf Sekunden ein JSON-Datensatz
- `<discovery-prefix>/sensor/...`: retained Home-Assistant-Konfiguration

Home Assistant legt daraus automatisch ein Gerät mit allen Sensoren an.

## Update

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

- **Adapter wird nicht angezeigt:** USB-Verbindung prüfen und mit
  `ls -l /dev/serial/by-id/` erneut suchen.
- **`cannot open or read`:** Gerätepfad, Gruppe und Ausgabe von
  `id netznoe-p1-reader` prüfen.
- **`0 bytes received`:** P1-Aktivierung, RJ12-Verkabelung und
  M-Bus-Pegelwandler prüfen.
- **Bytes, aber kein gültiger Frame:** Baudrate 2400, 8N1, Signalpegel und
  Verkabelung prüfen.
- **Entschlüsselung schlägt fehl:** GUEK auf exakt 32 Hex-Zeichen und Zuordnung
  zum richtigen Zähler prüfen.
- **Keine MQTT-Daten:** Brokeradresse, Zugangsdaten, ACLs und bei TLS Uhrzeit,
  Hostname und CA-Kette prüfen.
- **Keine Home-Assistant-Sensoren:** MQTT-Integration, Discovery-Präfix und
  Rechte für retained Discovery prüfen.

Echte Schlüssel oder Frames nicht in öffentliche Issues kopieren.

## Konfigurationsreferenz

Alle Variablen beginnen mit `NETZNOE_P1_`.

| Variable | Standard | Beschreibung |
| --- | --- | --- |
| `GUEK` | erforderlich | 32 Hex-Zeichen / 16 Byte |
| `SERIAL_PORT` | `/dev/ttyUSB0` | serieller M-Bus-Konverter |
| `SERIAL_BAUDRATE` | `2400` | Baudrate; 8N1 ist fest |
| `SERIAL_TIMEOUT_MS` | `1000` | Timeout für Teil-Frames |
| `MQTT_HOST` | `localhost` | Brokername oder Adresse |
| `MQTT_PORT` | `1883`, mit TLS `8883` | Brokerport |
| `MQTT_USERNAME` | leer | optionaler Benutzer |
| `MQTT_PASSWORD` | leer | optionales Passwort |
| `MQTT_TOPIC_PREFIX` | `netznoe/p1` | State/Availability-Basis |
| `DEVICE_ID` | Hostname-basiert | stabile, eindeutige ID |
| `DEVICE_NAME` | `Netz NÖ Smart Meter` | Anzeigename |
| `HA_DISCOVERY_PREFIX` | `homeassistant` | Discovery-Präfix |
| `MQTT_TLS` | `false` | TLS aktivieren |
| `MQTT_TLS_CA_CERT` | System-CAs | optionale private CA |
| `LOG_LEVEL` | `INFO` | Python-Loglevel |

TLS prüft Zertifikate immer; es gibt keinen unsicheren Modus.

## MQTT und Home Assistant

Der Dienst hält genau eine Paho-Verbindung mit eigener Network Loop und
automatischem Reconnect. Serielles Lesen wird von einem Broker-Ausfall nicht
blockiert; höchstens die neueste Messung bleibt zum Senden vorgemerkt.

- State: `<topic-prefix>/state`, QoS 1, nicht retained
- Availability: `<topic-prefix>/availability`, QoS 1, retained Last Will
- Discovery: `<discovery-prefix>/sensor/<device-id>/<sensor>/config`, QoS 1,
  retained
- Home-Assistant-Birth: `<discovery-prefix>/status`
- Sensor-Timeout: `expire_after` 30 Sekunden

Beispiel für eine State-Nachricht:

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

## Entwicklung

```console
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

Die Tests benötigen keine Hardware oder Netzwerkdienste. Sie prüfen Framing,
OBIS, Skalierung, MQTT und Discovery und entschlüsseln den öffentlichen
Netz-NÖ-Beispielrahmen. GitHub Actions führt die Prüfungen mit Python 3.11 bis
3.14 aus.

## Technische Details

### Protokoll und Robustheit

- wired M-Bus, 2400 Baud, 8N1, unidirektional
- M-Bus-Long-Frames `68 LL LL 68 ... checksum 16`
- DLMS/COSEM Security Suite 0 mit individuellem 16-Byte-GUEK
- Push-Intervall ungefähr fünf Sekunden
- Entschlüsselung und Fragmentzusammenführung mit `gurux-dlms`
- Interpretation anhand von OBIS statt fester XML-Positionen

Der Streaming-Framer verarbeitet fragmentierte Reads, mehrere Frames pro Read,
Datenmüll und beschädigte Frames. Er prüft Länge, Prüfsumme und Endbyte und
öffnet den Port nach Verbindungsfehlern mit exponentiellem Backoff erneut.

### Unterstützte OBIS-Werte

| JSON-Feld | OBIS | Einheit |
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

Zeitstempel und Zählernummer werden ebenfalls gelesen. Skalierer und Einheit
stammen aus dem COSEM-Datensatz. Fehlende oder unbekannte OBIS-Werte beenden
den Dienst nicht.

### Annahmen zum Kaifa-Frame

Der öffentliche Netz-NÖ-Beispielpush umfasst 282 Byte und besteht aus zwei
M-Bus-Long-Frames: `68 FA FA 68` mit 256 Byte und `68 14 14 68` mit 26 Byte.
Der zusammengesetzte PDU enthält einen 8-Byte-System-Title, Security Control
`0x20` für Security Suite 0, einen 32-Bit-Frame-Counter in Big-Endian und die
verschlüsselten Daten. Netz NÖ verwendet dabei keinen Authentication Key.

Diese Annahmen werden mit dem öffentlichen Beispiel getestet. Reale
Zählerstände, System Titles und Frame Counter sind nicht fest codiert.

## Quellen

- [Netz NÖ: Smart Meter Kundenschnittstelle P1, 6. Auflage, März 2026](https://netz-noe.at/getContentAsset/568bef9a-3bd1-4f2e-a710-6ba7e71cb746/0ee16eb8-9692-4f25-b8a4-d007b35915a4/218_20_SM_Kundenschnittstelle_WCAG.pdf?language=de)
- [Gurux DLMS Python](https://github.com/Gurux/Gurux.DLMS.Python)
- [Paho MQTT Python Client](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
- [Home Assistant MQTT](https://www.home-assistant.io/integrations/mqtt/)

## Lizenz

GPL-2.0-only, siehe [LICENSE](LICENSE).
