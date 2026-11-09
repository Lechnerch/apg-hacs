"""Sensor platform for the APG integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import ApgConfigEntry
from .const import POWERMONITOR_SLUGS, STATUS_PEAK
from .entity import ApgBaseEntity
from . import powermonitor as pm

PEAK_DEVICE = ("peak_hour", "APG Peak Hours")
PM_DEVICE = ("powermonitor", "APG Powermonitor")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ApgConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the APG sensors."""
    data = entry.runtime_data
    entities: list[SensorEntity] = [
        ApgPeakStatusSensor(data.peak_hour, entry.entry_id),
        ApgNextPeakSensor(data.peak_hour, entry.entry_id),
        ApgPeakHoursTodaySensor(data.peak_hour, entry.entry_id),
        ApgPeakHoursRemainingSensor(data.peak_hour, entry.entry_id),
    ]

    if data.powermonitor is not None:
        for slug in data.powermonitor.slugs:
            entities.append(
                ApgPowermonitorSensor(data.powermonitor, entry.entry_id, slug)
            )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Peak hour sensors
# ---------------------------------------------------------------------------
class _PeakSensorBase(ApgBaseEntity, SensorEntity):
    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, *PEAK_DEVICE)


class ApgPeakStatusSensor(_PeakSensorBase):
    """Current peak status as a readable text (peak / off_peak)."""

    _attr_translation_key = "peak_status"
    _attr_icon = "mdi:transmission-tower"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["peak", "off_peak"]

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_peak_status"

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        status = data.status_at(dt_util.utcnow())
        if status is None:
            return None
        return "peak" if status == STATUS_PEAK else "off_peak"


class ApgNextPeakSensor(_PeakSensorBase):
    """Start time of the next upcoming peak hour."""

    _attr_translation_key = "next_peak_hour"
    _attr_icon = "mdi:clock-alert-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_next_peak_hour"

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.next_peak_hour(dt_util.utcnow())


class ApgPeakHoursTodaySensor(_PeakSensorBase):
    """Number of peak hours on the local calendar day."""

    _attr_translation_key = "peak_hours_today"
    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "h"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_peak_hours_today"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return len(data.peak_hours_on(dt_util.now()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {}
        local_now = dt_util.now()
        return {
            "peak_hours": [
                h.astimezone(local_now.tzinfo).isoformat()
                for h in data.peak_hours_on(local_now)
            ]
        }


class ApgPeakHoursRemainingSensor(_PeakSensorBase):
    """Number of peak hours still to come from now until end of data."""

    _attr_translation_key = "peak_hours_remaining"
    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = "h"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_peak_hours_remaining"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return len(data.upcoming_peak_hours(dt_util.utcnow()))


# ---------------------------------------------------------------------------
# Powermonitor sensors (best effort, see powermonitor.py)
# ---------------------------------------------------------------------------
class ApgPowermonitorSensor(ApgBaseEntity, SensorEntity):
    """Latest numeric value of one Powermonitor content dataset."""

    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id: str, slug: str) -> None:
        super().__init__(coordinator, entry_id, *PM_DEVICE)
        self._slug = slug
        self._attr_unique_id = f"{entry_id}_pm_{slug}"
        self._attr_name = POWERMONITOR_SLUGS.get(slug, slug)

    def _payload(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.get(self._slug)

    @property
    def available(self) -> bool:
        return super().available and self._payload() is not None

    @property
    def native_value(self) -> float | None:
        payload = self._payload()
        if payload is None:
            return None
        return pm.summarize(payload)["value"]

    @property
    def native_unit_of_measurement(self) -> str | None:
        payload = self._payload()
        if payload is None:
            return None
        return pm.summarize(payload)["unit"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        payload = self._payload()
        if payload is None:
            return {}
        summary = pm.summarize(payload)
        return {
            "slug": self._slug,
            "date": summary["date"],
            "value_column": summary["value_column"],
            "mode": summary["mode"],
            "primary_category": summary["primary_category"],
            "breakdown": summary["breakdown"],
            "point_count": summary["point_count"],
            "series": summary["series"],
        }
