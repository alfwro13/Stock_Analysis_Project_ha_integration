# AGENTS.md — Stock Analysis Project (Home Assistant Integration)

This file guides AI coding agents working in this repository. Read it before making any changes.

---

## What This Repository Is

A Home Assistant custom integration (HACS-compatible) that connects HA to a self-hosted [Stock Analysis Project](../AGENTS.md) instance — a personal FastAPI portfolio dashboard (the parent repository this integration lives inside, as `Stock_Analysis_Project_ha_integration/`). It polls the main app's own REST API for portfolio totals and market/system status. Unlike the reference `ghostfolio_ha_integration/` in the same parent repo, it has no direct dependency on Yahoo Finance, Ghostfolio, or any other third-party service — all data comes from the one backend.

The full feature description is in [README.md](README.md). The phased build-out plan is in `task_prompt.md` — local-only, gitignored from this repo (see "Repository & CI" below), so that filename won't resolve as a link on GitHub.

---

## Project Layout

```
custom_components/stock_analysis_project/
├── __init__.py        # Coordinator, setup/unload lifecycle, async_prune_orphans()
├── api.py             # StockAnalysisAPI client (X-API-Key auth)
├── binary_sensor.py   # Server/Yahoo/US-market/UK-market/System Status diagnostic sensors
├── brand/              # Local HACS brand assets (icon.png / icon@2x.png)
├── button.py          # Refresh Data + Prune Orphaned Entities buttons
├── config_flow.py     # Setup and reconfigure UI flows
├── const.py           # ALL constants live here, plus device_info() helpers
├── diagnostics.py      # Redacted config-entry diagnostics download
├── manifest.json       # Integration metadata and version
├── number.py           # Refresh Interval number entity
├── sensor.py            # 10 static portfolio-total sensors + 12-per-account dynamic sensors
├── strings.json         # Translation source of truth (English only — see below)
├── switch.py             # Enable Auto Refresh switch
└── translations/
    └── en.json          # English only — see below
.github/workflows/        # CI — see "Repository & CI" below
tests/
├── conftest.py           # Fixtures: mock config entry, mock API, sample payloads
├── test_config_flow.py
├── test_coordinator.py
├── test_init.py
└── test_sensor.py
```

---

## Rules — Always Follow These

### Constants
- **All magic values belong in `const.py`** — config keys, defaults, timeouts, retry counts. Never hardcode them inline.
- `device_info()` helpers (`portfolio_device_info()`, `diagnostics_device_info()`) live in `const.py` too — always build device info through these, never construct the `identifiers`/`via_device` dict inline in a platform file.

### Logging
- **Use `%`-style formatting** for all `_LOGGER` calls — never f-strings.
  ```python
  # correct
  _LOGGER.debug("Request to %s failed, retrying (attempt %d/%d): %s", url, attempt, max, err)
  # wrong
  _LOGGER.debug(f"Request to {url} failed: {err}")
  ```
- Do not log full response bodies at ERROR level — `api.py` already truncates to 300 chars; keep that convention for any new logging.

### English Only
- **This integration ships English only** — `strings.json` and `translations/en.json`. Unlike `ghostfolio_ha_integration/` (which maintains `de.json` and `fr.json`), that precedent is deliberately **not** followed here: this is a personal, single-user project with one operator, and maintaining multiple translations for a private tool isn't worth the upkeep. Do not add other language files. Keep `strings.json` and `translations/en.json` in sync with each other (source of truth is `strings.json`, mirrored to `en.json`) — that pairing still matters even with only one language, since HA reads `strings.json` for the bundled default and `translations/en.json` for the runtime-served version.

### Coordinator Data Access
- **Always guard entity properties/callbacks** against `coordinator.data` being `None` or missing keys — see `sensor.py`'s `_totals` property and `binary_sensor.py`'s `_market_status` property, both of which return `{}` rather than raising when data isn't loaded yet.
- **Use `.get()` with defaults** on API response dicts — never bare `dict["key"]`. The backend's response shape is contractually additive-only (see Cross-Reference below) but a bare subscript still turns a transient/older-backend field omission into a crash instead of an `Unknown` state.

### Auto-Refresh Switch / Refresh Interval Number / Refresh Data Button ↔ Coordinator Contract

