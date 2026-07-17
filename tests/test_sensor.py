"""Tests for the per-Trading-account sensor set (Phase 2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stock_analysis_project.const import DOMAIN

from .conftest import (
    SAMPLE_ACCOUNT_METRICS,
    SAMPLE_ACCOUNT_METRICS_EMPTY,
    SAMPLE_CONFIG,
    SAMPLE_HOLDINGS,
    SAMPLE_HOLDINGS_EMPTY,
    SAMPLE_MACRO_CONDITIONS,
    SAMPLE_MACRO_CONDITIONS_EMPTY,
    SAMPLE_MARKET_REGIME,
    SAMPLE_MARKET_REGIME_EMPTY,
    SAMPLE_MARKETS,
    SAMPLE_MARKETS_EMPTY,
    SAMPLE_OTHER_ACCOUNTS,
    SAMPLE_OTHER_ACCOUNTS_EMPTY,
)

_MARKET_HEALTH_UNIQUE_ID_KEYS = (
    "market_regime", "us_market_classification", "uk_market_classification",
    "us_10y_treasury", "uk_10y_gilt", "treasury_auction_demand", "fear_greed_index",
)

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


async def test_last_update_success_sensor_present_and_matches_coordinator(
    hass: HomeAssistant, mock_api
) -> None:
    """The Last Update Success diagnostic sensor is always created (unconditional, unlike every
    other sensor group which is gated by a "Show ..." toggle) and reflects the coordinator's
    last_success_time so a user can confirm polling is actually happening even when every other
    fetched value has stayed identical across many polls."""
    entry = await _setup(hass, mock_api, data=dict(
        SAMPLE_CONFIG,
        show_portfolio_totals=False,
        show_accounts=False,
        show_holdings=False,
        show_other_accounts=False,
        show_market_health=False,
        show_markets=False,
    ))
    registry = er.async_get(hass)

    entity = next(
        (
            e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.unique_id == f"sap_last_update_success_{entry.entry_id}"
        ),
        None,
    )
    assert entity is not None

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state != "unavailable"

    coordinator = entry.runtime_data
    assert coordinator.last_success_time is not None


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


def _expected_holding_unique_id(entry_id: str, account_id: int, ticker: str) -> str:
    return f"sap_holding_market_value_{account_id}_{ticker}_{entry_id}"


def _holding_entities(registry: er.EntityRegistry, entry_id: str, holdings: list[dict]) -> list[er.RegistryEntry]:
    expected = {_expected_holding_unique_id(entry_id, h["account_id"], h["ticker"]) for h in holdings}
    return [
        e
        for e in er.async_entries_for_config_entry(registry, entry_id)
        if e.domain == "sensor" and e.unique_id in expected
    ]


async def test_three_holdings_create_3_sensors_grouped_into_per_account_holdings_devices(
    hass: HomeAssistant, mock_api
) -> None:
    """The 3-holding sample payload (2 in ISA/GIA... actually 1 in ISA, 2 in GIA) creates 3
    holding sensors, but only 2 Holdings devices — one per account, not one per holding."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    holding_entities = _holding_entities(registry, entry.entry_id, SAMPLE_HOLDINGS["holdings"])
    assert len(holding_entities) == 3

    device_registry = dr.async_get(hass)
    for h in SAMPLE_HOLDINGS["holdings"]:
        unique_id = _expected_holding_unique_id(entry.entry_id, h["account_id"], h["ticker"])
        entity = next((e for e in holding_entities if e.unique_id == unique_id), None)
        assert entity is not None, f"missing entity for {unique_id}"

        device = device_registry.async_get_device(
            identifiers={(DOMAIN, f"sap_account_holdings_{h['account_id']}_{entry.entry_id}")}
        )
        assert device is not None
        assert device.name == f"{h['account_name']} - Holdings"
        assert entity.device_id == device.id
        assert device.via_device_id is not None
        account_totals_device = device_registry.async_get_device(
            identifiers={(DOMAIN, f"sap_account_{h['account_id']}_{entry.entry_id}")}
        )
        assert device.via_device_id == account_totals_device.id

    isa_holdings = [h for h in SAMPLE_HOLDINGS["holdings"] if h["account_id"] == 3]
    gia_holdings = [h for h in SAMPLE_HOLDINGS["holdings"] if h["account_id"] == 7]
    assert len(isa_holdings) == 1
    assert len(gia_holdings) == 2


