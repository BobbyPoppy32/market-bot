<p align="center">
  <img src="assets/banner.svg" alt="Market Bot" width="100%" />
</p>

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img alt="No dependencies" src="https://img.shields.io/badge/dependencies-none-4fbf8b?style=flat-square" />
  <img alt="Discord" src="https://img.shields.io/badge/posts%20to-Discord-5865F2?style=flat-square&logo=discord&logoColor=white" />
  <img alt="License" src="https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square" />
</p>

Posts a daily stock market + AI news digest to a Discord channel, opening with
a plain-English summary of what actually happened — written by rules, not an
AI model, so it's free, instant, and can't invent a fact that isn't in the
data.

Python, **standard library only** — nothing to `pip install`. The only
credential you need is a Discord bot token.

## What it posts

One message a day, weekdays at 4:30 PM, right after the close:

| Section | Contents |
| --- | --- |
| Summary | 2–4 sentences describing the session |
| Indexes | S&P 500, Nasdaq (edit the list to add more) |
| AI & Big Tech | Your whole watchlist, ranked winners to losers |
| Rates, Commodities & Crypto | Gold, Bitcoin (edit the list to add more) |
| Market News | A handful of headlines from CNBC and Yahoo Finance |
| AI News | A handful of headlines from TechCrunch, The Verge, VentureBeat |

It's plain Discord text, not embeds — headlines are clickable links (Discord
auto-shows a small preview card for each), tickers are laid out in
easy-to-scan rows, and section headers use real Discord headings.

The summary reads like this — verbatim output from a real run, not a
mock-up:

> Stocks closed broadly lower on Monday, with the S&P 500 edging down 0.33%
> to 7,686. Across AI and big tech, 7 of 14 names advanced - Tesla rose
> 5.50%, while Amazon fell 2.50%.

## Setup

### 1. Invite the bot to your server

```
https://discord.com/oauth2/authorize?client_id=1544072497098530857&scope=bot&permissions=19456
```

That grants exactly three permissions: View Channel, Send Messages, Embed
Links.

### 2. Get the channel ID

In Discord: **User Settings → Advanced → Developer Mode** on. Then
right-click the channel you want the digest in → **Copy Channel ID**.

### 3. Fill in `.env`

```
DISCORD_BOT_TOKEN=your-bot-token
DISCORD_CHANNEL_ID=paste-the-17-to-20-digit-id-here
```

`.env` is gitignored — never commit it. If the token leaks, regenerate it in
the Discord Developer Portal.

### 4. Verify, then post

```bash
python market_bot.py --check
```

```bash
python market_bot.py
```

## Commands

| Command | Effect |
| --- | --- |
| `python market_bot.py` | Post the digest to Discord |
| `python market_bot.py --dry-run` | Print it to the terminal, send nothing |
| `python market_bot.py --check` | Validate credentials and data sources only |

Only `market_bot.py` gets run directly. Everything in `marketbot/` is a
module it imports — running one of those files on its own will fail with an
import error.

## Running it daily

`setup-schedule.ps1` registers a Windows Scheduled Task that runs the bot
automatically, even when nobody's logged in. From PowerShell in this folder:

```powershell
.\setup-schedule.ps1 -Time "16:30" -NoMorning
```

Test it immediately without waiting for the scheduled time:

```powershell
Start-ScheduledTask -TaskName "MarketBot Daily Digest"
```

Remove it:

```powershell
.\setup-schedule.ps1 -Remove
```

Since it runs in the background, its output goes to `logs\market-bot.log`
instead of a terminal — check that file if a scheduled run doesn't show up
in Discord.

## Customising

**Which tickers** — edit the lists at the top of `market_bot.py`:

```python
INDICES   = ["^GSPC", "^IXIC"]
MACRO     = ["GC=F", "BTC-USD"]
WATCHLIST = ["NVDA", "MSFT", "GOOGL", "AMZN", ...]
```

Any Yahoo Finance symbol works (`^` prefixes an index, `=F` a future). Add a
display name to `DISPLAY_NAMES` in `marketbot/formatting.py` if you want
something friendlier than the raw symbol — though most tickers look fine
automatically, since Yahoo's own company name gets tidied up (`"Marvell
Technology, Inc."` → `"Marvell"`).

**Which news sources** — `MARKET_FEEDS` and `AI_FEEDS` in
`marketbot/news.py` are plain RSS feed URLs. Add or remove any publisher's
feed URL to change what shows up.

**How the summary reads** — every sentence is a small function in
`marketbot/summary.py` (`_headline_sentence`, `_spread_sentence`,
`_volatility_sentence`, `_tech_sentence`, `_macro_sentence`). Each returns a
string, or `""` to stay silent when nothing interesting happened. Edit the
wording or the thresholds there.

**Layout of the message itself** — section order, headings, and how
tickers/headlines are laid out all live in `build_message()` in
`marketbot/formatting.py`.

## Layout

```
market_bot.py             entry point, ticker lists, CLI flags
marketbot/yahoo.py        market data (Yahoo Finance chart endpoint)
marketbot/news.py         headlines (publisher RSS feeds)
marketbot/summary.py      the plain-English write-up
marketbot/formatting.py   builds the Discord message text, enforces size limits
marketbot/discord_api.py  minimal Discord REST client
marketbot/timeutil.py     Eastern-time helpers
run-bot.cmd               Task Scheduler wrapper, logs to logs\
setup-schedule.ps1        registers/removes the scheduled task
```

## Notes

- Both data sources are undocumented public endpoints. Stable in practice,
  but no uptime guarantee. A ticker that fails is skipped rather than
  failing the run; if news fails entirely the digest still posts with
  market data.
- Timezone handling reads the exchange's UTC offset from the Yahoo response
  rather than using `zoneinfo`, because Windows ships no IANA timezone
  database and `zoneinfo` would otherwise need `pip install tzdata`.
- Discord caps a single message at 2000 characters; `split_for_discord()`
  in `marketbot/formatting.py` breaks the digest into multiple messages at
  section boundaries when it runs long.
