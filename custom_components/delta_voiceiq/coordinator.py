"""DataUpdateCoordinator for Delta VoiceIQ usage polling."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthExpired, CannotConnect, DeltaVoiceIQClient
from .const import DOMAIN, SCAN_INTERVALS, USAGE_INTERVALS

_LOGGER = logging.getLogger(__name__)


class DeltaUsageCoordinator(DataUpdateCoordinator[float]):
    """Polls UsageReport for a single interval (today/week/month/year)."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DeltaVoiceIQClient,
        mac_address: str,
        interval_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{mac_address}_{interval_name}",
            update_interval=SCAN_INTERVALS[interval_name],
        )
        self._client = client
        self._mac_address = mac_address
        self._interval_value = USAGE_INTERVALS[interval_name]

    async def _async_update_data(self) -> float:
        try:
            return await self._client.get_usage(self._mac_address, self._interval_value)
        except AuthExpired as err:
            raise ConfigEntryAuthFailed("Delta VoiceIQ token rejected") from err
        except CannotConnect as err:
            raise UpdateFailed(str(err)) from err
