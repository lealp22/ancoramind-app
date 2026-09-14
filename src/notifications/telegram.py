"""Telegram notifier — outbound reminder delivery via Bot API (BL-5).

Direct httpx calls to the Telegram Bot API: no Agno internals (ADR-001) and
no inbound webhook needed — sendMessage is outbound-only, so reminders work
even while the webhook channel is unavailable (see ADR-003 / BL-18).
"""

import logging
from datetime import UTC, datetime

import httpx

from src.domain.interactions.processor import TelegramSendError
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
        self._owns_client = client is None

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
            logger.error(
                "Telegram reminder delivery failed (reminder_id=%s, error_class=%s)",
                reminder.id,
                type(exc).__name__,
            )
            return False

        if response.status_code != 200:
            logger.error(
                "Telegram API rejected reminder (reminder_id=%s, http_status=%d)",
                reminder.id,
                response.status_code,
            )
            return False
        return True

    async def send_text(self, chat_id: int, text: str) -> int:
        """Send one persisted response chunk and return Telegram's message ID.

        The T5 processor records ``sending`` before this non-idempotent request.
        Transport uncertainty is marked ambiguous so the caller never resends a
        message that Telegram may already have accepted.
        """
        try:
            response = await self._client.post(
                f"{API_BASE_URL}/bot{self._token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
        except httpx.HTTPError as exc:
            raise TelegramSendError(
                "Telegram sendMessage transport failure",
                definitive=False,
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200 or not body.get("ok"):
            raise TelegramSendError(
                f"Telegram sendMessage rejected with HTTP {response.status_code}",
                definitive=400 <= response.status_code < 500,
            )
        result = body.get("result")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if not isinstance(message_id, int):
            raise TelegramSendError(
                "Telegram sendMessage response lacks message_id",
                definitive=False,
            )
        return message_id

    async def send_typing(self, chat_id: int) -> None:
        """Refresh Telegram's typing indicator without sending user content."""
        try:
            await self._client.post(
                f"{API_BASE_URL}/bot{self._token}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
            )
        except httpx.HTTPError:
            logger.debug("Telegram typing indicator request failed", exc_info=True)

    async def close(self) -> None:
        """Close the internally-owned HTTP client during application shutdown."""
        if self._owns_client:
            await self._client.aclose()
