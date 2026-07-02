"""Tests for the per-Trading-account sensor set (Phase 2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stock_analysis_project.const import DOMAIN

from .conftest import SAMPLE_ACCOUNT_METRICS, SAMPLE_ACCOUNT_METRICS_EMPTY, SAMPLE_CONFIG

_ACCOUNT_KEYS = (
    "cash_balance", "gain_1d", "gain_1w", "gain_1m", "gain_3m", "gain_1y",
    "equity_value", "realized_pnl", "unrealized_pnl", "dividend_income",
    "interest_income", "mwrr_pct",
)


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


def _expected_account_unique_ids(entry_id: str, accounts: list[dict]) -> set[str]:
    """Return the full set of expected per-account sensor unique_ids for the given accounts."""
    return {
        f"sap_{key}_{account['account_id']}_{entry_id}"
        for account in accounts
        for key in _ACCOUNT_KEYS
    }


def _account_entities(registry: er.EntityRegistry, entry_id: str, accounts: list[dict]) -> list[er.RegistryEntry]:
    """Return only the per-account sensor entities matching the expected unique_ids."""
    expected = _expected_account_unique_ids(entry_id, accounts)
    return [
        e
        for e in er.async_entries_for_config_entry(registry, entry_id)
        if e.domain == "sensor" and e.unique_id in expected
    ]


async def test_two_accounts_create_24_sensors_with_correct_unique_ids_and_devices(
    hass: HomeAssistant, mock_api
) -> None:
    """Two accounts in the sample payload create 24 (12 x 2) account sensors with correct ids/devices."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    account_entities = _account_entities(registry, entry.entry_id, SAMPLE_ACCOUNT_METRICS["accounts"])
    assert len(account_entities) == 24

    for account in SAMPLE_ACCOUNT_METRICS["accounts"]:
        account_id = account["account_id"]
        for key in _ACCOUNT_KEYS:
            expected_unique_id = f"sap_{key}_{account_id}_{entry.entry_id}"
            entity = next((e for e in account_entities if e.unique_id == expected_unique_id), None)
            assert entity is not None, f"missing entity for {expected_unique_id}"
            assert entity.device_id is not None

    device_registry = dr.async_get(hass)
    for account in SAMPLE_ACCOUNT_METRICS["accounts"]:
        account_id = account["account_id"]
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, f"sap_account_{account_id}_{entry.entry_id}")}
        )
        assert device is not None
        assert device.name == f"{account['name']} - Totals"


async def test_account_sensor_value_matches_own_account_not_other(
    hass: HomeAssistant, mock_api
) -> None:
    """A sensor's value matches its own account's field, not the other account's value for the same field."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    account_1, account_2 = SAMPLE_ACCOUNT_METRICS["accounts"]
    assert account_1["cash_balance"] != account_2["cash_balance"]

    entity_1 = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_cash_balance_{account_1['account_id']}_{entry.entry_id}"
    )
    state_1 = hass.states.get(entity_1.entity_id)
    assert state_1 is not None
    assert float(state_1.state) == account_1["cash_balance"]
    assert float(state_1.state) != account_2["cash_balance"]


async def test_zero_accounts_creates_no_account_sensors(hass: HomeAssistant, mock_api) -> None:
    """An empty accounts list creates zero per-account sensors without raising."""
    mock_api.get_account_metrics = AsyncMock(return_value=SAMPLE_ACCOUNT_METRICS_EMPTY)
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    account_entities = _account_entities(registry, entry.entry_id, SAMPLE_ACCOUNT_METRICS["accounts"])
    assert len(account_entities) == 0


async def test_show_accounts_disabled_skips_account_metrics_fetch(
    hass: HomeAssistant, mock_api
) -> None:
    """CONF_SHOW_ACCOUNTS=False means the coordinator never awaits get_account_metrics."""
    data = dict(SAMPLE_CONFIG, show_accounts=False)
    entry = await _setup(hass, mock_api, data=data)
    registry = er.async_get(hass)

    mock_api.get_account_metrics.assert_not_awaited()

    account_entities = _account_entities(registry, entry.entry_id, SAMPLE_ACCOUNT_METRICS["accounts"])
    assert len(account_entities) == 0


async def test_show_portfolio_totals_disabled_skips_portfolio_sensors(
    hass: HomeAssistant, mock_api
) -> None:
    """CONF_SHOW_PORTFOLIO_TOTALS=False creates zero portfolio-total sensors and never fetches them."""
    data = dict(SAMPLE_CONFIG, show_portfolio_totals=False)
    entry = await _setup(hass, mock_api, data=data)
    registry = er.async_get(hass)

    mock_api.get_portfolio_totals.assert_not_awaited()

    portfolio_entities = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor" and e.unique_id.startswith("sap_portfolio_")
    ]
    assert len(portfolio_entities) == 0

    # Account sensors are unaffected by this toggle.
    account_entities = _account_entities(registry, entry.entry_id, SAMPLE_ACCOUNT_METRICS["accounts"])
    assert len(account_entities) == 24
