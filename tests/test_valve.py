"""Tests for the DeltaFaucetValve entity."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.delta_voiceiq.api import AuthExpired, CannotConnect
from custom_components.delta_voiceiq.const import CONF_DEVICE_NAME, CONF_MAC_ADDRESS
from custom_components.delta_voiceiq.valve import DeltaFaucetValve


def _make_entry(client):
    entry = MagicMock()
    entry.data = {CONF_MAC_ADDRESS: "AABBCCDDEEFF", CONF_DEVICE_NAME: "Kitchen Faucet"}
    entry.runtime_data.client = client
    entry.async_start_reauth = MagicMock()
    return entry


@pytest.mark.asyncio
async def test_open_valve_calls_toggle_water_and_updates_state():
    client = AsyncMock()
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()
    valve.async_write_ha_state = MagicMock()

    await valve.async_open_valve()

    client.toggle_water.assert_awaited_once_with("AABBCCDDEEFF", on=True)
    assert valve.is_closed is False


@pytest.mark.asyncio
async def test_close_valve_calls_toggle_water_and_updates_state():
    client = AsyncMock()
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()
    valve.async_write_ha_state = MagicMock()

    await valve.async_close_valve()

    client.toggle_water.assert_awaited_once_with("AABBCCDDEEFF", on=False)
    assert valve.is_closed is True


@pytest.mark.asyncio
async def test_auth_expired_starts_reauth_and_raises():
    client = AsyncMock()
    client.toggle_water.side_effect = AuthExpired("nope")
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()

    with pytest.raises(HomeAssistantError):
        await valve.async_open_valve()

    entry.async_start_reauth.assert_called_once_with(valve.hass)


@pytest.mark.asyncio
async def test_cannot_connect_raises_home_assistant_error():
    client = AsyncMock()
    client.toggle_water.side_effect = CannotConnect("down")
    entry = _make_entry(client)
    valve = DeltaFaucetValve(entry)
    valve.hass = MagicMock()

    with pytest.raises(HomeAssistantError):
        await valve.async_close_valve()
