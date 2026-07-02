Read AGENTS.md (this directory) in full before writing a single line of code. Read the main app's own AGENTS.md (`../AGENTS.md`) if the change touches backend endpoints or `accounts_engine.py`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REPOSITORY STATUS (as of July 2026)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This directory is now a real, independent git repository pushed to
https://github.com/alfwro13/Stock_Analysis_Project_ha_integration (branch `main`), with its
own CI: `.github/workflows/validate.yml` (HACS), `hassfest.yaml`, `test.yml` (pytest), and
`release.yml` (auto-creates a GitHub Release + zip whenever
`custom_components/stock_analysis_project/manifest.json`'s `version` changes on a push to
`main`). This is earlier than the original plan ("gets split out into its own git repo only
once all 4 phases are complete") — the operator asked for it explicitly, to test via HACS
against a real Home Assistant instance while Phases 3-4 are still in progress. It's still a
subfolder of the main app's own checkout (and still gitignored from the main app's own repo)
— this is a *second*, independent git repo rooted at this same directory, not a replacement
for the main app's own version control. See "PUSHING TO GITHUB" under WHEN DONE below.

Local brand assets live at `custom_components/stock_analysis_project/brand/icon.png` /
`icon@2x.png` (the main app's `assets/logo_small.png` Quantamental "Q" logo) — this satisfies
HACS validation's brand-assets check without a submission to the separate
`home-assistant/brands` repository. The GitHub repo's description and topics are also set
(via `gh repo edit`) — HACS validation checks those too.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES — apply these to every line you write or touch
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONSTANTS
- All magic values (config keys, defaults, timeouts, retry counts, unique_id prefixes) live
  in const.py. Never hardcode them inline in a platform file.
- device_info() helpers (portfolio_device_info(), diagnostics_device_info()) live in const.py.
  Always build device_info through these, never construct the identifiers/via_device dict inline.

LOGGING
- Always use lazy-% form: _LOGGER.debug("failed: %s", err) — never f-strings in logger calls.
- Do not log full response bodies at ERROR level — truncate (api.py already does this at 300 chars).

COORDINATOR NULL GUARDS
- Every sensor/binary_sensor property that reads coordinator.data must guard against it being
  None or missing keys — return {} / False / None rather than raising. See sensor.py's _totals
  and binary_sensor.py's _market_status for the pattern.
- Use .get() with defaults on all API response dicts. Never bare dict["key"].

SESSION / AIOHTTP LIFECYCLE
- StockAnalysisAPI owns exactly one aiohttp.ClientSession (lazily created in _get_session()).
  Never create a second session. Close it only in async_unload_entry via api.close().

UNIQUE_ID STABILITY
- Current scheme: sap_{key}_{entry_id}. Never change the format of an existing entity's
  unique_id — it orphans the entity for every existing user.
- Any new entity added: add its unique_id to __init__.py's async_prune_orphans()
  valid_unique_ids set in the same change, or "Prune Orphaned Entities" will delete it.

ENGLISH ONLY
- strings.json + translations/en.json only. Do not add de.json/fr.json or any other language —
  this is a deliberate divergence from ghostfolio_ha_integration's precedent (personal,
  single-user project). Keep strings.json (source of truth) and en.json in sync.

EXTENSION POINTS
- const.py already declares CONF_SHOW_ACCOUNTS / CONF_SHOW_HOLDINGS / CONF_SHOW_OTHER_ACCOUNTS
  for Phases 2-4. Do not implement behavior gated on these keys until the relevant phase below
  is actually being built.

TESTING
- Run pytest inside this directory (activate .test_venv/ first) before considering any change
  complete. No change is done until it passes.

DO NOT
- Add features, refactor, or abstract beyond what the task requires.
- Add backwards-compatibility shims for removed code.
- Batch fixes — run pytest after every individual change.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK — phased build-out
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## Phase 1 — DONE (baseline shipped)

