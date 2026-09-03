"""Minimal Discord REST client.

A one-shot script doesn't need a gateway connection - posting a message is a
single authenticated POST. Standard library only.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"


class DiscordError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _request(path: str, token: str, method: str = "GET", body=None, attempts: int = 3):
    payload = json.dumps(body).encode("utf-8") if body is not None else None

    for attempt in range(attempts):
        request = urllib.request.Request(
            f"{API}{path}",
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
                "User-Agent": "MarketBot (https://example.invalid, 1.0)",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                text = response.read().decode("utf-8")
                return json.loads(text) if text else None
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except ValueError:
                data = {}

            # 429 = rate limited. Discord tells us how long to wait.
            if error.code == 429 and attempt < attempts - 1:
                time.sleep(float(data.get("retry_after", 1)) + 0.1)
                continue

            raise DiscordError(
                f"Discord {method} {path} failed: HTTP {error.code} — "
                f"{data.get('message', raw)}",
                status=error.code,
            ) from error
        except urllib.error.URLError as error:
            raise DiscordError(f"Could not reach Discord: {error.reason}") from error

    raise DiscordError(f"Discord {method} {path} failed: rate limited after {attempts} attempts")


def get_self(token):
    return _request("/users/@me", token)


def get_channel(token, channel_id):
    return _request(f"/channels/{channel_id}", token)


def post_text(token, channel_id, chunks):
    """Post one or more plain-text messages, in order.

    `chunks` comes from formatting.split_for_discord(), so each piece is
    already under Discord's 2000-character limit.
    """
    for chunk in chunks:
        if not chunk.strip():
            continue
        _request(
            f"/channels/{channel_id}/messages",
            token,
            method="POST",
            # allowed_mentions stops an stray @everyone in a headline from
            # actually pinging the channel.
            body={"content": chunk, "allowed_mentions": {"parse": []}},
        )


def explain_error(error) -> str:
    """Plain-language version of the common failure modes."""
    status = getattr(error, "status", None)
    if status == 401:
        return "Bot token is invalid or was regenerated. Update DISCORD_BOT_TOKEN in .env"
    if status == 403:
        return (
            "The bot is in the server but can't post in that channel. Give it "
            "View Channel + Send Messages + Embed Links."
        )
    if status == 404:
        return (
            "Channel not found. Either DISCORD_CHANNEL_ID is wrong, or the bot "
            "hasn't been invited to that server."
        )
    if status == 400:
        return "Discord rejected the message (usually an embed over a size limit)."
    return str(error)
