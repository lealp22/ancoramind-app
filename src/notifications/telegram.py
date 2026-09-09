"""Telegram notifier — outbound reminder delivery via Bot API (BL-5).

Direct httpx calls to the Telegram Bot API: no Agno internals (ADR-001) and
no inbound webhook needed — sendMessage is outbound-only, so reminders work
even while the webhook channel is unavailable (see ADR-003 / BL-18).
"""

import logging
from datetime import UTC, datetime

import httpx

from src.domain.reminders.models import Reminder

logger = logging.getLogger(__name__)

LATE_THRESHOLD_SECONDS = 300
"""Retries/downtime longer than this add a "fired late" note to the message."""

API_BASE_URL = "https://api.telegram.org"


def format_reminder_message(reminder: Reminder, now: datetime | None = None) -> str:
    """Render the outbound reminder text.

    Plain text on purpose: no parse_mode, since title/description are
    untrusted DATA (AGENTS.md §2.8) that could break Markdown rendering.
    """
    now = now or datetime.now(tz=UTC)
    lines = [f"⏰ Recordatorio: {reminder.title}"]
    if reminder.description:
        lines.append(reminder.description)
    trigger = reminder.trigger_at.strftime("%d/%m/%Y %H:%M")
    lines.append(f"Programado para: {trigger}")
    try:
        delay = (now - reminder.trigger_at).total_seconds()
    except TypeError:  # defensive: naive datetimes in hand-built objects
        delay = 0
    if delay > LATE_THRESHOLD_SECONDS:
        lines.append("⏱️ Disparado con retraso (el servicio estuvo parado o reiniciándose).")
    return "\n".join(lines)


def _chat_id_from_user_id(user_id: str) -> int | None:
    """Resolve the Telegram chat id from the AncoraMind user id.

    Private chats: the user id resolved by UserContext IS the Telegram chat
    id (see src/security/user_context.py). Returns None for anything else
    (future multi-channel user ids must not be silently messaged).
    """
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


class TelegramNotifier:
    """Deliver reminders via the Telegram Bot API sendMessage."""

    def __init__(self, token: str, client: httpx.AsyncClient | None = None):
        self._token = token
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def send_reminder(self, reminder: Reminder) -> bool:
        """Send the reminder message; True only on confirmed delivery."""
        chat_id = _chat_id_from_user_id(reminder.user_id)
        if chat_id is None:
            logger.error(
                "Cannot deliver reminder %s: user id %r is not a Telegram chat id",
                reminder.id,
                reminder.user_id,
            )
            return False

        payload = {
            "chat_id": chat_id,
            "text": format_reminder_message(reminder),
        }
        try:
            response = await self._client.post(
                f"{API_BASE_URL}/bot{self._token}/sendMessage",
                json=payload,
            )
        except httpx.HTTPError as exc:
            logger.error("Telegram delivery failed for reminder %s: %s", reminder.id, exc)
            return False

        if response.status_code != 200:
            logger.error(
                "Telegram API rejected reminder %s: HTTP %d %s",
                reminder.id,
                response.status_code,
                response.text[:200],
            )
            return False
        return True
