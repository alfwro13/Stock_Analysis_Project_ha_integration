"""The Stock Analysis Project integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import StockAnalysisAPI, StockAnalysisAPIError, StockAnalysisAuthError
from .const import CONF_API_KEY, CONF_BASE_URL, CONF_UPDATE_INTERVAL, CONF_VERIFY_SSL, DEFAULT_UPDATE_INTERVAL, DOMAIN

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
            portfolio_totals = await self.api.get_portfolio_totals()
            market_status = await self.api.get_market_status()
        except StockAnalysisAuthError as err:
            raise ConfigEntryAuthFailed("Invalid API key") from err
        except StockAnalysisAPIError as err:
            raise UpdateFailed(f"Stock Analysis Project API update failed: {err}") from err

        return {
            "server_online": True,
            "portfolio_totals": portfolio_totals,
            "market_status": market_status,
        }

    async def async_prune_orphans(self) -> None:
        """Remove entities that no longer correspond to a valid unique_id."""
        entity_registry = er.async_get(self.hass)
        entries = er.async_entries_for_config_entry(entity_registry, self.entry.entry_id)

        entry_id = self.entry.entry_id
        valid_unique_ids = {
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

        for entity_entry in entries:
            if entity_entry.unique_id not in valid_unique_ids:
                entity_registry.async_remove(entity_entry.entity_id)


type StockAnalysisConfigEntry = ConfigEntry[StockAnalysisDataUpdateCoordinator]
