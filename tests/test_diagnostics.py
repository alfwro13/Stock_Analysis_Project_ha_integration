"""Tests for the redacted diagnostics download."""
from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stock_analysis_project.const import DOMAIN
from custom_components.stock_analysis_project.diagnostics import async_get_config_entry_diagnostics

from .conftest import SAMPLE_CONFIG, SAMPLE_PORTFOLIO_TOTALS


async def test_diagnostics_redact_credentials_and_portfolio_figures(hass: HomeAssistant, mock_api) -> None:
    """The download carries neither the API key, the server address nor any portfolio value."""
    entry = MockConfigEntry(domain=DOMAIN, data=SAMPLE_CONFIG, title="SAP", unique_id=SAMPLE_CONFIG["base_url"])
    entry.add_to_hass(hass)
    with patch("custom_components.stock_analysis_project.StockAnalysisAPI", return_value=mock_api):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["config"]["api_key"] == "**REDACTED**"
    assert result["config"]["base_url"] == "**REDACTED**"
    assert result["coordinator"]["portfolio_totals"] == "**REDACTED**"
    assert result["coordinator"]["market_status"]["us_market_open"] is True
    text = str(result)
    assert SAMPLE_CONFIG["api_key"] not in text
    assert SAMPLE_CONFIG["base_url"] not in text
    assert str(SAMPLE_PORTFOLIO_TOTALS["current_value"]) not in text
