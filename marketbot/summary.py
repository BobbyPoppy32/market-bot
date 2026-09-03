"""Turns the day's numbers into a few sentences of plain English.

This is rule-based, not AI-generated: it reads the same data that goes into
the tables and describes it the way a person would. That keeps it free,
instant, and incapable of inventing a fact that isn't in the numbers.
"""

from __future__ import annotations

from .timeutil import et_session_weekday, et_weekday, is_fresh

# Friendlier than Yahoo's "NVIDIA Corporation" / "Alphabet Inc."
# How to display them
COMPANY_NAMES = {
    "NVDA": "Nvidia",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta",
    "AAPL": "Apple",
    "AMD": "AMD",
    "TSM": "TSMC",
    "PLTR": "Palantir",
    "MU": "Micron",
    "ORCL": "Oracle",
    "TSLA": "Tesla",
    "MRVL": "Marvwell",
}

INDEX_NAMES = {
    "^GSPC": "the S&P 500",
    "^IXIC": "the Nasdaq",

}

MACRO_NAMES = {
    "GC=F": "Gold",
    "BTC-USD": "Bitcoin",
}


def _by_symbol(quotes):
    return {quote.symbol: quote for quote in quotes}


def _pct(value) -> str:
    return f"{abs(value):.2f}%"


def _price(value) -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _sentence_case(text: str) -> str:
    """Uppercase the first letter only.
    str.capitalize() lowercases everything after it, which would turn
    'the S&P 500' into 'The s&p 500'.
    """
    return text[:1].upper() + text[1:] if text else text


def _move_phrase(pct: float, price) -> str:
    """A gerund phrase that slots after 'with the S&P 500 ...'.

    Picking the verb by magnitude keeps the sentence grammatical and gives the
    reader a sense of scale without a separate adverb.
    """
    size = abs(pct)
    if size < 0.15:
        return f"little changed at {_price(price)}"
    if size < 0.4:
        verb = "edging up" if pct > 0 else "edging down"
    elif size < 1.0:
        verb = "climbing" if pct > 0 else "slipping"
    elif size < 2.5:
        verb = "rallying" if pct > 0 else "sliding"
    else:
        verb = "surging" if pct > 0 else "tumbling"
    return f"{verb} {_pct(pct)} to {_price(price)}"


def _verb(pct: float, past=("rose", "fell")) -> str:
    return past[0] if pct >= 0 else past[1]


def _direction(pct: float) -> str:
    """'up' / 'down' - for clauses where a past-tense verb would not agree,
    e.g. 'with S&P 500 futures down 0.26%'."""
    return "up" if pct >= 0 else "down"


def _join(parts) -> str:
    """Oxford-comma join: ['a','b','c'] -> 'a, b and c'."""
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _headline_sentence(indices_by_symbol, when: str) -> str:
    """Opening line: overall direction and the S&P's move.

    `when` is the time phrase to use, e.g. 'on Monday' or 'at the last close' -
    the caller knows whether it's describing today's session or an earlier one.
    """
    core = [
        indices_by_symbol[sym]
        for sym in ("^GSPC", "^IXIC", "^DJI", "^RUT")
        if sym in indices_by_symbol and indices_by_symbol[sym].change_pct is not None
    ]
    if not core:
        return "Market data was unavailable for the latest session."

    up = [q for q in core if q.change_pct > 0]
    down = [q for q in core if q.change_pct < 0]

    if not down:
        breadth = "closed broadly higher"
    elif not up:
        breadth = "closed broadly lower"
    elif len(up) > len(down):
        breadth = "ended mostly higher"
    elif len(down) > len(up):
        breadth = "ended mostly lower"
    else:
        breadth = "ended mixed"

    spx = indices_by_symbol.get("^GSPC")
    if spx and spx.change_pct is not None:
        phrase = _move_phrase(spx.change_pct, spx.price)
        return f"Stocks {breadth} {when}, with the S&P 500 {phrase}."

    return f"Stocks {breadth} {when}."


def _spread_sentence(indices_by_symbol) -> str:
    """Which index led and which lagged - only worth saying if they differ."""
    core = [
        indices_by_symbol[sym]
        for sym in ("^IXIC", "^DJI", "^RUT")
        if sym in indices_by_symbol and indices_by_symbol[sym].change_pct is not None
    ]
    if len(core) < 2:
        return ""

    best = max(core, key=lambda q: q.change_pct)
    worst = min(core, key=lambda q: q.change_pct)

    # If everything moved together, there's no dispersion story to tell.
    if abs(best.change_pct - worst.change_pct) < 0.25:
        return ""

    best_name = INDEX_NAMES.get(best.symbol, best.symbol)
    worst_name = INDEX_NAMES.get(worst.symbol, worst.symbol)

    if worst.change_pct < 0 <= best.change_pct:
        return (
            f"{_sentence_case(best_name)} held up best at {best.change_pct:+.2f}%, "
            f"while {worst_name} lagged at {worst.change_pct:+.2f}%."
        )
    if best.change_pct < 0:
        return (
            f"{_sentence_case(worst_name)} led the declines "
            f"({worst.change_pct:+.2f}%), with {best_name} down least "
            f"({best.change_pct:+.2f}%)."
        )
    return (
        f"{_sentence_case(best_name)} led the gains ({best.change_pct:+.2f}%), "
        f"with {worst_name} trailing ({worst.change_pct:+.2f}%)."
    )


