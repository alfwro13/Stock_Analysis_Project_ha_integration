"""Button platform for Stock Analysis Project integration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StockAnalysisConfigEntry
from .const import diagnostics_device_info, portfolio_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StockAnalysisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Stock Analysis Project button platform."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            StockAnalysisRefreshDataButton(coordinator, config_entry),
            StockAnalysisPruneOrphansButton(coordinator, config_entry),
        ]
    )


class StockAnalysisRefreshDataButton(CoordinatorEntity, ButtonEntity):
    """Button that triggers an immediate backend refresh, then re-polls."""

    _attr_has_entity_name = True
    _attr_name = "Refresh Data"

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"sap_refresh_data_{config_entry.entry_id}"
        self._attr_device_info = portfolio_device_info(config_entry)

    async def async_press(self) -> None:
        """Trigger a backend refresh (awaited until the fetch actually completes) and re-poll."""
        await self.coordinator.api.trigger_refresh_now()
        await self.coordinator.async_request_refresh()


class StockAnalysisPruneOrphansButton(CoordinatorEntity, ButtonEntity):
    """Button that removes entity-registry entries with no valid unique_id."""

    _attr_has_entity_name = True
    _attr_name = "Prune Orphaned Entities"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"sap_prune_orphans_{config_entry.entry_id}"
        self._attr_device_info = diagnostics_device_info(config_entry)

    async def async_press(self) -> None:
        """Prune orphaned entities from the entity registry."""
        await self.coordinator.async_prune_orphans()
