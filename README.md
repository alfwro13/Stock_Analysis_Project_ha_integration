<div align="center">
   <img src="https://raw.githubusercontent.com/alfwro13/Stock_Analysis_Project_ha_integration/main/custom_components/stock_analysis_project/brand/icon.png" alt="Stock Analysis Project Logo" width="120" height="120">
</div>

# Stock Analysis Project (Home Assistant Integration)

A Home Assistant Custom Component (HACS integration) for monitoring a self-hosted [Stock Analysis Project](https://github.com/alfwro13/Stock_Analysis_Project) instance — a personal FastAPI portfolio dashboard. It pulls live portfolio totals, gain/return figures, and system/market health straight into Home Assistant so you can build dashboards and automations around your own portfolio, without needing Ghostfolio.

This is a companion project to the main Stock Analysis Project app and talks only to that app's own API — it has no connection to Ghostfolio, Yahoo Finance, or any other third-party service directly.

It exposes portfolio-wide totals, per-Trading-account metrics, per-holding data (including optional price-alert limits), and Pension/House account valuations as native sensors and number entities, plus auto-refresh controls (including automatically skipping refreshes while both UK and US markets are closed) and system/market diagnostics.

## Prerequisites

- A running instance of the main [Stock Analysis Project](https://github.com/alfwro13/Stock_Analysis_Project) app, reachable from your Home Assistant instance.
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
   - **Show Portfolio Totals** — create the ten portfolio-wide total sensors (cost, value, gain, dividends, TWR). Enabled by default.
   - **Show Account Totals** — create a separate sensor set (cash balance, gains, P&L, dividends, interest, MWRR) for each Trading account. Enabled by default.
   - **Show Holdings** — create a Market Value sensor plus Low/High Limit number entities for each holding, in each Trading account. Enabled by default.
   - **Show Other Accounts** — create a sensor for each Pension/House account, on a shared "Other Accounts" device. Enabled by default.
   - **Show Market Health** — create 7 sensors on a shared "Market Health" device: Market Regime, US/UK Market Classification, US 10Y Treasury, UK 10Y Gilt, US Treasury Auction Demand, and the Fear & Greed Index. Enabled by default.
   - **Show Markets** — create a sensor for every tracked global index, commodity, FX pair, and rate, on a shared "Markets" device. Enabled by default.
   - **Skip Refresh When Markets Closed** — while both the UK and US markets are closed, skip re-fetching portfolio/account/holdings data and reuse the last-known values instead, since live prices can't have changed. Other Accounts, Market Health, and Markets are never skipped this way — none of them is driven solely by UK/US market hours (Markets spans every global session, Other Accounts is scraper-driven, Market Health is daily-cadence). Enabled by default.
   - **Update Interval** — how often to poll for updated portfolio data, in minutes (default 15, range 1-1440).

The setup form validates the connection live by calling the portfolio-totals endpoint — this confirms both that the API key is valid and that the backend has the required endpoints deployed. You can revisit these same fields later via the integration's **Reconfigure** option — reconfiguring reloads the integration, so turning a "Show ..." toggle off removes its sensors from Home Assistant immediately rather than leaving them behind as unavailable.

## Entities

Static entities are split across two devices under the config entry: **Stock Analysis Project Portfolio** (the ten portfolio-total sensors plus the auto-refresh controls) and **Stock Analysis Project Diagnostics** (the five diagnostic binary sensors and the prune button), linked together via Home Assistant's device hierarchy. Trading accounts and holdings each get their own dynamically-created device (see below); Pension/House accounts share one single "Other Accounts" device, 7 market-wide macro/sentiment sensors share one single "Market Health" device, and every tracked global index/commodity/FX/rate shares one single "Markets" device (all described below).

### Stock Analysis Project Portfolio (sensors)

Controlled by the **Show Portfolio Totals** config option (default on). Disabling it via Reconfigure removes these ten sensors on the resulting reload.

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
| Refresh Data | button | Triggers an immediate backend refresh (live prices + performance cache), waits for it to actually finish, then re-polls Home Assistant — so sensor values are updated as soon as the button press completes, not on some later poll. |

### Stock Analysis Project Diagnostics (binary sensors + button)

| Entity | On means | Notes |
|---|---|---|
| Server Status | The last poll of the backend succeeded | device_class: connectivity |
| Yahoo Status | Yahoo Finance data is flowing successfully on the backend | device_class: connectivity |
| US Market Open | The NYSE is currently in its trading session | device_class: window |
| UK Market Open | The LSE is currently in its trading session | device_class: window |
| System Status | **A problem has been detected** on the backend (inverted polarity — "on" means something is wrong, matching Home Assistant's convention for problem-style binary sensors) | no device_class |
| Prune Orphaned Entities (button) | — | Removes any entities left behind in the Home Assistant entity registry that no longer correspond to a current sensor/entity from this integration — e.g. after an account is deleted on the backend, without waiting for the next restart/reconfigure. Safe to press at any time. |

### Per-Account Entities

One device per Trading account, named **`<account name>` - Totals**, linked via `via_device` to the Stock Analysis Project Portfolio device. Sensors are created dynamically as accounts are added on the backend. Controlled by the **Show Account Totals** config option (default on); disabling it via Reconfigure removes all per-account sensors on the resulting reload.

Entity removal (an account deleted on the backend, or a "Show ..." toggle turned off) happens automatically every time the integration is set up or reloaded — which a Reconfigure submission always triggers — so disabling a toggle takes effect immediately rather than leaving sensors showing as unavailable. The **Prune Orphaned Entities** button remains available for cleaning up after a backend-side change (e.g. a deleted account) without restarting or reconfiguring Home Assistant.

| Entity | Description | Unit |
|---|---|---|
| Cash Balance | Live cash balance for the account | base currency |
| Daily Gain | Gain/loss over the last 1 day, excluding deposits/withdrawals | base currency |
| 1 Week Gain | Gain/loss over the last 7 days, excluding deposits/withdrawals | base currency |
| 1 Month Gain | Gain/loss over the last 30 days, excluding deposits/withdrawals | base currency |
| 3 Month Gain | Gain/loss over the last 91 days, excluding deposits/withdrawals | base currency |
| 1 Year Gain | Gain/loss over the last 365 days, excluding deposits/withdrawals | base currency |
| Equity Value | Current market value of open holdings in the account | base currency |
| Realized P&L | Profit/loss booked on closed positions, since account inception | base currency |
| Unrealized P&L | Live equity value minus cost basis of currently-open holdings | base currency |
| Dividend Income | Total dividends received in the account | base currency |
| Interest Income | Total interest received in the account | base currency |
| Money Weighted Rate of Return | Since-inception Modified Dietz return (an IRR approximation) | % |

### Per-Holding Entities

One **Holdings** device per Trading account, named **`<account name>` - Holdings**, linked via `via_device` to that account's own Totals device — so each account shows up as two devices: `<account name>` - Totals and `<account name>` - Holdings. Every holding in that account (ticker) contributes its entities onto this single shared device rather than getting a device of its own; entity names are ticker-prefixed (e.g. "AAPL Market Value", "AAPL Low Limit") so holdings stay distinguishable on the shared device. The same ticker held in two different accounts appears on both accounts' respective Holdings devices independently — never merged. Entities are created dynamically as holdings appear on the backend. Controlled by the **Show Holdings** config option (default on); disabling it via Reconfigure removes all holding entities and both accounts' Holdings devices on the resulting reload.

Each holding has exactly one sensor — **`<ticker>` Market Value** (state = market value of that holding in that account, in the portfolio's base currency) — carrying every other data point as an attribute rather than as a separate entity:

| Attribute | Description |
|---|---|
| `ticker`, `account`, `number_of_shares` | Identity and position size |
| `currency_asset`, `currency_base` | The instrument's native currency vs. the portfolio's base currency |
| `market_price`, `market_price_currency`, `market_price_in_base_currency` | Live price, in native currency and converted |
| `average_buy_price`, `average_buy_price_currency` | Average cost basis (base currency) |
| `gain_value` / `profit_and_loss`, `gain_value_currency`, `gain_pct` | Unrealized gain/loss (the same figure under two keys, for parity with the prior Ghostfolio-based integration) |
| `accumulated_dividends`, `accumulated_dividends_currency` | Dividends received on this holding in this account |
| `trend_vs_buy` | `up`/`down` — current price vs. average buy price |
| `asset_class`, `data_source` | e.g. `EQUITY`/`ETF`/`Fixed Income` (`Fixed Income` for a UK Treasury Bill holding); `data_source` is `YAHOO` or `TBILL` |
| `market_change_24h`, `market_change_pct_24h` | 24-hour price change; for a Treasury Bill this is the bill's own known daily accretion rate rather than a live quote |
| `rsi`, `trend_50d`, `trend_200d` | 14-day RSI and 50-/200-day moving-average trend direction |
| `next_earnings_date` | Next scheduled earnings report date |
| `low_limit_set`, `low_limit_reached`, `high_limit_set`, `high_limit_reached` | Whether a price-alert limit is configured and whether it's currently breached |

Two **Number** entities per holding — **`<ticker>` Low Limit** and **`<ticker>` High Limit**, both disabled by default (enable manually if you want to configure and track a price-alert threshold) — set the corresponding limit in the instrument's native currency. Their value is read from and written to the backend (`holding_price_limits` table), not stored locally in Home Assistant, so it stays fully in sync with the same target set from the main app's own Stock Detail page (Position Targets) in both directions — a change on either end shows up on the other within one poll cycle (or immediately, on the end that made the change). **0 clears the limit** — since a real price target can never sensibly be 0, setting the number down to 0 (its minimum) clears that limit on the backend, mirroring the Stock Detail page's own "blank input clears the target" convention; a cleared/never-set limit likewise displays as 0 rather than "unknown". Watchlist-only tickers have no Trading-account holding and so never appear here — they can only be targeted from the Stock Detail page itself.

### Other Accounts (Pension/House) Entities

One shared **Other Accounts** device (not one device per account — unlike per-Trading-account devices above), linked via `via_device` to the Stock Analysis Project Portfolio device. Every Pension and House account on the backend contributes exactly one sensor onto this device. Controlled by the **Show Other Accounts** config option (default on); disabling it via Reconfigure removes all Other Accounts sensors and the device itself on the resulting reload.

Unlike every other entity in this integration, an Other Accounts sensor's `entity_id` is derived directly from the account's own name, with no device-name prefix — e.g. an account named "Aviva Pension" becomes `sensor.aviva_pension`, and "House - Alicia Avenue" becomes `sensor.house_alicia_avenue`. Its displayed friendly name still includes the device name ("Other Accounts Aviva Pension"), as is standard for any Home Assistant entity attached to a device — only the `entity_id` itself is unprefixed.

| Field | Where | Description |
|---|---|---|
| State | sensor state | The account's current value (`equity_value` — for a House account this deliberately excludes the purchase-price memo stored as `initial_cash`, which is not real cash), in the portfolio's base currency |
| `account_type` | attribute | `Pension` or `House` |
| `currency` | attribute | The account's own native currency |
| `performance_1m`, `performance_ytd`, `performance_1y` | attribute | % change over each window, derived from the backend's scraped/imported price history — `null` for a window with no price that far back yet |
| `last_updated` | attribute | The most recent date the backend's Account Price Scraper (or a manual CSV import) recorded a price for this account, `null` if never scraped |

### Market Health Entities

One shared **Market Health** device, linked via `via_device` to the Stock Analysis Project Portfolio device, holding 7 static sensors — market-wide macro/sentiment signals rather than portfolio data. Unlike Trading accounts, holdings, or Other Accounts, none of these are per-item — the full set is created once and never grows/shrinks with backend data. Controlled by the **Show Market Health** config option (default on); disabling it via Reconfigure removes all 7 sensors and the device itself on the resulting reload.

| Entity | State | Key attributes |
|---|---|---|
| Market Regime | HMM price-action regime: `Bull`, `Chop`, or `Crash` | `probability`, `as_of`, `last_change_date`, `last_change_from`, `last_change_to` |
| US Market Classification | EWMA-turbulence classification: `Normal`, `Volatile`, or `Crash` — a different taxonomy from Market Regime, computed from realized S&P 500 volatility | — |
| UK Market Classification | Same classification (`Normal`/`Volatile`/`Crash`), computed from realized FTSE 100 volatility | — |
| US 10Y Treasury | Yield threat level: `Low`, `Elevated`, or `High` (mapped from the backend's raw `GREEN`/`YELLOW`/`RED`), based on the 10-year Treasury yield's level and 3-day velocity | `raw_level`, `yield_velocity_bps`, `tyx_close`, `tnx_close`, `as_of` |
| UK 10Y Gilt | Same threat-level mapping, based on the UK 10-year Gilt yield | `raw_level`, `yield_velocity_bps`, `uk_gilt_close`, `as_of` |
| US Treasury Auction Demand | `Healthy` or `Weakness Detected`, based on whether any of the last 6 US Treasury auctions (any maturity, within 30 days) showed weak bid-to-cover or a wide yield tail; `Unknown` if there's no auction in that window to judge | `recent_auctions` (list of the underlying auction rows) |
| Fear & Greed Index | Numeric, 0-100 (CNN's Fear & Greed Index) | `label` (`Extreme Fear`/`Fear`/`Neutral`/`Greed`/`Extreme Greed`), `as_of` |

### Markets Entities

One shared **Markets** device, linked via `via_device` to the Stock Analysis Project Portfolio device, holding one sensor per tracked global index, commodity, FX pair, and rate (the same set shown on the main app's own `/markets` page) — dynamic per-item entities, unlike Market Health's fixed 7. Controlled by the **Show Markets** config option (default on); disabling it via Reconfigure removes every Markets sensor and the device itself on the resulting reload. Each sensor's friendly name is the registry's own display name (e.g. "FTSE 100", "S&P 500"), device-prefixed as standard for any entity attached to a device (e.g. "Markets FTSE 100").

Five of these tickers (S&P 500, Nasdaq 100, Dow, Russell 2000, Nikkei 225) auto-swap their live price between a spot instrument and a paired futures instrument depending on session — the sensor's identity stays stable across that swap (it never re-creates itself), only its `ticker`/`is_future` attributes and state change.

| Field | Where | Description |
|---|---|---|
| State | sensor state | Live price/level of the ticker currently in view for this instrument (spot or, outside the spot exchange's regular session, its paired future) |
| `ticker` | attribute | The resolved ticker symbol currently backing the state (may be a futures symbol — see `is_future`) |
| `change_pts`, `change_pct` | attribute | Change from the prior close, in points and percent |
| `is_positive` | attribute | Whether `change_pts`/`change_pct` is positive |
| `status` | attribute | Session status: `open`, `pre`, `post`, or `closed` — `post` is only available for exchanges the backend proxies via a live Yahoo index quote (NYSE, LSE, XETRA, TSE, HKEX, SSE, ASX, Euronext); other exchanges report `open`/`closed` only |
| `region` | attribute | `US`, `Europe`, `Asia`, or `Commodities_FX` — the backend's own coarse grouping, not a true country |
| `exchange` | attribute | The instrument's home exchange key (e.g. `NYSE`, `LSE`), `null` for FX pairs/rates with no single exchange |
| `currency` | attribute | The instrument's quote currency |
| `asset_type` | attribute | `Index`, `FX`, `Commodity`, or `Rate` |
| `is_future` | attribute | Whether the state is currently showing the paired futures instrument instead of spot |

## Support & Disclaimer

This is a personal hobby project maintained alongside the main Stock Analysis Project app. It is provided as-is with no warranty. If you hit an issue, check the main app's `/api/system/market-status` and `/api/accounts/portfolio-totals` endpoints directly (e.g. with `curl -H "X-API-Key: <your key>" <base_url>/api/accounts/portfolio-totals`) to confirm the backend is reachable and returning data before assuming the integration itself is at fault.

## License

This project follows the same license as the main Stock Analysis Project app.
