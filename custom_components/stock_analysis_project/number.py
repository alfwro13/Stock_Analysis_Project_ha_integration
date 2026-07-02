"""Number platform for Stock Analysis Project integration."""
from __future__ import annotations

from homeassistant.components.number import RestoreNumber
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StockAnalysisConfigEntry
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, portfolio_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StockAnalysisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Stock Analysis Project number platform."""
    coordinator = config_entry.runtime_data
    async_add_entities([StockAnalysisRefreshIntervalNumber(coordinator, config_entry)])


class StockAnalysisRefreshIntervalNumber(CoordinatorEntity, RestoreNumber):
    """Number entity controlling the coordinator's polling interval, in minutes."""

    _attr_has_entity_name = True
    _attr_name = "Refresh Interval"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = "box"
    _attr_native_min_value = 1
    _attr_native_max_value = 1440
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_unique_id = f"sap_refresh_interval_{config_entry.entry_id}"
        self._attr_device_info = portfolio_device_info(config_entry)
        self._attr_native_value = config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    async def async_added_to_hass(self) -> None:
        """Restore the last known value, falling back to the configured update interval."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_number_data()) is not None and last_data.native_value is not None:
            self._attr_native_value = last_data.native_value
        else:
            self._attr_native_value = self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    async def async_set_native_value(self, value: float) -> None:
        """Update the coordinator's polling interval and reschedule immediately."""
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_set_update_interval(int(value))
