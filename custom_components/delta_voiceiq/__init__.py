"""The Delta VoiceIQ integration."""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DeltaVoiceIQClient
from .const import CONF_ACCESS_TOKEN, CONF_MAC_ADDRESS, USAGE_INTERVALS
from .coordinator import DeltaUsageCoordinator

PLATFORMS: list[Platform] = [Platform.VALVE, Platform.SENSOR]


@dataclass
class DeltaVoiceIQRuntimeData:
    """Data owned by a single config entry for the lifetime of its setup."""

    client: DeltaVoiceIQClient
    coordinators: dict[str, DeltaUsageCoordinator] = field(default_factory=dict)


type DeltaVoiceIQConfigEntry = ConfigEntry[DeltaVoiceIQRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: DeltaVoiceIQConfigEntry) -> bool:
    """Set up Delta VoiceIQ from a config entry."""
    session = async_get_clientsession(hass)
    client = DeltaVoiceIQClient(session, access_token=entry.data[CONF_ACCESS_TOKEN])
    mac_address = entry.data[CONF_MAC_ADDRESS]

    coordinators: dict[str, DeltaUsageCoordinator] = {}
    for interval_name in USAGE_INTERVALS:
        coordinator = DeltaUsageCoordinator(hass, client, mac_address, interval_name)
        await coordinator.async_config_entry_first_refresh()
        coordinators[interval_name] = coordinator

    entry.runtime_data = DeltaVoiceIQRuntimeData(client=client, coordinators=coordinators)

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeltaVoiceIQConfigEntry) -> bool:
    """Unload a Delta VoiceIQ config entry."""
    if not PLATFORMS:
        return True
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
