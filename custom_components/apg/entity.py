"""Shared entity base classes for the APG integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER


class ApgBaseEntity(CoordinatorEntity):
    """Common attributes for every APG entity."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry_id: str, device_suffix: str, device_name: str) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{device_suffix}")},
            manufacturer=MANUFACTURER,
            name=device_name,
            configuration_url="https://www.apg-powermonitor.at",
        )
