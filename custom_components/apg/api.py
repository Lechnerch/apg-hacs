"""API client and data models for the Austrian Power Grid (APG) integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

import aiohttp
import async_timeout

from .const import (
    PEAK_HOUR_URL,
    POWERMONITOR_URL,
    STATUS_OFF_PEAK,
    STATUS_PEAK,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30


class ApgApiError(Exception):
    """Raised when the APG API returns an error or cannot be reached."""


class ApgAuthError(ApgApiError):
    """Raised when the Powermonitor token is missing or rejected (401)."""


def _parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp coming from the APG API."""
    # The API uses the "Z" suffix which datetime.fromisoformat only accepts
    # on Python 3.11+. Normalise it for maximum compatibility.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class PeakHourData:
    """Parsed result of the peak hour API.

    The API returns a default status for a whole time span plus a list of
    hourly exceptions. This class expands that into a lookup and exposes a
    few convenience properties for the entities.
    """

    default_status: str
    first_utc: datetime
    last_utc: datetime
    # Maps the start of each hour (aware UTC datetime) to its status string.
    overrides: dict[datetime, str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "PeakHourData":
        """Build a :class:`PeakHourData` from the raw API payload."""
        try:
            default_status = str(raw["DefaultStatus"])
            first_utc = _parse_utc(raw["FirstUtc"])
            last_utc = _parse_utc(raw["LastUtc"])
            overrides: dict[datetime, str] = {}
            for info in raw.get("StatusInfos", []) or []:
                overrides[_parse_utc(info["utc"])] = str(info["s"])
        except (KeyError, TypeError, ValueError) as err:
            raise ApgApiError(f"Unexpected peak hour payload: {err}") from err
        return cls(default_status, first_utc, last_utc, overrides)

    @staticmethod
    def _floor_hour(moment: datetime) -> datetime:
        return moment.replace(minute=0, second=0, microsecond=0)

    def status_at(self, moment: datetime) -> str | None:
        """Return the status string ("1"/"2") for the hour of *moment*."""
        hour = self._floor_hour(moment.astimezone(self.first_utc.tzinfo))
        if hour < self.first_utc or hour >= self.last_utc:
            return None
        return self.overrides.get(hour, self.default_status)

    def is_peak_at(self, moment: datetime) -> bool | None:
        """Return whether the hour containing *moment* is a peak hour."""
        status = self.status_at(moment)
        if status is None:
            return None
        return status == STATUS_PEAK

    def peak_hours(self) -> list[datetime]:
        """Return all peak hour starts in the covered span, sorted ascending."""
        result: list[datetime] = []
        hour = self.first_utc
        one_hour = timedelta(hours=1)
        while hour < self.last_utc:
            status = self.overrides.get(hour, self.default_status)
            if status == STATUS_PEAK:
                result.append(hour)
            hour += one_hour
        return result

    def upcoming_peak_hours(self, now: datetime) -> list[datetime]:
        """Peak hour starts whose hour has not finished yet."""
        current_hour = self._floor_hour(now.astimezone(self.first_utc.tzinfo))
        return [h for h in self.peak_hours() if h >= current_hour]

    def next_peak_hour(self, now: datetime) -> datetime | None:
        """Start of the next peak hour strictly after the current hour."""
        current_hour = self._floor_hour(now.astimezone(self.first_utc.tzinfo))
        for hour in self.peak_hours():
            if hour > current_hour:
                return hour
        return None

    def peak_hours_on(self, local_day: datetime) -> list[datetime]:
        """Peak hour starts that fall on the local calendar day of *local_day*."""
        day = local_day.date()
        result = []
        for hour in self.peak_hours():
            if hour.astimezone(local_day.tzinfo).date() == day:
                result.append(hour)
        return result


class ApgApiClient:
    """Thin async client around the two public APG APIs."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_get_peak_hours(self) -> PeakHourData:
        """Fetch and parse the peak hour status for the next five days."""
        raw = await self._get_json(PEAK_HOUR_URL)
        if not isinstance(raw, dict):
            raise ApgApiError("Peak hour API did not return an object")
        return PeakHourData.from_json(raw)

    async def async_get_powermonitor(self, slug: str, token: str) -> dict[str, Any]:
        """Fetch a Powermonitor content dataset by slug.

        Requires a Bearer token. The raw envelope is returned unmodified so the
        sensor layer can decide how to interpret it.
        """
        url = POWERMONITOR_URL.format(slug=slug)
        headers = {"Authorization": f"Bearer {token}", "accept": "*/*"}
        raw = await self._get_json(url, headers=headers)
        if not isinstance(raw, dict):
            raise ApgApiError(f"Powermonitor slug {slug} did not return an object")
        return raw

    async def _get_json(
        self, url: str, headers: dict[str, str] | None = None
    ) -> Any:
        try:
            async with async_timeout.timeout(REQUEST_TIMEOUT):
                response = await self._session.get(url, headers=headers)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ApgApiError(f"Error connecting to {url}: {err}") from err

        if response.status == 401:
            raise ApgAuthError("Powermonitor token missing or rejected (401)")
        if response.status == 429:
            raise ApgApiError("Rate limit reached (429), try again later")
        if response.status >= 400:
            raise ApgApiError(f"{url} returned HTTP {response.status}")

        try:
            return await response.json(content_type=None)
        except (aiohttp.ClientError, ValueError) as err:
            raise ApgApiError(f"Invalid JSON from {url}: {err}") from err