This integration exposes three controls that reach into the coordinator's polling behavior. The exact mechanism, as implemented in `__init__.py`, is:

- **`StockAnalysisEnableAutoRefreshSwitch`** (switch.py) reads `coordinator.auto_refresh_enabled` for its state and calls `coordinator.async_set_auto_refresh_enabled(bool)` on toggle. That method persists the flag to an HA `Store` (survives restarts), and — when disabling — cancels the pending refresh timer directly (`self._unsub_refresh(); self._unsub_refresh = None`) rather than waiting for it to fire and no-op; when re-enabling, it immediately calls `async_request_refresh()` rather than waiting for the next scheduled tick.
- **`StockAnalysisDataUpdateCoordinator._schedule_refresh()`** is overridden to be a no-op whenever `auto_refresh_enabled` is `False` — this is what actually stops the timer from ever being rearmed by the base class's own post-refresh bookkeeping, complementing the explicit cancel above.
- **`StockAnalysisRefreshIntervalNumber`** (number.py) calls `coordinator.async_set_update_interval(int(value))` on change, which updates `self.update_interval`, cancels and reschedules the timer, and immediately requests a refresh — so a new interval takes effect right away rather than only on the next natural tick.
- **`StockAnalysisRefreshDataButton`** (button.py) calls `await coordinator.api.trigger_refresh_now()` (backend background task — completion is not synchronous) then `await coordinator.async_request_refresh()` (HA-side re-poll). The re-poll can legitimately show stale data for a few seconds since the backend hasn't necessarily finished by the time HA re-polls; this is expected and matches the app's own "heavy operations return immediately" API convention.

**`[NEEDS REVIEW]` coupling to flag on any Home Assistant core upgrade:** `async_set_update_interval()`'s immediate-reschedule behavior relies on two "protected" `DataUpdateCoordinator` internals that are not part of HA's public API — `self._unsub_refresh` and `self._schedule_refresh()`. As of the HA core version this was implemented against (2026.7.0b3), `update_interval`'s setter alone does not cancel/reschedule the pending timer; only `_schedule_refresh()` does, and it's normally only invoked from the coordinator's own refresh-finished path. If a future HA core version renames or restructures these internals, the immediate-reschedule guarantee for both the switch and the number entity could silently stop working (falling back to "takes effect next tick" instead of "takes effect now"). This is already logged in the main app's `audit/audit.md` under the same `[NEEDS REVIEW]` heading — re-verify this coupling (and rerun `tests/test_coordinator.py::test_refresh_interval_change_reschedules`, which is designed to catch a regression here) after any Home Assistant core version bump.

### Entity Unique IDs
- **Never change the unique_id format of an existing entity.** The current schemes are `sap_{key}_{entry_id}` for static/singular entities (e.g. `sap_portfolio_gain_fx_{entry_id}`, `sap_enable_auto_refresh_{entry_id}`) and `sap_{key}_{item_id}_{entry_id}` for per-item dynamic entities (e.g. `sap_cash_balance_{account_id}_{entry_id}` — see "Dynamic Per-Item Entity Sets" below) — see the full construction in `__init__.py`'s `async_prune_orphans()`, which doubles as the canonical unique_id registry. Changing either format orphans the entity for every existing user, breaking their dashboards, automations, and history. If a rename is genuinely unavoidable, document it as a breaking change and update `async_prune_orphans()`'s `valid_unique_ids` set in the same change so the old id gets pruned rather than lingering forever.
- Adding a brand-new static entity means adding its unique_id to `valid_unique_ids` in the same change. A new per-item entity type follows "Dynamic Per-Item Entity Sets" below instead. Either way, an id missing from `valid_unique_ids` gets pruned — see "Config Toggles" below for when prune runs (not just the manual button).

### Session Lifecycle
- `StockAnalysisAPI` owns a single `aiohttp.ClientSession`, lazily created in `_get_session()`. It is closed in `async_unload_entry` via `await entry.runtime_data.api.close()`. Do not create additional sessions and do not call `close()` from anywhere else.

