"""Diagnostics support for the Stock Analysis Project integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import StockAnalysisConfigEntry
from .const import CONF_API_KEY

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: StockAnalysisConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    config = async_redact_data(dict(entry.data), TO_REDACT)

    data = coordinator.data or {}
    coord_state: dict[str, Any] = {
        "last_update_success": coordinator.last_update_success,
        "auto_refresh_enabled": coordinator.auto_refresh_enabled,
        "server_online": data.get("server_online", False),
        "portfolio_totals": data.get("portfolio_totals", {}),
        "market_status": data.get("market_status", {}),
    }

    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    entity_summary: dict[str, Any] = {
        "total": len(entries),
        "by_platform": {},
    }
    for entity_entry in entries:
        platform = entity_entry.domain
        entity_summary["by_platform"][platform] = entity_summary["by_platform"].get(platform, 0) + 1

    return {
        "config": config,
        "coordinator": coord_state,
        "entities": entity_summary,
    }
