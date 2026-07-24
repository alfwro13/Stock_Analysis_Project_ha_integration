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
├── number.py           # Refresh Interval number + per-holding Low/High Limit numbers
├── sensor.py            # 10 static portfolio-total + 7 static Market Health + per-account, per-holding, and per-other-account dynamic sensors
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
├── test_number.py
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
- **`StockAnalysisRefreshIntervalNumber`** (number.py) calls `coordinator.async_set_update_interval(int(value))` on change, which sets `self.update_interval` and immediately calls the public `async_request_refresh()` — so a new interval takes effect right away rather than only on the next natural tick. This relies on no protected coordinator internals: `DataUpdateCoordinator._async_refresh()` (run by `async_request_refresh()`) unsubscribes the pending timer at its own entry and re-arms it via `_schedule_refresh()` in its `finally` block once the refresh completes, picking up the just-updated interval automatically. (Fixed 2026-07-03 — see the narrowed `[NEEDS REVIEW]` note below, which now applies only to the auto-refresh-disable path.)
- **Restore-on-startup must also reach the coordinator (fixed 2026-07-11).** `StockAnalysisRefreshIntervalNumber` is a `RestoreNumber`: `async_added_to_hass()` restores its last value from HA's own entity-restore storage into `self._attr_native_value` on every startup. The original implementation stopped there — it never re-applied the restored value to `coordinator.update_interval`, which instead reverted silently to `CONF_UPDATE_INTERVAL` (the config-flow field, only ever used to construct the coordinator in `async_setup_entry`) on every restart. Net effect: the entity could *display* one interval while the coordinator was *actually* polling at a different one, indefinitely, until the user happened to touch the number entity again. Fixed by calling the new `coordinator.sync_update_interval_from_restore(minutes)` at the end of `async_added_to_hass()` — deliberately a separate method from `async_set_update_interval()`, since it must NOT force an `async_request_refresh()` (that would add one extra unconditional backend call to every single HA startup); it only corrects `self.update_interval` so the coordinator's *next* naturally-scheduled tick reschedules using the right value going forward. See `tests/test_coordinator.py::test_sync_update_interval_from_restore_applies_without_forcing_refresh`.
- **`StockAnalysisRefreshDataButton`** (button.py) calls `await coordinator.api.trigger_refresh_now()` (backend background task — completion is not synchronous) then `await coordinator.async_request_refresh()` (HA-side re-poll). The re-poll can legitimately show stale data for a few seconds since the backend hasn't necessarily finished by the time HA re-polls; this is expected and matches the app's own "heavy operations return immediately" API convention.

**`[NEEDS REVIEW]` coupling remaining after the 2026-07-03 fix to `async_set_update_interval()`:** `async_set_auto_refresh_enabled()`'s disable branch still cancels the pending timer directly (`self._unsub_refresh(); self._unsub_refresh = None`) — there's no public `DataUpdateCoordinator` API to cancel a pending scheduled refresh without either letting it run or fully shutting the coordinator down via `async_shutdown()` (too destructive here: it also unsubscribes the shutdown listener and permanently shuts down the debouncer). The `_schedule_refresh()` override (a no-op while `auto_refresh_enabled` is `False`) is a separate, already-accepted category of coupling — a subclass override of a documented extension point, not an external poke of a private attribute — and is unaffected by this note. `async_set_update_interval()` itself no longer touches either internal. If a future HA core version renames/restructures `_unsub_refresh` or the `_schedule_refresh()` override point, only the auto-refresh-disable path is at risk now, not the update-interval path. Re-verify `tests/test_coordinator.py::test_refresh_interval_change_reschedules` and `::test_disable_auto_refresh_suspends_timer` after any Home Assistant core version bump.

### Market-Hours-Aware Refresh Skip (Phase 4+)

`CONF_SKIP_REFRESH_WHEN_MARKETS_CLOSED` (default **off**, since the July 2026 "Always-on polling" follow-up — kept only for anyone who wants fewer polls purely to reduce load on their own server) makes `StockAnalysisDataUpdateCoordinator._async_update_data()` skip re-fetching `portfolio_totals`/`account_metrics`/`holdings` on a tick where both `market_status.us_market_open` and `market_status.uk_market_open` are `False` — those three are all tied to live market prices, which can't have changed while every market is shut, so re-fetching them is pure waste. The mechanism:

