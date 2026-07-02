"""Binary sensor platform for Stock Analysis Project integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StockAnalysisConfigEntry, StockAnalysisDataUpdateCoordinator
from .const import diagnostics_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StockAnalysisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Stock Analysis Project binary_sensor platform."""
    coordinator = config_entry.runtime_data

    async_add_entities(
        [
            StockAnalysisServerStatusSensor(coordinator, config_entry),
            StockAnalysisYahooStatusSensor(coordinator, config_entry),
            StockAnalysisUSMarketOpenSensor(coordinator, config_entry),
            StockAnalysisUKMarketOpenSensor(coordinator, config_entry),
            StockAnalysisSystemStatusSensor(coordinator, config_entry),
        ]
    )


class StockAnalysisBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base class for Stock Analysis Project diagnostic binary sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StockAnalysisDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the base binary sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_device_info = diagnostics_device_info(config_entry)

    @property
    def _market_status(self) -> dict[str, Any]:
        """Return the latest market_status payload, or {} if no data yet."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("market_status", {}) or {}


class StockAnalysisServerStatusSensor(StockAnalysisBaseBinarySensor):
    """Whether the backend server responded successfully on the last poll."""

    _attr_name = "Server Status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the server status sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"sap_server_status_{config_entry.entry_id}"

    @property
    def is_on(self) -> bool:
        """Return True if the last poll of the backend succeeded."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("server_online", False)


class StockAnalysisYahooStatusSensor(StockAnalysisBaseBinarySensor):
    """Whether Yahoo Finance data is currently flowing successfully."""

    _attr_name = "Yahoo Status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the Yahoo status sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"sap_yahoo_status_{config_entry.entry_id}"

    @property
    def is_on(self) -> bool | None:
        """Return True if Yahoo Finance is reachable/healthy."""
        return self._market_status.get("yahoo_ok")


class StockAnalysisUSMarketOpenSensor(StockAnalysisBaseBinarySensor):
    """Whether the US (NYSE) market is currently in its trading session."""

    _attr_name = "US Market Open"
    _attr_device_class = BinarySensorDeviceClass.WINDOW

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the US market open sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"sap_us_market_open_{config_entry.entry_id}"

    @property
    def is_on(self) -> bool | None:
        """Return True if the US market is open."""
        return self._market_status.get("us_market_open")


class StockAnalysisUKMarketOpenSensor(StockAnalysisBaseBinarySensor):
    """Whether the UK (LSE) market is currently in its trading session."""

    _attr_name = "UK Market Open"
    _attr_device_class = BinarySensorDeviceClass.WINDOW

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the UK market open sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"sap_uk_market_open_{config_entry.entry_id}"

    @property
    def is_on(self) -> bool | None:
        """Return True if the UK market is open."""
        return self._market_status.get("uk_market_open")


class StockAnalysisSystemStatusSensor(StockAnalysisBaseBinarySensor):
    """Whether the backend's own system diagnostics detected a problem."""

    _attr_name = "System Status"

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the system status sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"sap_system_status_{config_entry.entry_id}"

    @property
    def is_on(self) -> bool | None:
        """Inverted polarity: True means a problem exists (system_ok is False)."""
        system_ok = self._market_status.get("system_ok")
        if system_ok is None:
            return None
        return not system_ok
