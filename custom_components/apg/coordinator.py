"""Data update coordinators for the APG integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApgApiClient, ApgApiError, ApgAuthError, PeakHourData
from .const import DOMAIN, POWERMONITOR_INTERVAL_FACTOR

_LOGGER = logging.getLogger(__name__)


class PeakHourCoordinator(DataUpdateCoordinator[PeakHourData]):
    """Coordinator for the (unauthenticated) peak hour API."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ApgApiClient,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_peak_hour",
            update_interval=update_interval,
            config_entry=entry,
        )
        self._client = client

    async def _async_update_data(self) -> PeakHourData:
        try:
            return await self._client.async_get_peak_hours()
        except ApgApiError as err:
            raise UpdateFailed(str(err)) from err


class PowermonitorCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator for the authenticated Powermonitor API.

    ``data`` maps each configured slug to its raw envelope. A slug that fails to
    load is simply omitted so a single broken dataset does not take the others
    down with it.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ApgApiClient,
        token: str,
        slugs: list[str],
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_powermonitor",
            update_interval=update_interval * POWERMONITOR_INTERVAL_FACTOR,
            config_entry=entry,
        )
        self._client = client
        self._token = token
        self.slugs = slugs

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        last_error: ApgApiError | None = None
        for slug in self.slugs:
            try:
                result[slug] = await self._client.async_get_powermonitor(
                    slug, self._token
                )
            except ApgAuthError as err:
                # An auth error affects every slug, so fail the whole update.
                raise UpdateFailed(str(err)) from err
            except ApgApiError as err:
                _LOGGER.warning("Powermonitor slug %s failed: %s", slug, err)
                last_error = err

        if not result and last_error is not None:
            raise UpdateFailed(str(last_error))
        return result
