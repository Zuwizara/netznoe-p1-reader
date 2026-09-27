"""Non-blocking MQTT publishing and Home Assistant discovery."""

from __future__ import annotations

import json
import logging
import ssl
import threading
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion

from .config import MqttConfig
from .models import Measurement

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SensorDefinition:
    key: str
    name: str
    device_class: str | None = None
    state_class: str | None = None
    unit: str | None = None


SENSORS = (
    SensorDefinition("timestamp", "Zeitstempel", "timestamp"),
    SensorDefinition("energy_import_wh", "Wirkenergie Bezug", "energy", "total_increasing", "Wh"),
    SensorDefinition(
        "energy_export_wh", "Wirkenergie Einspeisung", "energy", "total_increasing", "Wh"
    ),
    SensorDefinition("power_import_w", "Momentanleistung Bezug", "power", "measurement", "W"),
    SensorDefinition("power_export_w", "Momentanleistung Einspeisung", "power", "measurement", "W"),
    SensorDefinition("voltage_l1_v", "Spannung L1", "voltage", "measurement", "V"),
    SensorDefinition("voltage_l2_v", "Spannung L2", "voltage", "measurement", "V"),
    SensorDefinition("voltage_l3_v", "Spannung L3", "voltage", "measurement", "V"),
    SensorDefinition("current_l1_a", "Strom L1", "current", "measurement", "A"),
    SensorDefinition("current_l2_a", "Strom L2", "current", "measurement", "A"),
    SensorDefinition("current_l3_a", "Strom L3", "current", "measurement", "A"),
    SensorDefinition("power_factor", "Leistungsfaktor", "power_factor", "measurement"),
    SensorDefinition("meter_number", "Zählernummer"),
)


def discovery_messages(config: MqttConfig) -> list[tuple[str, str]]:
    device = {
        "identifiers": [config.device_id],
        "name": config.device_name,
        "manufacturer": "Kaifa",
        "model": "MA309",
    }
    messages: list[tuple[str, str]] = []
    for sensor in SENSORS:
        payload: dict[str, Any] = {
            "name": sensor.name,
            "unique_id": f"{config.device_id}_{sensor.key}",
            "state_topic": config.state_topic,
            "availability_topic": config.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "value_template": f"{{{{ value_json.{sensor.key} }}}}",
            "expire_after": 30,
            "device": device,
        }
        if sensor.device_class:
            payload["device_class"] = sensor.device_class
        if sensor.state_class:
            payload["state_class"] = sensor.state_class
        if sensor.unit:
            payload["unit_of_measurement"] = sensor.unit
        topic = f"{config.discovery_prefix}/sensor/{config.device_id}/{sensor.key}/config"
        messages.append((topic, json.dumps(payload, separators=(",", ":"), ensure_ascii=False)))
    return messages


class MqttPublisher:
    """Own one Paho client and retain at most the newest pending measurement."""

    def __init__(self, config: MqttConfig, *, client: Any | None = None) -> None:
        self._config = config
        self._client = client or mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"{config.device_id}_reader",
            protocol=MQTTProtocolVersion.MQTTv311,
            reconnect_on_failure=True,
        )
        self._condition = threading.Condition()
        self._connected = False
        self._pending: Measurement | None = None
        self._stopping = False
        self._worker = threading.Thread(
            target=self._publish_worker, name="mqtt-publisher", daemon=True
        )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.max_queued_messages_set(100)
        self._client.will_set(config.availability_topic, "offline", qos=1, retain=True)
        if config.username is not None:
            self._client.username_pw_set(config.username, config.password)
        if config.tls:
            self._client.tls_set(
                ca_certs=str(config.tls_ca_cert) if config.tls_ca_cert else None,
                cert_reqs=ssl.CERT_REQUIRED,
            )
            self._client.tls_insecure_set(False)

    def start(self) -> None:
        self._worker.start()
        self._client.connect_async(
            self._config.host,
            self._config.port,
            keepalive=self._config.keepalive,
        )
        self._client.loop_start()

    def submit(self, measurement: Measurement) -> None:
        with self._condition:
            self._pending = measurement
            self._condition.notify()

    def stop(self) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
        self._worker.join(timeout=2)
        if self._connected:
            info = self._client.publish(
                self._config.availability_topic, "offline", qos=1, retain=True
            )
            try:
                info.wait_for_publish(timeout=2)
            except (RuntimeError, ValueError):
                LOGGER.debug("Could not confirm final MQTT availability publish")
        self._client.disconnect()
        self._client.loop_stop()

    def _publish_worker(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stopping or (self._connected and self._pending is not None)
                )
                if self._stopping:
                    return
                measurement = self._pending
                self._pending = None
            if measurement is None:
                continue
            payload = json.dumps(
                measurement.as_payload(), separators=(",", ":"), ensure_ascii=False
            )
            info = self._client.publish(self._config.state_topic, payload, qos=1, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                LOGGER.warning("MQTT state publish failed with code %s", info.rc)

    def _publish_discovery(self) -> None:
        for topic, payload in discovery_messages(self._config):
            info = self._client.publish(topic, payload, qos=1, retain=True)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                LOGGER.warning("MQTT discovery publish failed for %s with code %s", topic, info.rc)

    def _on_connect(
        self,
        client: Any,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        if getattr(reason_code, "is_failure", reason_code != 0):
            LOGGER.error("MQTT connection rejected: %s", reason_code)
            return
        LOGGER.info("Connected to MQTT broker")
        with self._condition:
            self._connected = True
            self._condition.notify()
        client.subscribe(f"{self._config.discovery_prefix}/status", qos=1)
        self._publish_discovery()
        client.publish(self._config.availability_topic, "online", qos=1, retain=True)

    def _on_disconnect(
        self,
        _client: Any,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        with self._condition:
            self._connected = False
        if reason_code != 0 and not self._stopping:
            LOGGER.warning("MQTT disconnected (%s); Paho will reconnect", reason_code)

    def _on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        if (
            message.topic == f"{self._config.discovery_prefix}/status"
            and message.payload.strip().lower() == b"online"
        ):
            LOGGER.info("Home Assistant birth message received; republishing discovery")
            self._publish_discovery()
