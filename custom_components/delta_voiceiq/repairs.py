"""Repair flow for refreshing a Delta VoiceIQ token before it expires.

Home Assistant triggers reauth reactively, once credentials have already
failed. That leaves the expiring-soon window with nowhere to act, so the
Repair itself carries the renewal: pick a provider, paste a fresh code,
done -- without waiting for the token to lapse first.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .api import (
    AuthExpired,
    CannotConnect,
    DeltaVoiceIQClient,
    InvalidCode,
    NoDevicesFound,
    build_login_url,
    extract_code,
)
from .const import CONF_ACCESS_TOKEN, CONF_EXP_TIMESTAMP, LOGIN_PROVIDERS

_LOGGER = logging.getLogger(__name__)


class TokenExpiryRepairFlow(RepairsFlow):
    """Collect a fresh sign-in code and swap it into the existing entry."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._provider: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_provider()

    async def async_step_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._provider = user_input["provider"]
            return await self.async_step_code()
        return self.async_show_form(
            step_id="provider",
            data_schema=vol.Schema({
                vol.Required("provider"): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": p, "label": p.capitalize()} for p in LOGIN_PROVIDERS],
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }),
        )

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
                return await self._async_apply(result.access_token, result.exp_timestamp)

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            description_placeholders={"login_url": build_login_url(self._provider)},
            errors=errors,
        )

    async def _async_apply(self, access_token: str, exp_timestamp: int | None) -> FlowResult:
        """Write the refreshed credentials to the entry and reload it."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            # The entry was removed while the Repair dialog sat open.
            return self.async_abort(reason="entry_not_found")

        self.hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCESS_TOKEN: access_token,
                CONF_EXP_TIMESTAMP: exp_timestamp,
            },
        )
        self.hass.async_create_task(self.hass.config_entries.async_reload(entry.entry_id))
        # Any non-ABORT result makes Home Assistant clear the Repair for us.
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Build the fix flow for a fixable delta_voiceiq issue."""
    entry_id = (data or {}).get("entry_id")
    return TokenExpiryRepairFlow(str(entry_id))
