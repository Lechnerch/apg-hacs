"""Binary sensor platform for the APG integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import ApgConfigEntry
from .entity import ApgBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ApgConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the APG binary sensors."""
    async_add_entities(
        [ApgPeakHourNowBinarySensor(entry.runtime_data.peak_hour, entry.entry_id)]
    )


class ApgPeakHourNowBinarySensor(ApgBaseEntity, BinarySensorEntity):
    """Whether the current clock hour is a peak hour."""

    _attr_translation_key = "peak_hour_now"
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "peak_hour", "APG Peak Hours")
        self._attr_unique_id = f"{entry_id}_peak_hour_now"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.is_peak_at(dt_util.utcnow())

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {}
        now = dt_util.utcnow()
        upcoming = data.upcoming_peak_hours(now)
        next_peak = data.next_peak_hour(now)
        return {
            "default_status": data.default_status,
            "first_utc": data.first_utc.isoformat(),
            "last_utc": data.last_utc.isoformat(),
            "next_peak_hour": next_peak.isoformat() if next_peak else None,
            "upcoming_peak_hours": [h.isoformat() for h in upcoming],
            "peak_hours_total": len(data.peak_hours()),
        }
