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

    assert by_platform.get("sensor") == 39  # 10 portfolio + 24 account (2x12) + 3 holdings + 2 other accounts
    assert by_platform.get("binary_sensor") == 5
    assert by_platform.get("switch") == 1
    assert by_platform.get("number") == 7  # 1 refresh interval + 3 holdings x 2 limit numbers
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


async def test_prune_orphans_removes_deleted_account_sensors(hass: HomeAssistant, mock_api) -> None:
    """After an account disappears from a refresh, prune removes only that account's 12 entities."""
    from unittest.mock import AsyncMock

    from .conftest import SAMPLE_ACCOUNT_METRICS

    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    remaining_account, removed_account = SAMPLE_ACCOUNT_METRICS["accounts"]

    mock_api.get_account_metrics = AsyncMock(
        return_value={
            "status": "success",
            "base_currency": "GBP",
            "accounts": [remaining_account],
        }
    )
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    await coordinator.async_prune_orphans()
    await hass.async_block_till_done()

    registered_ids = {
        e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    account_keys = (
        "cash_balance", "gain_1d", "gain_1w", "gain_1m", "gain_3m", "gain_1y",
        "equity_value", "realized_pnl", "unrealized_pnl", "dividend_income",
        "interest_income", "mwrr_pct",
    )

    for key in account_keys:
        assert f"sap_{key}_{remaining_account['account_id']}_{entry.entry_id}" in registered_ids
        assert f"sap_{key}_{removed_account['account_id']}_{entry.entry_id}" not in registered_ids


async def test_disabling_show_accounts_via_reload_auto_removes_account_sensors(
    hass: HomeAssistant, mock_api
) -> None:
    """Reconfigure always reloads the entry (unload + async_setup_entry re-running), and
    async_setup_entry prunes on every run — so disabling Show Account Totals removes the
    account sensors on reload, with no manual Prune Orphaned Entities press needed."""
    from .conftest import SAMPLE_ACCOUNT_METRICS

    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    account_entities_before = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor" and e.unique_id.startswith("sap_cash_balance_")
    ]
    assert len(account_entities_before) == 2

    account_ids = [acc["account_id"] for acc in SAMPLE_ACCOUNT_METRICS["accounts"]]
    for account_id in account_ids:
        assert device_registry.async_get_device(
            identifiers={(DOMAIN, f"sap_account_{account_id}_{entry.entry_id}")}
        ) is not None

    hass.config_entries.async_update_entry(entry, data={**entry.data, "show_accounts": False})
    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api,
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    account_entities_after = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor" and e.unique_id.startswith("sap_cash_balance_")
    ]
    assert len(account_entities_after) == 0

    for account_id in account_ids:
        assert device_registry.async_get_device(
            identifiers={(DOMAIN, f"sap_account_{account_id}_{entry.entry_id}")}
        ) is None

    # Portfolio and Diagnostics devices are unaffected by this toggle.
    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_portfolio_{entry.entry_id}")}
    ) is not None
    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_diagnostics_{entry.entry_id}")}
    ) is not None


async def test_disabling_show_portfolio_totals_via_reload_auto_removes_portfolio_sensors(
    hass: HomeAssistant, mock_api
) -> None:
    """Same auto-prune-on-reload behavior for the Show Portfolio Totals toggle."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    portfolio_entities_before = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor" and e.unique_id.startswith("sap_portfolio_")
    ]
    assert len(portfolio_entities_before) == 10

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "show_portfolio_totals": False}
    )
    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api,
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    portfolio_entities_after = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor" and e.unique_id.startswith("sap_portfolio_")
    ]
    assert len(portfolio_entities_after) == 0


async def test_prune_orphans_removes_deleted_holding_entities_keeps_device_with_sibling(
    hass: HomeAssistant, mock_api
) -> None:
    """After one holding disappears from a refresh, prune removes its sensor and both number
    entities, but its account's Holdings device stays — a sibling holding in the same account
    (GIA's VWRL.L) still has valid entities referencing that shared device."""
    from unittest.mock import AsyncMock

    from .conftest import SAMPLE_HOLDINGS

    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    isa_aapl, gia_aapl, gia_vwrl = SAMPLE_HOLDINGS["holdings"]

    mock_api.get_holdings = AsyncMock(
        return_value={
            "status": "success",
            "base_currency": "GBP",
            "holdings": [isa_aapl, gia_vwrl],
        }
    )
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    await coordinator.async_prune_orphans()
    await hass.async_block_till_done()

    registered_ids = {
        e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    for key in ("market_value", "low_limit", "high_limit"):
        assert f"sap_holding_{key}_{isa_aapl['account_id']}_AAPL_{entry.entry_id}" in registered_ids
        assert f"sap_holding_{key}_{gia_vwrl['account_id']}_VWRL.L_{entry.entry_id}" in registered_ids
        assert f"sap_holding_{key}_{gia_aapl['account_id']}_AAPL_{entry.entry_id}" not in registered_ids

    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_account_holdings_{gia_aapl['account_id']}_{entry.entry_id}")}
    ) is not None, "GIA's Holdings device must survive — VWRL.L still lives on it"
    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_account_holdings_{isa_aapl['account_id']}_{entry.entry_id}")}
    ) is not None


