"""Switch platform for Stock Analysis Project integration."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StockAnalysisConfigEntry
from .const import portfolio_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StockAnalysisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Stock Analysis Project switch platform."""
    coordinator = config_entry.runtime_data
    async_add_entities([StockAnalysisEnableAutoRefreshSwitch(coordinator, config_entry)])


class StockAnalysisEnableAutoRefreshSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable automatic background polling."""

    _attr_has_entity_name = True
    _attr_name = "Enable Auto Refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_unique_id = f"sap_enable_auto_refresh_{config_entry.entry_id}"
        self._attr_device_info = portfolio_device_info(config_entry)

    @property
    def is_on(self) -> bool:
        """Return True if auto-refresh is currently enabled."""
        return self.coordinator.auto_refresh_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Enable auto-refresh and resume polling immediately."""
        await self.coordinator.async_set_auto_refresh_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable auto-refresh and suspend the background polling timer."""
        await self.coordinator.async_set_auto_refresh_enabled(False)
        self.async_write_ha_state()
