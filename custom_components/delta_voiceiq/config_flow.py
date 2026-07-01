"""Config flow for Delta VoiceIQ."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .api import (
    AuthExpired,
    CannotConnect,
    DeltaDevice,
    DeltaVoiceIQClient,
    ExchangeResult,
    InvalidCode,
    NoDevicesFound,
    build_login_url,
    extract_code,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_NAME,
    CONF_EXP_TIMESTAMP,
    CONF_MAC_ADDRESS,
    CONF_PRODUCT_ID,
    CONF_USER_ID,
    DOMAIN,
    LOGIN_PROVIDERS,
)

_LOGGER = logging.getLogger(__name__)


class DeltaVoiceIQConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup and reauth for Delta VoiceIQ."""

    VERSION = 1

    def __init__(self) -> None:
        self._provider: str | None = None
        self._exchange_result: ExchangeResult | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._provider = user_input["provider"]
            return await self.async_step_code()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("provider"): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": p, "label": p.capitalize()} for p in LOGIN_PROVIDERS],
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_user()

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                code = extract_code(user_input["code"])
                session = async_get_clientsession(self.hass)
                client = DeltaVoiceIQClient(session)
                result = await client.exchange_code(code)
            except InvalidCode:
                errors["base"] = "invalid_code"
            except NoDevicesFound:
                return self.async_abort(reason="no_devices_found")
            except (CannotConnect, AuthExpired):
                errors["base"] = "cannot_connect"
            else:
                self._exchange_result = result
                if self.source == config_entries.SOURCE_REAUTH:
                    return await self._async_finish_reauth()
                if len(result.devices) == 1:
                    return await self._async_finish_setup(result.devices[0])
                return await self.async_step_device()

        login_url = build_login_url(self._provider)
        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            description_placeholders={"login_url": login_url},
            errors=errors,
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        assert self._exchange_result is not None
        if user_input is not None:
            chosen_mac = user_input["mac_address"]
            device = next(
                d for d in self._exchange_result.devices if d.mac_address == chosen_mac
            )
            return await self._async_finish_setup(device)

        options = {d.mac_address: d.name for d in self._exchange_result.devices}
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required("mac_address"): vol.In(options)}),
        )

    async def _async_finish_setup(self, device: DeltaDevice) -> FlowResult:
        assert self._exchange_result is not None
        await self.async_set_unique_id(device.mac_address)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=device.name,
            data={
                CONF_ACCESS_TOKEN: self._exchange_result.access_token,
                CONF_MAC_ADDRESS: device.mac_address,
                CONF_USER_ID: self._exchange_result.user_id,
                CONF_EXP_TIMESTAMP: self._exchange_result.exp_timestamp,
                CONF_DEVICE_NAME: device.name,
                CONF_PRODUCT_ID: device.product_id,
            },
        )

    async def _async_finish_reauth(self) -> FlowResult:
        assert self._exchange_result is not None
        assert self._reauth_entry is not None
        new_data = {
            **self._reauth_entry.data,
            CONF_ACCESS_TOKEN: self._exchange_result.access_token,
            CONF_EXP_TIMESTAMP: self._exchange_result.exp_timestamp,
        }
        return self.async_update_reload_and_abort(
            self._reauth_entry, data=new_data, reason="reauth_successful"
        )
