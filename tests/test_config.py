from __future__ import annotations

import pytest

from netznoe_p1_reader.config import AppConfig, ConfigError


def valid_env() -> dict[str, str]:
    return {
        "NETZNOE_P1_GUEK": "00112233445566778899aabbccddeeff",
        "NETZNOE_P1_DEVICE_ID": "meter_main",
    }


def test_key_is_validated_and_not_in_repr() -> None:
    config = AppConfig.from_env(valid_env())
    assert config.guek == bytes.fromhex("00112233445566778899aabbccddeeff")
    assert "001122" not in repr(config)


@pytest.mark.parametrize("key", ["", "00", "g" * 32, "00" * 17])
def test_rejects_invalid_key(key: str) -> None:
    env = valid_env()
    env["NETZNOE_P1_GUEK"] = key
    with pytest.raises(ConfigError, match="GUEK"):
        AppConfig.from_env(env)


def test_password_requires_username() -> None:
    env = valid_env() | {"NETZNOE_P1_MQTT_PASSWORD": "secret"}
    with pytest.raises(ConfigError, match="MQTT_USERNAME"):
        AppConfig.from_env(env)
