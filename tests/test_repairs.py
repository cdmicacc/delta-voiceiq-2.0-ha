"""Tests for the expiring-token Repair fix flow."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_voiceiq.api import ExchangeResult, InvalidCode
from custom_components.delta_voiceiq.const import (
    CONF_ACCESS_TOKEN,
    CONF_EXP_TIMESTAMP,
    CONF_MAC_ADDRESS,
    CONF_USER_ID,
    DOMAIN,
)
from custom_components.delta_voiceiq.repairs import async_create_fix_flow

NEW_EXP = int(datetime(2026, 9, 30, tzinfo=timezone.utc).timestamp())


def _entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "old_token",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            CONF_USER_ID: "u1",
            CONF_EXP_TIMESTAMP: 1000,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _flow(hass, entry):
    flow = await async_create_fix_flow(
        hass, f"{entry.entry_id}_expiring_soon", {"entry_id": entry.entry_id}
    )
    flow.hass = hass
    return flow


def _exchange_ok():
    return AsyncMock(
        return_value=ExchangeResult(
            access_token="fresh_token", user_id="u1", exp_timestamp=NEW_EXP, devices=[]
        )
    )


@pytest.mark.asyncio
async def test_home_assistant_can_discover_and_start_the_fix_flow(hass):
    """Drive the real repairs flow manager, not our class directly.

    This is what proves the Fix button works: it exercises platform discovery,
    RepairsProtocol conformance and the issue's is_fixable flag together. Testing
    only TokenExpiryRepairFlow in isolation would pass even if Home Assistant
    could never reach it.
    """
    assert await async_setup_component(hass, "repairs", {})
    entry = _entry(hass)
    with patch(
        "custom_components.delta_voiceiq.api.DeltaVoiceIQClient.get_usage",
        AsyncMock(return_value=1.0),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    issue_id = f"{entry.entry_id}_expiring_soon"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="expiring_soon",
        translation_placeholders={"days": "7"},
        data={"entry_id": entry.entry_id},
    )

    result = await hass.data["repairs"]["flow_manager"].async_init(
        DOMAIN, data={"issue_id": issue_id}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "provider"


@pytest.mark.asyncio
async def test_completed_fix_puts_the_new_token_into_the_running_client(hass):
    """Updating entry data is not enough -- the entry must reload.

    The live DeltaVoiceIQClient captures the token at setup, so without a reload
    the Repair would close successfully while the integration kept polling with
    the old, about-to-expire token.
    """
    entry = _entry(hass)
    with patch(
        "custom_components.delta_voiceiq.api.DeltaVoiceIQClient.get_usage",
        AsyncMock(return_value=1.0),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.client.access_token == "old_token"

        flow = await _flow(hass, entry)
        await flow.async_step_init()
        await flow.async_step_provider({"provider": "google"})
        with patch(
            "custom_components.delta_voiceiq.repairs.DeltaVoiceIQClient.exchange_code",
            _exchange_ok(),
        ):
            await flow.async_step_code({"code": "delta.code.abc123"})
        await hass.async_block_till_done()

        assert entry.runtime_data.client.access_token == "fresh_token"


@pytest.mark.asyncio
async def test_fix_flow_asks_for_provider_then_code(hass):
    """The flow collects the sign-in provider before asking for the code."""
    flow = await _flow(hass, _entry(hass))

    result = await flow.async_step_init()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "provider"

    result = await flow.async_step_provider({"provider": "google"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "code"
    # The sign-in link must be built for the provider the user actually picked.
    assert "provider=google" in result["description_placeholders"]["login_url"]


@pytest.mark.asyncio
async def test_fix_flow_stores_refreshed_token_on_valid_code(hass):
    """A valid code replaces the stored token and expiry on the existing entry."""
    entry = _entry(hass)
    flow = await _flow(hass, entry)
    await flow.async_step_init()
    await flow.async_step_provider({"provider": "google"})

    with patch(
        "custom_components.delta_voiceiq.repairs.DeltaVoiceIQClient.exchange_code",
        _exchange_ok(),
    ):
        result = await flow.async_step_code({"code": "delta.code.abc123"})
        await hass.async_block_till_done()

    # A non-ABORT result is what makes Home Assistant clear the Repair.
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_ACCESS_TOKEN] == "fresh_token"
    assert entry.data[CONF_EXP_TIMESTAMP] == NEW_EXP
    # Unrelated entry data must survive the refresh.
    assert entry.data[CONF_MAC_ADDRESS] == "AABBCCDDEEFF"


@pytest.mark.asyncio
async def test_fix_flow_reports_a_rejected_code_without_touching_the_entry(hass):
    """A bad code re-shows the form with an error and leaves the token alone."""
    entry = _entry(hass)
    flow = await _flow(hass, entry)
    await flow.async_step_init()
    await flow.async_step_provider({"provider": "google"})

    with patch(
        "custom_components.delta_voiceiq.repairs.DeltaVoiceIQClient.exchange_code",
        AsyncMock(side_effect=InvalidCode("nope")),
    ):
        result = await flow.async_step_code({"code": "delta.code.stale"})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "code"
    assert result["errors"] == {"base": "invalid_code"}
    assert entry.data[CONF_ACCESS_TOKEN] == "old_token"
    assert entry.data[CONF_EXP_TIMESTAMP] == 1000


@pytest.mark.asyncio
async def test_fix_flow_accepts_a_full_redirect_url(hass):
    """Users paste the whole justaddwater:// URL; the code is extracted from it."""
    entry = _entry(hass)
    flow = await _flow(hass, entry)
    await flow.async_step_init()
    await flow.async_step_provider({"provider": "google"})

    exchange = _exchange_ok()
    with patch(
        "custom_components.delta_voiceiq.repairs.DeltaVoiceIQClient.exchange_code",
        exchange,
    ):
        await flow.async_step_code({"code": "justaddwater://?code=delta.code.abc123"})
        await hass.async_block_till_done()

    exchange.assert_awaited_once_with("delta.code.abc123")
    assert entry.data[CONF_ACCESS_TOKEN] == "fresh_token"