- `market_status` itself is **always** fetched first, every tick, regardless of the toggle — it's the cheapest of the four calls and is what lets the coordinator notice a market reopening.
- The skip only applies from the **second** refresh onward (`self.data is not None`) — the very first refresh after setup always fetches everything, since there's no prior data yet to reuse.
- When skipped, the previous refresh's `portfolio_totals`/`account_metrics`/`holdings` values are carried forward verbatim into the new `self.data`, so sensors simply keep showing their last value rather than going `Unknown`.
- **Other Accounts (`get_other_accounts()`) is never gated by this toggle** — Pension/House valuations come from the backend's own Account Price Scraper, which runs on its own schedule independent of stock market hours, so there is no basis for assuming that data hasn't changed just because markets are closed.

Cross-reference: `tests/test_coordinator.py::test_markets_closed_skips_trading_fetches_on_second_refresh`, `::test_markets_open_always_fetches_trading_data`, `::test_skip_toggle_disabled_always_fetches_regardless_of_market_status`, `::test_first_refresh_always_fetches_even_if_markets_closed`.

### Entity Unique IDs
- **Never change the unique_id format of an existing entity.** The current schemes are `sap_{key}_{entry_id}` for static/singular entities (e.g. `sap_portfolio_gain_fx_{entry_id}`, `sap_enable_auto_refresh_{entry_id}`) and `sap_{key}_{item_id}_{entry_id}` for per-item dynamic entities (e.g. `sap_cash_balance_{account_id}_{entry_id}` — see "Dynamic Per-Item Entity Sets" below) — see the full construction in `__init__.py`'s `async_prune_orphans()`, which doubles as the canonical unique_id registry. Changing either format orphans the entity for every existing user, breaking their dashboards, automations, and history. If a rename is genuinely unavoidable, document it as a breaking change and update `async_prune_orphans()`'s `valid_unique_ids` set in the same change so the old id gets pruned rather than lingering forever.
- Adding a brand-new static entity means adding its unique_id to `valid_unique_ids` in the same change. A new per-item entity type follows "Dynamic Per-Item Entity Sets" below instead. Either way, an id missing from `valid_unique_ids` gets pruned — see "Config Toggles" below for when prune runs (not just the manual button).

### Session Lifecycle
- `StockAnalysisAPI` owns a single `aiohttp.ClientSession`, lazily created in `_get_session()`. It is closed in `async_unload_entry` via `await entry.runtime_data.api.close()`. Do not create additional sessions and do not call `close()` from anywhere else.

### Extension Points
All six phases have now shipped — `CONF_SHOW_PORTFOLIO_TOTALS` (Phase 1), `CONF_SHOW_ACCOUNTS` (Phase 2), `CONF_SHOW_HOLDINGS` (Phase 3), `CONF_SHOW_OTHER_ACCOUNTS` (Phase 4), `CONF_SHOW_MARKET_HEALTH` (Phase 5), and `CONF_SHOW_MARKETS` (Phase 6) are all fully implemented — see "Config Toggles" below for the pattern any new toggle must follow. There are no remaining reserved-but-unimplemented config keys.

---

## Rules — Never Do These

- **Do not use f-strings in logger calls.**
- **Do not hardcode config keys, timeouts, or retry counts** — use constants from `const.py`.
- **Do not change existing entity unique_id formats.**
- **Do not add a second `aiohttp.ClientSession`** — always go through `StockAnalysisAPI._get_session()`.
- **Do not add German/French/any non-English translation files** — this integration is English-only by design (see above).
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

### Per-Section Fallback on the Coordinator, Not Just Per-Request Retry (added July 2026)
`api.py`'s retry+backoff (above) only covers a single HTTP request. Before this fix, `_async_update_data()` awaited all ~8 backend fetches (`market_status`, `portfolio_totals`, `account_metrics`, `holdings`, `other_accounts`, `market_regime`, `macro_conditions`, `markets`) inside one `try`/`except`, so if *any one* of them still raised `StockAnalysisAPIError` after its retries were exhausted (e.g. the backend momentarily slow while a heavy scheduled job like ML training or the quant scan runs), the whole `_async_update_data()` call raised `UpdateFailed` — `coordinator.last_update_success` went `False` and every entity in the integration went unavailable, even though the other seven fetches in that same cycle had already succeeded and the web app itself was reachable throughout. Operator-reported symptom: "all sensors show unavailable a couple of times, even though the web app is up."