def _volatility_sentence(indices_by_symbol) -> str:
    vix = indices_by_symbol.get("^VIX")
    if not vix or vix.change_pct is None:
        return ""
    move = vix.change_pct
    if abs(move) < 2:
        return ""
    if move >= 8:
        return (
            f"Volatility spiked, with the VIX up {_pct(move)} to "
            f"{_price(vix.price)} - traders were paying up for protection."
        )
    if move > 0:
        return f"The VIX rose {_pct(move)} to {_price(vix.price)}, a modest uptick in nerves."
    if move <= -8:
        return f"Volatility collapsed, with the VIX down {_pct(move)} to {_price(vix.price)}."
    return f"The VIX eased {_pct(move)} to {_price(vix.price)}."


def _tech_sentence(watchlist) -> str:
    rated = [q for q in watchlist if q.change_pct is not None]
    if not rated:
        return ""

    advancers = [q for q in rated if q.change_pct > 0]
    best = max(rated, key=lambda q: q.change_pct)
    worst = min(rated, key=lambda q: q.change_pct)

    name = lambda q: COMPANY_NAMES.get(q.symbol, q.symbol)  # noqa: E731

    if len(advancers) == len(rated):
        breadth = "AI and big tech were green across the board"
    elif not advancers:
        breadth = "AI and big tech were red across the board"
    else:
        breadth = (
            f"Across AI and big tech, {len(advancers)} of {len(rated)} names advanced"
        )

    leader = f"{name(best)} {_verb(best.change_pct)} {_pct(best.change_pct)}"
    laggard = f"{name(worst)} {_verb(worst.change_pct)} {_pct(worst.change_pct)}"

    # When everything moved the same way, "led ... while ... lagged" reads wrong.
    if best.change_pct >= 0 > worst.change_pct:
        return f"{breadth} - {leader}, while {laggard}."
    return f"{breadth}, led by {leader}; {laggard} at the other end."


def _macro_sentence(macro_by_symbol) -> str:
    """Only mention rates and commodities when they actually did something."""
    notes = []

    yield_quote = macro_by_symbol.get("^TNX")
    if yield_quote and yield_quote.change_pct is not None and abs(yield_quote.change_pct) >= 1.0:
        notes.append(
            f"the 10-year yield {_verb(yield_quote.change_pct)} to "
            f"{yield_quote.price:.2f}%"
        )

    for symbol in ("CL=F", "GC=F", "BTC-USD"):
        quote = macro_by_symbol.get(symbol)
        if not quote or quote.change_pct is None or abs(quote.change_pct) < 1.5:
            continue
        label = MACRO_NAMES.get(symbol, quote.symbol).lower()
        verb = _verb(quote.change_pct, ("climbed", "slid"))
        notes.append(f"{label} {verb} {_pct(quote.change_pct)} to ${_price(quote.price)}")

    if not notes:
        return ""
    return "Elsewhere, " + _join(notes) + "."


def build_summary(indices, macro, watchlist) -> str:
    """Assemble the narrative. Returns a short paragraph."""
    indices_by_symbol = _by_symbol(indices)
    macro_by_symbol = _by_symbol(macro)

    spx = indices_by_symbol.get("^GSPC")
    closed = not is_fresh(spx, indices) if spx else True

    when = "at the last close" if closed else f"on {et_weekday()}"

    sentences = [
        _headline_sentence(indices_by_symbol, when),
        _spread_sentence(indices_by_symbol),
        _volatility_sentence(indices_by_symbol),
        _tech_sentence(watchlist),
        _macro_sentence(macro_by_symbol),
    ]

    paragraph = " ".join(s for s in sentences if s)

    if closed:
        paragraph = (
            "**US markets were closed today** - here's where things stood at the "
            "last session's close.\n\n" + paragraph
        )
    return paragraph


def build_recap_summary(indices, macro, watchlist) -> str:
    """Morning version: the same numbers, framed as the session just gone.

    Runs before the open, so the quotes on hand are the previous session's
    close. We name that session explicitly rather than saying "today".
    """
    indices_by_symbol = _by_symbol(indices)
    macro_by_symbol = _by_symbol(macro)

    spx = indices_by_symbol.get("^GSPC")
    weekday = et_session_weekday(spx, indices) if spx else ""
    when = f"on {weekday}" if weekday else "in the last session"

    sentences = [
        _headline_sentence(indices_by_symbol, when),
        _spread_sentence(indices_by_symbol),
        _volatility_sentence(indices_by_symbol),
        _tech_sentence(watchlist),
        _macro_sentence(macro_by_symbol),
    ]
    return " ".join(s for s in sentences if s)