Portfolio-wide totals, auto-refresh controls, and system/market diagnostics. Backed by 3 new
main-app endpoints and 4 new accounts_engine.py functions (see main app's AGENTS.md /
task_prompt.md for that side's own history).

Files shipped:
- Backend (main app, not this repo): `accounts_engine.py` (`portfolio_totals()`,
  `portfolio_gain_fx_decomposition()`, `portfolio_twr_fx()`, `portfolio_twr_ex_fx()`,
  `_bucket_equity_by_currency()`), `db_accounts.py` (`upsert_value_snapshot_currency()`,
  `get_value_history_currency()`), new table `account_value_history_currency`,
  `api_routes_accounts.py` (`GET /portfolio-totals`, `POST /refresh-now`),
  `api_routes_system.py` (`GET /market-status`), `scheduler_manifest.py`
  (`ha_refresh_now_source`), `notification_engine.py` (`ha_refresh_now_status`).
- This integration: `manifest.json`, `hacs.json`, `const.py`, `api.py`, `config_flow.py`,
  `__init__.py`, `sensor.py` (10 sensors), `binary_sensor.py` (5 sensors), `switch.py`,
  `number.py`, `button.py`, `diagnostics.py`, `strings.json`/`translations/en.json`,
  `tests/` (conftest, test_config_flow, test_coordinator, test_init).

Documented Phase 1 simplification: `portfolio_gain_fx_decomposition()`'s scope is **open
holdings only** — it does not include realized/closed-position gains. If lifetime
(open + realized) FX decomposition is wanted later, that's a Phase 2+ extension to the
backend engine function, not something this integration can work around client-side.

## Phase 2 — DONE: individual Trading account sensors

Gated by `CONF_SHOW_ACCOUNTS` (config_flow toggle, default on). One sensor set of 12 per
Trading account: Cash Balance, Daily/1w/1m/3m/1y Gain, Equity Value, Realized P&L,
Unrealized P&L, Dividend Income, Interest Income, Money Weighted Rate of Return %.

Backend work was composition, not new formulas, as expected: `accounts_engine.py`'s new
`account_metrics_list()` merges the existing `account_performance_cache` (via
`get_performance_cache()`/`refresh_performance_cache()`, lazily refreshed the same way
`GET /accounts/{id}/live-performance` already does) with `account_summary()`'s
dividend/interest/realized_pnl, which the cache doesn't track. No new DB table, no new
scheduler job — reads data already produced by the existing intraday scan and
`POST /accounts/refresh-now`.

Files shipped:
- Backend (main app, not this repo): `accounts_engine.py` (`account_metrics_list()`,
  added `get_performance_cache` to its `db_accounts` import), `api_routes_accounts.py`
  (`GET /accounts/list-with-metrics`), `assets/api_reference.md`.
- This integration: `const.py` (`account_device_info()`), `api.py`
  (`get_account_metrics()`), `__init__.py` (gated third fetch in `_async_update_data()`,
  `async_prune_orphans()` extended with the 12 per-account unique_ids per account),
  `config_flow.py` (`CONF_SHOW_ACCOUNTS` toggle in `_build_schema()`),
  `strings.json`/`translations/en.json`, `sensor.py` (`_ACCOUNT_MONETARY_SENSORS`/
  `_ACCOUNT_PERCENT_SENSORS`, `StockAnalysisAccountBaseSensor` and its two subclasses,
  dynamic `known_ids` + `coordinator.async_add_listener` entity-creation pattern in
  `async_setup_entry`, mirroring `ghostfolio_ha_integration/`'s reference pattern),
  `tests/conftest.py` (`SAMPLE_ACCOUNT_METRICS`), `tests/test_sensor.py` (new file),
  `tests/test_init.py` (prune-on-account-deletion test).

Unique_id scheme for per-account entities: `sap_{key}_{account_id}_{entry_id}`. Per-account
device: `sap_account_{account_id}_{entry_id}`, named "`<account name>` - Totals" (renamed from
an earlier "Stock Analysis Project - `<account name>`" scheme in the July 2026 follow-up
below, before any real users existed, so no unique_id/device-identifier change was needed —
only the display `name` field), `via_device` linked to the portfolio device. Entity removal
on account deletion is
via the existing "Prune Orphaned Entities" button (immediate, no restart needed) or
automatically on the next integration setup/reload (see the July 2026 follow-up below) — not
a live listener that reacts mid-session to a coordinator update, consistent with Phase 1's
architecture and the `ghostfolio_ha_integration/` reference.

Documented Phase 2 simplification: all monetary fields are in the backend's `BASE_CURRENCY`
(a single top-level `base_currency` key in the response), not the account's own native
transaction currency — there is deliberately no per-account `currency` field in the response,
since exposing one would invite exactly the kind of field-mix-up bug Phase 1 hit.

### Follow-up (July 2026) — Show Portfolio Totals toggle + auto-prune on reload

Two gaps found after Phase 2 shipped, fixed in the same session: (1) Phase 1's ten
portfolio-total sensors had no config toggle at all (always created) — added
`CONF_SHOW_PORTFOLIO_TOTALS` (`show_portfolio_totals`), gating both the `sensor.py` entity
creation and the `_async_update_data()` fetch, mirroring how `CONF_SHOW_ACCOUNTS` already
gated Phase 2. (2) Disabling either toggle left the now-hidden entities showing as
"unavailable" in the registry instead of actually being removed — checked the
`ghostfolio_ha_integration/` reference for how it solves this and found it has the identical
gap (its reconfigure flow also just reloads via `async_update_reload_and_abort`, with
`async_prune_orphans()` only ever invoked from its own manual prune button) — so there was
nothing to copy. Fixed here by calling `await coordinator.async_prune_orphans()` once inside
the module-level `async_setup_entry()` (`__init__.py`), right after the coordinator's first
refresh and before platform forwarding. Since a Reconfigure submission always reloads the
config entry (`async_update_reload_and_abort`'s default `reload_even_if_entry_is_unchanged`),
this makes prune re-run — with the freshly gated `valid_unique_ids` — on every reload, so a
disabled toggle's entities are gone by the time the reload completes. The manual "Prune
Orphaned Entities" button is unchanged and still needed for the case where the backend state
changes (e.g. an account deleted) without a Home Assistant restart/reconfigure in between.

## Phase 3 — per-holding sensors

Gated by `CONF_SHOW_HOLDINGS`. One sensor per asset held across all Trading accounts
(mirroring ghostfolio's per-holding pattern: market value, gain, gain %, average buy price,
etc.), plus price-limit number entities (Low Limit / High Limit) per holding.

Needs a new backend endpoint exposing `accounts_engine.holdings_with_market_value()`
aggregated across all Trading accounts (ticker, shares, cost basis, market value, currency,
account membership) — this function already exists per-account; Phase 3's backend work is
mostly a thin aggregating endpoint, similar in spirit to Phase 2's.

## Phase 4 — Pension/House account sensors

Gated by `CONF_SHOW_OTHER_ACCOUNTS`. Sensors for the main app's Pension and House account
types (property/pension valuations tracked via its Account Price Scraper —
`account_scraper_engine.py`, `account_price_history` table). Needs a new backend endpoint
exposing current value + basic performance for each Pension/House account; no FX/TWR math
needed since these are typically single-currency, single-holding constructs already.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DOCUMENTATION — update in the same task, before marking done
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For every change: does this add/remove/alter an entity, config option, endpoint dependency,
or phase milestone?

  README.md      — update the entity table and/or the Planned Phases section for any new
                   entity, config field, or phase that ships.
  AGENTS.md      — update if a new architectural decision, rule, or cross-cutting pattern
                   is introduced (e.g. the dynamic-entity unique_id scheme Phase 2 needs).
  task_prompt.md — update this file's phase descriptions once a phase actually ships, moving
                   it from "next"/planned to "DONE" with the real file list, the same way
                   Phase 1 is documented above.

If backend endpoints change: cross-check against the main app's `AGENTS.md` and its
`assets/api_reference.md` in the same task — this integration's `api.py` must be updated
in lockstep with any renamed/removed backend field.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TESTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Run pytest inside this directory after every individual fix or new test. Do not batch.
- If a change causes a test failure, fix it before moving on — do not comment out tests.
- Write tests for any new business logic: dynamic entity creation/removal, new coordinator
  fields, new config_flow options. Pure glue/thin wrappers do not need dedicated tests.
- Follow conftest.py's existing fixture style (SAMPLE_PORTFOLIO_TOTALS, mock_config_entry,
  mock_api, setup_integration).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHEN DONE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Report:
  - What was changed and in which files (this integration and/or the main app).
  - Tests added or modified, and confirmation pytest passes in this directory.
  - Documentation updated (README.md / AGENTS.md / this file).
  - Any cross-repo impact: if backend endpoints changed, confirm the main app's own
    AGENTS.md/api_reference.md were updated in the same task and note it here.

PUSHING TO GITHUB (see REPOSITORY STATUS above)
  - Commit changes from inside this directory (`Stock_Analysis_Project_ha_integration/` is its
    own separate git repo — do not run these from the main app's repo root) and
    `git push origin main`.
  - After pushing, check `gh run list --repo alfwro13/Stock_Analysis_Project_ha_integration`
    (or the Actions tab) and confirm Validate, Validate with hassfest, and Tests all pass on
    the new commit before considering the task done. A green local `pytest` run does not
    guarantee HACS/hassfest validation also passes — they check things local tests can't (repo
    metadata, `hacs.json`/`manifest.json` schema conformance, brand assets).
  - Only bump `custom_components/stock_analysis_project/manifest.json`'s `version` (which
    triggers `release.yml` and creates a GitHub Release) when a phase or fix is genuinely ready
    to ship — not on every small commit. Confirm with the operator before bumping unless
    they've already asked for it directly.
