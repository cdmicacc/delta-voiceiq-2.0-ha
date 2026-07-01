"""Sensor entities for Delta VoiceIQ."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from . import DeltaVoiceIQConfigEntry
from .const import CONF_EXP_TIMESTAMP, CONF_MAC_ADDRESS, CONF_PRODUCT_ID, CONF_USER_ID, DOMAIN, LITERS_PER_GALLON, USAGE_INTERVALS
from .coordinator import DeltaUsageCoordinator

_LOGGER = logging.getLogger(__name__)

_INTERVAL_TITLES = {"today": "Usage Today", "week": "Usage Week", "month": "Usage Month", "year": "Usage Year"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeltaVoiceIQConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators = entry.runtime_data.coordinators
    entities: list[SensorEntity] = [
        UsageSensor(entry, coordinators[name], name) for name in USAGE_INTERVALS
    ]
    entities.append(TokenExpirySensor(entry))
    entities.append(
        StaticInfoSensor(entry, "MAC Address", "mac_address_info", entry.data[CONF_MAC_ADDRESS])
    )
    entities.append(StaticInfoSensor(entry, "User ID", "user_id_info", entry.data[CONF_USER_ID]))
    if product_id := entry.data.get(CONF_PRODUCT_ID):
        entities.append(StaticInfoSensor(entry, "Model", "product_id_info", product_id))
    async_add_entities(entities)


def _device_info(entry: DeltaVoiceIQConfigEntry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.data[CONF_MAC_ADDRESS])})


class UsageSensor(CoordinatorEntity[DeltaUsageCoordinator], SensorEntity):
    """Reports usage for one UsageReport interval, in liters."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS

    def __init__(self, entry: DeltaVoiceIQConfigEntry, coordinator: DeltaUsageCoordinator, interval_name: str) -> None:
        super().__init__(coordinator)
        mac_address = entry.data[CONF_MAC_ADDRESS]
        self._attr_name = _INTERVAL_TITLES[interval_name]
        self._attr_unique_id = f"{mac_address}_usage_{interval_name}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        gallons = self.coordinator.data
        if gallons is None:
            return None
        return round(gallons * LITERS_PER_GALLON, 2)


class TokenExpirySensor(SensorEntity):
    """Reports days remaining until the stored access token expires."""

    _attr_has_entity_name = True
    _attr_name = "Token Expiry"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_icon = "mdi:key-chain"
    _attr_should_poll = False

    def __init__(self, entry: DeltaVoiceIQConfigEntry) -> None:
        self._entry = entry
        mac_address = entry.data[CONF_MAC_ADDRESS]
        self._attr_unique_id = f"{mac_address}_token_expiry"
        self._attr_device_info = _device_info(entry)
        self._update_value()

    def _update_value(self) -> None:
        exp = self._entry.data.get(CONF_EXP_TIMESTAMP)
        if not exp:
            self._attr_native_value = None
            return
        days_left = (exp - dt_util.utcnow().timestamp()) / 86400
        self._attr_native_value = round(days_left)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_interval(self.hass, self._handle_update, timedelta(hours=1))
        )

    async def _handle_update(self, now) -> None:
        self._update_value()
        self.async_write_ha_state()


class StaticInfoSensor(SensorEntity):
    """A fixed, non-polling value read once from the config entry."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: DeltaVoiceIQConfigEntry,
        name: str,
        unique_suffix: str,
        value: str,
        *,
        diagnostic: bool = True,
    ) -> None:
        mac_address = entry.data[CONF_MAC_ADDRESS]
        self._attr_name = name
        self._attr_unique_id = f"{mac_address}_{unique_suffix}"
        self._attr_native_value = value
        self._attr_device_info = _device_info(entry)
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
