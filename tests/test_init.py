"""Tests for delta_voiceiq/__init__.py entry setup."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.helpers import issue_registry as ir

from custom_components.delta_voiceiq import _async_check_token_expiry
from custom_components.delta_voiceiq.api import DeltaVoiceIQClient
from custom_components.delta_voiceiq.const import (
    CONF_ACCESS_TOKEN,
    CONF_EXP_TIMESTAMP,
    CONF_MAC_ADDRESS,
    CONF_USER_ID,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_setup_entry_creates_client_and_four_coordinators(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "tok123",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            CONF_USER_ID: "u1",
            CONF_EXP_TIMESTAMP: 9999999999,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)

    with patch.object(DeltaVoiceIQClient, "get_usage", AsyncMock(return_value=1.0)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_data = entry.runtime_data
    assert runtime_data.client.access_token == "tok123"
    assert set(runtime_data.coordinators.keys()) == {"today", "week", "month", "year"}
    for coordinator in runtime_data.coordinators.values():
        assert coordinator.data == 1.0


@pytest.mark.asyncio
async def test_unload_entry_succeeds(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "tok123",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            CONF_USER_ID: "u1",
            CONF_EXP_TIMESTAMP: 9999999999,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)

    with patch.object(DeltaVoiceIQClient, "get_usage", AsyncMock(return_value=1.0)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


def _entry_with_exp(hass, exp_timestamp):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "tok123",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            CONF_USER_ID: "u1",
            CONF_EXP_TIMESTAMP: exp_timestamp,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_check_token_expiry_creates_unparseable_issue_when_exp_is_none(hass):
    entry = _entry_with_exp(hass, None)

    _async_check_token_expiry(hass, entry)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_exp_unparseable")
    assert issue is not None


@pytest.mark.asyncio
async def test_check_token_expiry_no_issue_when_far_from_expiry(hass):
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    exp = int(now.timestamp()) + 30 * 86400
    entry = _entry_with_exp(hass, exp)

    with patch("custom_components.delta_voiceiq.dt_util.utcnow", return_value=now):
        _async_check_token_expiry(hass, entry)

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_expiring_soon") is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_exp_unparseable") is None


@pytest.mark.asyncio
async def test_check_token_expiry_creates_expiring_soon_issue_under_threshold(hass):
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    exp = int(now.timestamp()) + 3 * 86400  # 3 days left, under the 7-day threshold
    entry = _entry_with_exp(hass, exp)

    with patch("custom_components.delta_voiceiq.dt_util.utcnow", return_value=now):
        _async_check_token_expiry(hass, entry)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_expiring_soon")
    assert issue is not None


@pytest.mark.asyncio
async def test_check_token_expiry_clears_issue_once_resolved(hass):
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    soon = int(now.timestamp()) + 3 * 86400
    entry = _entry_with_exp(hass, soon)

    with patch("custom_components.delta_voiceiq.dt_util.utcnow", return_value=now):
        _async_check_token_expiry(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_expiring_soon") is not None

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_EXP_TIMESTAMP: int(now.timestamp()) + 30 * 86400}
    )
    with patch("custom_components.delta_voiceiq.dt_util.utcnow", return_value=now):
        _async_check_token_expiry(hass, entry)

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_expiring_soon") is None
