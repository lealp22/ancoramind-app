"""Deterministic final-response chunking for the Telegram logical-response outbox."""

from __future__ import annotations

TELEGRAM_MAX_MESSAGE_CHARS = 4000
"""Conservative limit below Telegram's 4096-character sendMessage maximum."""


def split_telegram_message(content: str, limit: int = TELEGRAM_MAX_MESSAGE_CHARS) -> list[str]:
    """Split final content deterministically, preferring line/word boundaries.

    The same content always produces the same chunks, so chunks need not be
    stored independently alongside the encrypted logical response.
    """
    if limit < 1:
        raise ValueError("Telegram chunk limit must be positive")
    if not content:
        return [""]

    chunks: list[str] = []
    remainder = content
    while len(remainder) > limit:
        split_at = max(remainder.rfind("\n", 0, limit + 1), remainder.rfind(" ", 0, limit + 1))
        if split_at <= 0:
            split_at = limit
        chunk = remainder[:split_at].rstrip()
        if not chunk:
            chunk = remainder[:limit]
            split_at = limit
        chunks.append(chunk)
        remainder = remainder[split_at:].lstrip("\n ")
    chunks.append(remainder)
    return chunks