async def test_same_ticker_two_accounts_creates_two_separate_holdings_devices_not_merged(
    hass: HomeAssistant, mock_api
) -> None:
    """AAPL held in both ISA and GIA (sample fixture) must produce two distinct Holdings devices
    (one per account), not one merged device — the core Phase 3 per-account-scoping regression
    test, now expressed at the device-per-account level rather than device-per-holding."""
    entry = await _setup(hass, mock_api)
    device_registry = dr.async_get(hass)

    aapl_rows = [h for h in SAMPLE_HOLDINGS["holdings"] if h["ticker"] == "AAPL"]
    assert len(aapl_rows) == 2

    devices = [
        device_registry.async_get_device(
            identifiers={(DOMAIN, f"sap_account_holdings_{h['account_id']}_{entry.entry_id}")}
        )
        for h in aapl_rows
    ]
    assert all(d is not None for d in devices)
    assert devices[0].id != devices[1].id


async def test_same_ticker_two_accounts_shows_same_company_name_disambiguated_by_device(
    hass: HomeAssistant, mock_api
) -> None:
    """Regression (2026-07-17): _attr_name is the company name (e.g. "Apple Inc."), so AAPL held
    in both ISA and GIA legitimately shows the same company-name suffix on both entities' full
    friendly_name — they're distinguished by the account-specific device prefix each is joined
    with (Home Assistant always joins the device name in once a device is attached, regardless of
    has_entity_name — a bare, unprefixed name isn't achievable while keeping the shared per-account
    Holdings device), plus their own distinct entity_id/device_id."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    aapl_rows = [h for h in SAMPLE_HOLDINGS["holdings"] if h["ticker"] == "AAPL"]
    entities = [
        next(
            e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.unique_id == _expected_holding_unique_id(entry.entry_id, h["account_id"], "AAPL")
        )
        for h in aapl_rows
    ]
    states = [hass.states.get(e.entity_id) for e in entities]

    assert entities[0].entity_id != entities[1].entity_id
    assert entities[0].device_id != entities[1].device_id
    assert states[0].attributes.get("friendly_name") == "ISA - Holdings Apple Inc."
    assert states[1].attributes.get("friendly_name") == "GIA - Holdings Apple Inc."
    assert states[0].attributes.get("company_name") == "Apple Inc."
    assert states[1].attributes.get("company_name") == "Apple Inc."


async def test_holding_entity_id_is_deterministic_per_account_and_ticker(hass: HomeAssistant, mock_api) -> None:
    """entity_id is explicitly assigned from account_id+ticker, not auto-derived from the
    company-name-based _attr_name, so it stays stable even if Yahoo's company name for a ticker
    changes later — matching the StockAnalysisOtherAccountSensor pattern of an explicit
    entity_id assignment."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    row = next(h for h in SAMPLE_HOLDINGS["holdings"] if h["ticker"] == "VWRL.L")
    entity = next(
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == _expected_holding_unique_id(entry.entry_id, row["account_id"], "VWRL.L")
    )
    assert entity.entity_id == f"sensor.holding_{row['account_id']}_vwrl_l"