Fixed with `coordinator._fetch_section(key, coro)`: each of the 8 fetches is now wrapped individually. On a `StockAnalysisAPIError`, if `self.data` already holds a previous value for that section (i.e. this isn't the coordinator's very first refresh), it logs a warning and returns the last-known value for that section only — the update as a whole still succeeds, `last_update_success` stays `True`, `last_success_time` still advances, and every other section still gets its fresh value. `StockAnalysisAuthError` is deliberately **not** caught here — an invalid API key isn't a transient, per-section problem, so it still propagates straight through to `ConfigEntryAuthFailed` exactly as before. A section failing on the very first-ever refresh (`self.data is None`, nothing to fall back to) still raises and fails `config_entry_first_refresh`, unchanged from before — this only fixes the *steady-state* case where the coordinator has already refreshed successfully at least once.

This means a section can now silently serve stale data indefinitely if its endpoint stays broken — there is no staleness cutoff that eventually flips it to unavailable. That's an intentional simplicity tradeoff, not an oversight: `StockAnalysisLastUpdateSuccessSensor` (see above) already exists specifically so a user can tell "coordinator still polling, this value just hasn't changed" from the log line each stale section now emits (`_LOGGER.warning("Failed to refresh %s, using last-known data: %s", key, err)`), and per-value TTLs would be new complexity beyond what was actually asked for.

Cross-reference: `tests/test_coordinator.py::test_transient_error_on_subsequent_refresh_falls_back_to_last_known_data` and the pre-existing `::test_api_error_marks_server_offline` (unchanged — still covers the first-refresh-has-no-fallback case).

### System Status Polarity (Inverted)
`StockAnalysisSystemStatusSensor` (binary_sensor.py) reports `is_on = not system_ok` — "on" means a problem was detected, matching Home Assistant's convention that a `binary_sensor`'s "on" state should be the notable/alert state (compare to `BinarySensorDeviceClass.PROBLEM` semantics elsewhere in HA, though this entity intentionally uses no `device_class` since it's a bespoke "is anything wrong on the backend" flag rather than any single standard problem category). Do not flip this polarity without updating the README's polarity note in the same change.

### Last Update Success Sensor — Poll Timestamp, Not Value-Change Timestamp (added 2026-07-11)
Home Assistant only updates an entity's own `last_changed` when its *state value* actually differs from the previous poll — a `force_update`-less entity polling successfully every minute but returning an identical number every time looks, from its own history, indistinguishable from an entity that stopped being polled entirely. This is expected and correct for slow-moving backend data (e.g. `gain_1d` genuinely doesn't change over a weekend, since `account_performance_refresh_job` only runs Mon-Fri and `account_value_snapshot_job` only runs once daily) but it means no existing entity in this integration could answer "is the coordinator actually still polling?" on its own. `StockAnalysisLastUpdateSuccessSensor` (sensor.py, `device_class: timestamp`, on the Diagnostics device) exists specifically to answer that: `coordinator.last_success_time` (`__init__.py`) is stamped with `dt_util.utcnow()` at the very end of a successful `_async_update_data()` — after every fetch has completed but only on the success path (an exception raised earlier in the method skips the stamp, so a failed poll leaves this sensor's value exactly where it was) — regardless of whether anything else in the returned payload changed. Unlike every other sensor in this integration it is **unconditional**, not gated behind any "Show ..." toggle, since its entire purpose is confirming the coordinator's health independent of which data groups are enabled.

### Devices: Two Static + Four Dynamic Families, Per Config Entry
Every static (non-per-item) entity belongs to exactly one of two fixed devices per config entry — "Stock Analysis Project Portfolio" (portfolio-total sensors + the three refresh controls) or "Stock Analysis Project Diagnostics" (the four read-only diagnostic binary sensors + System Status + Last Update Success + Prune Orphaned Entities), linked via `via_device` back to the Portfolio device. Phase 2 added a third, *dynamic* device family on top of this — one device per Trading account (built via `account_device_info()` in `const.py`), also `via_device`-linked to the Portfolio device — for the per-account entity sets (see "Dynamic Per-Item Entity Sets" below). Phase 3 added a fourth device family — one **Holdings** device per Trading account (built via `account_holdings_device_info()`), `via_device`-linked to that account's own Totals device — so each account with holdings shows up as two devices: `"<name> - Totals"` and `"<name> - Holdings"`. Unlike the account-device family, the holdings-device family is not one-device-per-item: every holding (ticker) in an account contributes its entities onto that account's single shared Holdings device rather than getting a device of its own — see "Shared-Device Per-Item Entity Sets" below for why. Phase 4 added a fifth device family — a single **"Other Accounts"** device, `via_device`-linked to the Portfolio device, shared by every Pension/House account's sensor — see "Single Shared Device for a Non-Item-Specific Group (Phase 4+)" below; this is a third, distinct device-topology choice from the two above. Phase 5 added a sixth device — **"Market Health"**, `via_device`-linked to the Portfolio device — but it is *not* a new per-item pattern: its 7 sensors are static and non-per-item (no list of backend items to discover/prune), so it's really a third instance of the original static-fixed-device shape (alongside Portfolio and Diagnostics), just for a third conceptual grouping (market-wide macro/sentiment signals) rather than a new topology choice. See `StockAnalysisMarketHealthBaseSensor` (`sensor.py`) — built exactly like `StockAnalysisBaseBinarySensor`, just targeting `market_health_device_info()` instead of `diagnostics_device_info()`. Phase 6 added a seventh device — a single **"Markets"** device, `via_device`-linked to the Portfolio device — a fourth *dynamic* per-item family using the same "shared device for a non-item-specific group" topology as Phase 4's Other Accounts (`markets_device_info()`), one sensor per tracked global index/commodity/FX/rate ticker. When adding a new static entity, decide which of these three fixed devices it conceptually belongs to (portfolio data/controls, passive backend/system diagnostics, or market-wide macro/sentiment) rather than introducing a new fixed device. When adding a new per-item entity set, decide up front which of the four existing per-item device patterns fits: one device per item (Phase 2), one shared device per item's natural parent (Phase 3), or one shared device for the whole group with no natural parent (Phase 4/6).

### Stable Identity for Items Whose Own Symbol Can Change (Phase 6)
`GET /api/markets`' tile payload carries a resolved `ticker` field (whichever of a dual-instrument index's spot/futures symbols is "in session" right now, per `markets_engine.resolve_tile()`, e.g. `^GSPC` ↔ `ES=F`) that changes independently of the underlying index's own identity — never key a sensor's `unique_id` off a field like this. The first Phase 6 design used one sensor per index and keyed it off the tile's `registry_ticker` field (the registry row's own stable primary ticker) specifically to avoid recreating the entity every time the resolved ticker swapped. The operator then asked for independent spot and futures sensors instead (see below), which sidesteps the problem a different way — but the underlying lesson still applies to any future per-item entity set: before keying identity off a backend API field, check whether it's documented as the row's own primary key vs. something described as "currently displayed" or "resolved," since only the former is safe to build a `unique_id` on.

