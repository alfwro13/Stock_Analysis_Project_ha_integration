"""Tests for StockAnalysisDataUpdateCoordinator."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from homeassistant.util import dt as dt_util

from custom_components.stock_analysis_project import StockAnalysisDataUpdateCoordinator
from custom_components.stock_analysis_project.api import StockAnalysisAPIError, StockAnalysisAuthError
from custom_components.stock_analysis_project.const import DOMAIN

from .conftest import (
    SAMPLE_CONFIG,
    SAMPLE_MARKET_STATUS,
    SAMPLE_MARKET_STATUS_CLOSED,
    SAMPLE_PORTFOLIO_TOTALS,
    SAMPLE_PORTFOLIO_TOTALS_EMPTY,
)


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_api) -> StockAnalysisDataUpdateCoordinator:
    """Return a coordinator wired to the mock API (not yet refreshed)."""
    entry = MockConfigEntry(domain=DOMAIN, data=SAMPLE_CONFIG)
    entry.add_to_hass(hass)
    return StockAnalysisDataUpdateCoordinator(hass, mock_api, 15, entry)


async def test_first_refresh_populates_all_fields(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator
) -> None:
    """First refresh populates all 10 portfolio-total fields correctly."""
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    data = coordinator.data
    assert data is not None
    assert data["server_online"] is True
    assert data["portfolio_totals"] == SAMPLE_PORTFOLIO_TOTALS
    assert data["market_status"] == SAMPLE_MARKET_STATUS

    totals = data["portfolio_totals"]
    for field in (
        "total_investment",
        "current_value",
        "portfolio_gain",
        "portfolio_gain_fx",
        "portfolio_dividends",
        "unrealized_pnl",
        "unrealized_pnl_pct",
        "portfolio_gain_pct",
        "twr_pct",
        "twr_fx_pct",
    ):
        assert field in totals


async def test_api_error_marks_server_offline(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator, mock_api
) -> None:
    """StockAnalysisAPIError leads to last_update_success False (server_online reads False)."""
    mock_api.get_portfolio_totals = AsyncMock(side_effect=StockAnalysisAPIError("connection refused"))

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    # Coordinator keeps last-known data (None here, since this was the first refresh).
    assert coordinator.data is None


async def test_auth_error_raises_config_entry_auth_failed(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator, mock_api
) -> None:
    """StockAnalysisAuthError maps to ConfigEntryAuthFailed."""
    mock_api.get_portfolio_totals = AsyncMock(side_effect=StockAnalysisAuthError("invalid key"))

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_zero_accounts_percent_fields_are_none(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator, mock_api
) -> None:
    """Zero-Trading-accounts fixture: percent/TWR fields are None, not an exception."""
    mock_api.get_portfolio_totals = AsyncMock(return_value=SAMPLE_PORTFOLIO_TOTALS_EMPTY)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    totals = coordinator.data["portfolio_totals"]
    assert totals["portfolio_gain_pct"] is None
    assert totals["unrealized_pnl_pct"] is None
    assert totals["twr_pct"] is None
    assert totals["twr_fx_pct"] is None


async def test_refresh_interval_change_reschedules(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator
) -> None:
    """Changing update_interval via async_set_update_interval reschedules the timer.

    DataUpdateCoordinator's update_interval setter alone does NOT cancel/reschedule
    the pending timer -- but requesting an immediate refresh does: _async_refresh()
    unsubscribes the old timer at entry and re-arms it via _schedule_refresh() in its
    finally block, picking up whatever interval is set by then.
    """
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(minutes=15)

    # Register a listener so _schedule_refresh actually arms a timer.
    coordinator.async_add_listener(lambda: None)
    assert coordinator._unsub_refresh is not None
    old_unsub = coordinator._unsub_refresh

    await coordinator.async_set_update_interval(5)

    assert coordinator.update_interval == timedelta(minutes=5)
    # The old timer handle was cancelled and replaced with a new one.
    assert coordinator._unsub_refresh is not None
    assert coordinator._unsub_refresh is not old_unsub

    # Advance time by the new (shorter) interval and confirm a refresh actually fires.
    call_count_before = coordinator.api.get_portfolio_totals.call_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()
    assert coordinator.api.get_portfolio_totals.call_count > call_count_before

    await coordinator.async_shutdown()


async def test_disable_auto_refresh_suspends_timer(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator
) -> None:
    """Disabling auto-refresh unsubscribes the coordinator's internal polling timer."""
    await coordinator.async_refresh()
    coordinator.async_add_listener(lambda: None)
    assert coordinator._unsub_refresh is not None

    await coordinator.async_set_auto_refresh_enabled(False)

    assert coordinator.auto_refresh_enabled is False
    assert coordinator._unsub_refresh is None

    # Advancing time must NOT trigger a refresh while disabled.
    call_count_before = coordinator.api.get_portfolio_totals.call_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=30))
    await hass.async_block_till_done()
    assert coordinator.api.get_portfolio_totals.call_count == call_count_before


async def test_enable_auto_refresh_resumes_immediately(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator
) -> None:
    """Re-enabling auto-refresh triggers an immediate refresh, not waiting for the next tick."""
    await coordinator.async_refresh()
    coordinator.async_add_listener(lambda: None)
    await coordinator.async_set_auto_refresh_enabled(False)

    call_count_before = coordinator.api.get_portfolio_totals.call_count
    await coordinator.async_set_auto_refresh_enabled(True)

    assert coordinator.auto_refresh_enabled is True
    assert coordinator.api.get_portfolio_totals.call_count > call_count_before
    assert coordinator._unsub_refresh is not None

    await coordinator.async_shutdown()


