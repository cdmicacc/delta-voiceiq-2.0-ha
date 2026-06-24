"""Tests for DeltaUsageCoordinator."""
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.delta_voiceiq.api import AuthExpired, CannotConnect
from custom_components.delta_voiceiq.coordinator import DeltaUsageCoordinator


@pytest.mark.asyncio
async def test_coordinator_fetches_usage_for_its_interval(hass):
    client = AsyncMock()
    client.get_usage.return_value = 12.5
    coordinator = DeltaUsageCoordinator(hass, client, "AABBCCDDEEFF", "week")

    data = await coordinator._async_update_data()

    assert data == 12.5
    client.get_usage.assert_awaited_once_with("AABBCCDDEEFF", 1)  # 1 == USAGE_INTERVALS["week"]


@pytest.mark.asyncio
async def test_coordinator_raises_config_entry_auth_failed_on_401(hass):
    client = AsyncMock()
    client.get_usage.side_effect = AuthExpired("nope")
    coordinator = DeltaUsageCoordinator(hass, client, "AABBCCDDEEFF", "today")

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_raises_update_failed_on_other_errors(hass):
    client = AsyncMock()
    client.get_usage.side_effect = CannotConnect("network down")
    coordinator = DeltaUsageCoordinator(hass, client, "AABBCCDDEEFF", "month")

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