async def test_holdings_in_same_account_share_one_holdings_device(hass: HomeAssistant, mock_api) -> None:
    """AAPL and VWRL.L, both held in GIA (sample fixture), must share the same Holdings device —
    the core requirement of this device-grouping redesign."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    aapl_gia = next(h for h in SAMPLE_HOLDINGS["holdings"] if h["ticker"] == "AAPL" and h["account_id"] == 7)
    vwrl_gia = next(h for h in SAMPLE_HOLDINGS["holdings"] if h["ticker"] == "VWRL.L" and h["account_id"] == 7)

    aapl_entity = next(
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == _expected_holding_unique_id(entry.entry_id, aapl_gia["account_id"], "AAPL")
    )
    vwrl_entity = next(
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == _expected_holding_unique_id(entry.entry_id, vwrl_gia["account_id"], "VWRL.L")
    )
    assert aapl_entity.device_id == vwrl_entity.device_id

    aapl_state = hass.states.get(aapl_entity.entity_id)
    vwrl_state = hass.states.get(vwrl_entity.entity_id)
    assert aapl_state.attributes.get("friendly_name") == "GIA - Holdings Apple Inc."
    assert vwrl_state.attributes.get("friendly_name") == "GIA - Holdings Vanguard FTSE All-World"


async def test_holding_sensor_value_matches_own_holding_not_other_account_same_ticker(
    hass: HomeAssistant, mock_api
) -> None:
    """A holding sensor's value matches its own (account, ticker) row, not the value of the same
    ticker held in a different account — cross-item value-mixup regression test."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    isa_row, gia_row = [h for h in SAMPLE_HOLDINGS["holdings"] if h["ticker"] == "AAPL"]
    assert isa_row["market_value"] != gia_row["market_value"]

    entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == _expected_holding_unique_id(entry.entry_id, isa_row["account_id"], "AAPL")
    )
    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert float(state.state) == isa_row["market_value"]
    assert float(state.state) != gia_row["market_value"]


async def test_holding_sensor_attributes_match_ghostfolio_shape(hass: HomeAssistant, mock_api) -> None:
    """The holding sensor's attributes carry the full Ghostfolio-style + additional field set."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    row = SAMPLE_HOLDINGS["holdings"][0]
    entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == _expected_holding_unique_id(entry.entry_id, row["account_id"], row["ticker"])
    )
    state = hass.states.get(entity.entity_id)
    assert state is not None
    for key, expected in (
        ("ticker", row["ticker"]),
        ("company_name", row["company_name"]),
        ("account", row["account_name"]),
        ("number_of_shares", row["shares"]),
        ("market_price", row["market_price"]),
        ("gain_value", row["gain_value"]),
        ("gain_pct", row["gain_pct"]),
        ("profit_and_loss", row["profit_and_loss"]),
        ("accumulated_dividends", row["accumulated_dividends"]),
        ("trend_vs_buy", row["trend_vs_buy"]),
        ("asset_class", row["asset_class"]),
        ("data_source", row["data_source"]),
        ("market_change_24h", row["market_change_24h"]),
        ("market_change_pct_24h", row["market_change_pct_24h"]),
        ("pre_market_change_pct", row["pre_market_change_pct"]),
        ("post_market_change_pct", row["post_market_change_pct"]),
        ("rsi", row["rsi"]),
        ("trend_50d", row["trend_50d"]),
        ("trend_200d", row["trend_200d"]),
        ("next_earnings_date", row["next_earnings_date"]),
        ("low_limit_set", row["low_limit_set"]),
        ("low_limit_reached", row["low_limit_reached"]),
        ("high_limit_set", row["high_limit_set"]),
        ("high_limit_reached", row["high_limit_reached"]),
    ):
        assert state.attributes.get(key) == expected, f"attribute {key} mismatch: {state.attributes}"


async def test_zero_holdings_creates_no_holding_sensors(hass: HomeAssistant, mock_api) -> None:
    """An empty holdings list creates zero per-holding sensors without raising."""
    mock_api.get_holdings = AsyncMock(return_value=SAMPLE_HOLDINGS_EMPTY)
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    holding_entities = _holding_entities(registry, entry.entry_id, SAMPLE_HOLDINGS["holdings"])
    assert len(holding_entities) == 0


async def test_show_holdings_disabled_skips_holdings_fetch_and_entities(
    hass: HomeAssistant, mock_api
) -> None:
    """CONF_SHOW_HOLDINGS=False means the coordinator never awaits get_holdings and creates no entities."""
    data = dict(SAMPLE_CONFIG, show_holdings=False)
    entry = await _setup(hass, mock_api, data=data)
    registry = er.async_get(hass)

    mock_api.get_holdings.assert_not_awaited()

    holding_entities = _holding_entities(registry, entry.entry_id, SAMPLE_HOLDINGS["holdings"])
    assert len(holding_entities) == 0


def _other_account_entities(registry: er.EntityRegistry, entry_id: str) -> list[er.RegistryEntry]:
    """Return only the per-other-account sensor entities."""
    return [
        e
        for e in er.async_entries_for_config_entry(registry, entry_id)
        if e.domain == "sensor" and e.unique_id.startswith("sap_other_account_value_")
    ]


async def test_two_other_accounts_create_2_sensors_on_shared_device(
    hass: HomeAssistant, mock_api
) -> None:
    """Both sample Pension/House accounts create one sensor each, sharing one "Other Accounts"
    device rather than getting one device per account (unlike Phase 2's account devices)."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    other_entities = _other_account_entities(registry, entry.entry_id)
    assert len(other_entities) == 2

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_other_accounts_{entry.entry_id}")}
    )
    assert device is not None
    assert device.name == "Other Accounts"
    for entity in other_entities:
        assert entity.device_id == device.id


