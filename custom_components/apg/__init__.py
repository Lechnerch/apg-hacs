"""The Austrian Power Grid (APG) integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api import ApgApiClient
from .const import (
    CONF_POWERMONITOR_SLUGS,
    CONF_POWERMONITOR_TOKEN,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)
from .coordinator import PeakHourCoordinator, PowermonitorCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


@dataclass
class ApgRuntimeData:
    """Objects shared across the platforms of one config entry."""

    peak_hour: PeakHourCoordinator
    powermonitor: PowermonitorCoordinator | None


type ApgConfigEntry = ConfigEntry[ApgRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: ApgConfigEntry) -> bool:
    """Set up APG from a config entry."""
    session = async_get_clientsession(hass)
    client = ApgApiClient(session)

    minutes = entry.options.get(
        CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
    )
    interval = timedelta(minutes=minutes)

    peak_hour = PeakHourCoordinator(hass, entry, client, interval)
    await peak_hour.async_config_entry_first_refresh()

    powermonitor: PowermonitorCoordinator | None = None
    token = entry.options.get(
        CONF_POWERMONITOR_TOKEN, entry.data.get(CONF_POWERMONITOR_TOKEN)
    )
    slugs = entry.options.get(
        CONF_POWERMONITOR_SLUGS, entry.data.get(CONF_POWERMONITOR_SLUGS, [])
    )
    if token and slugs:
        powermonitor = PowermonitorCoordinator(
            hass, entry, client, token, list(slugs), interval
        )
        # Use async_refresh (not first_refresh) so a failing optional
        # Powermonitor API does not abort setup of the peak-hour part.
        await powermonitor.async_refresh()

    entry.runtime_data = ApgRuntimeData(peak_hour=peak_hour, powermonitor=powermonitor)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The peak hour entities derive their state from the current clock hour.
    # Re-notify listeners right after every full hour so the "is it a peak
    # hour now" state flips on time without hammering the API.
    @callback
    def _hourly_refresh(_now) -> None:
        peak_hour.async_update_listeners()

    entry.async_on_unload(
        async_track_time_change(hass, _hourly_refresh, minute=0, second=10)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ApgConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ApgConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
