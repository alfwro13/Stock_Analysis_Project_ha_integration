"""Config flow for Stock Analysis Project integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import StockAnalysisAPI, StockAnalysisAPIError, StockAnalysisAuthError
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_SHOW_ACCOUNTS,
    CONF_SHOW_HOLDINGS,
    CONF_SHOW_MARKET_HEALTH,
    CONF_SHOW_MARKETS,
    CONF_SHOW_OTHER_ACCOUNTS,
    CONF_SHOW_PORTFOLIO_TOTALS,
    CONF_SKIP_REFRESH_WHEN_MARKETS_CLOSED,
    CONF_UPDATE_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _build_schema() -> vol.Schema:
    """Return the shared config schema used by both setup and reconfigure steps."""
    return vol.Schema(
        {
            vol.Required(CONF_BASE_URL): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Required(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_VERIFY_SSL, default=True): BooleanSelector(),
            vol.Optional(CONF_SHOW_PORTFOLIO_TOTALS, default=True): BooleanSelector(),
            vol.Optional(CONF_SHOW_ACCOUNTS, default=True): BooleanSelector(),
            vol.Optional(CONF_SHOW_HOLDINGS, default=True): BooleanSelector(),
            vol.Optional(CONF_SHOW_OTHER_ACCOUNTS, default=True): BooleanSelector(),
            vol.Optional(CONF_SHOW_MARKET_HEALTH, default=True): BooleanSelector(),
            vol.Optional(CONF_SHOW_MARKETS, default=True): BooleanSelector(),
            vol.Optional(CONF_SKIP_REFRESH_WHEN_MARKETS_CLOSED, default=False): BooleanSelector(),
            vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): NumberSelector(
                NumberSelectorConfig(
                    mode=NumberSelectorMode.BOX,
                    min=1,
                    max=1440,
                    unit_of_measurement="minutes",
                )
            ),
        }
    )


async def _async_validate_connection(
    user_input: dict[str, Any],
) -> tuple[str | None, dict[str, str]]:
    """Validate credentials and connectivity.

    Returns (unique_id, errors). unique_id is None when validation failed.
    """
    errors: dict[str, str] = {}

    if not user_input[CONF_BASE_URL].startswith(("http://", "https://")):
        errors["base_url"] = "invalid_url"
        return None, errors

    api = StockAnalysisAPI(
        base_url=user_input[CONF_BASE_URL],
        api_key=user_input[CONF_API_KEY],
        verify_ssl=user_input.get(CONF_VERIFY_SSL, True),
    )
    try:
        await api.get_portfolio_totals()
        return user_input[CONF_BASE_URL], errors
    except StockAnalysisAuthError:
        errors["base"] = "auth_failed"
    except StockAnalysisAPIError:
        errors["base"] = "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected exception during connection validation")
        errors["base"] = "cannot_connect"
    finally:
        await api.close()

    return None, errors


class StockAnalysisProjectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Stock Analysis Project."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id, errors = await _async_validate_connection(user_input)
            if unique_id:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration of the integration."""
        config_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id, errors = await _async_validate_connection(user_input)
            if unique_id:
                for existing_entry in self._async_current_entries(include_ignore=False):
                    if (
                        existing_entry.entry_id != config_entry.entry_id
                        and existing_entry.unique_id == unique_id
                    ):
                        return self.async_abort(reason="already_configured")

                return self.async_update_reload_and_abort(
                    config_entry,
                    unique_id=unique_id,
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _build_schema(),
                config_entry.data,
            ),
            errors=errors,
        )
