"""Valve entity for the Delta faucet."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components.valve import ValveDeviceClass, ValveEntity, ValveEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeltaVoiceIQConfigEntry
from .api import AuthExpired, CannotConnect, convert_to_ml
from .const import CONF_DEVICE_NAME, CONF_MAC_ADDRESS, CONF_PRODUCT_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeltaVoiceIQConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([DeltaFaucetValve(entry)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "dispense",
        {
            vol.Required("amount"): vol.Coerce(float),
            vol.Optional("unit", default="ml"): vol.In(["ml", "l", "gal", "fl_oz"]),
        },
        "async_dispense",
    )
    platform.async_register_entity_service("hand_wash", {}, "async_hand_wash")


class DeltaFaucetValve(ValveEntity):
    """Represents the faucet's water flow as an open/closed valve."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = ValveDeviceClass.WATER
    _attr_reports_position = False
    _attr_assumed_state = True
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE

    def __init__(self, entry: DeltaVoiceIQConfigEntry) -> None:
        self._entry = entry
        self._client = entry.runtime_data.client
        self._mac_address = entry.data[CONF_MAC_ADDRESS]
        self._attr_unique_id = f"{self._mac_address}_valve"
        self._attr_is_closed = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._mac_address)},
            name=entry.data[CONF_DEVICE_NAME],
            manufacturer="Delta",
            model=entry.data.get(CONF_PRODUCT_ID),
        )

    async def async_open_valve(self) -> None:
        await self._set_state(open_=True)

    async def async_close_valve(self) -> None:
        await self._set_state(open_=False)

    async def _set_state(self, open_: bool) -> None:
        try:
            await self._client.toggle_water(self._mac_address, on=open_)
        except AuthExpired as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                "Delta faucet authentication expired; reauthentication started"
            ) from err
        except CannotConnect as err:
            raise HomeAssistantError(str(err)) from err
        self._attr_is_closed = not open_
        self.async_write_ha_state()

    async def async_dispense(self, amount: float, unit: str = "ml") -> None:
        milliliters = convert_to_ml(amount, unit)
        try:
            await self._client.dispense(self._mac_address, milliliters)
        except AuthExpired as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                "Delta faucet authentication expired; reauthentication started"
            ) from err
        except CannotConnect as err:
            raise HomeAssistantError(str(err)) from err

    async def async_hand_wash(self) -> None:
        try:
            await self._client.hand_wash(self._mac_address)
        except AuthExpired as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                "Delta faucet authentication expired; reauthentication started"
            ) from err
        except CannotConnect as err:
            raise HomeAssistantError(str(err)) from err
