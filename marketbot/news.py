"""Fetches news headlines from RSS feeds.

We read straight from each publisher's own feed. Google News was the obvious
alternative, but its links are 250-character redirect blobs that would eat most
of Discord's 2000-character message limit. These feeds give clean, short links
like https://www.cnbc.com/2026/08/31/some-story.html

Uses Python's built-in XML parser - nothing to pip install.
"""

from __future__ import annotations
import html
import urllib.request
import xml.etree.ElementTree as ElementTree
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# Add or remove feeds here. Any normal RSS or Atom feed URL works.
# Market-specific feeds only. CNBC's general "top news" feed was pulling in
# politics and human-interest stories, which is not what this brief is for.
MARKET_FEEDS = [
    "https://www.cnbc.com/id/20910258/device/rss/rss.html",  # CNBC: markets
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",  # CNBC: economy
    "https://finance.yahoo.com/news/rssindex",  # Yahoo Finance
]

AI_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://venturebeat.com/category/ai/feed/",
]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml",
}

# Atom feeds (The Verge) put their tags in this namespace; RSS feeds don't.
ATOM = "{http://www.w3.org/2005/Atom}"


class Headline:
    """One news story: what it says, where it lives, who wrote it."""

    def __init__(self, title, link, source, published):
        self.title = title
        self.link = link
        self.source = source
        self.published = published

    def __repr__(self):
        return f"<Headline {self.title[:40]!r} ({self.source})>"


def _download(url):
    """Download a feed and return its raw bytes.

    We hand bytes (not text) to the XML parser so it can honour whatever
    encoding the feed declares in its own header. Guessing UTF-8 ourselves
    turned curly quotes into replacement characters.
    """
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read()


def _clean_text(text):
    """Tidy a headline: collapse whitespace and decode HTML entities.

    Some feeds escape their text twice, so a right single quote arrives as
    "&amp;#8217;". The XML parser undoes one layer; html.unescape undoes the
    other, which is why this runs after parsing.
    """
    return html.unescape(" ".join(text.split()))


def _publisher_name(url):
    """Turn a URL into a readable source name: 'www.cnbc.com' -> 'CNBC'."""
    host = url.split("/")[2] if "://" in url else url
    host = host.replace("www.", "").replace("feeds.", "")
    name = host.split(".")[0]
    nicer = {
        "cnbc": "CNBC",
        "techcrunch": "TechCrunch",
        "theverge": "The Verge",
        "venturebeat": "VentureBeat",
        "finance": "Yahoo Finance",
        "arstechnica": "Ars Technica",
        "marketwatch": "MarketWatch",
    }
    return nicer.get(name, name.capitalize())


def _read_date(text):
    """Parse a feed's date string. Returns None if it can't be understood."""
    if not text:
        return None
    try:
        moment = parsedate_to_datetime(text)
    except Exception:
        try:
            # Atom style: "2026-08-31T14:05:00Z"
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _parse_feed(xml_bytes, feed_url):
    """Pull the headlines out of one feed's XML."""
    headlines = []

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return headlines  # Malformed feed - skip it rather than crash.

    # RSS calls them <item>; Atom calls them <entry>. Look for both.
    entries = root.findall(".//item") + root.findall(f".//{ATOM}entry")

    for entry in entries:
        title_tag = entry.find("title")
        if title_tag is None:
            title_tag = entry.find(f"{ATOM}title")
        if title_tag is None or not title_tag.text:
            continue
        title = _clean_text(title_tag.text)

        # RSS puts the URL inside <link>; Atom puts it in a href attribute.
        link_tag = entry.find("link")
        if link_tag is not None and link_tag.text:
            link = link_tag.text.strip()
        else:
            atom_link = entry.find(f"{ATOM}link")
            link = atom_link.get("href", "") if atom_link is not None else ""
        if not link:
            continue

        date_tag = entry.find("pubDate")
        if date_tag is None:
            date_tag = entry.find(f"{ATOM}published") or entry.find(f"{ATOM}updated")
        published = _read_date(date_tag.text if date_tag is not None else None)

        headlines.append(
            Headline(
                title=title,
                link=link,
                source=_publisher_name(link or feed_url),
                published=published,
            )
        )

    return headlines


def _fetch_one(feed_url):
    """Download and parse a single feed. Never raises - a dead feed just
    contributes nothing, so one outage can't stop the whole brief."""
    try:
        return _parse_feed(_download(feed_url), feed_url)
    except Exception:
        return []


OLDEST_POSSIBLE = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _newest_first(headlines):
    """Sort newest to oldest. Stories with no date go last."""
    return sorted(headlines, key=lambda h: h.published or OLDEST_POSSIBLE, reverse=True)


def _take_turns(batches, limit):
    """Pick one story from each feed in turn, until we have enough.

    Sorting everything purely by time let whichever outlet published most
    recently fill the entire list. Taking turns keeps a mix of sources.
    """
    chosen = []
    seen_titles = set()
    position = 0

    while len(chosen) < limit:
        added_any = False
        for batch in batches:
            if position >= len(batch):
                continue
            story = batch[position]
            added_any = True

            # Skip the same story reported by two different outlets.
            key = story.title.lower()[:60]
            if key in seen_titles:
                continue
            seen_titles.add(key)

            chosen.append(story)
            if len(chosen) >= limit:
                break
        if not added_any:
            break  # Every feed is exhausted.
        position += 1

    return chosen


def _collect(feed_urls, limit, max_age_hours=36):
    """Fetch every feed and return a recent, mixed selection of stories."""
    with ThreadPoolExecutor(max_workers=len(feed_urls)) as pool:
        batches = list(pool.map(_fetch_one, feed_urls))

    # Drop anything older than max_age_hours so the brief stays current.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    fresh_batches = []
    for batch in batches:
        recent = [h for h in batch if h.published is None or h.published >= cutoff]
        if recent:
            fresh_batches.append(_newest_first(recent))

    return _take_turns(fresh_batches, limit)


def fetch_market_news(limit=6):
    """Business and market headlines."""
    return _collect(MARKET_FEEDS, limit)


def fetch_ai_news(limit=6):
    """AI and tech headlines."""
    return _collect(AI_FEEDS, limit)
