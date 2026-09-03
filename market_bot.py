#!/usr/bin/env python3
"""Daily stock market + AI news digest, posted to Discord.

    python market_bot.py             post the digest to Discord
    python market_bot.py --dry-run   print it here, send nothing
    python market_bot.py --check     verify credentials and data sources only

Standard library only - there is nothing to pip install.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from marketbot import discord_api, formatting, news, summary, yahoo
from marketbot.timeutil import et_date_label

HERE = Path(__file__).resolve().parent

# ---- What gets tracked. Edit these lists to taste. -------------------------
# Which comapny to fetch
WATCHLIST = [
    "NVDA", "MSFT", "GOOGL", "AMZN", "META", "AAPL",
    "AMD", "TSM", "MU", "MRVL", "TSLA",
]

INDICES = ["^GSPC", "^IXIC"]

MACRO = ["GC=F", "BTC-USD"]



def force_utf8_output() -> None:
    """Print UTF-8 regardless of the console's codepage.

    Windows terminals default to cp1252, which cannot encode the emoji in the
    digest - printing it raises UnicodeEncodeError. This affects --dry-run and
    the scheduled task's log file; the Discord POST itself always encoded as
    UTF-8 and was never affected.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # Not a real console (piped or redirected in an odd way).


def load_env(path: Path) -> None:
    """Read a .env file into os.environ. Avoids needing python-dotenv."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Don't clobber a variable that's already set in the real environment.
        if key and key not in os.environ:
            os.environ[key] = value


def fail(message: str) -> None:
    print(f"\n[X] {message}\n", file=sys.stderr)
    sys.exit(1)


def preflight(token: str, channel_id: str):
    if not token:
        fail("DISCORD_BOT_TOKEN is missing from .env")
    if not channel_id:
        fail("DISCORD_CHANNEL_ID is missing or empty in .env")
    if not (channel_id.isdigit() and 17 <= len(channel_id) <= 20):
        fail(
            f'DISCORD_CHANNEL_ID "{channel_id}" does not look like a Discord ID '
            "(it should be 17-20 digits)."
        )

    try:
        me = discord_api.get_self(token)
    except discord_api.DiscordError as error:
        fail(discord_api.explain_error(error))
    print(f"  bot        : {me['username']} ({me['id']})")

    try:
        channel = discord_api.get_channel(token, channel_id)
    except discord_api.DiscordError as error:
        fail(discord_api.explain_error(error))
    print(f"  channel    : #{channel['name']} ({channel['id']})")


def gather():
    """Fetch every data source at once."""
    with ThreadPoolExecutor(max_workers=5) as pool:
        indices_future = pool.submit(yahoo.fetch_quotes, INDICES)
        macro_future = pool.submit(yahoo.fetch_quotes, MACRO)
        watchlist_future = pool.submit(yahoo.fetch_quotes, WATCHLIST)
        # Five each keeps the whole post to about two Discord messages.
        market_news_future = pool.submit(news.fetch_market_news, 5)
        ai_news_future = pool.submit(news.fetch_ai_news, 5)

        indices = indices_future.result()
        macro = macro_future.result()
        watchlist = watchlist_future.result()
        # Headlines are a nice-to-have; the digest still works without them.
        try:
            market_news = market_news_future.result()
        except Exception:  # noqa: BLE001
            market_news = []
        try:
            ai_news = ai_news_future.result()
        except Exception:  # noqa: BLE001
            ai_news = []

    if not indices and not watchlist:
        fail(
            "Could not fetch any market data - Yahoo Finance may be unreachable. "
            "Check your internet connection."
        )

    return indices, macro, watchlist, market_news, ai_news


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="print the digest instead of posting it")
    parser.add_argument("--check", action="store_true",
                        help="verify credentials and data sources, then exit")
    parser.add_argument("-m", "--morning", action="store_true",
                        help="post the morning recap of the last session instead "
                             "of the closing digest")
    args = parser.parse_args()

    force_utf8_output()
    load_env(HERE / ".env")
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    channel_id = os.environ.get("DISCORD_CHANNEL_ID", "").strip()

    started = time.time()
    mode = "Morning Recap" if args.morning else "Closing Digest"
    print(f"Market Bot ({mode}) - {et_date_label()} (ET)")

    if not args.dry_run:
        preflight(token, channel_id)

    # Both posts read the same session data. The morning run lands before the
    # open, so those quotes are the previous session's close - it just frames
    # them as a recap instead of as today's result.
    indices, macro, watchlist, market_news, ai_news = gather()
    print(
        f"  fetched    : {len(indices)} indices, {len(macro)} macro, "
        f"{len(watchlist)} tickers, {len(market_news) + len(ai_news)} headlines"
    )

    if args.check:
        print("\n[ok] All checks passed. Run without --check to post.\n")
        return

    # Write the summary paragraph, then lay out the whole post as text.
    if args.morning:
        summary_text = summary.build_recap_summary(indices, macro, watchlist)
    else:
        summary_text = summary.build_summary(indices, macro, watchlist)

    message = formatting.build_message(
        indices, macro, watchlist, market_news, ai_news,
        summary_text=summary_text, morning=args.morning,
    )
    chunks = formatting.split_for_discord(message)

    if args.dry_run:
        print("\n--- DRY RUN: nothing was sent to Discord ---\n")
        print(message)
        print(
            f"\n--- end of preview "
            f"({len(message)} characters, {len(chunks)} message(s)) ---\n"
        )
        return

    try:
        discord_api.post_text(token, channel_id, chunks)
    except discord_api.DiscordError as error:
        fail(discord_api.explain_error(error))

    elapsed = time.time() - started
    print(f"\n[ok] Posted {len(chunks)} message(s) in {elapsed:.1f}s\n")


if __name__ == "__main__":
    main()