**Dual-instrument tickers get two independent sensors, not one swapping sensor.** `assemble_markets_payload()`'s tile payload has a `dual_instrument` field (`None` for a plain ticker; `{"spot": {...}, "future": {...}}` for one of the 5 dual-instrument indexes) carrying **both** instruments' live price/change simultaneously — `registry_lookup_tickers()` was extended to warm both the spot and future ticker's `market_pulse_cache` row regardless of which one the `/markets` page itself is currently displaying, so both are always populated. `StockAnalysisMarketIndexSensor` takes a `sub_key` (`None`/`"spot"`/`"future"`) selecting which side it represents; its `unique_id` is keyed by that side's own fixed ticker (`row["ticker"]`/`row["future_ticker"]`, e.g. `ES=F`) — naturally stable on its own, since a spot sensor is always spot and a futures sensor always futures, with no swap at the entity level at all. An `is_active` attribute (present only on spot/futures sensors) tells you which side the `/markets` page itself currently treats as primary, without affecting either sensor's own state. The `registry_ticker` field is still used internally to relocate a tile in `coordinator.market_tiles()` (tiles are still one-per-registry-row, not one-per-instrument) but no longer needs to double as the unique_id.

### Dynamic Per-Item Entity Sets (Phase 2+)
Phase 2 introduced the integration's first per-item dynamic entity set (per-Trading-account sensors, one device per account). Use this pattern for a new per-item entity set only when each item is genuinely independent and worth its own device — see Phase 3 and Phase 4 below for the two alternatives when items share a natural grouping instead.

