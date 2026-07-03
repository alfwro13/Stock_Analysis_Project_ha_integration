"""The Stock Analysis Project integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import StockAnalysisAPI, StockAnalysisAPIError, StockAnalysisAuthError
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_SHOW_ACCOUNTS,
    CONF_SHOW_HOLDINGS,
    CONF_SHOW_PORTFOLIO_TOTALS,
    CONF_UPDATE_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: StockAnalysisConfigEntry) -> bool:
    """Set up Stock Analysis Project from a config entry."""
    api = StockAnalysisAPI(
        base_url=entry.data[CONF_BASE_URL],
        api_key=entry.data[CONF_API_KEY],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
    )

    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator = StockAnalysisDataUpdateCoordinator(hass, api, update_interval, entry)

    await coordinator.async_config_entry_first_refresh()

    # Reconfigure always reloads the entry (unload + this function re-running), so pruning here
    # is what makes disabling a "Show ..." toggle actually remove its entities instead of just
    # leaving them unavailable — no need to wait for a manual "Prune Orphaned Entities" press.
    await coordinator.async_prune_orphans()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: StockAnalysisConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.api.close()
    return unloaded


class StockAnalysisDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Stock Analysis Project data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: StockAnalysisAPI,
        update_interval_minutes: int,
        entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=update_interval_minutes),
        )
        self.api = api
        self.entry = entry

        self._store = Store(hass, 1, f"{DOMAIN}_state_{entry.entry_id}")
        self.auto_refresh_enabled = True
        self._state_loaded = False

    async def _async_load_state(self) -> None:
        """Load persisted coordinator state from HA storage, once."""
        if self._state_loaded:
            return
        self._state_loaded = True
        stored = await self._store.async_load()
        if stored:
            self.auto_refresh_enabled = stored.get("auto_refresh_enabled", True)

    async def _save_state(self) -> None:
        """Persist coordinator state to HA storage."""
        await self._store.async_save({"auto_refresh_enabled": self.auto_refresh_enabled})

    def _schedule_refresh(self) -> None:
        """Override to suppress timer scheduling when auto-refresh is disabled."""
        if self.auto_refresh_enabled:
            super()._schedule_refresh()

    async def async_set_auto_refresh_enabled(self, enabled: bool) -> None:
        """Enable or disable automatic polling and persist the state."""
        self.auto_refresh_enabled = enabled
        await self._save_state()
        if not enabled:
            if self._unsub_refresh:
                self._unsub_refresh()
                self._unsub_refresh = None
        else:
            await self.async_request_refresh()

    async def async_set_update_interval(self, minutes: int) -> None:
        """Change the polling interval at runtime and reschedule immediately."""
        self.update_interval = timedelta(minutes=minutes)
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None
        self._schedule_refresh()
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict:
        """Fetch portfolio totals and market status from the backend."""
        await self._async_load_state()

        try:
            portfolio_totals = (
                await self.api.get_portfolio_totals()
                if self.entry.data.get(CONF_SHOW_PORTFOLIO_TOTALS, True)
                else {}
            )
            market_status = await self.api.get_market_status()
            account_metrics = (
                await self.api.get_account_metrics()
                if self.entry.data.get(CONF_SHOW_ACCOUNTS, True)
                else {"base_currency": None, "accounts": []}
            )
            holdings = (
                await self.api.get_holdings()
                if self.entry.data.get(CONF_SHOW_HOLDINGS, True)
                else {"base_currency": None, "holdings": []}
            )
        except StockAnalysisAuthError as err:
            raise ConfigEntryAuthFailed("Invalid API key") from err
        except StockAnalysisAPIError as err:
            raise UpdateFailed(f"Stock Analysis Project API update failed: {err}") from err

        return {
            "server_online": True,
            "portfolio_totals": portfolio_totals,
            "market_status": market_status,
            "account_metrics": account_metrics,
            "holdings": holdings,
        }

    async def async_prune_orphans(self) -> None:
        """Remove entities and devices that no longer correspond to a valid unique_id."""
        entity_registry = er.async_get(self.hass)
        entries = er.async_entries_for_config_entry(entity_registry, self.entry.entry_id)

        entry_id = self.entry.entry_id
        valid_unique_ids = {
            f"sap_server_status_{entry_id}",
            f"sap_yahoo_status_{entry_id}",
            f"sap_us_market_open_{entry_id}",
            f"sap_uk_market_open_{entry_id}",
            f"sap_system_status_{entry_id}",
            f"sap_enable_auto_refresh_{entry_id}",
            f"sap_refresh_interval_{entry_id}",
            f"sap_refresh_data_{entry_id}",
            f"sap_prune_orphans_{entry_id}",
        }

        if self.entry.data.get(CONF_SHOW_PORTFOLIO_TOTALS, True):
            valid_unique_ids.update({
                f"sap_portfolio_cost_{entry_id}",
                f"sap_portfolio_value_{entry_id}",
                f"sap_portfolio_gain_{entry_id}",
                f"sap_portfolio_gain_fx_{entry_id}",
                f"sap_portfolio_total_dividend_{entry_id}",
                f"sap_portfolio_unrealized_pnl_{entry_id}",
                f"sap_portfolio_unrealized_pnl_pct_{entry_id}",
                f"sap_portfolio_simple_gain_pct_{entry_id}",
                f"sap_portfolio_twr_pct_{entry_id}",
                f"sap_portfolio_twr_fx_pct_{entry_id}",
            })

        valid_account_ids: set[int] = set()
        if self.entry.data.get(CONF_SHOW_ACCOUNTS, True):
            for acc in (self.data or {}).get("account_metrics", {}).get("accounts", []):
                valid_account_ids.add(acc["account_id"])

        for account_id in valid_account_ids:
            for key in (
                "cash_balance", "gain_1d", "gain_1w", "gain_1m", "gain_3m", "gain_1y",
                "equity_value", "realized_pnl", "unrealized_pnl", "dividend_income",
                "interest_income", "mwrr_pct",
            ):
                valid_unique_ids.add(f"sap_{key}_{account_id}_{entry_id}")

        valid_holding_keys: set[tuple[int, str]] = set()
        if self.entry.data.get(CONF_SHOW_HOLDINGS, True):
            for h in (self.data or {}).get("holdings", {}).get("holdings", []):
                valid_holding_keys.add((h["account_id"], h["ticker"]))

        for account_id, ticker in valid_holding_keys:
            valid_unique_ids.add(f"sap_holding_market_value_{account_id}_{ticker}_{entry_id}")
            valid_unique_ids.add(f"sap_holding_low_limit_{account_id}_{ticker}_{entry_id}")
            valid_unique_ids.add(f"sap_holding_high_limit_{account_id}_{ticker}_{entry_id}")

        for entity_entry in entries:
            if entity_entry.unique_id not in valid_unique_ids:
                entity_registry.async_remove(entity_entry.entity_id)

        device_registry = dr.async_get(self.hass)
        valid_device_ids = {f"sap_portfolio_{entry_id}", f"sap_diagnostics_{entry_id}"}
        valid_device_ids.update(f"sap_account_{aid}_{entry_id}" for aid in valid_account_ids)
        valid_device_ids.update(
            f"sap_account_holdings_{account_id}_{entry_id}"
            for account_id in {account_id for account_id, _ticker in valid_holding_keys}
        )

        for device_entry in dr.async_entries_for_config_entry(device_registry, entry_id):
            device_ids = {ident for domain, ident in device_entry.identifiers if domain == DOMAIN}
            if device_ids and not device_ids & valid_device_ids:
                device_registry.async_remove_device(device_entry.id)


type StockAnalysisConfigEntry = ConfigEntry[StockAnalysisDataUpdateCoordinator]
