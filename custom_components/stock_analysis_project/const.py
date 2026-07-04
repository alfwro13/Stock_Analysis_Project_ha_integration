"""Constants for the Stock Analysis Project integration."""

DOMAIN = "stock_analysis_project"

# Configuration keys
CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_VERIFY_SSL = "verify_ssl"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_SHOW_PORTFOLIO_TOTALS = "show_portfolio_totals"
CONF_SHOW_ACCOUNTS = "show_accounts"
CONF_SHOW_HOLDINGS = "show_holdings"
CONF_SHOW_OTHER_ACCOUNTS = "show_other_accounts"
CONF_SKIP_REFRESH_WHEN_MARKETS_CLOSED = "skip_refresh_when_markets_closed"
CONF_SHOW_MARKET_HEALTH = "show_market_health"

# Default values
DEFAULT_NAME = "Stock Analysis Project"
DEFAULT_UPDATE_INTERVAL = 15  # minutes

# API client configuration
API_TIMEOUT = 30  # seconds
API_MAX_RETRIES = 3


def portfolio_device_info(config_entry) -> dict:
    """Return the shared device_info dict for the top-level portfolio device."""
    return {
        "identifiers": {(DOMAIN, f"sap_portfolio_{config_entry.entry_id}")},
        "name": "Stock Analysis Project Portfolio",
        "manufacturer": "Stock Analysis Project",
        "model": "Portfolio Tracker",
    }


def diagnostics_device_info(config_entry) -> dict:
    """Return the shared device_info dict for the system diagnostics device."""
    return {
        "identifiers": {(DOMAIN, f"sap_diagnostics_{config_entry.entry_id}")},
        "name": "Stock Analysis Project Diagnostics",
        "manufacturer": "Stock Analysis Project",
        "model": "System Diagnostics",
        "via_device": (DOMAIN, f"sap_portfolio_{config_entry.entry_id}"),
    }


def account_device_info(config_entry, account_id: int, account_name: str) -> dict:
    """Return the device_info dict for one Trading account's device, linked to the portfolio device."""
    return {
        "identifiers": {(DOMAIN, f"sap_account_{account_id}_{config_entry.entry_id}")},
        "name": f"{account_name} - Totals",
        "manufacturer": "Stock Analysis Project",
        "model": "Trading Account",
        "via_device": (DOMAIN, f"sap_portfolio_{config_entry.entry_id}"),
    }


def other_accounts_device_info(config_entry) -> dict:
    """Return the shared device_info dict for every Pension/House account's sensor — a single
    device for the whole heterogeneous group (unlike account_device_info's one-per-item scheme
    or account_holdings_device_info's one-per-parent scheme), since these accounts have no
    natural per-item grouping of their own beyond "not a Trading account"."""
    return {
        "identifiers": {(DOMAIN, f"sap_other_accounts_{config_entry.entry_id}")},
        "name": "Other Accounts",
        "manufacturer": "Stock Analysis Project",
        "model": "Pension / House Accounts",
        "via_device": (DOMAIN, f"sap_portfolio_{config_entry.entry_id}"),
    }


def account_holdings_device_info(config_entry, account_id: int, account_name: str) -> dict:
    """Return the device_info dict for one Trading account's Holdings device — a single device
    per account holding every one of that account's per-ticker sensors/numbers as entities,
    separate from that account's Totals device (account_device_info above) but nested under it,
    so an account ends up with two devices: "<name> - Totals" and "<name> - Holdings"."""
    return {
        "identifiers": {(DOMAIN, f"sap_account_holdings_{account_id}_{config_entry.entry_id}")},
        "name": f"{account_name} - Holdings",
        "manufacturer": "Stock Analysis Project",
        "model": "Trading Account Holdings",
        "via_device": (DOMAIN, f"sap_account_{account_id}_{config_entry.entry_id}"),
    }


def market_health_device_info(config_entry) -> dict:
    """Return the shared device_info dict for the Market Health device (Phase 5) — a single
    fixed device for 7 static, non-per-item sensors (Market Regime, US/UK classification, US 10Y
    Treasury, UK 10Y Gilt, Treasury Auction Demand, Fear & Greed Index), same one-device-for-the-
    whole-group topology as other_accounts_device_info() above."""
    return {
        "identifiers": {(DOMAIN, f"sap_market_health_{config_entry.entry_id}")},
        "name": "Market Health",
        "manufacturer": "Stock Analysis Project",
        "model": "Macro & Sentiment Signals",
        "via_device": (DOMAIN, f"sap_portfolio_{config_entry.entry_id}"),
    }
