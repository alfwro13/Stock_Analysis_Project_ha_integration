"""API client for Stock Analysis Project."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import API_MAX_RETRIES, API_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class StockAnalysisAPIError(Exception):
    """General API error (network failure, non-200 non-401 response)."""


class StockAnalysisAuthError(Exception):
    """Raised on HTTP 401 — invalid API key."""


class StockAnalysisAPI:
    """API client for Stock Analysis Project."""

    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = True) -> None:
        """Initialize the API client."""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self._session: aiohttp.ClientSession | None = None

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}

    def _ssl(self):
        return False if not self.verify_ssl else None

    async def _get(self, path: str) -> dict[str, Any]:
        """GET with retry+backoff on network errors."""
        url = f"{self.base_url}{path}"
        headers = self._headers()
        ssl_context = self._ssl()

        for attempt in range(API_MAX_RETRIES):
            try:
                async with self._get_session().get(url, headers=headers, ssl=ssl_context) as response:
                    if response.status == 200:
                        try:
                            return await response.json()
                        except ValueError as err:
                            raise StockAnalysisAPIError(f"Invalid JSON response from {url}") from err
                    if response.status == 401:
                        raise StockAnalysisAuthError("Invalid API key")
                    response_text = await response.text()
                    _LOGGER.error(
                        "Failed to fetch data from %s: status=%s body=%s",
                        url, response.status, response_text[:300],
                    )
                    raise StockAnalysisAPIError(f"API request failed: {response.status}")
            except aiohttp.ClientError as err:
                if attempt < API_MAX_RETRIES - 1:
                    _LOGGER.debug(
                        "Request to %s failed, retrying (attempt %d/%d): %s",
                        url, attempt + 1, API_MAX_RETRIES, err,
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise StockAnalysisAPIError(f"Connection error after {API_MAX_RETRIES} attempts: {err}") from err

    async def _post(self, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST with retry+backoff on network errors, accepting 200 or 202 as success."""
        url = f"{self.base_url}{path}"
        headers = self._headers()
        ssl_context = self._ssl()

        for attempt in range(API_MAX_RETRIES):
            try:
                async with self._get_session().post(
                    url, json=json_body, headers=headers, ssl=ssl_context
                ) as response:
                    if response.status in (200, 202):
                        try:
                            return await response.json()
                        except ValueError as err:
                            raise StockAnalysisAPIError(f"Invalid JSON response from {url}") from err
                    if response.status == 401:
                        raise StockAnalysisAuthError("Invalid API key")
                    response_text = await response.text()
                    _LOGGER.error(
                        "Failed to post data to %s: status=%s body=%s",
                        url, response.status, response_text[:300],
                    )
                    raise StockAnalysisAPIError(f"API request failed: {response.status}")
            except aiohttp.ClientError as err:
                if attempt < API_MAX_RETRIES - 1:
                    _LOGGER.debug(
                        "Request to %s failed, retrying (attempt %d/%d): %s",
                        url, attempt + 1, API_MAX_RETRIES, err,
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise StockAnalysisAPIError(f"Connection error after {API_MAX_RETRIES} attempts: {err}") from err

    async def get_portfolio_totals(self) -> dict[str, Any]:
        """Fetch aggregated portfolio totals (value, gain, TWR, dividends)."""
        return await self._get("/api/accounts/portfolio-totals")

    async def get_account_metrics(self) -> dict[str, Any]:
        """Fetch per-Trading-account metrics (cash, gains, P&L, MWRR)."""
        return await self._get("/api/accounts/list-with-metrics")

    async def get_market_status(self) -> dict[str, Any]:
        """Fetch current market-open status and system health flags."""
        return await self._get("/api/system/market-status")

    async def trigger_refresh_now(self) -> dict[str, Any]:
        """Trigger an immediate portfolio data refresh on the backend."""
        return await self._post("/api/accounts/refresh-now")

    async def get_holdings(self) -> dict[str, Any]:
        """Fetch per-holding metrics across every Trading account (Phase 3)."""
        return await self._get("/api/accounts/holdings-list")

    async def set_holding_price_limit(
        self, account_id: int, ticker: str, low_limit: float | None = None, high_limit: float | None = None
    ) -> dict[str, Any]:
        """Set one holding's low and/or high price alert limit. Only the kwarg(s) actually passed
        are included in the request body, so the backend's partial-update semantics are preserved
        — setting a Low Limit never clears an already-set High Limit and vice versa."""
        body: dict[str, Any] = {"account_id": account_id, "ticker": ticker}
        if low_limit is not None:
            body["low_limit"] = low_limit
        if high_limit is not None:
            body["high_limit"] = high_limit
        return await self._post("/api/accounts/holding-price-limit", json_body=body)

    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
