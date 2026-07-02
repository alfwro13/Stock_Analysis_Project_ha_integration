"""Sensor platform for Stock Analysis Project integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StockAnalysisConfigEntry, StockAnalysisDataUpdateCoordinator
from .const import portfolio_device_info

_MONETARY_SENSORS: list[tuple[str, str, str]] = [
    ("portfolio_cost", "Portfolio Cost", "total_investment"),
    ("portfolio_value", "Portfolio Value", "current_value"),
    ("portfolio_gain", "Portfolio Gain", "portfolio_gain"),
    ("portfolio_gain_fx", "Portfolio Gain with FX", "portfolio_gain_fx"),
    ("portfolio_total_dividend", "Portfolio Total Dividend", "portfolio_dividends"),
    ("portfolio_unrealized_pnl", "Portfolio Unrealized P&L", "unrealized_pnl"),
]

_PERCENT_SENSORS: list[tuple[str, str, str]] = [
    ("portfolio_unrealized_pnl_pct", "Portfolio Unrealized P&L %", "unrealized_pnl_pct"),
    ("portfolio_simple_gain_pct", "Portfolio Simple Gain %", "portfolio_gain_pct"),
    ("portfolio_twr_pct", "Portfolio Time Weighted Return %", "twr_pct"),
    ("portfolio_twr_fx_pct", "Portfolio Time Weighted Return with FX %", "twr_fx_pct"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StockAnalysisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Stock Analysis Project sensor platform."""
    coordinator = config_entry.runtime_data

    entities: list[SensorEntity] = [
        StockAnalysisMonetarySensor(coordinator, config_entry, key, name, field)
        for key, name, field in _MONETARY_SENSORS
    ]
    entities.extend(
        StockAnalysisPercentSensor(coordinator, config_entry, key, name, field)
        for key, name, field in _PERCENT_SENSORS
    )

    async_add_entities(entities)


class StockAnalysisBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Stock Analysis Project portfolio-total sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StockAnalysisDataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_key: str,
        name: str,
        field: str,
    ) -> None:
        """Initialize the base sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._field = field
        self._attr_name = name
        self._attr_unique_id = f"sap_{unique_id_key}_{config_entry.entry_id}"
        self._attr_device_info = portfolio_device_info(config_entry)

    @property
    def _totals(self) -> dict[str, Any]:
        """Return the latest portfolio_totals payload, or {} if no data yet."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("portfolio_totals", {}) or {}

    @property
    def native_value(self) -> float | None:
        """Return the field's value from the latest portfolio totals."""
        return self._totals.get(self._field)


class StockAnalysisMonetarySensor(StockAnalysisBaseSensor):
    """A portfolio-total sensor denominated in the portfolio's base currency."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the portfolio's base currency."""
        return self._totals.get("base_currency", "GBP")


class StockAnalysisPercentSensor(StockAnalysisBaseSensor):
    """A portfolio-total sensor expressed as a percentage."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 2
