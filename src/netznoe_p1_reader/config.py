"""Environment based application configuration."""

from __future__ import annotations

import os
import re
import socket
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

PREFIX = "NETZNOE_P1_"
_DEVICE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ConfigError(ValueError):
    """Raised when environment configuration is invalid."""


def _value(env: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = env.get(PREFIX + name, default)
    if value is None or not value.strip():
        raise ConfigError(f"{PREFIX}{name} must be set")
    return value.strip()


def _integer(
    env: Mapping[str, str], name: str, default: int, *, minimum: int, maximum: int
) -> int:
    raw = env.get(PREFIX + name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{PREFIX}{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{PREFIX}{name} must be between {minimum} and {maximum}")
    return value


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(PREFIX + name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{PREFIX}{name} must be true or false")


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(PREFIX + name)
    return value.strip() if value and value.strip() else None


@dataclass(frozen=True, slots=True)
class SerialConfig:
    port: str
    baudrate: int = 2400
    timeout: float = 1.0
    reconnect_min_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class MqttConfig:
    host: str
    port: int
    username: str | None
    password: str | None = field(repr=False)
    topic_prefix: str = "netznoe/p1"
    discovery_prefix: str = "homeassistant"
    device_id: str = "netznoe_p1"
    device_name: str = "Netz NÖ Smart Meter"
    tls: bool = False
    tls_ca_cert: Path | None = None
    keepalive: int = 60

    @property
    def state_topic(self) -> str:
        return f"{self.topic_prefix}/state"

    @property
    def availability_topic(self) -> str:
        return f"{self.topic_prefix}/availability"


@dataclass(frozen=True, slots=True)
class AppConfig:
    serial: SerialConfig
    mqtt: MqttConfig
    guek: bytes = field(repr=False)
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AppConfig:
        source = os.environ if env is None else env
        key_hex = _value(source, "GUEK")
        if len(key_hex) != 32:
            raise ConfigError(f"{PREFIX}GUEK must contain exactly 32 hexadecimal characters")
        try:
            key = bytes.fromhex(key_hex)
        except ValueError as exc:
            raise ConfigError(f"{PREFIX}GUEK must contain only hexadecimal characters") from exc
        if len(key) != 16:
            raise ConfigError(f"{PREFIX}GUEK must decode to exactly 16 bytes")

        device_default = re.sub(r"[^a-z0-9_-]+", "_", socket.gethostname().lower())[:48]
        device_id = source.get(PREFIX + "DEVICE_ID", f"netznoe_p1_{device_default}").strip()
        if not _DEVICE_ID_RE.fullmatch(device_id):
            raise ConfigError(
                f"{PREFIX}DEVICE_ID must match {_DEVICE_ID_RE.pattern!r} "
                "and be at most 64 characters"
            )

        username = _optional(source, "MQTT_USERNAME")
        password = _optional(source, "MQTT_PASSWORD")
        if password is not None and username is None:
            raise ConfigError(f"{PREFIX}MQTT_USERNAME is required when MQTT_PASSWORD is set")

        tls = _boolean(source, "MQTT_TLS", False)
        ca_raw = _optional(source, "MQTT_TLS_CA_CERT")
        ca_cert = Path(ca_raw) if ca_raw else None
        if ca_cert is not None and not tls:
            raise ConfigError(f"{PREFIX}MQTT_TLS must be true when MQTT_TLS_CA_CERT is set")
        if ca_cert is not None and not ca_cert.is_file():
            raise ConfigError(f"{PREFIX}MQTT_TLS_CA_CERT does not point to a readable file")

        topic_prefix = _value(source, "MQTT_TOPIC_PREFIX", "netznoe/p1").strip("/")
        discovery_prefix = _value(source, "HA_DISCOVERY_PREFIX", "homeassistant").strip("/")
        if not topic_prefix or "+" in topic_prefix or "#" in topic_prefix:
            raise ConfigError(f"{PREFIX}MQTT_TOPIC_PREFIX must be a concrete MQTT topic")
        if not discovery_prefix or "+" in discovery_prefix or "#" in discovery_prefix:
            raise ConfigError(f"{PREFIX}HA_DISCOVERY_PREFIX must be a concrete MQTT topic")

        log_level = source.get(PREFIX + "LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError(f"{PREFIX}LOG_LEVEL is invalid")

        return cls(
            serial=SerialConfig(
                port=_value(source, "SERIAL_PORT", "/dev/ttyUSB0"),
                baudrate=_integer(source, "SERIAL_BAUDRATE", 2400, minimum=300, maximum=115200),
                timeout=_integer(source, "SERIAL_TIMEOUT_MS", 1000, minimum=100, maximum=10000)
                / 1000,
            ),
            mqtt=MqttConfig(
                host=_value(source, "MQTT_HOST", "localhost"),
                port=_integer(source, "MQTT_PORT", 8883 if tls else 1883, minimum=1, maximum=65535),
                username=username,
                password=password,
                topic_prefix=topic_prefix,
                discovery_prefix=discovery_prefix,
                device_id=device_id,
                device_name=_value(source, "DEVICE_NAME", "Netz NÖ Smart Meter"),
                tls=tls,
                tls_ca_cert=ca_cert,
                keepalive=_integer(source, "MQTT_KEEPALIVE", 60, minimum=10, maximum=3600),
            ),
            guek=key,
            log_level=log_level,
        )
