"""Tests for delta_voiceiq/__init__.py entry setup."""
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
