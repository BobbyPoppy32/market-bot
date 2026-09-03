"""Builds the message text that gets posted to Discord.

Everything here returns plain strings. Discord understands a fair bit of
markdown in an ordinary message:

    ## Heading        a real heading, bigger and bolder than **bold**
    ### Heading       a smaller heading
    **bold**          bold
    _italic_          italic
    -# subtext        small grey text, good for captions
    [text](url)       a clickable link with the URL hidden

Bots may use masked links in normal messages even though people typing in the
chat box cannot, which is why headlines here are links rather than bare URLs.

Note we avoid backticks for prices and names. A backtick makes Discord render
text in a grey code box, which reads as "this is code" rather than "this is a
number".
"""

from __future__ import annotations

from datetime import datetime, timezone

from .timeutil import et_long_date, et_session_label

# Discord refuses any single message longer than this.
DISCORD_MESSAGE_LIMIT = 2000

# Short, readable names for the tickers we track.
DISPLAY_NAMES = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq",
    "^DJI": "Dow Jones",
    "^RUT": "Russell 2000",
    "^VIX": "VIX",
    "^TNX": "US 10-Year Yield",
    "CL=F": "Crude Oil",
    "GC=F": "Gold",
    "BTC-USD": "Bitcoin",
    "NVDA": "Nvidia",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta",
    "AAPL": "Apple",
    "AMD": "AMD",
    "AVGO": "Broadcom",
    "TSM": "TSMC",
    "PLTR": "Palantir",
    "MU": "Micron",
    "ORCL": "Oracle",
    "TSLA": "Tesla",
    "CRM": "Salesforce",
    "MRVL": "Marvell",
}

# Yahoo returns full legal names like "Marvell Technology, Inc.". Trimming
# these endings means a ticker you add to the watchlist looks tidy straight
# away, without having to add it to DISPLAY_NAMES above first.
COMPANY_SUFFIXES = (
    ", inc.", " inc.", ", inc", " inc", " incorporated",
    " corporation", " corp.", " corp",
    ", ltd.", " ltd.", " ltd", " limited",
    " holdings", " holding", " company", " co.",
    " technologies", " technology",
    " plc", " n.v.", " s.a.", " a/s", " ag", " se",
)

# Symbols quoted in dollars. Everything else is an index level or a percentage.
DOLLAR_SYMBOLS = {"CL=F", "GC=F", "BTC-USD"}

# Symbols that are themselves a percentage, so "4.76%" is the value, not a move.
PERCENT_SYMBOLS = {"^TNX"}

# Symbols where "up" is bad news rather than good, so the dot should flip
# instead of following the sign of change_pct like everything else.
INVERTED_SYMBOLS = {"^VIX"}

def tidy_company_name(name):
    """'Marvell Technology, Inc.' -> 'Marvell'

    Strips one suffix at a time and keeps going, since names often carry two
    ("Technology" then ", Inc."). Never trims away the whole name.
    """
    cleaned = name.strip()
    changed = True
    while changed:
        changed = False
        for suffix in COMPANY_SUFFIXES:
            if cleaned.lower().endswith(suffix):
                shorter = cleaned[: -len(suffix)].strip(" ,")
                if shorter:  # Don't let "Inc" alone become an empty string.
                    cleaned = shorter
                    changed = True
    return cleaned or name


def name_of(quote):
    """The friendly name for a quote.

    Looks in DISPLAY_NAMES first, then tidies whatever Yahoo reported, then
    falls back to the ticker symbol itself.
    """
    if quote.symbol in DISPLAY_NAMES:
        return DISPLAY_NAMES[quote.symbol]
    if quote.name:
        return tidy_company_name(quote.name)
    return quote.symbol


def format_price(value):
    """7686.14 -> '7,686.14'"""
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value:,.2f}"


def format_percent(value):
    """-0.33 -> '-0.33%'  (with a sign, always)"""
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value:+.2f}%"


def format_level(quote):
    """The price, written the way that symbol is normally quoted.

    Gold is $4,497.30; the 10-year yield is 4.76%; the S&P 500 is just
    7,686.14. Without this the yield row read "4.76 (+0.81%)", which looks
    like two different percentages sitting next to each other.
    """
    text = format_price(quote.price)
    if quote.symbol in DOLLAR_SYMBOLS:
        return f"${text}"
    if quote.symbol in PERCENT_SYMBOLS:
        return f"{text}%"
    return text


def dot_for(value, symbol=None):
    """A coloured dot showing direction at a glance.

    Flipped for INVERTED_SYMBOLS (like the VIX), where a rise is bad news
    rather than good - otherwise a spiking VIX would show as green.
    """
    if not isinstance(value, (int, float)):
        return "⚪"
    if symbol in INVERTED_SYMBOLS:
        value = -value
    if value > 0:
        return "🟢"
    if value < 0:
        return "🔴"
    return "⚪"