async def test_other_account_sensor_entity_id_derived_from_account_name_no_device_prefix(
    hass: HomeAssistant, mock_api
) -> None:
    """Unlike every other entity in this integration, the Other Accounts sensor explicitly sets
    entity_id in __init__ rather than relying on has_entity_name + device-name derivation —
    matching the operator's explicit spec (sensor.<account_name_slug>, no device-name prefix)."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    pension_row, house_row = SAMPLE_OTHER_ACCOUNTS["accounts"]
    pension_entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_other_account_value_{pension_row['account_id']}_{entry.entry_id}"
    )
    house_entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_other_account_value_{house_row['account_id']}_{entry.entry_id}"
    )

    assert pension_entity.entity_id == "sensor.aviva_pension"
    assert house_entity.entity_id == "sensor.house_alicia_avenue"

    pension_state = hass.states.get(pension_entity.entity_id)
    assert pension_state is not None
    # The exact friendly-name text (whether the device name is joined in) is Home Assistant
    # core version-dependent behavior, not part of this integration's contract — only the
    # entity_id itself is the operator's explicit spec, so that's the only thing asserted here.
    assert "Aviva Pension" in pension_state.name


async def test_other_account_sensor_value_matches_own_account_not_other(
    hass: HomeAssistant, mock_api
) -> None:
    """A sensor's value/attributes match its own account, not the other account's data."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    pension_row, house_row = SAMPLE_OTHER_ACCOUNTS["accounts"]
    assert pension_row["current_value"] != house_row["current_value"]

    entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_other_account_value_{pension_row['account_id']}_{entry.entry_id}"
    )
    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert float(state.state) == pension_row["current_value"]
    assert float(state.state) != house_row["current_value"]
    assert state.attributes.get("account_type") == "Pension"
    assert state.attributes.get("performance_1m") == pension_row["performance"]["1m"]
    assert state.attributes.get("performance_ytd") == pension_row["performance"]["ytd"]
    assert state.attributes.get("performance_1y") == pension_row["performance"]["1y"]
    assert state.attributes.get("last_updated") == pension_row["last_updated"]


async def test_zero_other_accounts_creates_no_other_account_sensors(
    hass: HomeAssistant, mock_api
) -> None:
    """An empty other-accounts list creates zero sensors without raising."""
    mock_api.get_other_accounts = AsyncMock(return_value=SAMPLE_OTHER_ACCOUNTS_EMPTY)
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    assert _other_account_entities(registry, entry.entry_id) == []


async def test_show_other_accounts_disabled_skips_fetch_and_entities(
    hass: HomeAssistant, mock_api
) -> None:
    """CONF_SHOW_OTHER_ACCOUNTS=False means the coordinator never awaits get_other_accounts and
    creates no entities."""
    data = dict(SAMPLE_CONFIG, show_other_accounts=False)
    entry = await _setup(hass, mock_api, data=data)
    registry = er.async_get(hass)

    mock_api.get_other_accounts.assert_not_awaited()
    assert _other_account_entities(registry, entry.entry_id) == []


