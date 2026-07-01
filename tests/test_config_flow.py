"""Tests for the Delta VoiceIQ config flow."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_voiceiq.api import (
    CannotConnect,
    DeltaDevice,
    ExchangeResult,
    InvalidCode,
)
from custom_components.delta_voiceiq.const import (
    CONF_ACCESS_TOKEN,
    CONF_MAC_ADDRESS,
    DOMAIN,
)

ONE_DEVICE = ExchangeResult(
    access_token="tok123",
    user_id="u1",
    exp_timestamp=9999999999,
    devices=[DeltaDevice(mac_address="AABBCCDDEEFF", name="Kitchen Faucet")],
)

TWO_DEVICES = ExchangeResult(
    access_token="tok123",
    user_id="u1",
    exp_timestamp=9999999999,
    devices=[
        DeltaDevice(mac_address="AABBCCDDEEFF", name="Kitchen Faucet"),
        DeltaDevice(mac_address="112233445566", name="Bathroom Faucet"),
    ],
)


@pytest.mark.asyncio
async def test_happy_path_single_device(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )
    assert result["step_id"] == "code"

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(return_value=ONE_DEVICE)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "delta.code.ABC123"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC_ADDRESS] == "AABBCCDDEEFF"
    assert result["data"][CONF_ACCESS_TOKEN] == "tok123"


@pytest.mark.asyncio
async def test_multi_device_shows_picker_then_creates_chosen_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(return_value=TWO_DEVICES)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "delta.code.ABC123"}
        )

    assert result["step_id"] == "device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"mac_address": "112233445566"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC_ADDRESS] == "112233445566"


@pytest.mark.asyncio
async def test_invalid_code_shows_error_and_keeps_user_on_code_step(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(side_effect=InvalidCode("bad"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "garbage"}
        )

    assert result["step_id"] == "code"
    assert result["errors"] == {"base": "invalid_code"}


@pytest.mark.asyncio
async def test_cannot_connect_shows_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(side_effect=CannotConnect("down"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "delta.code.ABC123"}
        )

    assert result["step_id"] == "code"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_reauth_flow_updates_existing_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AABBCCDDEEFF",
        data={
            CONF_ACCESS_TOKEN: "old-token",
            CONF_MAC_ADDRESS: "AABBCCDDEEFF",
            "user_id": "u1",
            "exp_timestamp": 1,
            "device_name": "Kitchen Faucet",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"provider": "apple"}
    )
    assert result["step_id"] == "code"

    with patch(
        "custom_components.delta_voiceiq.config_flow.DeltaVoiceIQClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.exchange_code = AsyncMock(return_value=ONE_DEVICE)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "delta.code.NEW"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "tok123"