def time_ago(moment):
    """'2h ago' / 'just now'. Returns '' when we have no timestamp."""
    if moment is None:
        return ""

    minutes = (datetime.now(timezone.utc) - moment).total_seconds() / 60
    if minutes < 0:
        return ""  # Clock skew - better to say nothing than something silly.
    if minutes < 5:
        return "just now"
    if minutes < 60:
        return f"{int(minutes)}m ago"

    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h ago"
    return f"{int(hours / 24)}d ago"


def quote_line(quote):
    """One market row: '🔴 **S&P 500**  7,686.14  ·  -0.33%'"""
    return (
        f"{dot_for(quote.change_pct, quote.symbol)} **{name_of(quote)}**  "
        f"{format_level(quote)}  ·  {format_percent(quote.change_pct)}"
    )


def movers_table(quotes):
    """Names and moves as aligned columns, best performer first.

    Wrapped in a code block by the caller, since a fixed-width table only
    lines up in Discord's monospace font.
    """
    ranked = sorted(quotes, key=lambda q: q.change_pct, reverse=True)

    # Pad every name to the width of the longest one, so the percent column
    # starts in the same place on every row.
    name_width = max(len(name_of(q)) for q in ranked) + 2

    lines = []
    for quote in ranked:
        name = name_of(quote).ljust(name_width)
        pct = format_percent(quote.change_pct).rjust(7)
        lines.append(f"{name}{pct}")
    return lines


def news_lines(headlines):
    """Numbered headlines, each a clickable link with a small caption under it."""
    lines = []
    for number, story in enumerate(headlines, start=1):
        # The title is the link text, so the raw URL never clutters the message.
        lines.append(f"**{number}.** [{story.title}]({story.link})")

        caption = story.source
        when = time_ago(story.published)
        if when:
            caption += f" · {when}"
        lines.append(f"-# {caption}")
    return lines


def glance_line(indices):
    """A single bold line with every index's move, e.g.
    '**S&P 500 +0.42% · Nasdaq +0.61%**' - the headline number, readable
    without opening the message or reading the summary paragraph.
    """
    moves = [q for q in indices if q.change_pct is not None]
    if not moves:
        return ""
    return "**" + " · ".join(
        f"{name_of(q)} {format_percent(q.change_pct)}" for q in moves
    ) + "**"


def market_section(indices):
    """The index rows."""
    if not indices:
        return []
    return ["### 📊 Indexes"] + [quote_line(q) for q in indices]


def tech_section(watchlist):
    """The whole AI / big tech watchlist as an aligned table, best first."""
    rated = [q for q in watchlist if q.change_pct is not None]
    if not rated:
        return []

    return (
        ["### 🤖 AI & Big Tech", "```"]
        + movers_table(rated)
        + ["```"]
    )


def macro_section(macro):
    """Rates, commodities and crypto."""
    if not macro:
        return []
    return ["### 🛢️ Rates, Commodities & Crypto"] + [quote_line(q) for q in macro]


def news_section(heading, headlines):
    """One block of numbered headlines."""
    if not headlines:
        return []
    return [heading] + news_lines(headlines)


def build_message(indices, macro, watchlist, market_news, ai_news,
                  summary_text="", morning=False):
    """Assemble the whole post as one long string.

    Sections are separated by blank lines, which is also where we split the
    text if it grows past Discord's message limit.
    """
    spx = next((q for q in indices if q.symbol == "^GSPC"), None)

    if morning:
        session = et_session_label(spx, indices) if spx else "the last session"
        title = f"## ☀️ Morning Brief · {session}"
    else:
        title = f"## 🔔 Market Close · {et_long_date()}"

    # Each entry here is one section: a list of lines.
    glance = glance_line(indices)
    sections = [
        [title],
        [glance] if glance else [],
        [summary_text] if summary_text else [],
        market_section(indices),
        tech_section(watchlist),
        macro_section(macro),
        news_section("### 📰 Market News", market_news),
        news_section("### 🧠 AI News", ai_news),
    ]

    blocks = ["\n".join(section) for section in sections if section]
    return "\n\n".join(blocks)


def split_for_discord(text, limit=DISCORD_MESSAGE_LIMIT):
    """Break a long post into message-sized chunks.

    We split on blank lines so a section never gets cut in half. If a single
    section is somehow longer than the limit, it gets split line by line.
    """
    chunks = []
    current = ""

    for block in text.split("\n\n"):
        # +2 for the blank line we would add back between blocks.
        if current and len(current) + len(block) + 2 <= limit:
            current += "\n\n" + block
            continue

        if current:
            chunks.append(current)

        if len(block) <= limit:
            current = block
            continue

        # Rare: one section on its own is too long. Fall back to single lines,
        # and if even one line is too long, to hard character slices. Without
        # that last step an enormous headline would produce an over-limit
        # chunk, which Discord rejects outright.
        current = ""
        for line in block.split("\n"):
            while len(line) > limit:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(line[:limit])
                line = line[limit:]

            if current and len(current) + len(line) + 1 > limit:
                chunks.append(current)
                current = ""
            current = f"{current}\n{line}" if current else line

    if current:
        chunks.append(current)

    return chunks
