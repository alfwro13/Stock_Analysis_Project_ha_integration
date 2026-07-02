# Stock Analysis Project (Home Assistant Integration)

A Home Assistant Custom Component (HACS integration) for monitoring a self-hosted [Stock Analysis Project](https://github.com/awroblew/Stock_Analysis_Project) instance — a personal FastAPI portfolio dashboard. It pulls live portfolio totals, gain/return figures, and system/market health straight into Home Assistant so you can build dashboards and automations around your own portfolio, without needing Ghostfolio.

This is a companion project to the main Stock Analysis Project app and talks only to that app's own API — it has no connection to Ghostfolio, Yahoo Finance, or any other third-party service directly.

**Status:** Phase 1 (portfolio totals, auto-refresh controls, diagnostics). Individual trading accounts, per-holding sensors, and Pension/House account sensors are planned but not yet implemented — see [Planned: Phases 2-4](#planned-phases-2-4-not-yet-implemented) below.

## Prerequisites

- A running instance of the main [Stock Analysis Project](https://github.com/awroblew/Stock_Analysis_Project) app, reachable from your Home Assistant instance.
- An API key generated from that app: **Settings → User Account → API Key → Generate New API Key**. This key is sent as an `X-API-Key` header on every request; generating a new key immediately invalidates the old one, so update this integration's configuration if you regenerate it.
- At least one **Trading** account configured in the main app's Built-in Accounts (`/accounts`) — portfolio totals aggregate across Trading accounts only. With zero Trading accounts configured, the sensors simply report zero/unavailable rather than erroring.

## Installation

### HACS (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed.
2. Add this repository as a custom repository in HACS:
   - Go to HACS → Integrations.
   - Click the three dots in the top right corner.
   - Select "Custom repositories".
   - Add this repository's URL and select "Integration" as the category.
3. Install "Stock Analysis Project" from HACS.
4. Restart Home Assistant.

### Manual Installation

1. Download the latest release (or clone this repository).
2. Copy the `custom_components/stock_analysis_project` folder into your Home Assistant `custom_components` directory.
3. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services**.
2. Click **Add Integration** and search for **"Stock Analysis Project"**.
3. Fill in the setup form:
   - **Base URL** — the URL of your Stock Analysis Project instance (e.g. `http://192.168.1.71:8090`). Must start with `http://` or `https://`.
   - **API Key** — the key generated from Settings → User Account in the main app.
   - **Verify SSL Certificate** — leave enabled unless your instance sits behind a self-signed certificate or a corporate proxy (e.g. Zscaler) that intercepts SSL.
   - **Update Interval** — how often to poll for updated portfolio data, in minutes (default 15, range 1-1440).

The setup form validates the connection live by calling the portfolio-totals endpoint — this confirms both that the API key is valid and that the backend has the required endpoints deployed. You can revisit these same fields later via the integration's **Reconfigure** option.

## Entities (Phase 1)

Entities are split across two devices under the config entry: **Stock Analysis Project Portfolio** (the ten portfolio-total sensors plus the auto-refresh controls) and **Stock Analysis Project Diagnostics** (the five diagnostic binary sensors and the prune button), linked together via Home Assistant's device hierarchy.

### Stock Analysis Project Portfolio (sensors)

| Entity | Description | Unit |
|---|---|---|
| Portfolio Cost | Total amount invested across all Trading accounts | base currency |
| Portfolio Value | Current total value across all Trading accounts | base currency |
| Portfolio Gain | Unrealized gain, re-expressed at each holding's purchase-time exchange rate (FX-neutral) | base currency |
| Portfolio Gain with FX | Unrealized gain at today's live exchange rates (FX-inclusive/actual) | base currency |
| Portfolio Total Dividend | Total dividends received across all Trading accounts | base currency |
| Portfolio Unrealized P&L | Unrealized profit/loss across all open holdings | base currency |
| Portfolio Unrealized P&L % | Unrealized P&L as a percentage | % |
| Portfolio Simple Gain % | Portfolio gain as a percentage of cost | % |
| Portfolio Time Weighted Return % | Chain-linked Time-Weighted Return, FX-neutral | % |
| Portfolio Time Weighted Return with FX % | Chain-linked Time-Weighted Return, FX-inclusive | % |

The base currency for all monetary sensors is whatever the backend reports as the portfolio's `base_currency` (typically your configured `BASE_CURRENCY`, e.g. GBP).

### Stock Analysis Project Portfolio (config/control entities)

| Entity | Type | Description |
|---|---|---|
| Enable Auto Refresh | switch | Turn background polling on/off. Turning it off suspends the coordinator's timer entirely; turning it back on resumes polling immediately and persists across Home Assistant restarts. |
| Refresh Interval | number | Change the polling interval (1-1440 minutes) at runtime — takes effect immediately, no restart needed. |
| Refresh Data | button | Triggers an immediate backend refresh (live prices + performance cache) and re-polls Home Assistant shortly after. The backend refresh runs in the background, so sensor values may take a few seconds to update after pressing. |

### Stock Analysis Project Diagnostics (binary sensors + button)

| Entity | On means | Notes |
|---|---|---|
| Server Status | The last poll of the backend succeeded | device_class: connectivity |
| Yahoo Status | Yahoo Finance data is flowing successfully on the backend | device_class: connectivity |
| US Market Open | The NYSE is currently in its trading session | device_class: window |
| UK Market Open | The LSE is currently in its trading session | device_class: window |
| System Status | **A problem has been detected** on the backend (inverted polarity — "on" means something is wrong, matching Home Assistant's convention for problem-style binary sensors) | no device_class |
| Prune Orphaned Entities (button) | — | Removes any entities left behind in the Home Assistant entity registry that no longer correspond to a current sensor/entity from this integration. Safe to press at any time. |

## Planned: Phases 2-4 (not yet implemented)

This integration is being built out in phases. Only Phase 1 (above) currently exists. Planned future phases:

- **Phase 2 — Individual Trading accounts:** a sensor set per Trading account (value, cost, gain, unrealized P&L, simple gain %, Time-Weighted Return %, dividends, cash balance), mirroring the portfolio-wide sensors but scoped to one account.
- **Phase 3 — Per-holding sensors:** one sensor per asset held across your Trading accounts, plus price-limit number entities for setting alert thresholds.
- **Phase 4 — Pension/House accounts:** sensors for the main app's Pension and House account types (property/pension valuations tracked via its Account Price Scraper).

Until these ship, this integration only exposes the portfolio-wide totals and diagnostics described above.

## Support & Disclaimer

This is a personal hobby project maintained alongside the main Stock Analysis Project app. It is provided as-is with no warranty. If you hit an issue, check the main app's `/api/system/market-status` and `/api/accounts/portfolio-totals` endpoints directly (e.g. with `curl -H "X-API-Key: <your key>" <base_url>/api/accounts/portfolio-totals`) to confirm the backend is reachable and returning data before assuming the integration itself is at fault.

## License

This project follows the same license as the main Stock Analysis Project app.