async def test_prune_orphans_removes_holdings_device_when_account_has_no_holdings_left(
    hass: HomeAssistant, mock_api
) -> None:
    """When every holding in an account disappears from a refresh, prune removes that account's
    Holdings device entirely, while a sibling account's Holdings device is untouched."""
    from unittest.mock import AsyncMock

    from .conftest import SAMPLE_HOLDINGS

    entry = await _setup(hass, mock_api)
    device_registry = dr.async_get(hass)

    isa_aapl, gia_aapl, gia_vwrl = SAMPLE_HOLDINGS["holdings"]
    assert gia_aapl["account_id"] == gia_vwrl["account_id"]

    mock_api.get_holdings = AsyncMock(
        return_value={
            "status": "success",
            "base_currency": "GBP",
            "holdings": [isa_aapl],
        }
    )
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    await coordinator.async_prune_orphans()
    await hass.async_block_till_done()

    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_account_holdings_{gia_aapl['account_id']}_{entry.entry_id}")}
    ) is None
    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_account_holdings_{isa_aapl['account_id']}_{entry.entry_id}")}
    ) is not None


async def test_disabling_show_holdings_via_reload_auto_removes_holding_entities(
    hass: HomeAssistant, mock_api
) -> None:
    """Same auto-prune-on-reload behavior for the Show Holdings toggle."""
    from .conftest import SAMPLE_HOLDINGS

    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    holding_entities_before = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id.startswith("sap_holding_market_value_")
    ]
    assert len(holding_entities_before) == 3

    hass.config_entries.async_update_entry(entry, data={**entry.data, "show_holdings": False})
    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api,
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    holding_entities_after = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id.startswith("sap_holding_market_value_") or e.unique_id.startswith("sap_holding_low_limit_")
        or e.unique_id.startswith("sap_holding_high_limit_")
    ]
    assert len(holding_entities_after) == 0

    for account_id in {h["account_id"] for h in SAMPLE_HOLDINGS["holdings"]}:
        assert device_registry.async_get_device(
            identifiers={(DOMAIN, f"sap_account_holdings_{account_id}_{entry.entry_id}")}
        ) is None


async def test_prune_orphans_removes_deleted_other_account_entity_keeps_device_with_sibling(
    hass: HomeAssistant, mock_api
) -> None:
    """After one Pension/House account disappears from a refresh, prune removes its own sensor,
    but the shared "Other Accounts" device stays — the sibling account still has a valid entity
    referencing it."""
    from unittest.mock import AsyncMock

    from .conftest import SAMPLE_OTHER_ACCOUNTS

    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    pension_row, house_row = SAMPLE_OTHER_ACCOUNTS["accounts"]

    mock_api.get_other_accounts = AsyncMock(
        return_value={"status": "success", "base_currency": "GBP", "accounts": [pension_row]}
    )
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    await coordinator.async_prune_orphans()
    await hass.async_block_till_done()

    registered_ids = {
        e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert f"sap_other_account_value_{pension_row['account_id']}_{entry.entry_id}" in registered_ids
    assert f"sap_other_account_value_{house_row['account_id']}_{entry.entry_id}" not in registered_ids

    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_other_accounts_{entry.entry_id}")}
    ) is not None, "Other Accounts device must survive — the Pension account still lives on it"


async def test_disabling_show_other_accounts_via_reload_auto_removes_entities_and_device(
    hass: HomeAssistant, mock_api
) -> None:
    """Same auto-prune-on-reload behavior for the Show Other Accounts toggle: disabling it
    removes every Other Accounts sensor and the shared device itself, since none of its
    siblings survive either."""
    from .conftest import SAMPLE_OTHER_ACCOUNTS

    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    other_entities_before = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id.startswith("sap_other_account_value_")
    ]
    assert len(other_entities_before) == 2
    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_other_accounts_{entry.entry_id}")}
    ) is not None

    hass.config_entries.async_update_entry(entry, data={**entry.data, "show_other_accounts": False})
    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api,
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    other_entities_after = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id.startswith("sap_other_account_value_")
    ]
    assert len(other_entities_after) == 0
    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_other_accounts_{entry.entry_id}")}
    ) is None

    # Unrelated devices are unaffected.
    assert device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_portfolio_{entry.entry_id}")}
    ) is not None
