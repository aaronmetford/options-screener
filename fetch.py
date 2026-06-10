"""
fetch.py — ALL marketdata.app I/O lives here.

Swappable: replace this file with a ThetaData/IBKR backend and
analyze/report/db/scan stay untouched.  The only contract is that
fetch_ticker(ticker) returns {'call': {...}, 'put': {...}} where each
dict has the keys documented below.

Token security: read from os.environ only; NEVER logged or printed.
"""
import datetime
import logging
import os
import threading
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import BACKOFF_BASE, MAX_RETRIES, REQUESTS_PER_MINUTE

logger = logging.getLogger(__name__)

BASE_URL = "https://api.marketdata.app/v1"

# Map internal field names -> exact JSON keys returned by marketdata.app.
# If step0_verify.py shows different field names, update only this dict.
FIELD_MAP: dict[str, str] = {
    "bid":            "bid",
    "ask":            "ask",
    "mid":            "mid",
    "volume":         "volume",
    "openInterest":   "openInterest",
    "strike":         "strike",
    "expiration":     "expiration",
    "underlyingPrice": "underlyingPrice",
    "last":           "last",
}

_rate_lock = threading.Lock()
_last_call_ts: float = 0.0
_min_interval: float = 60.0 / max(REQUESTS_PER_MINUTE, 1)


def _get_token() -> str:
    token = os.environ.get("MARKETDATA_TOKEN")
    if not token:
        raise RuntimeError(
            "MARKETDATA_TOKEN not set — create .env with MARKETDATA_TOKEN=your_token"
        )
    return token


def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_BASE,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
        allowed_methods=["GET"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


_SESSION: requests.Session = _build_session()


def _rate_limit() -> None:
    """Serialise requests to stay within REQUESTS_PER_MINUTE."""
    global _last_call_ts
    with _rate_lock:
        elapsed = time.monotonic() - _last_call_ts
        gap = _min_interval - elapsed
        if gap > 0:
            time.sleep(gap)
        _last_call_ts = time.monotonic()


def _extract(data: dict, field: str):
    """Return data[api_key][0], or None if absent/empty."""
    try:
        api_key = FIELD_MAP.get(field, field)
        arr = data.get(api_key)
        if arr and len(arr) > 0 and arr[0] is not None:
            return arr[0]
    except Exception:
        pass
    return None


def _extract_expiration(data: dict) -> Optional[str]:
    """Return expiration as YYYY-MM-DD string (handles Unix timestamp or string)."""
    val = _extract(data, "expiration")
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.datetime.utcfromtimestamp(val).strftime("%Y-%m-%d")
        except Exception:
            return str(val)
    return str(val)


def _parse_credit_headers(resp: requests.Response) -> dict:
    """Pull credits-used / credits-remaining from response headers or body."""
    info: dict = {}
    for hdr in ("X-Credits-Used", "X-Api-Credits-Used"):
        if hdr in resp.headers:
            info["credits_used"] = resp.headers[hdr]
            break
    for hdr in ("X-Credits-Remaining", "X-Api-Credits-Remaining"):
        if hdr in resp.headers:
            info["credits_remaining"] = resp.headers[hdr]
            break
    return info


def fetch_side(ticker: str, side: str) -> dict:
    """
    Fetch the first OTM option for one side ('call' or 'put').

    Returns a dict with keys:
        ticker, side, bid, ask, mid, volume, openInterest, strike,
        expiration, underlyingPrice, last,
        credits_used, credits_remaining, error (None on success)
    """
    _rate_limit()

    url = f"{BASE_URL}/options/chain/{ticker}/"
    params = {"side": side, "strikeLimit": 1}
    headers = {"Authorization": f"Bearer {_get_token()}"}

    base_result = {"ticker": ticker, "side": side, "error": None,
                   "credits_used": None, "credits_remaining": None}

    try:
        resp = _SESSION.get(url, headers=headers, params=params, timeout=15)

        # Log any rate-limit or credit headers (value only, not the token)
        credit_info = _parse_credit_headers(resp)
        if credit_info:
            logger.debug(
                "%s %s credits — used: %s  remaining: %s",
                ticker, side,
                credit_info.get("credits_used", "?"),
                credit_info.get("credits_remaining", "?"),
            )

        if resp.status_code == 404:
            return {**base_result, "error": "no chain data (404)"}
        if resp.status_code == 429:
            return {**base_result, "error": "rate limited (429)"}
        if not resp.ok:
            return {**base_result, "error": f"HTTP {resp.status_code}"}

        data = resp.json()

        # marketdata.app signals errors in the body with {"s": "error", "errmsg": "..."}
        if isinstance(data, dict) and data.get("s") == "error":
            return {**base_result, "error": data.get("errmsg", "API error in body")}

        bid = _extract(data, "bid")
        ask = _extract(data, "ask")
        mid = _extract(data, "mid")

        # Fallback: compute mid from bid/ask if not returned
        if mid is None and bid is not None and ask is not None:
            mid = (bid + ask) / 2.0

        # Also check body for credit info (some API versions put it there)
        body_credits_used = (
            data.get("creditsUsed") or data.get("credits_used")
            or credit_info.get("credits_used")
        )
        body_credits_remaining = (
            data.get("creditsRemaining") or data.get("credits_remaining")
            or credit_info.get("credits_remaining")
        )

        return {
            "ticker": ticker,
            "side": side,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "volume": _extract(data, "volume"),
            "openInterest": _extract(data, "openInterest"),
            "strike": _extract(data, "strike"),
            "expiration": _extract_expiration(data),
            "underlyingPrice": _extract(data, "underlyingPrice"),
            "last": _extract(data, "last"),
            "credits_used": body_credits_used,
            "credits_remaining": body_credits_remaining,
            "error": None,
        }

    except requests.RequestException as exc:
        logger.warning("Request error %s %s: %s", ticker, side, exc)
        return {**base_result, "error": str(exc)}
    except Exception as exc:
        logger.warning("Unexpected error %s %s: %s", ticker, side, exc)
        return {**base_result, "error": f"unexpected: {exc}"}


def fetch_ticker(ticker: str) -> dict:
    """Fetch call and put sides. Returns {'call': {...}, 'put': {...}}."""
    return {
        "call": fetch_side(ticker, "call"),
        "put":  fetch_side(ticker, "put"),
    }
