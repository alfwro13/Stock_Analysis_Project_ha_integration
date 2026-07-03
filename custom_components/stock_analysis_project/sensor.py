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
    CONF_SHOW_HOLDINGS,
    CONF_SHOW_PORTFOLIO_TOTALS,
    account_device_info,
    account_holdings_device_info,
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

    known_holding_ids: set[str] = set()

    @callback
    def _update_holding_sensors() -> None:
        """Add a sensor for any (account_id, ticker) holding not yet represented as an entity."""
        if not config_entry.data.get(CONF_SHOW_HOLDINGS, True):
            return
        if not coordinator.data:
            return
        holdings = coordinator.data.get("holdings", {}).get("holdings", []) or []
        new_entities: list[SensorEntity] = []
        for h in holdings:
            unique_id = f"sap_holding_market_value_{h['account_id']}_{h['ticker']}_{config_entry.entry_id}"
            if unique_id not in known_holding_ids:
                known_holding_ids.add(unique_id)
                new_entities.append(
                    StockAnalysisHoldingSensor(
                        coordinator, config_entry, h["account_id"], h["account_name"], h["ticker"]
                    )
                )
        if new_entities:
            async_add_entities(new_entities)

    config_entry.async_on_unload(coordinator.async_add_listener(_update_holding_sensors))
    _update_holding_sensors()


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


class StockAnalysisHoldingSensor(CoordinatorEntity, SensorEntity):
    """One sensor per (account, ticker) holding — state is market value in the portfolio's base
    currency, all other Ghostfolio-style fields plus RSI/trend/earnings/limits are exposed as
    attributes rather than as separate entities. Lives on the shared per-account Holdings device
    alongside every other holding in that account, so the entity name is ticker-prefixed to stay
    distinguishable from sibling holdings on the same device."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: StockAnalysisDataUpdateCoordinator,
        config_entry: ConfigEntry,
        account_id: int,
        account_name: str,
        ticker: str,
    ) -> None:
        """Initialize the per-holding sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._account_id = account_id
        self._ticker = ticker
        self._attr_name = f"{ticker} Market Value"
        self._attr_unique_id = f"sap_holding_market_value_{account_id}_{ticker}_{config_entry.entry_id}"
        self._attr_device_info = account_holdings_device_info(config_entry, account_id, account_name)

    @property
    def _holding(self) -> dict[str, Any]:
        """Return this sensor's holding row from the latest fetch, or {} if not found yet."""
        if not self.coordinator.data:
            return {}
        holdings = self.coordinator.data.get("holdings", {}).get("holdings", []) or []
        for row in holdings:
            if row.get("account_id") == self._account_id and row.get("ticker") == self._ticker:
                return row
        return {}

    @property
    def native_value(self) -> float | None:
        """Return the holding's market value in the portfolio's base currency."""
        return self._holding.get("market_value")

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the portfolio's base currency."""
        if not self.coordinator.data:
            return "GBP"
        return self.coordinator.data.get("holdings", {}).get("base_currency") or "GBP"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full Ghostfolio-style attribute set plus RSI/trend/earnings/limits."""
        h = self._holding
        if not h:
            return {}
        return {
            "ticker": h.get("ticker"),
            "account": h.get("account_name"),
            "number_of_shares": h.get("shares"),
            "currency_asset": h.get("currency_asset"),
            "currency_base": h.get("currency_base"),
            "market_price": h.get("market_price"),
            "market_price_currency": h.get("market_price_currency"),
            "market_price_in_base_currency": h.get("market_price_in_base_currency"),
            "average_buy_price": h.get("average_buy_price"),
            "average_buy_price_currency": h.get("average_buy_price_currency"),
            "gain_value": h.get("gain_value"),
            "gain_value_currency": h.get("gain_value_currency"),
            "gain_pct": h.get("gain_pct"),
            "accumulated_dividends": h.get("accumulated_dividends"),
            "accumulated_dividends_currency": h.get("accumulated_dividends_currency"),
            "trend_vs_buy": h.get("trend_vs_buy"),
            "asset_class": h.get("asset_class"),
            "data_source": h.get("data_source"),
            "market_change_24h": h.get("market_change_24h"),
            "market_change_pct_24h": h.get("market_change_pct_24h"),
            "low_limit_set": h.get("low_limit_set"),
            "low_limit_reached": h.get("low_limit_reached"),
            "high_limit_set": h.get("high_limit_set"),
            "high_limit_reached": h.get("high_limit_reached"),
            "profit_and_loss": h.get("profit_and_loss"),
            "rsi": h.get("rsi"),
            "trend_50d": h.get("trend_50d"),
            "trend_200d": h.get("trend_200d"),
            "next_earnings_date": h.get("next_earnings_date"),
        }
