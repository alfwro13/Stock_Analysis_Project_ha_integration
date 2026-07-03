"""Common fixtures for Stock Analysis Project tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stock_analysis_project.const import DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components discoverable in every test without per-test boilerplate."""
    yield


# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = {
    "base_url": "http://sap.local",
    "api_key": "test-api-key",
    "verify_ssl": False,
    "update_interval": 15,
}

SAMPLE_PORTFOLIO_TOTALS = {
    "status": "success",
    "account_count": 3,
    "base_currency": "GBP",
    "as_of": 1751393020.0,
    "current_value": 128430.55,
    "total_investment": 98500.00,
    "portfolio_gain": 27650.20,
    "portfolio_gain_pct": 28.07,
    "portfolio_gain_fx": 29930.55,
    "portfolio_gain_fx_pct": 30.38,
    "unrealized_pnl": 24800.10,
    "unrealized_pnl_pct": 25.18,
    "twr_pct": 20.9,
    "twr_fx_pct": 22.4,
    "portfolio_dividends": 1875.40,
}

SAMPLE_PORTFOLIO_TOTALS_EMPTY = {
    "status": "success",
    "account_count": 0,
    "base_currency": "GBP",
    "as_of": None,
    "current_value": 0,
    "total_investment": 0,
    "portfolio_gain": 0,
    "portfolio_gain_pct": None,
    "portfolio_gain_fx": 0,
    "portfolio_gain_fx_pct": None,
    "unrealized_pnl": 0,
    "unrealized_pnl_pct": None,
    "twr_pct": None,
    "twr_fx_pct": None,
    "portfolio_dividends": 0,
}

SAMPLE_MARKET_STATUS = {
    "status": "success",
    "us_market_open": True,
    "uk_market_open": False,
    "yahoo_ok": True,
    "system_ok": True,
}

SAMPLE_ACCOUNT_METRICS = {
    "status": "success",
    "base_currency": "GBP",
    "accounts": [
        {
            "account_id": 3,
            "name": "ISA",
            "cash_balance": 512.68,
            "equity_value": 9840.20,
            "unrealized_pnl": 1120.40,
            "realized_pnl": 340.00,
            "dividend_income": 84.30,
            "interest_income": 12.50,
            "gain_1d": 45.10,
            "gain_1w": 120.60,
            "gain_1m": 310.20,
            "gain_3m": 890.15,
            "gain_1y": 2140.00,
            "mwrr_pct": 18.4,
        },
        {
            "account_id": 7,
            "name": "GIA",
            "cash_balance": 203.11,
            "equity_value": 4310.75,
            "unrealized_pnl": -210.55,
            "realized_pnl": 95.20,
            "dividend_income": 22.60,
            "interest_income": 4.15,
            "gain_1d": -12.30,
            "gain_1w": 33.40,
            "gain_1m": -88.90,
            "gain_3m": 205.65,
            "gain_1y": 610.30,
            "mwrr_pct": 7.9,
        },
    ],
}

SAMPLE_ACCOUNT_METRICS_EMPTY = {
    "status": "success",
    "base_currency": "GBP",
    "accounts": [],
}

