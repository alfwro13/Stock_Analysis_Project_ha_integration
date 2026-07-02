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
    api.trigger_refresh_now = AsyncMock(return_value={"status": "success"})
    api.close = AsyncMock()
    return api
