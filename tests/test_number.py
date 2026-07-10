"""Tests for number entities: Refresh Interval (Phase 1) and per-holding price limits (Phase 3)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stock_analysis_project.const import DOMAIN

from .conftest import SAMPLE_CONFIG, SAMPLE_HOLDINGS


async def _setup(hass: HomeAssistant, api, data: dict | None = None) -> MockConfigEntry:
    """Helper: add a config entry and set up the integration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data if data is not None else SAMPLE_CONFIG,
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


def _limit_entity(registry: er.EntityRegistry, entry_id: str, account_id: int, ticker: str, limit_key: str):
    unique_id = f"sap_holding_{limit_key}_{account_id}_{ticker}_{entry_id}"
    return next(
        (e for e in er.async_entries_for_config_entry(registry, entry_id) if e.unique_id == unique_id),
        None,
    )


async def test_holding_limit_numbers_default_disabled(hass: HomeAssistant, mock_api) -> None:
    """Both Low Limit and High Limit numbers are registered but disabled by default."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    row = SAMPLE_HOLDINGS["holdings"][0]
    for limit_key in ("low_limit", "high_limit"):
        entity = _limit_entity(registry, entry.entry_id, row["account_id"], row["ticker"], limit_key)
        assert entity is not None, f"missing entity for {limit_key}"
        assert entity.disabled_by == er.RegistryEntryDisabler.INTEGRATION


async def test_holding_limit_number_native_value_reads_from_coordinator(hass: HomeAssistant, mock_api) -> None:
    """An enabled Low Limit number's state reflects the coordinator's stored value."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    row = SAMPLE_HOLDINGS["holdings"][0]
    assert row["low_limit"] is not None
    entity = _limit_entity(registry, entry.entry_id, row["account_id"], row["ticker"], "low_limit")
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.async_block_till_done()
    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api,
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert float(state.state) == row["low_limit"]


async def test_holding_limit_number_set_native_value_posts_to_api_and_requests_refresh(
    hass: HomeAssistant, mock_api
) -> None:
    """Setting the Low Limit calls the API with only low_limit, and requests a coordinator refresh."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    row = SAMPLE_HOLDINGS["holdings"][0]
    entity = _limit_entity(registry, entry.entry_id, row["account_id"], row["ticker"], "low_limit")
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.async_block_till_done()
    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api,
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    mock_api.set_holding_price_limit.reset_mock()
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": entity.entity_id, "value": 175.0},
        blocking=True,
    )
    await hass.async_block_till_done()

    mock_api.set_holding_price_limit.assert_awaited_once_with(row["account_id"], row["ticker"], low_limit=175.0)


async def test_holding_limit_number_set_low_does_not_pass_high_limit_kwarg(
    hass: HomeAssistant, mock_api
) -> None:
    """Regression test for the partial-update correctness point: setting one limit must never
    forward the sibling field, even as None — a caller that did so would silently clear it."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    row = SAMPLE_HOLDINGS["holdings"][0]
    entity = _limit_entity(registry, entry.entry_id, row["account_id"], row["ticker"], "high_limit")
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.async_block_till_done()
    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api,
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    mock_api.set_holding_price_limit.reset_mock()
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": entity.entity_id, "value": 250.0},
        blocking=True,
    )
    await hass.async_block_till_done()

    call_kwargs = mock_api.set_holding_price_limit.call_args.kwargs
    assert "low_limit" not in call_kwargs
    assert call_kwargs.get("high_limit") == 250.0


async def test_holding_limit_number_set_to_zero_clears_limit(hass: HomeAssistant, mock_api) -> None:
    """Setting the number to 0 (its native_min_value) must clear the limit on the backend (sent
    as low_limit=None), not store a literal 0 threshold — a High Limit of 0 would otherwise fire
    immediately, since price is always >= 0."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    row = SAMPLE_HOLDINGS["holdings"][0]
    assert row["low_limit"] is not None
    entity = _limit_entity(registry, entry.entry_id, row["account_id"], row["ticker"], "low_limit")
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.async_block_till_done()
    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api,
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    mock_api.set_holding_price_limit.reset_mock()
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": entity.entity_id, "value": 0},
        blocking=True,
    )
    await hass.async_block_till_done()

    mock_api.set_holding_price_limit.assert_awaited_once_with(row["account_id"], row["ticker"], low_limit=None)


async def test_holding_limit_number_native_value_defaults_to_zero_when_unset(
    hass: HomeAssistant, mock_api
) -> None:
    """A never-set (or cleared) limit displays as 0 rather than 'unknown', matching the
    0-means-clear convention in both directions."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    row = SAMPLE_HOLDINGS["holdings"][0]
    assert row["high_limit"] is None
    entity = _limit_entity(registry, entry.entry_id, row["account_id"], row["ticker"], "high_limit")
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.async_block_till_done()
    with patch(
        "custom_components.stock_analysis_project.StockAnalysisAPI",
        return_value=mock_api,
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert float(state.state) == 0