SAMPLE_HOLDINGS = {
    "status": "success",
    "base_currency": "GBP",
    "holdings": [
        {
            "account_id": 3, "account_name": "ISA", "ticker": "AAPL", "company_name": "Apple Inc.",
            "shares": 10.0, "currency_asset": "USD", "currency_base": "GBP",
            "market_price": 195.20, "market_price_currency": "USD",
            "market_price_in_base_currency": 154.30,
            "average_buy_price": 140.00, "average_buy_price_currency": "GBP",
            "market_value": 1543.00, "total_investment": 1400.00,
            "gain_value": 143.00, "gain_value_currency": "GBP", "gain_pct": 10.21,
            "profit_and_loss": 143.00,
            "accumulated_dividends": 12.40, "accumulated_dividends_currency": "GBP",
            "trend_vs_buy": "up", "asset_class": "EQUITY", "data_source": "YAHOO",
            "market_change_24h": 1.20, "market_change_pct_24h": 0.62,
            "rsi": 58.4, "trend_50d": "up", "trend_200d": "up",
            "next_earnings_date": "2026-07-25",
            "priced_at_cost": False, "allocation_pct": 40.0,
            "low_limit": 150.0, "low_limit_set": True, "low_limit_reached": False,
            "high_limit": None, "high_limit_set": False, "high_limit_reached": False,
        },
        {
            "account_id": 7, "account_name": "GIA", "ticker": "AAPL", "company_name": "Apple Inc.",
            "shares": 5.0, "currency_asset": "USD", "currency_base": "GBP",
            "market_price": 195.20, "market_price_currency": "USD",
            "market_price_in_base_currency": 154.30,
            "average_buy_price": 160.00, "average_buy_price_currency": "GBP",
            "market_value": 771.50, "total_investment": 800.00,
            "gain_value": -28.50, "gain_value_currency": "GBP", "gain_pct": -3.56,
            "profit_and_loss": -28.50,
            "accumulated_dividends": 6.20, "accumulated_dividends_currency": "GBP",
            "trend_vs_buy": "down", "asset_class": "EQUITY", "data_source": "YAHOO",
            "market_change_24h": 1.20, "market_change_pct_24h": 0.62,
            "rsi": 58.4, "trend_50d": "up", "trend_200d": "up",
            "next_earnings_date": "2026-07-25",
            "priced_at_cost": False, "allocation_pct": 18.0,
            "low_limit": None, "low_limit_set": False, "low_limit_reached": False,
            "high_limit": 200.0, "high_limit_set": True, "high_limit_reached": False,
        },
        {
            "account_id": 7, "account_name": "GIA", "ticker": "VWRL.L", "company_name": "Vanguard FTSE All-World",
            "shares": 20.0, "currency_asset": "GBP", "currency_base": "GBP",
            "market_price": 110.50, "market_price_currency": "GBP",
            "market_price_in_base_currency": 110.50,
            "average_buy_price": 95.00, "average_buy_price_currency": "GBP",
            "market_value": 2210.00, "total_investment": 1900.00,
            "gain_value": 310.00, "gain_value_currency": "GBP", "gain_pct": 16.32,
            "profit_and_loss": 310.00,
            "accumulated_dividends": 45.10, "accumulated_dividends_currency": "GBP",
            "trend_vs_buy": "up", "asset_class": "ETF", "data_source": "YAHOO",
            "market_change_24h": -0.30, "market_change_pct_24h": -0.27,
            "rsi": 62.1, "trend_50d": "up", "trend_200d": "up",
            "next_earnings_date": None,
            "priced_at_cost": False, "allocation_pct": 42.0,
            "low_limit": None, "low_limit_set": False, "low_limit_reached": False,
            "high_limit": None, "high_limit_set": False, "high_limit_reached": False,
        },
    ],
}

SAMPLE_HOLDINGS_EMPTY = {"status": "success", "base_currency": "GBP", "holdings": []}

SAMPLE_MARKET_STATUS_CLOSED = {
    "status": "success",
    "us_market_open": False,
    "uk_market_open": False,
    "yahoo_ok": True,
    "system_ok": True,
}

SAMPLE_OTHER_ACCOUNTS = {
    "status": "success",
    "base_currency": "GBP",
    "accounts": [
        {
            "account_id": 21,
            "name": "Aviva Pension",
            "account_type": "Pension",
            "currency": "GBP",
            "current_value": 84210.55,
            "performance": {"1m": 1.8, "ytd": 6.4, "1y": 11.2},
            "last_updated": "2026-07-02",
        },
        {
            "account_id": 22,
            "name": "House - Alicia Avenue",
            "account_type": "House",
            "currency": "GBP",
            "current_value": 350000.0,
            "performance": {"1m": None, "ytd": 0.0, "1y": 2.9},
            "last_updated": "2026-06-01",
        },
    ],
}

SAMPLE_OTHER_ACCOUNTS_EMPTY = {"status": "success", "base_currency": "GBP", "accounts": []}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data=SAMPLE_CONFIG,
        title="Stock Analysis Project",
        unique_id="http://sap.local",
    )


@pytest.fixture
def mock_api():
    """Return a pre-configured mock StockAnalysisAPI."""
    api = MagicMock()
    api.get_portfolio_totals = AsyncMock(return_value=SAMPLE_PORTFOLIO_TOTALS)
    api.get_market_status = AsyncMock(return_value=SAMPLE_MARKET_STATUS)
    api.get_account_metrics = AsyncMock(return_value=SAMPLE_ACCOUNT_METRICS)
    api.get_holdings = AsyncMock(return_value=SAMPLE_HOLDINGS)
    api.get_other_accounts = AsyncMock(return_value=SAMPLE_OTHER_ACCOUNTS)
    api.set_holding_price_limit = AsyncMock(return_value={"status": "success"})
    api.trigger_refresh_now = AsyncMock(return_value={"status": "success"})
    api.close = AsyncMock()
    return api
