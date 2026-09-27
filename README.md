# netznoe-p1-reader

`netznoe-p1-reader` ist ein kleiner, dauerhaft laufender Python-Dienst für den
Raspberry Pi. Er liest die verschlüsselte P1-Kundenschnittstelle eines
Netz-NÖ-Smart-Meters über einen wired-M-Bus-zu-USB-Konverter, entschlüsselt die
DLMS/COSEM-Push-Nachrichten mit dem individuellen GUEK und veröffentlicht pro
Push eine gemeinsame JSON-Nachricht über MQTT. Home Assistant MQTT Discovery
ist integriert.

Der erste Release ist bewusst auf den Kaifa MA309 von Netz NÖ fokussiert. Es
gibt keine Weboberfläche und der Dienst schreibt nicht zum Zähler.

## Protokoll und Datenfluss

- wired M-Bus, 2400 Baud, 8N1, unidirektional
- M-Bus-Long-Frames `68 LL LL 68 ... checksum 16`
- DLMS/COSEM Security Suite 0 mit einem individuellen 16-Byte-GUEK
- Push-Intervall ungefähr fünf Sekunden
- Entschlüsselung und Fragmentzusammenführung mit `gurux-dlms`
- Interpretation ausschließlich anhand der OBIS-Kennzahlen
- Skalierer und Einheit werden aus jedem COSEM-Datensatz gelesen

Der Streaming-Framer verwendet keine feste Paketgröße. Er verarbeitet
fragmentierte Reads, mehrere Frames in einem Read und Datenmüll, prüft beide
Längenbytes, Prüfsumme und Endbyte und synchronisiert sich nach beschädigten
Frames neu. Ein serieller Timeout verwirft unvollständige Kandidaten. Nach
Verbindungsfehlern wird der Port mit exponentiellem Backoff erneut geöffnet.

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

Zeitstempel und Zählernummer werden ebenfalls ausgegeben. Fehlende und
unbekannte OBIS-Werte beenden den Dienst nicht; fehlende bekannte Werte stehen
im JSON auf `null`.

## Installation auf dem Raspberry Pi

Voraussetzungen sind Python 3.11 oder neuer, ein M-Bus-Konverter und ein nicht
als root laufendes Dienstkonto. Die folgenden Befehle sind ein Beispiel und
werden von diesem Repository nicht automatisch ausgeführt. Der Quellcode wird
dabei nach `/opt/netznoe-p1-reader/src` geklont und gehört dem Dienstkonto:

```console
sudo useradd --system --home /opt/netznoe-p1-reader --shell /usr/sbin/nologin netznoe-p1-reader
sudo usermod -aG dialout netznoe-p1-reader
sudo mkdir -p /opt/netznoe-p1-reader
sudo chown netznoe-p1-reader:netznoe-p1-reader /opt/netznoe-p1-reader
sudo -u netznoe-p1-reader git clone https://github.com/Zuwizara/netznoe-p1-reader.git /opt/netznoe-p1-reader/src
sudo -u netznoe-p1-reader python3 -m venv /opt/netznoe-p1-reader/.venv
sudo -u netznoe-p1-reader /opt/netznoe-p1-reader/.venv/bin/pip install /opt/netznoe-p1-reader/src
```

Je nach Distribution heißt die Gruppe für `/dev/ttyUSB0` oder `/dev/ttyAMA0`
anders. Mit `stat -c '%G' /dev/ttyUSB0` lässt sie sich prüfen. Nach einer
Gruppenänderung ist eine neue Sitzung beziehungsweise ein Dienstneustart nötig.

### Konfiguration

Alle Variablen beginnen mit `NETZNOE_P1_`. `.env.example` enthält sichere
Platzhalter. Der echte GUEK darf weder committed noch in Tickets oder Logs
kopiert werden.

```console
sudo install -o root -g netznoe-p1-reader -m 0640 .env.example /etc/netznoe-p1-reader.env
sudoedit /etc/netznoe-p1-reader.env
```

| Variable | Standard | Beschreibung |
| --- | --- | --- |
| `NETZNOE_P1_GUEK` | erforderlich | exakt 32 Hex-Zeichen / 16 Byte |
| `NETZNOE_P1_SERIAL_PORT` | `/dev/ttyUSB0` | serieller M-Bus-Konverter |
| `NETZNOE_P1_SERIAL_BAUDRATE` | `2400` | Baudrate; 8N1 ist fest |
| `NETZNOE_P1_SERIAL_TIMEOUT_MS` | `1000` | Timeout für Teil-Frames |
| `NETZNOE_P1_MQTT_HOST` | `localhost` | Brokername oder Adresse |
| `NETZNOE_P1_MQTT_PORT` | `1883`, mit TLS `8883` | Brokerport |
| `NETZNOE_P1_MQTT_USERNAME` | leer | optionaler Benutzer |
| `NETZNOE_P1_MQTT_PASSWORD` | leer | optionales Passwort |
| `NETZNOE_P1_MQTT_TOPIC_PREFIX` | `netznoe/p1` | State/Availability-Basis |
| `NETZNOE_P1_DEVICE_ID` | Hostname-basiert | stabile, eindeutige ID |
| `NETZNOE_P1_HA_DISCOVERY_PREFIX` | `homeassistant` | Discovery-Präfix |
| `NETZNOE_P1_MQTT_TLS` | `false` | TLS aktivieren |
| `NETZNOE_P1_MQTT_TLS_CA_CERT` | System-CAs | optionale private CA |

