"""Eastern-time helpers.

Windows ships no IANA timezone database, so `zoneinfo.ZoneInfo("America/New_York")`
fails unless you pip install `tzdata`. To stay dependency-free we take the
exchange's own UTC offset straight from the Yahoo response, and only fall back
to computing the US DST rule ourselves if no quote is available.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _second_sunday_of_march(year: int) -> datetime:
    march_first = datetime(year, 3, 1, tzinfo=timezone.utc)
    days_to_sunday = (6 - march_first.weekday()) % 7
    return march_first + timedelta(days=days_to_sunday + 7)


def _first_sunday_of_november(year: int) -> datetime:
    nov_first = datetime(year, 11, 1, tzinfo=timezone.utc)
    days_to_sunday = (6 - nov_first.weekday()) % 7
    return nov_first + timedelta(days=days_to_sunday)


def _fallback_et_offset(moment: datetime) -> timedelta:
    """US Eastern offset: EDT (-4) between the 2nd Sunday of March and the
    1st Sunday of November, EST (-5) otherwise."""
    year = moment.year
    if _second_sunday_of_march(year) <= moment < _first_sunday_of_november(year):
        return timedelta(hours=-4)
    return timedelta(hours=-5)


def et_offset(quotes=None) -> timedelta:
    """Prefer the exchange offset reported by Yahoo; otherwise compute it."""
    for quote in quotes or []:
        if isinstance(getattr(quote, "gmt_offset", None), int):
            return timedelta(seconds=quote.gmt_offset)
    return _fallback_et_offset(datetime.now(timezone.utc))


def et_now(quotes=None) -> datetime:
    return datetime.now(timezone.utc) + et_offset(quotes)


def et_date_label(quotes=None) -> str:
    """e.g. 'Mon, Aug 31, 2026'"""
    return et_now(quotes).strftime("%a, %b %d, %Y").replace(" 0", " ")


def et_weekday(quotes=None) -> str:
    return et_now(quotes).strftime("%A")


def et_long_date(quotes=None) -> str:
    """e.g. 'Monday, August 31' - reads better in a sentence than the
    abbreviated label used in embed titles."""
    # %-d (no leading zero) is not portable to Windows, so strip it by hand.
    return et_now(quotes).strftime("%A, %B %d").replace(" 0", " ")


def hours_since_print(quote) -> float:
    """How many hours ago this symbol last traded.

    Used to tell a market that's genuinely closed (a holiday, or Asia after its
    session) from one that's actively trading, so the brief doesn't present a
    three-day-old print as this morning's move.
    """
    if not quote or not getattr(quote, "market_time", None):
        return float("inf")
    printed = datetime.fromtimestamp(quote.market_time, tz=timezone.utc)
    return (datetime.now(timezone.utc) - printed).total_seconds() / 3600.0


def et_session_datetime(quote, quotes=None):
    """When this quote actually last traded, in Eastern time.

    The morning recap runs before the open, so the numbers on hand belong to
    the *previous* session. This gives us that session's real date instead of
    assuming it was yesterday - which would be wrong on a Monday, or after a
    holiday.
    """
    if not quote or not getattr(quote, "market_time", None):
        return None
    return datetime.fromtimestamp(quote.market_time, tz=timezone.utc) + et_offset(quotes)


def et_session_weekday(quote, quotes=None) -> str:
    """'Monday' - the weekday the quote's session fell on."""
    moment = et_session_datetime(quote, quotes)
    return moment.strftime("%A") if moment else ""


def et_session_label(quote, quotes=None) -> str:
    """'Monday, August 31' - for headings and greetings."""
    moment = et_session_datetime(quote, quotes)
    if not moment:
        return et_long_date(quotes)
    return moment.strftime("%A, %B %d").replace(" 0", " ")


def is_fresh(quote, quotes=None) -> bool:
    """True when the quote's last print happened on the current ET day -
    i.e. we're looking at today's session, not a stale weekend close."""
    if not quote or not getattr(quote, "market_time", None):
        return False
    offset = et_offset(quotes)
    printed = datetime.fromtimestamp(quote.market_time, tz=timezone.utc) + offset
    return printed.date() == et_now(quotes).date()