async def test_show_portfolio_totals_disabled_skips_fetch(hass: HomeAssistant, mock_api) -> None:
    """CONF_SHOW_PORTFOLIO_TOTALS=False means the coordinator never awaits get_portfolio_totals."""
    entry = MockConfigEntry(domain=DOMAIN, data={**SAMPLE_CONFIG, "show_portfolio_totals": False})
    entry.add_to_hass(hass)
    coordinator = StockAnalysisDataUpdateCoordinator(hass, mock_api, 15, entry)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data["portfolio_totals"] == {}
    mock_api.get_portfolio_totals.assert_not_awaited()

    await coordinator.async_shutdown()


async def test_show_holdings_disabled_skips_fetch(hass: HomeAssistant, mock_api) -> None:
    """CONF_SHOW_HOLDINGS=False means the coordinator never awaits get_holdings."""
    entry = MockConfigEntry(domain=DOMAIN, data={**SAMPLE_CONFIG, "show_holdings": False})
    entry.add_to_hass(hass)
    coordinator = StockAnalysisDataUpdateCoordinator(hass, mock_api, 15, entry)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data["holdings"] == {"base_currency": None, "holdings": []}
    mock_api.get_holdings.assert_not_awaited()

    await coordinator.async_shutdown()


async def test_first_refresh_always_fetches_even_if_markets_closed(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator, mock_api
) -> None:
    """There's no prior data to reuse on the very first refresh, so it always fetches
    everything regardless of market status."""
    mock_api.get_market_status = AsyncMock(return_value=SAMPLE_MARKET_STATUS_CLOSED)

    await coordinator.async_refresh()

    mock_api.get_portfolio_totals.assert_awaited_once()
    mock_api.get_account_metrics.assert_awaited_once()
    mock_api.get_holdings.assert_awaited_once()
    mock_api.get_other_accounts.assert_awaited_once()


async def test_markets_closed_skips_trading_fetches_on_second_refresh(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator, mock_api
) -> None:
    """Once there's prior data, a refresh with both markets closed reuses the previous
    portfolio/account/holdings data instead of re-fetching it — prices can't have changed.
    Other Accounts is unaffected, since it isn't tied to stock market hours."""
    await coordinator.async_refresh()
    mock_api.get_market_status = AsyncMock(return_value=SAMPLE_MARKET_STATUS_CLOSED)

    portfolio_calls_before = mock_api.get_portfolio_totals.call_count
    account_calls_before = mock_api.get_account_metrics.call_count
    holdings_calls_before = mock_api.get_holdings.call_count
    other_calls_before = mock_api.get_other_accounts.call_count

    await coordinator.async_refresh()

    assert mock_api.get_portfolio_totals.call_count == portfolio_calls_before
    assert mock_api.get_account_metrics.call_count == account_calls_before
    assert mock_api.get_holdings.call_count == holdings_calls_before
    assert mock_api.get_other_accounts.call_count == other_calls_before + 1
    assert coordinator.data["portfolio_totals"] == SAMPLE_PORTFOLIO_TOTALS


async def test_markets_open_always_fetches_trading_data(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator, mock_api
) -> None:
    """With at least one market open (the default SAMPLE_MARKET_STATUS fixture), a second
    refresh still re-fetches the trading-related data."""
    await coordinator.async_refresh()
    calls_before = mock_api.get_portfolio_totals.call_count

    await coordinator.async_refresh()

    assert mock_api.get_portfolio_totals.call_count > calls_before


async def test_skip_toggle_disabled_always_fetches_regardless_of_market_status(
    hass: HomeAssistant, mock_api
) -> None:
    """skip_refresh_when_markets_closed=False keeps fetching every tick even with both markets
    closed."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={**SAMPLE_CONFIG, "skip_refresh_when_markets_closed": False}
    )
    entry.add_to_hass(hass)
    coordinator = StockAnalysisDataUpdateCoordinator(hass, mock_api, 15, entry)
    mock_api.get_market_status = AsyncMock(return_value=SAMPLE_MARKET_STATUS_CLOSED)

    await coordinator.async_refresh()
    calls_before = mock_api.get_portfolio_totals.call_count

    await coordinator.async_refresh()

    assert mock_api.get_portfolio_totals.call_count > calls_before
    await coordinator.async_shutdown()


async def test_show_other_accounts_disabled_skips_fetch(hass: HomeAssistant, mock_api) -> None:
    """CONF_SHOW_OTHER_ACCOUNTS=False means the coordinator never awaits get_other_accounts."""
    entry = MockConfigEntry(domain=DOMAIN, data={**SAMPLE_CONFIG, "show_other_accounts": False})
    entry.add_to_hass(hass)
    coordinator = StockAnalysisDataUpdateCoordinator(hass, mock_api, 15, entry)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data["other_accounts"] == {"base_currency": None, "accounts": []}
    mock_api.get_other_accounts.assert_not_awaited()

    await coordinator.async_shutdown()


async def test_refresh_button_flow_calls_trigger_then_refresh(
    hass: HomeAssistant, coordinator: StockAnalysisDataUpdateCoordinator, mock_api
) -> None:
    """The Refresh Data button flow: trigger_refresh_now() then async_request_refresh()."""
    await coordinator.async_refresh()

    call_count_before = mock_api.get_portfolio_totals.call_count
    await mock_api.trigger_refresh_now()
    await coordinator.async_request_refresh()

    mock_api.trigger_refresh_now.assert_called_once()
    assert mock_api.get_portfolio_totals.call_count > call_count_before

    await coordinator.async_shutdown()
