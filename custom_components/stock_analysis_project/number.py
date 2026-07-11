"""Number platform for Stock Analysis Project integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, RestoreNumber
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StockAnalysisConfigEntry, StockAnalysisDataUpdateCoordinator
from .const import (
    CONF_SHOW_HOLDINGS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    account_holdings_device_info,
    portfolio_device_info,
)

_HOLDING_LIMIT_NUMBERS: list[tuple[str, str, str]] = [
    ("low_limit", "Low Limit"),
    ("high_limit", "High Limit"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StockAnalysisConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Stock Analysis Project number platform."""
    coordinator = config_entry.runtime_data
    async_add_entities([StockAnalysisRefreshIntervalNumber(coordinator, config_entry)])

    known_ids: set[str] = set()

    @callback
    def _update_holding_limit_numbers() -> None:
        """Add Low/High Limit numbers for any holding not yet represented as entities."""
        if not config_entry.data.get(CONF_SHOW_HOLDINGS, True):
            return
        if not coordinator.data:
            return
        holdings = coordinator.data.get("holdings", {}).get("holdings", []) or []
        new_entities: list[NumberEntity] = []
        for h in holdings:
            account_id, ticker, account_name = h["account_id"], h["ticker"], h["account_name"]
            for limit_key, name in _HOLDING_LIMIT_NUMBERS:
                unique_id = f"sap_holding_{limit_key}_{account_id}_{ticker}_{config_entry.entry_id}"
                if unique_id not in known_ids:
                    known_ids.add(unique_id)
                    new_entities.append(
                        StockAnalysisHoldingLimitNumber(
                            coordinator, config_entry, account_id, account_name, ticker, limit_key, name
                        )
                    )
        if new_entities:
            async_add_entities(new_entities)

    config_entry.async_on_unload(coordinator.async_add_listener(_update_holding_limit_numbers))
    _update_holding_limit_numbers()


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
        """Restore the last known value, falling back to the configured update interval.

        Also re-applies the restored value to the coordinator's actual polling interval —
        without this, the coordinator's timer silently reverts to CONF_UPDATE_INTERVAL (the
        config-flow field) on every HA restart while this entity kept displaying whatever value
        was last set here, so the displayed and effective intervals could disagree indefinitely
        until the user happened to touch this entity again.
        """
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_number_data()) is not None and last_data.native_value is not None:
            self._attr_native_value = last_data.native_value
        else:
            self._attr_native_value = self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self.coordinator.sync_update_interval_from_restore(int(self._attr_native_value))

    async def async_set_native_value(self, value: float) -> None:
        """Update the coordinator's polling interval and reschedule immediately."""
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_set_update_interval(int(value))


class StockAnalysisHoldingLimitNumber(CoordinatorEntity, NumberEntity):
    """A Low/High price-alert limit for one (account, ticker) holding. Unlike
    StockAnalysisRefreshIntervalNumber, the source of truth here is the backend DB
    (holding_price_limits table) via the coordinator, not local HA restore state — the value
    must stay in sync with the same limit shown as an attribute on the holding's Market Value
    sensor, so it is always read fresh from coordinator data rather than cached locally. Lives on
    the shared per-account Holdings device alongside every other holding's entities, so the
    entity name is ticker-prefixed to stay distinguishable from sibling holdings on that device.

    0 means "not set": HA's NumberEntity always carries a concrete float and has no native way to
    submit an explicit null the way the Stock Detail page's Set Targets panel can (blank input).
    Since a real Low/High Limit can never sensibly be 0 (a High Limit of 0 would fire immediately,
    as price is always >= 0), 0 — already the entity's native_min_value — doubles as the "clear
    this limit" sentinel in both directions: dragging the number down to 0 clears the backend
    value, and a cleared/never-set backend value displays as 0 rather than "unknown"."""

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False
    _attr_mode = "box"
    _attr_native_step = 0.01
    _attr_native_min_value = 0
    _attr_native_max_value = 1_000_000

    def __init__(
        self,
        coordinator: StockAnalysisDataUpdateCoordinator,
        config_entry,
        account_id: int,
        account_name: str,
        ticker: str,
        limit_key: str,
        name: str,
    ) -> None:
        """Initialize the holding limit number entity."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._account_id = account_id
        self._ticker = ticker
        self._limit_key = limit_key
        self._attr_name = f"{ticker} {name}"
        self._attr_unique_id = f"sap_holding_{limit_key}_{account_id}_{ticker}_{config_entry.entry_id}"
        self._attr_device_info = account_holdings_device_info(config_entry, account_id, account_name)

    @property
    def _holding(self) -> dict[str, Any]:
        """Return this number's holding row from the latest fetch, or {} if not found yet."""
        if not self.coordinator.data:
            return {}
        holdings = self.coordinator.data.get("holdings", {}).get("holdings", []) or []
        for row in holdings:
            if row.get("account_id") == self._account_id and row.get("ticker") == self._ticker:
                return row
        return {}

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the holding's native asset currency — limits are set in native price terms."""
        return self._holding.get("market_price_currency")

    @property
    def native_value(self) -> float | None:
        """Return the currently stored limit value from the backend, or 0 if unset/cleared."""
        return self._holding.get(self._limit_key) or 0

    async def async_set_native_value(self, value: float) -> None:
        """Push the new limit value to the backend, then refresh so native_value reflects it.
        A value of 0 clears the limit (sent as None) rather than storing a literal 0 threshold."""
        kwargs = {self._limit_key: value if value > 0 else None}
        await self.coordinator.api.set_holding_price_limit(self._account_id, self._ticker, **kwargs)
        await self.coordinator.async_request_refresh()