# ---------------------------------------------------------------------------
# Market Health sensors (Phase 5)
# ---------------------------------------------------------------------------

def _market_health_entities(registry: er.EntityRegistry, entry_id: str) -> list[er.RegistryEntry]:
    """Return only the Market Health sensor entities."""
    expected = {f"sap_{key}_{entry_id}" for key in _MARKET_HEALTH_UNIQUE_ID_KEYS}
    return [
        e
        for e in er.async_entries_for_config_entry(registry, entry_id)
        if e.domain == "sensor" and e.unique_id in expected
    ]


async def test_market_health_creates_7_sensors_on_shared_device(
    hass: HomeAssistant, mock_api
) -> None:
    """All 7 Market Health sensors are created once (static, non-per-item) and share one
    "Market Health" device, via_device-linked to the Portfolio device."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    entities = _market_health_entities(registry, entry.entry_id)
    assert len(entities) == 7

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"sap_market_health_{entry.entry_id}")}
    )
    assert device is not None
    assert device.name == "Market Health"
    for entity in entities:
        assert entity.device_id == device.id


async def test_market_regime_sensor_value_and_attributes(hass: HomeAssistant, mock_api) -> None:
    """Market Regime sensor state is the HMM label, not the turbulence-classifier label —
    both are distinct 'Crash'-containing taxonomies on the same backend row, the exact shape of
    bug that bit Phase 1's field-swap."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_market_regime_{entry.entry_id}"
    )
    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == "Bull"
    assert state.state != SAMPLE_MARKET_REGIME["current"]["us_regime_label"]
    assert state.attributes.get("probability") == 0.87
    assert state.attributes.get("as_of") == "2026-07-03"
    assert state.attributes.get("last_change_from") == "Chop"
    assert state.attributes.get("last_change_to") == "Bull"


async def test_us_uk_market_classification_sensors_use_turbulence_label(
    hass: HomeAssistant, mock_api
) -> None:
    """US/UK Market Classification sensors read us/uk_regime_label, not the HMM's own label."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    us_entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_us_market_classification_{entry.entry_id}"
    )
    uk_entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_uk_market_classification_{entry.entry_id}"
    )
    assert hass.states.get(us_entity.entity_id).state == "Normal"
    assert hass.states.get(uk_entity.entity_id).state == "Volatile"


async def test_us_10y_treasury_and_uk_10y_gilt_map_threat_level_to_low_elevated_high(
    hass: HomeAssistant, mock_api
) -> None:
    """GREEN/YELLOW/RED raw threat levels map to Low/Elevated/High sensor state, with the raw
    value preserved as an attribute."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    us_entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_us_10y_treasury_{entry.entry_id}"
    )
    uk_entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_uk_10y_gilt_{entry.entry_id}"
    )
    us_state = hass.states.get(us_entity.entity_id)
    uk_state = hass.states.get(uk_entity.entity_id)

    assert us_state.state == "Elevated"  # YELLOW
    assert us_state.attributes.get("raw_level") == "YELLOW"
    assert us_state.attributes.get("yield_velocity_bps") == 18.5

    assert uk_state.state == "Low"  # GREEN
    assert uk_state.attributes.get("raw_level") == "GREEN"
    assert uk_state.attributes.get("uk_gilt_close") == 4.10


async def test_treasury_auction_demand_sensor_weak_and_healthy_and_unknown(
    hass: HomeAssistant, mock_api
) -> None:
    """Healthy=False -> "Weakness Detected"; Healthy=True -> "Healthy"; Healthy=None -> Unknown
    (no auctions in the window is a distinct case from "all auctions were fine")."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_treasury_auction_demand_{entry.entry_id}"
    )
    state = hass.states.get(entity.entity_id)
    assert state.state == "Weakness Detected"
    assert len(state.attributes.get("recent_auctions")) == 1

    healthy_macro = dict(SAMPLE_MACRO_CONDITIONS, treasury_auction={"healthy": True, "recent": []})
    entry.runtime_data.api.get_macro_conditions = AsyncMock(return_value=healthy_macro)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "Healthy"

    unknown_macro = dict(SAMPLE_MACRO_CONDITIONS, treasury_auction={"healthy": None, "recent": []})
    entry.runtime_data.api.get_macro_conditions = AsyncMock(return_value=unknown_macro)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "unknown"


async def test_fear_greed_index_sensor_numeric_state_with_label_attribute(
    hass: HomeAssistant, mock_api
) -> None:
    """Fear & Greed is the one Market Health sensor with a numeric state; label is an attribute."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_fear_greed_index_{entry.entry_id}"
    )
    state = hass.states.get(entity.entity_id)
    assert float(state.state) == 62.0
    assert state.attributes.get("label") == "Greed"


