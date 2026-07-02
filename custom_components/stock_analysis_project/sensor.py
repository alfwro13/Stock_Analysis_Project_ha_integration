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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StockAnalysisConfigEntry, StockAnalysisDataUpdateCoordinator
from .const import (
    CONF_SHOW_ACCOUNTS,
    CONF_SHOW_PORTFOLIO_TOTALS,
    account_device_info,
    portfolio_device_info,
)

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

_ACCOUNT_MONETARY_SENSORS: list[tuple[str, str, str]] = [
    ("cash_balance", "Cash Balance", "cash_balance"),
    ("gain_1d", "Daily Gain", "gain_1d"),
    ("gain_1w", "1 Week Gain", "gain_1w"),
    ("gain_1m", "1 Month Gain", "gain_1m"),
    ("gain_3m", "3 Month Gain", "gain_3m"),
    ("gain_1y", "1 Year Gain", "gain_1y"),
    ("equity_value", "Equity Value", "equity_value"),
    ("realized_pnl", "Realized P&L", "realized_pnl"),
    ("unrealized_pnl", "Unrealized P&L", "unrealized_pnl"),
    ("dividend_income", "Dividend Income", "dividend_income"),
    ("interest_income", "Interest Income", "interest_income"),
]

_ACCOUNT_PERCENT_SENSORS: list[tuple[str, str, str]] = [
    ("mwrr_pct", "Money Weighted Rate of Return", "mwrr_pct"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StockAnalysisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Stock Analysis Project sensor platform."""
    coordinator = config_entry.runtime_data

    entities: list[SensorEntity] = []
    if config_entry.data.get(CONF_SHOW_PORTFOLIO_TOTALS, True):
        entities.extend(
            StockAnalysisMonetarySensor(coordinator, config_entry, key, name, field)
            for key, name, field in _MONETARY_SENSORS
        )
        entities.extend(
            StockAnalysisPercentSensor(coordinator, config_entry, key, name, field)
            for key, name, field in _PERCENT_SENSORS
        )

    if entities:
        async_add_entities(entities)

    known_ids: set[str] = set()

    @callback
    def _update_account_sensors() -> None:
        """Add sensors for any Trading account not yet represented as entities."""
        if not config_entry.data.get(CONF_SHOW_ACCOUNTS, True):
            return
        if not coordinator.data:
            return
        accounts = coordinator.data.get("account_metrics", {}).get("accounts", []) or []
        new_entities: list[SensorEntity] = []
        for acc in accounts:
            account_id = acc["account_id"]
            account_name = acc["name"]
            for key, name, field in _ACCOUNT_MONETARY_SENSORS:
                unique_id = f"sap_{key}_{account_id}_{config_entry.entry_id}"
                if unique_id not in known_ids:
                    known_ids.add(unique_id)
                    new_entities.append(
                        StockAnalysisAccountMonetarySensor(
                            coordinator, config_entry, key, name, field, account_id, account_name
                        )
                    )
            for key, name, field in _ACCOUNT_PERCENT_SENSORS:
                unique_id = f"sap_{key}_{account_id}_{config_entry.entry_id}"
                if unique_id not in known_ids:
                    known_ids.add(unique_id)
                    new_entities.append(
                        StockAnalysisAccountPercentSensor(
                            coordinator, config_entry, key, name, field, account_id, account_name
                        )
                    )
        if new_entities:
            async_add_entities(new_entities)

    config_entry.async_on_unload(coordinator.async_add_listener(_update_account_sensors))
    _update_account_sensors()


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


class StockAnalysisAccountBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for one Trading account's per-account sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StockAnalysisDataUpdateCoordinator,
        config_entry: ConfigEntry,
        unique_id_key: str,
        name: str,
        field: str,
        account_id: int,
        account_name: str,
    ) -> None:
        """Initialize the per-account sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._field = field
        self._account_id = account_id
        self._attr_name = name
        self._attr_unique_id = f"sap_{unique_id_key}_{account_id}_{config_entry.entry_id}"
        self._attr_device_info = account_device_info(config_entry, account_id, account_name)

    @property
    def _account_data(self) -> dict[str, Any]:
        """Return this sensor's account row from the latest fetch, or {} if not found yet."""
        if not self.coordinator.data:
            return {}
        accounts = self.coordinator.data.get("account_metrics", {}).get("accounts", []) or []
        for row in accounts:
            if row.get("account_id") == self._account_id:
                return row
        return {}

    @property
    def native_value(self) -> float | None:
        """Return the field's value from the latest account row."""
        return self._account_data.get(self._field)


class StockAnalysisAccountMonetarySensor(StockAnalysisAccountBaseSensor):
    """A per-account sensor denominated in the portfolio's base currency."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the portfolio's base currency."""
        if not self.coordinator.data:
            return "GBP"
        return self.coordinator.data.get("account_metrics", {}).get("base_currency") or "GBP"


class StockAnalysisAccountPercentSensor(StockAnalysisAccountBaseSensor):
    """A per-account sensor expressed as a percentage."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 2
