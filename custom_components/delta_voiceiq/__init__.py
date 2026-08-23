"""The Delta VoiceIQ integration."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.util.dt as dt_util

from .api import DeltaVoiceIQClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXP_TIMESTAMP,
    CONF_MAC_ADDRESS,
    DOMAIN,
    TOKEN_EXPIRY_WARNING_DAYS,
    USAGE_INTERVALS,
)
from .coordinator import DeltaUsageCoordinator

PLATFORMS: list[Platform] = [Platform.VALVE, Platform.SENSOR]


@dataclass
class DeltaVoiceIQRuntimeData:
    """Data owned by a single config entry for the lifetime of its setup."""

    client: DeltaVoiceIQClient
    coordinators: dict[str, DeltaUsageCoordinator] = field(default_factory=dict)


type DeltaVoiceIQConfigEntry = ConfigEntry[DeltaVoiceIQRuntimeData]


@callback
def _async_check_token_expiry(hass: HomeAssistant, entry: DeltaVoiceIQConfigEntry) -> None:
    """Create/clear Repair issues for an unparseable exp claim or a soon-to-expire token."""
    unparseable_issue_id = f"{entry.entry_id}_exp_unparseable"
    expiring_issue_id = f"{entry.entry_id}_expiring_soon"
    exp = entry.data.get(CONF_EXP_TIMESTAMP)

    if exp is None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            unparseable_issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="exp_unparseable",
        )
        ir.async_delete_issue(hass, DOMAIN, expiring_issue_id)
        return

    ir.async_delete_issue(hass, DOMAIN, unparseable_issue_id)
    days_left = (exp - dt_util.utcnow().timestamp()) / 86400
    # Compare on whole days remaining, matching the Token Expiry sensor. Warning
    # at `days_left < 7` would have fired with only ~6.9 days left -- less notice
    # than the threshold promises. Firing once the floored count reaches 7 gives
    # a full 7 days at minimum, and keeps the Repair in step with the sensor:
    # the Repair is present exactly when the sensor reads 7 or below.
    whole_days_left = math.floor(days_left)
    if whole_days_left <= TOKEN_EXPIRY_WARNING_DAYS:
        ir.async_create_issue(
            hass,
            DOMAIN,
            expiring_issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="expiring_soon",
            translation_placeholders={"days": str(whole_days_left)},
            data={"entry_id": entry.entry_id},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, expiring_issue_id)


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

    _async_check_token_expiry(hass, entry)

    @callback
    def _recheck_token_expiry(now) -> None:
        _async_check_token_expiry(hass, entry)

    entry.async_on_unload(
        async_track_time_interval(hass, _recheck_token_expiry, timedelta(hours=24))
    )

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeltaVoiceIQConfigEntry) -> bool:
    """Unload a Delta VoiceIQ config entry."""
    if not PLATFORMS:
        return True
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