- **Unique_id scheme:** `sap_{key}_{item_id}_{entry_id}` — the item's own id inserted between the field key and the entry id (Phase 2: `item_id` is the Trading account's DB id, e.g. `sap_cash_balance_{account_id}_{entry_id}`).
- **Device scheme:** one HA device per item, identifier `sap_{item_type}_{item_id}_{entry_id}` (Phase 2: `sap_account_{account_id}_{entry_id}`), named `"<item name> - Totals"` — the item's own name from the backend, unprefixed — `via_device` linked to the shared Portfolio device. Built through a `const.py` helper (`account_device_info()`), same as the two static devices — never construct the identifiers dict inline in a platform file. Because every per-item entity sets `_attr_has_entity_name = True`, this device name also drives the auto-generated `entity_id` (`sensor.<device_name_slug>_<entity_name_slug>`, e.g. `sensor.isa_totals_1_month_gain`) — there is no separate entity_id scheme to hand-maintain.
- **Dynamic creation:** a `known_ids: set[str]` built inside `async_setup_entry`, plus a `@callback`-decorated `_update_*_sensors()` closure registered via `config_entry.async_on_unload(coordinator.async_add_listener(...))` and also invoked once immediately after the initial static `async_add_entities(...)` call (covers data already present from the first refresh). Mirrors `ghostfolio_ha_integration/`'s reference pattern in its own `sensor.py`, though no code is shared between the two repos.
- **Per-item field lookup must key by the item's id, never by list index** — coordinator data list order across refreshes is not guaranteed stable. Every per-item sensor's value/state property scans the latest list and matches on id, defaulting to `{}` if the item is momentarily missing (e.g. deleted mid-session, before the next prune).
- **Dynamic removal** happens two ways: on-demand via the existing "Prune Orphaned Entities" button, and automatically every time the config entry is set up or reloaded (see "Config Toggles" below) — never via a live listener reacting mid-session to a coordinator update. An item disappearing from a refresh leaves its entities/device in the registry (stale) until one of those two triggers runs.

Cross-reference: `tests/test_sensor.py` (dynamic-entity tests, including a cross-item value-mixup regression test) and `tests/test_init.py::test_prune_orphans_removes_deleted_account_sensors`.

### Shared-Device Per-Item Entity Sets (Phase 3+)
Phase 3 (per-holding sensors/numbers) needed a variant of the pattern above: **the operator explicitly asked for holdings to NOT each get their own device** — instead, all of a Trading account's holdings share that one account's single Holdings device. This is a different tradeoff from Phase 2's accounts (where each account genuinely is its own independent thing worth a device) — holdings are numerous, per-account, and conceptually "parts of" the account, so grouping them onto one device per account keeps the device list from exploding into dozens of near-empty devices.

- **Unique_id scheme is unchanged from the pattern above:** `sap_{key}_{item_id}_{entry_id}`, still fully per-item — Phase 3's `item_id` is a composite `{account_id}_{ticker}`, e.g. `sap_holding_market_value_{account_id}_{ticker}_{entry_id}`, since a ticker alone isn't unique across accounts. Unique_id uniqueness has nothing to do with which device an entity is assigned to.
- **Device scheme is per-*parent*, not per-item:** one device per Trading account dedicated to holdings, identifier `sap_account_holdings_{account_id}_{entry_id}`, named `"<account name> - Holdings"`, `via_device` linked to that same account's Totals device (`sap_account_{account_id}_{entry_id}`) rather than the Portfolio device — keeping the per-account grouping visible two levels deep (Portfolio → Account Totals → Account Holdings). Built through `const.py`'s `account_holdings_device_info(config_entry, account_id, account_name)` — never construct the identifiers dict inline in a platform file.
- **Entity names must be item-prefixed to stay distinguishable on a shared device:** since multiple holdings' entities all live on the same device and `_attr_has_entity_name = True`, a bare `_attr_name = "Market Value"` would produce ambiguous/colliding entity_ids for every holding in the account. Each entity's `_attr_name` is prefixed with its own item identity instead — `f"{ticker} Market Value"`, `f"{ticker} Low Limit"`, `f"{ticker} High Limit"` — so the resulting friendly names/entity_ids (`sensor.isa_holdings_aapl_market_value`) stay unique per holding even though the device name itself doesn't vary.
- **Prune-orphans device removal is keyed by the shared parent, not the item:** `valid_device_ids` gets one `sap_account_holdings_{account_id}_{entry_id}` per account that still has at least one valid holding (not one per `(account_id, ticker)`), so a single holding disappearing only removes that holding's own entities — the shared device survives as long as any sibling holding in the same account still has valid entities on it. The device is removed only when the *last* holding in that account disappears (or the `CONF_SHOW_HOLDINGS` toggle is switched off).
- **One sensor per item, not one sensor per field, is a separate, independent choice from the device-sharing above** — Phase 3's holding sensor is a deliberate departure from Phase 1/2's "one entity per metric" convention: a single Market Value sensor carries every other data point (shares, prices, gain, dividends, trend, RSI, earnings date, limit flags, etc.) as `extra_state_attributes` rather than as sibling entities. This mirrors the reference Ghostfolio sensor's own shape and was an explicit operator choice, not a default to assume for future phases — evaluate per-phase which shape better serves the data (attributes for read-only context that doesn't need its own history graph; separate entities for anything a user would want to graph, automate on, or individually enable/disable).

