Read AGENTS.md (this directory) in full before writing a single line of code. Read the main app's own AGENTS.md (`../AGENTS.md`) if the change touches backend endpoints or `accounts_engine.py`.

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

## Phase 2 — next: individual Trading account sensors

Gated by `CONF_SHOW_ACCOUNTS` (already declared, unused). Mirrors ghostfolio's per-account
sensor set: value, cost, gain, unrealized P&L, simple gain %, Time-Weighted Return %,
dividends, cash balance — one sensor set per Trading account.

Expected backend work is much smaller than Phase 1's: `accounts_engine.py` already has
`account_summary()`, `total_value()`, `unrealized_pnl()`, `holdings_with_market_value()`,
etc. per-account — Phase 1's new math (FX decomposition, TWR) was the hard part and Phase 2
should mostly be composing already-existing per-account functions into one bulk response,
not deriving new formulas.

Expected new backend surface (to confirm/adjust at implementation time, not to blindly
follow): a single new endpoint (e.g. `GET /api/accounts/list-with-metrics` or similar)
returning an array of per-account metric dicts for every non-deleted Trading account, so
this integration issues one API call per coordinator cycle rather than N.

Expected new integration-side work:
- `const.py`: no new constants needed beyond what's declared, unless a per-account entity
  needs its own unique_id qualifier (likely `sap_{key}_{account_id}_{entry_id}` — decide
  the exact scheme before writing sensor.py changes, and document it in this integration's
  AGENTS.md once chosen).
- `sensor.py`: dynamic entity creation per account (this is new — Phase 1's 10 sensors are
  static/singular). Follow ghostfolio's `known_ids`-set dedup pattern referenced in its own
  AGENTS.md as the closest prior art, even though this repo doesn't share code with it.
- `config_flow.py` + `strings.json`/`en.json`: surface `CONF_SHOW_ACCOUNTS` as a real toggle.
- New tests for dynamic per-account entity creation/removal as accounts are added/deleted
  on the backend.

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