Für reproduzierbare Home-Assistant-IDs sollte `DEVICE_ID` explizit gesetzt und
später nicht mehr geändert werden. Eine IP-Adresse ist dafür ungeeignet.
`netznoe-p1-reader --check-config` validiert die Konfiguration, ohne seriellen
Port oder Netzwerk zu öffnen. Konfigurationsobjekte blenden GUEK und Passwort
in ihrer Darstellung aus; vollständige Frames werden nicht geloggt.

TLS prüft Zertifikate immer. Es gibt keine Option, die Zertifikatsprüfung
unsicher abzuschalten.

## systemd

Die Vorlage liegt unter `contrib/netznoe-p1-reader.service`. Pfade und Benutzer
gegebenenfalls anpassen:

```console
sudo install -o root -g root -m 0644 contrib/netznoe-p1-reader.service \
  /etc/systemd/system/netznoe-p1-reader.service
sudo systemctl daemon-reload
sudo systemctl enable --now netznoe-p1-reader.service
systemctl status netznoe-p1-reader.service
journalctl -u netznoe-p1-reader.service -f
```

Der Dienst läuft als `netznoe-p1-reader`, erhält ergänzend `dialout` und benötigt
keine Root-Rechte.

### Update

```console
sudo -u netznoe-p1-reader git -C /opt/netznoe-p1-reader/src pull --ff-only
sudo systemctl stop netznoe-p1-reader.service
sudo -u netznoe-p1-reader /opt/netznoe-p1-reader/.venv/bin/pip install --upgrade /opt/netznoe-p1-reader/src
sudo systemctl start netznoe-p1-reader.service
```

## MQTT und Home Assistant

Es existiert genau eine dauerhafte Paho-MQTT-Verbindung mit eigener Network
Loop und automatischem Reconnect. Serielles Lesen und MQTT sind entkoppelt.
Während eines Broker-Ausfalls bleibt höchstens die neueste Messung im
Anwendungsspeicher; auch die interne Paho-Warteschlange ist begrenzt.

- State: `<topic-prefix>/state`, QoS 1, nicht retained
- Availability: `<topic-prefix>/availability`, QoS 1, retained Last Will
- Discovery: `<discovery-prefix>/sensor/<device-id>/<sensor>/config`, QoS 1,
  retained
- Birth Topic: `<discovery-prefix>/status`; bei `online` wird Discovery erneut
  veröffentlicht
- `expire_after`: 30 Sekunden

Alle Sensoren gehören zu einem gemeinsamen Gerät. Energie verwendet
`total_increasing`, momentane Größen `measurement`. Beispiel:

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

## Entwicklung und Tests

```console
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src
```

Die Tests benötigen weder seriellen Adapter noch Broker oder Home Assistant.
MQTT wird gemockt. Der öffentliche Beispielrahmen samt Beispielschlüssel aus
der Netz-NÖ-Dokumentation dient als Integrationsfixture; er enthält keine
persönlichen Kundendaten.

## Annahmen zum Kaifa-MA309-Frameformat

Die aktuelle Netz-NÖ-Dokumentation zeigt einen 282 Byte langen Push. Er besteht
aus zwei M-Bus-Long-Frames: zuerst `68 FA FA 68` (256 Byte insgesamt), danach
`68 14 14 68` (26 Byte). Im zusammengesetzten DLMS-PDU folgen auf den
8-Byte-System-Title ein Security-Control-Byte (`0x20`, Verschlüsselung, Suite
0), der 32-Bit-Frame-Counter in Big-Endian-Reihenfolge und die verschlüsselten
Daten. Netz NÖ nennt ausdrücklich keinen Authentication Key. Fragmentierung
und AES-GCM-Verarbeitung übernimmt Gurux; davor validiert der Reader jeden
M-Bus-Frame selbst.

Diese Annahmen sind mit dem offiziellen Beispiel getestet. Ein realer Zähler
kann andere Zählerstände, System Titles und Frame Counter liefern. Die
Auswertung hängt nicht an festen XML-Positionen, sondern an OBIS.

## Troubleshooting

- **Permission denied am seriellen Port:** Geräte-Gruppe prüfen und den
  Dienstbenutzer zur passenden Gruppe (`dialout`) hinzufügen.
- **Keine Frames:** Verkabelung/Polarität, M-Bus-Pegelwandler, Port und 2400
  Baud 8N1 prüfen. Ein USB-UART-Kabel ersetzt keinen M-Bus-Pegelwandler.
- **Checksum-/Endbyte-Warnungen:** meist Verkabelungs-, Pegel- oder
  Baudratenproblem. Der Reader synchronisiert sich automatisch neu.
- **DLMS kann nicht entschlüsseln:** GUEK muss zum Zähler gehören und exakt 32
  Hex-Zeichen lang sein. Schlüssel nicht in Logs posten.
- **Keine MQTT-Daten:** Adresse, Zugangsdaten, ACLs und bei TLS Uhrzeit,
  Hostname sowie CA-Kette prüfen.
- **Home Assistant findet nichts:** MQTT-Integration, Discovery-Präfix, ACLs
  für retained Discovery und `homeassistant/status` prüfen.

## Quellen

- [Netz NÖ: Smart Meter Kundenschnittstelle P1, 6. Auflage, März 2026](https://netz-noe.at/getContentAsset/568bef9a-3bd1-4f2e-a710-6ba7e71cb746/0ee16eb8-9692-4f25-b8a4-d007b35915a4/218_20_SM_Kundenschnittstelle_WCAG.pdf?language=de)
- [Gurux DLMS Python](https://github.com/Gurux/Gurux.DLMS.Python)
- [Paho MQTT Python Client](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
- [Home Assistant MQTT](https://www.home-assistant.io/integrations/mqtt/)

## Lizenz

GPL-2.0-only, siehe `LICENSE`.