async def test_market_health_degrades_to_unknown_on_fresh_backend(
    hass: HomeAssistant, mock_api
) -> None:
    """A fresh backend with no market_regimes/macro_regimes rows must degrade every one of the
    7 sensors to Unknown, never raise, and never silently show 0 in place of None."""
    mock_api.get_market_regime = AsyncMock(return_value=SAMPLE_MARKET_REGIME_EMPTY)
    mock_api.get_macro_conditions = AsyncMock(return_value=SAMPLE_MACRO_CONDITIONS_EMPTY)
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    for entity in _market_health_entities(registry, entry.entry_id):
        state = hass.states.get(entity.entity_id)
        assert state is not None
        assert state.state == "unknown"


async def test_show_market_health_disabled_skips_fetch_and_entities(
    hass: HomeAssistant, mock_api
) -> None:
    """CONF_SHOW_MARKET_HEALTH=False means the coordinator never awaits either Market Health
    fetch and creates no entities."""
    data = dict(SAMPLE_CONFIG, show_market_health=False)
    entry = await _setup(hass, mock_api, data=data)
    registry = er.async_get(hass)

    mock_api.get_market_regime.assert_not_awaited()
    mock_api.get_macro_conditions.assert_not_awaited()
    assert _market_health_entities(registry, entry.entry_id) == []


# ---------------------------------------------------------------------------
# Markets sensors (Phase 6)
# ---------------------------------------------------------------------------

def _market_index_entities(registry: er.EntityRegistry, entry_id: str) -> list[er.RegistryEntry]:
    """Return only the Markets sensor entities."""
    return [
        e
        for e in er.async_entries_for_config_entry(registry, entry_id)
        if e.domain == "sensor" and e.unique_id.startswith("sap_market_index_")
    ]


async def test_dual_and_plain_tickers_create_3_sensors_on_shared_markets_device(
    hass: HomeAssistant, mock_api
) -> None:
    """The dual-instrument S&P 500 tile creates two independent sensors (spot + future); the
    plain FTSE tile creates one — 3 total, all sharing one "Markets" device, via_device-linked
    to the Portfolio device."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    entities = _market_index_entities(registry, entry.entry_id)
    assert len(entities) == 3
    assert {e.unique_id for e in entities} == {
        f"sap_market_index_^GSPC_{entry.entry_id}",
        f"sap_market_index_ES=F_{entry.entry_id}",
        f"sap_market_index_^FTSE_{entry.entry_id}",
    }

    device = device_registry.async_get_device(identifiers={(DOMAIN, f"sap_markets_{entry.entry_id}")})
    assert device is not None
    assert device.name == "Markets"
    for entity in entities:
        assert entity.device_id == device.id


async def test_plain_ticker_sensor_value_and_attributes(hass: HomeAssistant, mock_api) -> None:
    """State is the live price; attributes cover change, session status, region, exchange. No
    is_active attribute for a plain (non-dual-instrument) ticker."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_market_index_^FTSE_{entry.entry_id}"
    )
    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert float(state.state) == 8210.55
    assert state.attributes.get("ticker") == "^FTSE"
    assert state.attributes.get("change_pts") == -5.10
    assert state.attributes.get("change_pct") == -0.06
    assert state.attributes.get("is_positive") is False
    assert state.attributes.get("status") == "closed"
    assert state.attributes.get("region") == "Europe"
    assert state.attributes.get("exchange") == "LSE"
    assert state.attributes.get("currency") == "GBP"
    assert state.attributes.get("asset_type") == "Index"
    assert "is_active" not in state.attributes


