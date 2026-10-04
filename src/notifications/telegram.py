"""Telegram notifier — outbound reminder delivery via Bot API (BL-5).

Direct httpx calls to the Telegram Bot API: no Agno internals (ADR-001) and
no inbound webhook needed — sendMessage is outbound-only, so reminders work
even while the webhook channel is unavailable (see ADR-003 / BL-18).
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx

from src.domain.actions.presentation import ConsentButton
from src.domain.interactions.processor import TelegramSendError
from src.domain.preferences.timezone import resolve_user_timezone, to_local_display
from src.domain.reminders.models import Reminder
from src.notifications.markup import MAX_MESSAGE_CHARS, markdown_to_telegram_html
from src.security.user_context import UserContext

logger = logging.getLogger(__name__)

LATE_THRESHOLD_SECONDS = 300
"""Retries/downtime longer than this add a "fired late" note to the message."""

API_BASE_URL = "https://api.telegram.org"

_MARKUP_REJECTION_MARKERS = (
    "can't parse entities",
    "unsupported start tag",
    "can't find end tag",
    "unsupported utf-8",
)
"""Telegram descriptions that mean our markup (not the message) was rejected."""


def _is_markup_rejection(error: TelegramSendError) -> bool:
    """True when Telegram answered 4xx because of the declared parse mode."""
    if error.description is None:
        return False
    description = error.description.lower()
    return any(marker in description for marker in _MARKUP_REJECTION_MARKERS)


def format_reminder_message(reminder: Reminder, now: datetime | None = None) -> str:
    """Render the outbound reminder text.

    Plain text on purpose: no parse_mode, since title/description are
    untrusted DATA (AGENTS.md §2.8) that could break Markdown rendering. The
    persisted trigger is canonical UTC, but users must see their resolved local
    time, matching proposal, confirmation, and list displays.
    """
    now = now or datetime.now(tz=UTC)
    lines = [f"⏰ Recordatorio: {reminder.title}"]
    if reminder.description:
        lines.append(reminder.description)
    user_context = UserContext(user_id=reminder.user_id)
    trigger = to_local_display(
        reminder.trigger_at,
        resolve_user_timezone(user_context),
    ).strftime("%d/%m/%Y %H:%M")
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

    async def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        button_rows: Sequence[tuple[ConsentButton, ConsentButton]] | None = None,
    ) -> int:
        """Send one persisted response chunk and return Telegram's message ID.

        Model Markdown is rendered as Telegram HTML (BL-29). Formatting never
        risks the message itself: rendering falls back to plain text when it
        would exceed Telegram's limit, and a markup rejection by the API is
        retried once as plain text before the chunk is reported as failed.
        ``button_rows`` renders one inline-keyboard row per proposal
        (specs/023 T4.3-T4.4); on a plain-text retry they stay attached, since
        Telegram accepts ``reply_markup`` independently of ``parse_mode``.

        The T5 processor records ``sending`` before this non-idempotent request.
        Transport uncertainty is marked ambiguous so the caller never resends a
        message that Telegram may already have accepted.
        """
        rendered = markdown_to_telegram_html(text)
        if len(rendered) <= MAX_MESSAGE_CHARS:
            try:
                return await self._send_message(
                    chat_id, rendered, parse_mode="HTML", button_rows=button_rows
                )
            except TelegramSendError as exc:
                if not exc.definitive or not _is_markup_rejection(exc):
                    raise
                logger.warning(
                    "Telegram rejected rendered markup (telegram.description=%s); "
                    "resending the chunk as plain text",
                    exc.description,
                )
        return await self._send_message(
            chat_id, text, parse_mode=None, button_rows=button_rows
        )

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None,
        button_rows: Sequence[tuple[ConsentButton, ConsentButton]] | None = None,
    ) -> int:
        """Issue one sendMessage call, classifying failures by retry safety."""
        payload: dict[str, object] = {"chat_id": chat_id, "text": text}
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        if button_rows:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {"text": yes.label, "callback_data": yes.callback_data},
                        {"text": no.label, "callback_data": no.callback_data},
                    ]
                    for yes, no in button_rows
                ]
            }
        try:
            response = await self._client.post(
                f"{API_BASE_URL}/bot{self._token}/sendMessage",
                json=payload,
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
            description = body.get("description")
            raise TelegramSendError(
                f"Telegram sendMessage rejected with HTTP {response.status_code}",
                definitive=400 <= response.status_code < 500,
                description=description if isinstance(description, str) else None,
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