### Extension Points Reserved for Later Phases
- `const.py` declares `CONF_SHOW_OTHER_ACCOUNTS` for Phase 4 — not yet implemented, existing purely so `config_flow.py`'s schema doesn't need a breaking rename later. **Do not implement any behavior gated on this key until Phase 4 is actually being built.** `CONF_SHOW_PORTFOLIO_TOTALS` (Phase 1), `CONF_SHOW_ACCOUNTS` (Phase 2), and `CONF_SHOW_HOLDINGS` (Phase 3) are already implemented — see "Config Toggles" below for the pattern any new toggle must follow.

---

## Rules — Never Do These

- **Do not use f-strings in logger calls.**
- **Do not hardcode config keys, timeouts, or retry counts** — use constants from `const.py`.
- **Do not change existing entity unique_id formats.**
- **Do not add a second `aiohttp.ClientSession`** — always go through `StockAnalysisAPI._get_session()`.
- **Do not add German/French/any non-English translation files** — this integration is English-only by design (see above).
- **Do not implement behavior for `CONF_SHOW_OTHER_ACCOUNTS`** until Phase 4 is actually being built. (`CONF_SHOW_PORTFOLIO_TOTALS`, `CONF_SHOW_ACCOUNTS`, and `CONF_SHOW_HOLDINGS` are already implemented, Phases 1-3.)
- **Do not mutate `coordinator.auto_refresh_enabled` or `coordinator.update_interval` directly from an entity** — always go through `async_set_auto_refresh_enabled()` / `async_set_update_interval()`, which handle persistence and rescheduling together.
- **Do not skip the `coordinator.data` null guard** in any new sensor/binary_sensor property.
- **Do not catch `Exception` silently with `pass`** — at minimum log at debug level with the exception, matching `api.py`'s existing pattern.

---

## Key Architectural Decisions to Preserve

