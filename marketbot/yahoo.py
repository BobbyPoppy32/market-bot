"""Market data from Yahoo Finance's public chart endpoint.

No API key needed. Yahoo's /v7/quote endpoint returns 401 these days, but the
/v8/chart endpoint still serves a full quote inside its "meta" block, so we
read from there.

Uses only the Python standard library - nothing to pip install.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class Quote:
    """One ticker's latest numbers."""

    def __init__(self, **kwargs):
        self.symbol = kwargs.get("symbol", "")
        self.name = kwargs.get("name", "")
        self.price = kwargs.get("price")
        self.prev_close = kwargs.get("prev_close")
        self.change = kwargs.get("change")
        self.change_pct = kwargs.get("change_pct")
        self.day_high = kwargs.get("day_high")
        self.day_low = kwargs.get("day_low")
        self.volume = kwargs.get("volume")
        self.week52_high = kwargs.get("week52_high")
        self.week52_low = kwargs.get("week52_low")
        self.currency = kwargs.get("currency", "USD")
        # Epoch seconds of the last regular-session print, plus the exchange's
        # UTC offset. We read the offset from Yahoo rather than using zoneinfo,
        # because Windows ships no IANA timezone database by default.
        self.market_time = kwargs.get("market_time")
        self.gmt_offset = kwargs.get("gmt_offset")
        self.tz_abbrev = kwargs.get("tz_abbrev", "ET")

    def __repr__(self):
        pct = f"{self.change_pct:+.2f}%" if self.change_pct is not None else "n/a"
        return f"<Quote {self.symbol} {self.price} ({pct})>"


def _get(url: str, timeout: int = 10, retries: int = 2) -> str:
    """GET a URL as text, retrying briefly on failure."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as error:  # noqa: BLE001 - any network failure is retryable
            last_error = error
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))
    raise last_error  # type: ignore[misc]
 

def fetch_quote(symbol: str):
    """Fetch one symbol. Returns None instead of raising, so a single bad
    ticker cannot take down the whole digest."""
    url = f"{BASE}/{urllib.parse.quote(symbol)}?interval=1d&range=1d"
    try:
        payload = json.loads(_get(url))
        meta = payload["chart"]["result"][0]["meta"]
    except Exception:  # noqa: BLE001
        return None

    price = meta.get("regularMarketPrice")
    if not isinstance(price, (int, float)):
        return None

    prev_close = meta.get("chartPreviousClose", meta.get("previousClose"))

    # Prefer Yahoo's own percentage; fall back to computing it ourselves.
    change_pct = meta.get("regularMarketChangePercent")
    if not isinstance(change_pct, (int, float)) and prev_close:
        change_pct = ((price - prev_close) / prev_close) * 100

    change = price - prev_close if isinstance(prev_close, (int, float)) else None

    return Quote(
        symbol=meta.get("symbol", symbol),
        name=meta.get("shortName") or meta.get("longName") or symbol,
        price=price,
        prev_close=prev_close,
        change=change,
        change_pct=change_pct if isinstance(change_pct, (int, float)) else None,
        day_high=meta.get("regularMarketDayHigh"),
        day_low=meta.get("regularMarketDayLow"),
        volume=meta.get("regularMarketVolume"),
        week52_high=meta.get("fiftyTwoWeekHigh"),
        week52_low=meta.get("fiftyTwoWeekLow"),
        currency=meta.get("currency", "USD"),
        market_time=meta.get("regularMarketTime"),
        gmt_offset=meta.get("gmtoffset"),
        tz_abbrev=meta.get("timezone", "ET"),
    )


def fetch_quotes(symbols, workers: int = 5):
    """Fetch many symbols in parallel. Drops any that failed."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch_quote, symbols))
    return [quote for quote in results if quote is not None]