Cross-reference: `tests/test_sensor.py` (holding sensor tests, including `test_holdings_in_same_account_share_one_holdings_device` and the per-account device-separation regression test), `tests/test_number.py` (Phase 3 holding-limit number tests), and `tests/test_init.py::test_prune_orphans_removes_deleted_holding_entities_keeps_device_with_sibling` / `::test_prune_orphans_removes_holdings_device_when_account_has_no_holdings_left`.

**Low/High Limit two-way sync with the main app's Stock Detail page (July 2026 follow-up).** These two Number entities are not a one-way display of a backend value — they are meant to be settable from either end and stay in sync. The backend→HA direction is free: `holdings-list` is fetched on every coordinator poll (see the always-on-polling note above), so a target set from the Stock Detail page shows up in HA within one poll cycle. The HA→backend direction (`async_set_native_value` → `api.set_holding_price_limit` → `async_request_refresh()`) already existed from Phase 3, but had a real bug: HA's `NumberEntity` always carries a concrete float and has no way to submit an explicit `null`, so dragging the number to its minimum (0) previously sent a literal `low_limit=0`/`high_limit=0` to the backend instead of clearing the target — dangerous for a High Limit specifically, since the alert engine's `current_price >= high_limit` check with `high_limit=0` fires immediately on the next intraday scan. Fixed by treating 0 as a client-side "clear" sentinel, exactly mirroring the Stock Detail page's own JS convention (`_targetInputValue()` in the main app's `static/js/stock_detail.js`, blank/≤0 input → `null` sent to the backend): `StockAnalysisHoldingLimitNumber.async_set_native_value()` now sends `None` instead of the literal value whenever `value <= 0`, and `api.py`'s `set_holding_price_limit()` was changed from `float | None = None` defaults (which couldn't distinguish "field omitted" from "field explicitly cleared") to a `_UNSET` sentinel default, so a caller can now pass `low_limit=None` to explicitly clear that field in the request body without also having to pass the sibling field. `native_value` was changed to return `0` instead of `None`/"unknown" when the backend value is unset, so the displayed state round-trips consistently with the 0-clears convention. **"Set for all accounts" is a Stock Detail-page-only convenience** (it loops one POST per account client-side) — confirmed with the operator that HA intentionally does **not** replicate this: changing one account's Low/High Limit number in HA affects only that (account, ticker) pair, same as every other per-item entity in this integration; a user wanting the same limit across several accounts sets each account's HA entity individually. Watchlist tickers are out of scope for this integration entirely — `holdings-list` only ever returns Trading-account holdings, so a Watchlist-only target set from the Stock Detail page has no corresponding HA entity to sync to. Cross-reference: `tests/test_number.py::test_holding_limit_number_set_to_zero_clears_limit`, `::test_holding_limit_number_native_value_defaults_to_zero_when_unset`.

**Auto-enable/disable of Low/High Limit numbers (July 2026 follow-up).** These entities are `enabled_registry_default=False`, so a target set from the Stock Detail page previously had no effect on the entity's HA-side visibility at all — the operator had to remember to go find and manually enable the right entity in the HA UI before it would show up, which defeated the point of a backend-driven target. `StockAnalysisDataUpdateCoordinator.sync_holding_limit_enablement(unique_id, is_set)` (`__init__.py`), called from `number.py`'s existing `_update_holding_limit_numbers()` coordinator listener for every holding on every poll, now keeps entity-registry enablement in sync with whether a target actually exists on the backend:

- **Enable is immediate, uncapped:** as soon as `is_set` is `True` for a unique_id, if its registry entry is currently disabled — for *any* reason — it's flipped to `disabled_by = None`. No rate limit — the operator explicitly asked for this to happen "as soon as the value is set (on next integration sync)," unlike disabling.
- **Disable is capped at once per UTC calendar day per unique_id** (`self._holding_limit_last_disabled`, persisted via the coordinator's existing `Store`) — an explicit operator requirement, to stop a target being set/cleared/set/cleared several times in one session from repeatedly writing to the entity registry. Once a unique_id has been auto-disabled today, it stays enabled (if re-enabled) through any further clears that same day; the next UTC day resets the cap.
- **`is_set` is the single source of truth for enabled state — deliberately with no notion of "who last enabled/disabled it."** The first implementation of this method only auto-enabled an entity whose registry entry was `disabled_by == RegistryEntryDisabler.INTEGRATION` (i.e. only ever re-enabled an entity it had disabled itself), on the theory that overriding a manual `disabled_by == USER` disable would fight the user. **This was wrong in practice and reported as a bug the same day it shipped**: on a long-running install, most Low/High Limit entities had already been manually toggled at least once during earlier ad-hoc testing (well before this auto-enable feature existed), leaving them at `disabled_by == USER` — which meant auto-enable was permanently inert for almost every real entity, exactly the "set a target on the backend, wait several poll cycles, nothing enables" symptom the operator reported. The operator reproduced this precisely (manually enabled a never-set entity → set a target from the web app → cleared it from HA, which correctly auto-disabled it back to `disabled_by == INTEGRATION` → set the target again from the web app → *that* time it re-enabled, because it was now sitting at `INTEGRATION` not `USER`) and asked for the distinction to be removed outright: "we need to lose that. That will be confusing long term." Fixed by dropping the `disabled_by` check entirely on the enable side — a manual HA-UI disable is no longer sticky against a backend-set target. The trade-off, accepted explicitly: an operator can no longer permanently hide one specific Low/High Limit entity from the HA UI while its backend target stays active: the next poll re-enables it.
- **The one remaining guard is unrelated to the above and was kept:** disable only ever applies to a unique_id that has itself been observed at `is_set=True` at least once (`self._holding_limit_ever_set`, persisted). **This guard is load-bearing, not cosmetic** — without it, an operator manually enabling a never-set entity from the HA UI in order to type in its *first* target (an explicitly required workflow: "I must be able to enable any number entity in home assistant and set the target from home assistant") would have that same entity auto-disabled again on the very next poll, before they could finish, since a not-yet-set target and an already-cleared one are indistinguishable from `is_set` alone. This guard doesn't care who enabled the entity or what its current `disabled_by` value is — it only tracks whether a value has ever existed for it, which is orthogonal to the `disabled_by`-ignoring change above. Regression test: `tests/test_number.py::test_holding_limit_number_manual_enable_of_never_set_entity_is_not_auto_disabled`. Once a unique_id has genuinely had a value at least once, it's "ours" to manage for the rest of that config entry's life (survives restarts via the persisted flag) — a target that's been used once and cleared will auto-disable on the next clear, at the daily cap.
- Both `_holding_limit_last_disabled` and `_holding_limit_ever_set` are plain per-unique_id state, unrelated to and independent of `holding_price_limits`' own backend `(account_id, ticker)` row — a unique_id that no longer exists (holding sold, sub-limit deleted) is never proactively pruned from either dict, deliberately: the dicts are small (bounded by however many limits have ever existed for this config entry) and a stale entry is inert, since `sync_holding_limit_enablement` only ever consults it for a unique_id that's still being iterated over from the current `holdings` payload.

Cross-reference: `tests/test_number.py::test_holding_limit_number_auto_enables_when_target_set_on_backend`, `::test_holding_limit_number_auto_disables_when_target_cleared_on_backend`, `::test_holding_limit_number_auto_disable_capped_at_once_per_day`, `::test_holding_limit_number_reenables_entity_disabled_by_user`.

### Single Shared Device for a Non-Item-Specific Group (Phase 4+)
Phase 4 (Pension/House account sensors) needed a third variant, distinct from both patterns above: **the operator explicitly asked for one shared "Other Accounts" device holding one sensor per account** — unlike Phase 2 (each item is independent, gets its own device) and unlike Phase 3 (items share a device per their own natural parent, e.g. per Trading account). Pension/House accounts have no natural parent to group under other than "the whole set of non-Trading accounts", so they share one fixed device instead.

- **Unique_id scheme is unchanged from the patterns above:** `sap_other_account_value_{account_id}_{entry_id}`, still fully per-item.
- **Device scheme is one fixed device for the entire group**, identifier `sap_other_accounts_{entry_id}`, named `"Other Accounts"`, built through `const.py`'s `other_accounts_device_info(config_entry)` — `via_device` linked directly to the Portfolio device (there is no per-account "Totals" device to nest under, unlike Phase 3's holdings). Every Pension/House account's sensor lives on this one device regardless of how many accounts exist.
- **`entity_id` is explicitly assigned, not derived from has_entity_name + device name — this is the one entity type in the whole integration that does this.** The operator's spec was a literal `sensor.<account_name_slug>` with **no** device-name prefix (e.g. `sensor.aviva_pension`, not `sensor.other_accounts_aviva_pension`). Setting `_attr_has_entity_name = False` alone does **not** achieve this: Home Assistant's entity registry (`_async_get_full_entity_name` in `entity_registry.py`) still joins the device name into the derived entity_id whenever `_attr_name`/`original_name` is set, regardless of `has_entity_name` — that flag only controls whether a name is *stripped* of an already-matching device-name prefix, not whether one gets added. The only way to get an unprefixed entity_id is to set `self.entity_id = f"sensor.{slugify(account_name)}"` directly in `__init__`, before the entity is added to hass — `StockAnalysisOtherAccountSensor` (sensor.py) does this. The entity's *displayed friendly name* is unaffected by this and still shows as `"Other Accounts <account name>"`, which is normal, expected Home Assistant behavior for any entity attached to a device without `has_entity_name = True` — only the entity_id itself is exempted from the device-name join.
- **Prune-orphans device removal is keyed by the whole group, not any single item:** the shared device id is added to `valid_device_ids` whenever `CONF_SHOW_OTHER_ACCOUNTS` is on (not conditioned on any particular account existing), mirroring how the two always-on static devices work — a device row only ever exists in HA's registry if some entity actually referenced it, so this is safe even with zero Pension/House accounts.

Cross-reference: `tests/test_sensor.py::test_two_other_accounts_create_2_sensors_on_shared_device`, `::test_other_account_sensor_entity_id_derived_from_account_name_no_device_prefix`, and `tests/test_init.py::test_prune_orphans_removes_deleted_other_account_entity_keeps_device_with_sibling` / `::test_disabling_show_other_accounts_via_reload_auto_removes_entities_and_device`.

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

This integration is a pure API consumer of the parent Stock Analysis Project app. It currently depends on exactly 10 backend endpoints:

- `GET /api/accounts/portfolio-totals`
- `POST /api/accounts/refresh-now`
- `GET /api/system/market-status`
- `GET /api/accounts/list-with-metrics` (Phase 2 — per-Trading-account metrics)
- `GET /api/accounts/holdings-list` (Phase 3 — per-holding metrics across all Trading accounts)
- `POST /api/accounts/holding-price-limit` (Phase 3 — sets a holding's Low/High Limit)
- `GET /api/accounts/other-accounts-list` (Phase 4 — current value + basic performance for every Pension/House account)
- `GET /api/market-regime/current` (Phase 5 — HMM Bull/Chop/Crash label plus US/UK Normal/Volatile/Crash turbulence classification)
- `GET /api/macro-conditions` (Phase 5 — sovereign-yield threat levels, Treasury auction demand, Fear & Greed)
- `GET /api/markets` (Phase 6 — live price/change/session-status for every tracked global index, commodity, FX pair, and rate)

All 6 planned phases have now shipped. The main app's own `AGENTS.md` (`../AGENTS.md`) documents the rule that any change to these endpoints' response schema, auth, or behavior must be checked against this integration in the same change — additive-only field changes are safe (this integration's `.get()`-based access degrades gracefully), but renames or removals require updating this integration in lockstep. If you're working from the main app's side and touch `accounts_engine.py`'s `portfolio_totals()`/`portfolio_gain_fx_decomposition()`/`portfolio_twr_fx()`/`portfolio_twr_ex_fx()`/`account_metrics_list()`/`holdings_with_metrics_all_accounts()`/`set_holding_price_limit()`/`other_accounts_list()`/`scraped_price_performance()`, or `api_routes_accounts.py`'s `portfolio-totals`/`refresh-now`/`list-with-metrics`/`holdings-list`/`holding-price-limit`/`other-accounts-list` routes, or `api_routes_system.py`'s `market-status` route, or (Phase 5) `regime_engine.py`'s `calculate_market_regime()`/`run_price_regime_hmm()`, `sentiment_engine.py`'s `get_latest_fear_greed()`, `database.get_auction_summary()` (`db_helpers.py`), `api_routes_analysis.py`'s `market-regime/current`/`macro-conditions` routes, or the `market_regimes`/`macro_regimes`/`treasury_auction_results` tables, or (Phase 6) `markets_engine.py`'s `assemble_markets_payload()`/`get_exchange_state()`/`get_region_state()`, `market_pulse.py`'s `get_exchange_session_state()`, `api_routes_system.py`'s `markets` route, or the `market_ticker_registry`/`market_pulse_cache` tables — re-read this file and `task_prompt.md` before assuming the integration side is unaffected.

---

## Files Not to Touch

- `hacs.json` — HACS metadata, only change for category/filename updates
- `custom_components/stock_analysis_project/manifest.json` — if a change is necessary (e.g. a version bump, a new dependency), inform the operator rather than editing silently
- `.test_venv/` — scratch test environment, gitignored, regenerate rather than hand-edit