### X-API-Key Static-Header Auth (Not Token Exchange)
Unlike `ghostfolio_ha_integration/`, which performs an anonymous-token-exchange dance (`POST /api/v1/auth/anonymous`) to obtain a bearer token, this integration authenticates with a single static `X-API-Key` header sent on every request (`api.py:_headers()`). This is simpler because the main Stock Analysis Project app's own auth middleware already validates a static API key globally across all `/api/*` routes for any caller that isn't using a session cookie — there is no per-session token to exchange or refresh, and no expiry to handle. `StockAnalysisAuthError` is raised on a 401 response and surfaces to the config flow as `auth_failed`, or to the coordinator as `ConfigEntryAuthFailed` (which prompts the user to reconfigure in HA's UI).

### English-Only Strings
See "Rules — Always Follow These" above. This is a deliberate, explicit divergence from `ghostfolio_ha_integration/`'s de/fr precedent, not an oversight.

### Retry+Backoff on Network Errors, Not on Auth/API Errors
`api.py`'s `_get`/`_post` retry loop (`API_MAX_RETRIES`, exponential backoff `2 ** attempt`) only catches `aiohttp.ClientError` (transport-level failures). A 401 raises `StockAnalysisAuthError` immediately with no retry — retrying an invalid key wastes time and doesn't change the outcome. A non-200/401 response raises `StockAnalysisAPIError` immediately for the same reason — retrying won't fix a 500 from the backend within the same request cycle either, and the coordinator's own next scheduled poll is the effective retry.

### System Status Polarity (Inverted)
`StockAnalysisSystemStatusSensor` (binary_sensor.py) reports `is_on = not system_ok` — "on" means a problem was detected, matching Home Assistant's convention that a `binary_sensor`'s "on" state should be the notable/alert state (compare to `BinarySensorDeviceClass.PROBLEM` semantics elsewhere in HA, though this entity intentionally uses no `device_class` since it's a bespoke "is anything wrong on the backend" flag rather than any single standard problem category). Do not flip this polarity without updating the README's polarity note in the same change.

### Devices: Two Static + One Dynamic Family, Per Config Entry
Every static (non-per-item) entity belongs to exactly one of two fixed devices per config entry — "Stock Analysis Project Portfolio" (portfolio-total sensors + the three refresh controls) or "Stock Analysis Project Diagnostics" (the four read-only diagnostic binary sensors + System Status + Prune Orphaned Entities), linked via `via_device` back to the Portfolio device. Phase 2 added a third, *dynamic* device family on top of this — one device per Trading account (built via `account_device_info()` in `const.py`), also `via_device`-linked to the Portfolio device — for the per-account entity sets (see "Dynamic Per-Item Entity Sets" below). When adding a new static entity, decide which of the two fixed devices it conceptually belongs to (portfolio data/controls vs. passive backend/market health signals) rather than introducing a new fixed device. When adding a new per-item entity set (Phase 3 holdings, Phase 4 pension/house), follow the same per-item dynamic-device pattern as accounts rather than lumping items onto one of the two fixed devices.

### Dynamic Per-Item Entity Sets (Phase 2+)
Phase 2 introduced the integration's first per-item dynamic entity set (per-Trading-account sensors); Phase 3 (per-holding) follows the same pattern with one deliberate exception (nested `via_device`, see below); Phase 4 (Pension/House) should follow suit too.

- **Unique_id scheme:** `sap_{key}_{item_id}_{entry_id}` — the item's own id inserted between the field key and the entry id (Phase 2: `item_id` is the Trading account's DB id, e.g. `sap_cash_balance_{account_id}_{entry_id}`; Phase 3: `item_id` is a composite `{account_id}_{ticker}`, e.g. `sap_holding_market_value_{account_id}_{ticker}_{entry_id}`, since a ticker alone isn't unique across accounts).
- **Device scheme:** one HA device per item, identifier `sap_{item_type}_{item_id}_{entry_id}` (Phase 2: `sap_account_{account_id}_{entry_id}`; Phase 3: `sap_holding_{account_id}_{ticker}_{entry_id}`), named `"<item name> - Totals"` for Phase 2 or `"<ticker> (<account name>)"` for Phase 3 — the item's own name from the backend. `via_device` links to the shared Portfolio device **for Phase 2** (`sap_portfolio_{entry_id}`), but Phase 3 holdings are a deliberate exception — `via_device` links to the **owning account's** device (`sap_account_{account_id}_{entry_id}`) instead, since a holding is conceptually owned by its account and nesting it there keeps the per-account separation visible in HA's own device tree, matching the account-scoped semantics of the reference Ghostfolio sensor this phase was modeled on (each holding carries an `account:` field, not a bare cross-account ticker identity). A future per-item entity set should default to "via_device → Portfolio" unless it has the same kind of natural parent-item relationship holdings have to accounts. Built through a `const.py` helper (`account_device_info()` / `holding_device_info()`), same as the two static devices — never construct the identifiers dict inline in a platform file. Because every per-item entity sets `_attr_has_entity_name = True`, this device name also drives the auto-generated `entity_id` (`sensor.<device_name_slug>_<entity_name_slug>`, e.g. `sensor.isa_totals_1_month_gain`) — there is no separate entity_id scheme to hand-maintain.
- **Dynamic creation:** a `known_ids: set[str]` built inside `async_setup_entry`, plus a `@callback`-decorated `_update_*_sensors()` closure registered via `config_entry.async_on_unload(coordinator.async_add_listener(...))` and also invoked once immediately after the initial static `async_add_entities(...)` call (covers data already present from the first refresh). Mirrors `ghostfolio_ha_integration/`'s reference pattern in its own `sensor.py`, though no code is shared between the two repos. Phase 3 also introduced this same scaffolding in `number.py`, which previously had no dynamic-entity pattern at all (its only entity, Refresh Interval, is a static singleton).
- **Per-item field lookup must key by the item's id, never by list index** — coordinator data list order across refreshes is not guaranteed stable. Every per-item sensor's value/state property scans the latest list and matches on id (Phase 3: matches on `(account_id, ticker)` tuple, not `ticker` alone), defaulting to `{}` if the item is momentarily missing (e.g. deleted mid-session, before the next prune).
- **Dynamic removal** happens two ways: on-demand via the existing "Prune Orphaned Entities" button, and automatically every time the config entry is set up or reloaded (see "Config Toggles" below) — never via a live listener reacting mid-session to a coordinator update. An item disappearing from a refresh leaves its entities/device in the registry (stale) until one of those two triggers runs.
- **One sensor per item, not one sensor per field, is also a valid choice** — Phase 3's holding sensor is a deliberate departure from Phase 1/2's "one entity per metric" convention: a single Market Value sensor carries every other data point (shares, prices, gain, dividends, trend, RSI, earnings date, limit flags, etc.) as `extra_state_attributes` rather than as sibling entities. This mirrors the reference Ghostfolio sensor's own shape and was an explicit operator choice, not a default to assume for future phases — evaluate per-phase which shape better serves the data (attributes for read-only context that doesn't need its own history graph; separate entities for anything a user would want to graph, automate on, or individually enable/disable).

Cross-reference: `tests/test_sensor.py` (dynamic-entity tests, including a cross-item value-mixup regression test), `tests/test_number.py` (Phase 3 holding-limit number tests), and `tests/test_init.py::test_prune_orphans_removes_deleted_account_sensors` / `::test_prune_orphans_removes_deleted_holding_entities_and_devices`.

### Config Toggles ("Show ...") Must Gate Fetch + Entities + Prune Together, and Prune Runs on Every Setup
Every `CONF_SHOW_*` toggle that gates a sensor group must gate three things together, not just entity creation:
1. The coordinator's `_async_update_data()` fetch for that group — skip the API call entirely, substituting the same empty/None shape its `.get()`-based readers already treat as "no data yet" (e.g. `{}` for portfolio totals, `{"base_currency": None, "accounts": []}` for account metrics).
2. The corresponding platform's entity construction in `async_setup_entry`.
3. `async_prune_orphans()`'s `valid_unique_ids` computation for that group's static ids. (Per-item dynamic ids are covered for free, since they're only added to `valid_unique_ids` when present in the — now correctly gated — coordinator data.)

`async_prune_orphans()` is called once inside the module-level `async_setup_entry()` (`__init__.py`), immediately after `coordinator.async_config_entry_first_refresh()` and before `hass.config_entries.async_forward_entry_setups(...)` — and it removes both stale entities *and* devices with no remaining valid entities (an account whose entities are all pruned no longer leaves an empty device behind). Since a Reconfigure submission always reloads the config entry by default (`async_update_reload_and_abort`'s `reload_even_if_entry_is_unchanged=True`), this makes disabling a toggle during Reconfigure take effect immediately — its entities and device are pruned as part of the very reload that applies the new setting — rather than only being cleaned up on a manual "Prune Orphaned Entities" press. Safe to call at this point in setup because prune only ever *removes* pre-existing registry rows and never depends on the current session's entities having been (re-)added yet.

`ghostfolio_ha_integration/` does **not** have this auto-prune-on-setup behavior — checked it as prior art and found the identical gap (its reconfigure flow also just reloads, with `async_prune_orphans()` only ever invoked from its own manual prune button) — so this is this integration's own addition, not adopted from the reference.

Cross-reference: `tests/test_init.py::test_disabling_show_accounts_via_reload_auto_removes_account_sensors` and `::test_disabling_show_portfolio_totals_via_reload_auto_removes_portfolio_sensors`.

---

## Adding a New Feature — Checklist

- [ ] New constants in `const.py`
- [ ] Logic in the appropriate platform file (`sensor.py`, `binary_sensor.py`, etc.)
- [ ] Translation key added to `strings.json` AND `translations/en.json` (no other language files)
- [ ] If a new config option: add to both `async_step_user` and `async_step_reconfigure` in `config_flow.py` (both already call the single shared `_build_schema()`, so one edit covers both)
- [ ] If a new `CONF_SHOW_*` toggle: gate the coordinator fetch, the platform's entity construction, AND `async_prune_orphans()`'s `valid_unique_ids` together — see "Config Toggles" above. A toggle that only gates entity creation leaves stale rows behind when disabled.
- [ ] If a new static entity: unique_id follows `sap_{key}_{entry_id}`, and the id is added to `async_prune_orphans()`'s `valid_unique_ids` set in `__init__.py`. If a new per-item dynamic entity set: follow "Dynamic Per-Item Entity Sets" above (unique_id/device scheme, `known_ids` + listener, id-based lookup) instead.
- [ ] `README.md` updated to document the new feature/entity
- [ ] `task_prompt.md` updated if the change advances or revises one of the phased milestones — this file is local-only and gitignored from this repo, see "Repository & CI" below
- [ ] Checked against the main app's `AGENTS.md` and the 4 HA-integration-consumed endpoints (see Cross-Reference below) if the change assumes anything about the backend's response shape
- [ ] `pytest` run inside this directory and passing (see Testing below)

---

## Testing Changes

Unlike `ghostfolio_ha_integration/` (no automated tests), this integration has a real `pytest` suite from day one, using `pytest-homeassistant-custom-component`. **Run the test suite inside this directory before considering any change complete:**

```bash
cd Stock_Analysis_Project_ha_integration
source .test_venv/bin/activate   # scratch venv set up during initial build, gitignored
pytest
```

`requirements_test.txt` pins the test dependencies (`pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component`). If `.test_venv/` doesn't exist (e.g. a fresh clone), recreate it and `pip install -r requirements_test.txt` before running `pytest`. There is no live Home Assistant instance available in this environment — `pytest-homeassistant-custom-component` provides the test harness that stands in for one.

---

## Repository & CI

As of July 2026 this directory is **also** its own independent git repository, published at https://github.com/alfwro13/Stock_Analysis_Project_ha_integration (branch `main`) — in addition to remaining a subfolder of the main app's own checkout (where it's gitignored, so the main app's own repo never sees these files). Commit and push changes from inside this directory; it has its own remote, separate from the main app's.

CI runs on every push/PR via `.github/workflows/`:
- `validate.yml` — HACS repository validation (`hacs/action`).
- `hassfest.yaml` — Home Assistant's own manifest/schema validator.
- `test.yml` — runs this repo's `pytest` suite (not present in `ghostfolio_ha_integration/`, which has tests but no CI workflow that runs them — added here deliberately).
- `release.yml` — creates a GitHub Release + zip asset whenever `custom_components/stock_analysis_project/manifest.json`'s `version` changes on a push to `main`. Only bump the version when a phase or fix is genuinely ready to ship, and confirm with the operator first unless they've already asked for it directly.

A green local `pytest` run does not guarantee CI passes — `validate.yml` also checks repository-level GitHub metadata (description, topics, brand assets at `custom_components/stock_analysis_project/brand/icon.png`) that local tests can't see. After pushing, check `gh run list --repo alfwro13/Stock_Analysis_Project_ha_integration` (or the Actions tab) before considering a change done.

`task_prompt.md` (this directory's own phase-by-phase implementation notes) is intentionally gitignored from this repo — it's an internal AI-agent working doc, not something that belongs in a public HACS repo (same treatment as `audit/ha_integration_task_prompt.md` in the main app's own repo). It still exists locally and should still be read/updated per the checklist above; it just never gets committed here.

---

## Cross-Reference to the Main App

This integration is a pure API consumer of the parent Stock Analysis Project app. It currently depends on exactly 6 backend endpoints:

- `GET /api/accounts/portfolio-totals`
- `POST /api/accounts/refresh-now`
- `GET /api/system/market-status`
- `GET /api/accounts/list-with-metrics` (Phase 2 — per-Trading-account metrics)
- `GET /api/accounts/holdings-list` (Phase 3 — per-holding metrics across all Trading accounts)
- `POST /api/accounts/holding-price-limit` (Phase 3 — sets a holding's Low/High Limit)

The main app's own `AGENTS.md` (`../AGENTS.md`) documents the rule that any change to these endpoints' response schema, auth, or behavior must be checked against this integration in the same change — additive-only field changes are safe (this integration's `.get()`-based access degrades gracefully), but renames or removals require updating this integration in lockstep. If you're working from the main app's side and touch `accounts_engine.py`'s `portfolio_totals()`/`portfolio_gain_fx_decomposition()`/`portfolio_twr_fx()`/`portfolio_twr_ex_fx()`/`account_metrics_list()`/`holdings_with_metrics_all_accounts()`/`set_holding_price_limit()`, or `api_routes_accounts.py`'s `portfolio-totals`/`refresh-now`/`list-with-metrics`/`holdings-list`/`holding-price-limit` routes, or `api_routes_system.py`'s `market-status` route — re-read this file and `task_prompt.md` before assuming the integration side is unaffected.

---

## Files Not to Touch

- `hacs.json` — HACS metadata, only change for category/filename updates
- `custom_components/stock_analysis_project/manifest.json` — if a change is necessary (e.g. a version bump, a new dependency), inform the operator rather than editing silently
- `.test_venv/` — scratch test environment, gitignored, regenerate rather than hand-edit
