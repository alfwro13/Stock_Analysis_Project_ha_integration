"""Constants for the Stock Analysis Project integration."""

DOMAIN = "stock_analysis_project"

# Configuration keys
CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_VERIFY_SSL = "verify_ssl"
CONF_UPDATE_INTERVAL = "update_interval"

# Extension points for later phases (Phase 2: per-account sensors, Phase 3: per-holding sensors,
# Phase 4: pension/house accounts) — declared now so config_flow's schema won't need a breaking
# rename later. Do NOT implement any behavior for these keys yet.
CONF_SHOW_ACCOUNTS = "show_accounts"
CONF_SHOW_HOLDINGS = "show_holdings"
CONF_SHOW_OTHER_ACCOUNTS = "show_other_accounts"

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
        "name": f"Stock Analysis Project - {account_name}",
        "manufacturer": "Stock Analysis Project",
        "model": "Trading Account",
        "via_device": (DOMAIN, f"sap_portfolio_{config_entry.entry_id}"),
    }
