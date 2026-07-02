"""Tests for integration setup, unload, and entity/device registration."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stock_analysis_project.const import DOMAIN

from .conftest import SAMPLE_CONFIG


async def _setup(hass: HomeAssistant, api) -> MockConfigEntry:
    """Helper: add a config entry and set up the integration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=SAMPLE_CONFIG,
        title="Stock Analysis Project",
        unique_id=SAMPLE_CONFIG["base_url"],
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=api,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_setup_and_unload(hass: HomeAssistant, mock_api) -> None:
    """Integration loads successfully and unloads cleanly, closing the API session."""
    entry = await _setup(hass, mock_api)

    assert entry.state.value == "loaded"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.value == "not_loaded"
    mock_api.close.assert_called_once()


EXPECTED_UNIQUE_IDS = [
    "sap_portfolio_cost_{eid}",
    "sap_portfolio_value_{eid}",
    "sap_portfolio_gain_{eid}",
    "sap_portfolio_gain_fx_{eid}",
    "sap_portfolio_total_dividend_{eid}",
    "sap_portfolio_unrealized_pnl_{eid}",
    "sap_portfolio_unrealized_pnl_pct_{eid}",
    "sap_portfolio_simple_gain_pct_{eid}",
    "sap_portfolio_twr_pct_{eid}",
    "sap_portfolio_twr_fx_pct_{eid}",
    "sap_server_status_{eid}",
    "sap_yahoo_status_{eid}",
    "sap_us_market_open_{eid}",
    "sap_uk_market_open_{eid}",
    "sap_system_status_{eid}",
    "sap_enable_auto_refresh_{eid}",
    "sap_refresh_interval_{eid}",
    "sap_refresh_data_{eid}",
    "sap_prune_orphans_{eid}",
]


async def test_all_entities_registered_with_correct_unique_ids(hass: HomeAssistant, mock_api) -> None:
    """All 19 entities are registered with the exact unique_ids from the spec."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    registered_ids = {
        e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    expected_ids = {tmpl.format(eid=entry.entry_id) for tmpl in EXPECTED_UNIQUE_IDS}
    assert expected_ids.issubset(registered_ids)


async def test_platform_entity_counts(hass: HomeAssistant, mock_api) -> None:
    """Each platform gets its expected entity count."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)

    by_platform: dict[str, int] = {}
    for e in entries:
        by_platform[e.domain] = by_platform.get(e.domain, 0) + 1

    assert by_platform.get("sensor") == 10
    assert by_platform.get("binary_sensor") == 5
    assert by_platform.get("switch") == 1
    assert by_platform.get("number") == 1
    assert by_platform.get("button") == 2


async def test_devices_created_with_via_device_linkage(hass: HomeAssistant, mock_api) -> None:
    """Portfolio and Diagnostics devices are both created, Diagnostics linked via_device."""
    entry = await _setup(hass, mock_api)
    device_registry = dr.async_get(hass)

    portfolio_device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_portfolio_{entry.entry_id}")}
    )
    diagnostics_device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_diagnostics_{entry.entry_id}")}
    )

    assert portfolio_device is not None
    assert diagnostics_device is not None
    assert diagnostics_device.via_device_id == portfolio_device.id


async def test_portfolio_value_sensor_state(hass: HomeAssistant, mock_api) -> None:
    """Portfolio Value sensor reports the expected state from the mock API."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    portfolio_value_entity = next(
        (
            e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.unique_id == f"sap_portfolio_value_{entry.entry_id}"
        ),
        None,
    )
    assert portfolio_value_entity is not None

    state = hass.states.get(portfolio_value_entity.entity_id)
    assert state is not None
    assert float(state.state) == pytest.approx(128430.55)


async def test_server_status_binary_sensor_state(hass: HomeAssistant, mock_api) -> None:
    """Server Status binary_sensor reports 'on' when the API succeeds."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    server_entity = next(
        (
            e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.unique_id == f"sap_server_status_{entry.entry_id}"
        ),
        None,
    )
    assert server_entity is not None

    state = hass.states.get(server_entity.entity_id)
    assert state is not None
    assert state.state == "on"


async def test_zero_accounts_percent_sensor_is_unknown(hass: HomeAssistant, mock_api) -> None:
    """With the zero-accounts fixture, percent/TWR sensors render as 'unknown', not raise."""
    from unittest.mock import AsyncMock

    from .conftest import SAMPLE_PORTFOLIO_TOTALS_EMPTY

    mock_api.get_portfolio_totals = AsyncMock(return_value=SAMPLE_PORTFOLIO_TOTALS_EMPTY)
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    twr_entity = next(
        (
            e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.unique_id == f"sap_portfolio_twr_pct_{entry.entry_id}"
        ),
        None,
    )
    assert twr_entity is not None

    state = hass.states.get(twr_entity.entity_id)
    assert state is not None
    assert state.state == "unknown"
