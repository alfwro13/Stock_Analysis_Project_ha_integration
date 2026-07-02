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
    api.trigger_refresh_now = AsyncMock(return_value={"status": "success"})
    api.close = AsyncMock()
    return api
