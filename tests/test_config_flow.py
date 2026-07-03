"""Tests for the Stock Analysis Project config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.stock_analysis_project.api import (
    StockAnalysisAPIError,
    StockAnalysisAuthError,
)
from custom_components.stock_analysis_project.const import DOMAIN

from .conftest import (
    SAMPLE_ACCOUNT_METRICS_EMPTY,
    SAMPLE_CONFIG,
    SAMPLE_HOLDINGS_EMPTY,
    SAMPLE_MARKET_STATUS,
    SAMPLE_OTHER_ACCOUNTS_EMPTY,
    SAMPLE_PORTFOLIO_TOTALS,
)


@pytest.fixture
def mock_api_for_flow():
    """Return a mock StockAnalysisAPI suitable for config flow tests. A successful flow
    (CREATE_ENTRY or a reconfigure's "reconfigure_successful" abort) triggers a real
    async_setup_entry -> coordinator first-refresh, which imports StockAnalysisAPI directly in
    __init__.py rather than through config_flow's patched reference — so every coordinator
    fetch method needs mocking here too, or that refresh hits a real, unmocked aiohttp session
    that never gets closed."""
    api = MagicMock()
    api.get_portfolio_totals = AsyncMock(return_value=SAMPLE_PORTFOLIO_TOTALS)
    api.get_market_status = AsyncMock(return_value=SAMPLE_MARKET_STATUS)
    api.get_account_metrics = AsyncMock(return_value=SAMPLE_ACCOUNT_METRICS_EMPTY)
    api.get_holdings = AsyncMock(return_value=SAMPLE_HOLDINGS_EMPTY)
    api.get_other_accounts = AsyncMock(return_value=SAMPLE_OTHER_ACCOUNTS_EMPTY)
    api.close = AsyncMock()
    return api


async def test_user_step_success(hass: HomeAssistant, mock_api_for_flow) -> None:
    """Happy path: valid credentials create a config entry."""
    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ), patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=SAMPLE_CONFIG
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["base_url"] == SAMPLE_CONFIG["base_url"]
    assert result["data"]["api_key"] == SAMPLE_CONFIG["api_key"]


async def test_user_step_cannot_connect(hass: HomeAssistant) -> None:
    """Connection error maps to 'cannot_connect' form error."""
    api = MagicMock()
    api.get_portfolio_totals = AsyncMock(side_effect=StockAnalysisAPIError("connection refused"))
    api.close = AsyncMock()

    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=api,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=SAMPLE_CONFIG
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"].get("base") == "cannot_connect"


async def test_user_step_auth_failed(hass: HomeAssistant) -> None:
    """StockAnalysisAuthError maps to 'auth_failed' form error."""
    api = MagicMock()
    api.get_portfolio_totals = AsyncMock(side_effect=StockAnalysisAuthError("invalid key"))
    api.close = AsyncMock()

    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=api,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=SAMPLE_CONFIG
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"].get("base") == "auth_failed"


async def test_user_step_invalid_url(hass: HomeAssistant) -> None:
    """URL without scheme maps to 'invalid_url' field error."""
    bad_input = {**SAMPLE_CONFIG, "base_url": "sap.local"}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=bad_input
    )

    assert result["type"] == FlowResultType.FORM
    assert "base_url" in result["errors"]


async def test_duplicate_entry_aborts(hass: HomeAssistant, mock_api_for_flow) -> None:
    """Second setup with the same unique_id is aborted."""
    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ), patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=SAMPLE_CONFIG
        )
        await hass.async_block_till_done()

        result2 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], user_input=SAMPLE_CONFIG
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_reconfigure_updates_entry(hass: HomeAssistant, mock_config_entry, mock_api_for_flow) -> None:
    """Reconfigure flow updates an existing entry's data."""
    mock_config_entry.add_to_hass(hass)

    updated_input = {**SAMPLE_CONFIG, "update_interval": 30}

    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ), patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=updated_input
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data["update_interval"] == 30


async def test_user_step_defaults_show_toggles_to_true(hass: HomeAssistant, mock_api_for_flow) -> None:
    """Omitting the show_* toggles from user_input still creates an entry (schema defaults apply)."""
    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ), patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=SAMPLE_CONFIG
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"].get("show_portfolio_totals", True) is True
    assert result["data"].get("show_accounts", True) is True
    assert result["data"].get("show_holdings", True) is True
    assert result["data"].get("show_other_accounts", True) is True
    assert result["data"].get("skip_refresh_when_markets_closed", True) is True


async def test_reconfigure_can_disable_show_accounts(
    hass: HomeAssistant, mock_config_entry, mock_api_for_flow
) -> None:
    """Reconfigure flow can flip show_accounts to False."""
    mock_config_entry.add_to_hass(hass)

    updated_input = {**SAMPLE_CONFIG, "show_accounts": False}

    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ), patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=updated_input
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data["show_accounts"] is False


async def test_reconfigure_can_disable_show_holdings(
    hass: HomeAssistant, mock_config_entry, mock_api_for_flow
) -> None:
    """Reconfigure flow can flip show_holdings to False."""
    mock_config_entry.add_to_hass(hass)

    updated_input = {**SAMPLE_CONFIG, "show_holdings": False}

    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ), patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=updated_input
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data["show_holdings"] is False


async def test_reconfigure_can_disable_show_other_accounts(
    hass: HomeAssistant, mock_config_entry, mock_api_for_flow
) -> None:
    """Reconfigure flow can flip show_other_accounts to False."""
    mock_config_entry.add_to_hass(hass)

    updated_input = {**SAMPLE_CONFIG, "show_other_accounts": False}

    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ), patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=updated_input
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data["show_other_accounts"] is False


async def test_reconfigure_can_disable_skip_refresh_when_markets_closed(
    hass: HomeAssistant, mock_config_entry, mock_api_for_flow
) -> None:
    """Reconfigure flow can flip skip_refresh_when_markets_closed to False."""
    mock_config_entry.add_to_hass(hass)

    updated_input = {**SAMPLE_CONFIG, "skip_refresh_when_markets_closed": False}

    with patch(
        "custom_components.stock_analysis_project.config_flow.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ), patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api_for_flow,
    ):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=updated_input
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data["skip_refresh_when_markets_closed"] is False
