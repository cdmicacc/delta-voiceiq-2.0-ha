"""Tests for Delta VoiceIQ sensors."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from custom_components.delta_voiceiq.const import CONF_EXP_TIMESTAMP, CONF_MAC_ADDRESS, CONF_USER_ID
from custom_components.delta_voiceiq.sensor import StaticInfoSensor, TokenExpirySensor, UsageSensor


def _make_entry(exp_timestamp=None):
    entry = MagicMock()
    entry.data = {
        CONF_MAC_ADDRESS: "AABBCCDDEEFF",
        CONF_USER_ID: "u1",
        CONF_EXP_TIMESTAMP: exp_timestamp,
        "device_name": "Kitchen Faucet",
    }
    return entry


def test_usage_sensor_converts_gallons_to_liters():
    entry = _make_entry()
    coordinator = MagicMock()
    coordinator.data = 5.0  # gallons
    sensor = UsageSensor(entry, coordinator, "week")

    assert sensor.native_value == 18.93  # round(5.0 * 3.785411784, 2)
    assert sensor.unique_id == "AABBCCDDEEFF_usage_week"


def test_usage_sensor_returns_none_when_coordinator_has_no_data():
    entry = _make_entry()
    coordinator = MagicMock()
    coordinator.data = None
    sensor = UsageSensor(entry, coordinator, "today")

    assert sensor.native_value is None


def test_token_expiry_sensor_computes_days_remaining():
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    exp = int(now.timestamp()) + 10 * 86400  # 10 days from "now"
    entry = _make_entry(exp_timestamp=exp)

    with patch("homeassistant.util.dt.utcnow", return_value=now):
        sensor = TokenExpirySensor(entry)

    assert sensor.native_value == 10


def test_token_expiry_sensor_unknown_when_exp_missing():
    entry = _make_entry(exp_timestamp=None)
    sensor = TokenExpirySensor(entry)

    assert sensor.native_value is None


def test_static_info_sensor_is_diagnostic_by_default():
    entry = _make_entry()
    sensor = StaticInfoSensor(entry, "MAC Address", "mac_address_info", "AABBCCDDEEFF")

    assert sensor.native_value == "AABBCCDDEEFF"
    assert sensor.entity_category == "diagnostic"
    assert sensor.unique_id == "AABBCCDDEEFF_mac_address_info"
