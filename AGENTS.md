# AGENTS.md — Stock Analysis Project (Home Assistant Integration)

This file guides AI coding agents working in this repository. Read it before making any changes.

---

## What This Repository Is

A Home Assistant custom integration (HACS-compatible) that connects HA to a self-hosted [Stock Analysis Project](../AGENTS.md) instance — a personal FastAPI portfolio dashboard (the parent repository this integration lives inside, as `Stock_Analysis_Project_ha_integration/`). It polls the main app's own REST API for portfolio totals and market/system status. Unlike the reference `ghostfolio_ha_integration/` in the same parent repo, it has no direct dependency on Yahoo Finance, Ghostfolio, or any other third-party service — all data comes from the one backend.

The full feature description is in [README.md](README.md). The phased build-out plan is in [task_prompt.md](task_prompt.md).

---

## Project Layout

```
custom_components/stock_analysis_project/
├── __init__.py        # Coordinator, setup/unload lifecycle
├── api.py             # StockAnalysisAPI client (X-API-Key auth)
├── binary_sensor.py   # Server/Yahoo/US-market/UK-market/System Status diagnostic sensors
├── button.py          # Refresh Data + Prune Orphaned Entities buttons
├── config_flow.py     # Setup and reconfigure UI flows
├── const.py           # ALL constants live here, plus device_info() helpers
├── diagnostics.py      # Redacted config-entry diagnostics download
├── manifest.json       # Integration metadata and version
├── number.py           # Refresh Interval number entity
├── sensor.py            # 10 portfolio-total sensors
├── strings.json         # Translation source of truth (English only — see below)
├── switch.py             # Enable Auto Refresh switch
└── translations/
    └── en.json          # English only — see below
tests/
├── conftest.py           # Fixtures: mock config entry, mock API, sample payloads
├── test_config_flow.py
├── test_coordinator.py
└── test_init.py
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
- **Never change the unique_id format of an existing entity.** The current scheme is `sap_{key}_{entry_id}` (e.g. `sap_portfolio_gain_fx_{entry_id}`, `sap_enable_auto_refresh_{entry_id}`) — see the full list in `__init__.py`'s `async_prune_orphans()`, which doubles as the canonical unique_id registry. Changing this format orphans the entity for every existing user, breaking their dashboards, automations, and history. If a rename is genuinely unavoidable, document it as a breaking change and update `async_prune_orphans()`'s `valid_unique_ids` set in the same change so the old id gets pruned rather than lingering forever.
- Adding a brand-new entity (Phase 2+) means adding its unique_id to `valid_unique_ids` in the same change — an entity missing from that set gets silently pruned the next time someone presses "Prune Orphaned Entities".

### Session Lifecycle
- `StockAnalysisAPI` owns a single `aiohttp.ClientSession`, lazily created in `_get_session()`. It is closed in `async_unload_entry` via `await entry.runtime_data.api.close()`. Do not create additional sessions and do not call `close()` from anywhere else.

### Extension Points Reserved for Later Phases
- `const.py` already declares `CONF_SHOW_ACCOUNTS`, `CONF_SHOW_HOLDINGS`, `CONF_SHOW_OTHER_ACCOUNTS` for Phases 2-4. **Phase 1 code must not implement any behavior gated on these keys yet** — they exist purely so `config_flow.py`'s schema doesn't need a breaking rename later. Do not read these keys from `config_entry.data` anywhere in the current Phase 1 platforms.

---

## Rules — Never Do These

- **Do not use f-strings in logger calls.**
- **Do not hardcode config keys, timeouts, or retry counts** — use constants from `const.py`.
- **Do not change existing entity unique_id formats.**
- **Do not add a second `aiohttp.ClientSession`** — always go through `StockAnalysisAPI._get_session()`.
- **Do not add German/French/any non-English translation files** — this integration is English-only by design (see above).
- **Do not implement behavior for `CONF_SHOW_ACCOUNTS`/`CONF_SHOW_HOLDINGS`/`CONF_SHOW_OTHER_ACCOUNTS`** until their respective phase is actually being built.
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

### Two Devices, One Config Entry
Every entity in Phase 1 belongs to exactly one of two devices per config entry — "Stock Analysis Project Portfolio" (portfolio-total sensors + the three refresh controls) or "Stock Analysis Project Diagnostics" (the four read-only diagnostic binary sensors + System Status + Prune Orphaned Entities), linked via `via_device`. When adding a new entity, decide which device it conceptually belongs to using this same split — portfolio data and its controls on one device, passive backend/market health signals on the other — rather than introducing a third device or scattering entities inconsistently.

---

## Adding a New Feature — Checklist

- [ ] New constants in `const.py`
- [ ] Logic in the appropriate platform file (`sensor.py`, `binary_sensor.py`, etc.)
- [ ] Translation key added to `strings.json` AND `translations/en.json` (no other language files)
- [ ] If a new config option: add to both `async_step_user` and `async_step_reconfigure` in `config_flow.py`
- [ ] If a new entity: unique_id follows the pattern `sap_{key}_{entry_id}`, and the id is added to `async_prune_orphans()`'s `valid_unique_ids` set in `__init__.py`
- [ ] `README.md` updated to document the new feature/entity
- [ ] `task_prompt.md` updated if the change advances or revises one of the phased milestones
- [ ] Checked against the main app's `AGENTS.md` and the 3 HA-integration-consumed endpoints (see Cross-Reference below) if the change assumes anything about the backend's response shape
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

## Cross-Reference to the Main App

This integration is a pure API consumer of the parent Stock Analysis Project app. It currently depends on exactly 3 backend endpoints:

- `GET /api/accounts/portfolio-totals`
- `POST /api/accounts/refresh-now`
- `GET /api/system/market-status`

The main app's own `AGENTS.md` (`../AGENTS.md`) documents the rule that any change to these endpoints' response schema, auth, or behavior must be checked against this integration in the same change — additive-only field changes are safe (this integration's `.get()`-based access degrades gracefully), but renames or removals require updating this integration in lockstep. If you're working from the main app's side and touch `accounts_engine.py`'s `portfolio_totals()`/`portfolio_gain_fx_decomposition()`/`portfolio_twr_fx()`/`portfolio_twr_ex_fx()`, or `api_routes_accounts.py`'s `portfolio-totals`/`refresh-now` routes, or `api_routes_system.py`'s `market-status` route — re-read this file and `task_prompt.md` before assuming the integration side is unaffected.

---

## Files Not to Touch

- `hacs.json` — HACS metadata, only change for category/filename updates
- `custom_components/stock_analysis_project/manifest.json` — if a change is necessary (e.g. a version bump, a new dependency), inform the operator rather than editing silently
- `.test_venv/` — scratch test environment, gitignored, regenerate rather than hand-edit
