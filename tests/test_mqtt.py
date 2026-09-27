from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from netznoe_p1_reader.config import MqttConfig
from netznoe_p1_reader.models import Measurement
from netznoe_p1_reader.mqtt import MqttPublisher, discovery_messages


class PublishInfo:
    rc = 0

    def wait_for_publish(self, timeout: float) -> None:
        del timeout


class FakeClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, int, bool]] = []
        self.subscriptions: list[tuple[str, int]] = []
        self.on_connect: Any = None
        self.on_disconnect: Any = None
        self.on_message: Any = None

    def reconnect_delay_set(self, **_kwargs: Any) -> None: pass
    def max_queued_messages_set(self, _count: int) -> None: pass
    def will_set(self, *_args: Any, **_kwargs: Any) -> None: pass
    def username_pw_set(self, *_args: Any) -> None: pass
    def connect_async(self, *_args: Any, **_kwargs: Any) -> None: pass
    def loop_start(self) -> None: pass
    def loop_stop(self) -> None: pass
    def disconnect(self) -> None: pass

    def subscribe(self, topic: str, qos: int) -> None:
        self.subscriptions.append((topic, qos))

    def publish(self, topic: str, payload: str, qos: int, retain: bool) -> PublishInfo:
        self.published.append((topic, payload, qos, retain))
        return PublishInfo()


def config() -> MqttConfig:
    return MqttConfig("broker", 1883, None, None, device_id="meter_main")


def test_discovery_uses_one_device_and_correct_energy_metadata() -> None:
    messages = dict(discovery_messages(config()))
    topic = "homeassistant/sensor/meter_main/energy_import_wh/config"
    payload = json.loads(messages[topic])
    assert payload["unique_id"] == "meter_main_energy_import_wh"
    assert payload["name"] == "Energy import"
    assert payload["device"]["identifiers"] == ["meter_main"]
    assert payload["device_class"] == "energy"
    assert payload["state_class"] == "total_increasing"
    assert payload["unit_of_measurement"] == "Wh"
    assert payload["expire_after"] == 30


def test_connect_and_birth_publish_retained_discovery() -> None:
    client = FakeClient()
    publisher = MqttPublisher(config(), client=client)
    publisher._on_connect(client, None, None, 0, None)
    discovery_count = len(discovery_messages(config()))
    retained = [item for item in client.published if item[3]]
    assert len(retained) == discovery_count + 1  # discovery plus availability
    assert client.subscriptions == [("homeassistant/status", 1)]

    message = type("Message", (), {"topic": "homeassistant/status", "payload": b"online"})()
    publisher._on_message(client, None, message)
    assert len(client.published) == 2 * discovery_count + 1


def test_pending_state_is_bounded_to_latest_value() -> None:
    client = FakeClient()
    publisher = MqttPublisher(replace(config(), topic_prefix="meter"), client=client)
    publisher.submit(Measurement(power_import_w=1))
    publisher.submit(Measurement(power_import_w=2))
    assert publisher._pending is not None
    assert publisher._pending.power_import_w == 2