async def test_spot_and_future_sensors_are_independent_and_simultaneously_populated(
    hass: HomeAssistant, mock_api
) -> None:
    """Both the spot and futures sensor for a dual-instrument index show their own live price
    at the same time — no swapping, both always populated, is_active distinguishing which side
    the backend currently treats as primary."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    spot_entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_market_index_^GSPC_{entry.entry_id}"
    )
    future_entity = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.unique_id == f"sap_market_index_ES=F_{entry.entry_id}"
    )
    spot_state = hass.states.get(spot_entity.entity_id)
    future_state = hass.states.get(future_entity.entity_id)

    assert float(spot_state.state) == 5645.20
    assert spot_state.attributes.get("ticker") == "^GSPC"
    assert spot_state.attributes.get("is_active") is True
    # Both sensors share the same session status/region/exchange from the parent tile.
    assert spot_state.attributes.get("status") == "open"
    assert spot_state.attributes.get("region") == "US"

    assert float(future_state.state) == 5648.00
    assert future_state.attributes.get("ticker") == "ES=F"
    assert future_state.attributes.get("change_pts") == 10.10
    assert future_state.attributes.get("is_active") is False
    assert future_state.attributes.get("status") == "open"
    assert future_state.attributes.get("region") == "US"


async def test_spot_and_future_sensor_identities_stay_stable_across_active_side_flip(
    hass: HomeAssistant, mock_api
) -> None:
    """Flipping which side is "active" (e.g. NYSE closes) must not destroy/recreate either
    sensor — both unique_ids are fixed per-instrument, never dependent on which one is active."""
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)

    flipped_tile = dict(
        SAMPLE_MARKETS["data"]["regions"][0]["tiles"][0],
        market_state="pre",
        dual_instrument={
            "spot": {**SAMPLE_MARKETS["data"]["regions"][0]["tiles"][0]["dual_instrument"]["spot"], "is_active": False},
            "future": {**SAMPLE_MARKETS["data"]["regions"][0]["tiles"][0]["dual_instrument"]["future"], "is_active": True},
        },
    )
    flipped_payload = {
        "status": "success",
        "data": {
            "view": "dynamic",
            "regions": [
                {"region": "US", "state": "pre", "tiles": [flipped_tile]},
                SAMPLE_MARKETS["data"]["regions"][1],
            ],
        },
    }
    entry.runtime_data.api.get_markets = AsyncMock(return_value=flipped_payload)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    entities_after = _market_index_entities(registry, entry.entry_id)
    assert {e.unique_id for e in entities_after} == {
        f"sap_market_index_^GSPC_{entry.entry_id}",
        f"sap_market_index_ES=F_{entry.entry_id}",
        f"sap_market_index_^FTSE_{entry.entry_id}",
    }
    spot_entity = next(e for e in entities_after if e.unique_id == f"sap_market_index_^GSPC_{entry.entry_id}")
    future_entity = next(e for e in entities_after if e.unique_id == f"sap_market_index_ES=F_{entry.entry_id}")
    assert hass.states.get(spot_entity.entity_id).attributes.get("is_active") is False
    assert hass.states.get(future_entity.entity_id).attributes.get("is_active") is True


async def test_zero_markets_tickers_creates_no_market_sensors(hass: HomeAssistant, mock_api) -> None:
    mock_api.get_markets = AsyncMock(return_value=SAMPLE_MARKETS_EMPTY)
    entry = await _setup(hass, mock_api)
    registry = er.async_get(hass)
    assert _market_index_entities(registry, entry.entry_id) == []


async def test_show_markets_disabled_skips_fetch_and_entities(hass: HomeAssistant, mock_api) -> None:
    """CONF_SHOW_MARKETS=False means the coordinator never awaits the markets fetch and creates
    no entities."""
    data = dict(SAMPLE_CONFIG, show_markets=False)
    entry = await _setup(hass, mock_api, data=data)
    registry = er.async_get(hass)

    mock_api.get_markets.assert_not_awaited()
    assert _market_index_entities(registry, entry.entry_id) == []
