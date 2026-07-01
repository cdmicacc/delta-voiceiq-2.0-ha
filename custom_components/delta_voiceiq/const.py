"""Constants for the Delta VoiceIQ integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "delta_voiceiq"

LOGIN_PROVIDERS = ("apple", "google", "amazon")

CONF_ACCESS_TOKEN = "access_token"
CONF_MAC_ADDRESS = "mac_address"
CONF_USER_ID = "user_id"
CONF_EXP_TIMESTAMP = "exp_timestamp"
CONF_DEVICE_NAME = "device_name"

USAGE_INTERVALS: dict[str, int] = {
    "today": 0,
    "week": 1,
    "month": 2,
    "year": 3,
}

SCAN_INTERVALS: dict[str, timedelta] = {
    "today": timedelta(minutes=10),
    "week": timedelta(hours=1),
    "month": timedelta(hours=5),
    "year": timedelta(hours=24),
}

TOKEN_EXPIRY_WARNING_DAYS = 7

LITERS_PER_GALLON = 3.785411784
