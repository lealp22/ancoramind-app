"""Unit tests for the Telegram notifier (BL-5, specs/010)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from src.domain.interactions.processor import TelegramSendError
from src.domain.reminders.models import Reminder
from src.notifications.telegram import (
    LATE_THRESHOLD_SECONDS,
    TelegramNotifier,
    format_reminder_message,
)


def _reminder(
    title: str = "ITV",
    description: str | None = "Pedir cita",
    minutes_ago: float = 1,
    user_id: str = "452022640",
) -> Reminder:
    return Reminder(
        id=uuid4(),
        user_id=user_id,
        title=title,
        description=description,
        trigger_at=datetime.now(tz=UTC) - timedelta(minutes=minutes_ago),
        status="pending",
        source_document_id=None,
        source_action_id=None,
        created_at=datetime.now(tz=UTC),
    )


class TestFormatReminderMessage:
    def test_displays_scheduled_time_in_resolved_user_timezone(self) -> None:
        """A canonical UTC trigger is shown in the same local time as confirmation."""
        reminder = _reminder()
        reminder.trigger_at = datetime(2026, 10, 4, 19, 59, tzinfo=UTC)

        text = format_reminder_message(reminder, now=datetime(2026, 10, 4, 19, 59, tzinfo=UTC))

        assert "Programado para: 04/10/2026 21:59" in text
        assert "Programado para: 04/10/2026 19:59" not in text

    def test_includes_title_description_and_scheduled_date(self) -> None:
        reminder = _reminder(title="Renovar seguro", description="Llamar a la correduría")
        text = format_reminder_message(reminder)
        assert "Renovar seguro" in text
        assert "Llamar a la correduría" in text
        assert "Programado para:" in text
        assert "retraso" not in text

    def test_omits_description_when_missing(self) -> None:
        text = format_reminder_message(_reminder(description=None))
        assert "Programado para:" in text
        assert text.count("\n") == 1  # only title + scheduled line

    def test_adds_late_note_when_fired_long_after_trigger(self) -> None:
        reminder = _reminder(minutes_ago=30)
        late_by = timedelta(seconds=LATE_THRESHOLD_SECONDS + 60)
        now = reminder.trigger_at + late_by
        text = format_reminder_message(reminder, now=now)
        assert "retraso" in text

    def test_no_late_note_within_threshold(self) -> None:
        reminder = _reminder(minutes_ago=1)
        now = reminder.trigger_at + timedelta(seconds=LATE_THRESHOLD_SECONDS - 1)
        text = format_reminder_message(reminder, now=now)
        assert "retraso" not in text


class TestTelegramNotifier:
    def _client(
        self,
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def test_send_reminder_success(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))
        delivered = await notifier.send_reminder(_reminder())

        assert delivered is True
        assert len(requests) == 1
        assert "/bot123456:ABC/sendMessage" in str(requests[0].url)
        body = requests[0].read()
        assert b'"chat_id":452022640' in body
        assert b"parse_mode" not in body  # plain text (untrusted DATA, §2.8)

    async def test_send_reminder_api_rejection(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"ok": False, "description": "Bad Request"})

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))
        assert await notifier.send_reminder(_reminder()) is False

    async def test_send_reminder_network_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down")

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))
        assert await notifier.send_reminder(_reminder()) is False

    async def test_send_reminder_rejects_non_numeric_user_id(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"ok": True})

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))
        delivered = await notifier.send_reminder(_reminder(user_id="some-uuid-user"))

        assert delivered is False
        assert requests == []  # no HTTP call for non-Telegram user ids

    async def test_send_text_returns_confirmed_message_id(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))

        assert await notifier.send_text(452022640, "respuesta final") == 77

    async def test_send_text_renders_markdown_as_html(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 78}})

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))

        assert await notifier.send_text(452022640, "**hola** y `x < y`") == 78

        body = requests[0].read().decode()
        assert '"parse_mode":"HTML"' in body
        assert "<b>hola</b>" in body
        assert "<code>x &lt; y</code>" in body

    async def test_send_text_falls_back_to_plain_text_when_rendering_exceeds_limit(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 79}})

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))
        chunk = "**a**" * 780  # 3900 raw characters; HTML rendering would exceed 4096

        assert await notifier.send_text(452022640, chunk) == 79

        body = requests[0].read().decode()
        assert "parse_mode" not in body
        assert chunk in body

    async def test_send_text_retries_once_as_plain_text_on_markup_rejection(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if b"parse_mode" in request.read():
                return httpx.Response(
                    400,
                    json={
                        "ok": False,
                        "description": (
                            "Bad Request: can't parse entities: "
                            'Unsupported start tag "foo" at byte offset 0'
                        ),
                    },
                )
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 80}})

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))

        assert await notifier.send_text(452022640, "**hola**") == 80

        assert len(requests) == 2
        assert "parse_mode" not in requests[1].read().decode()

    async def test_send_text_does_not_retry_unrelated_rejections(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                400,
                json={"ok": False, "description": "Bad Request: chat not found"},
            )

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))

        with pytest.raises(TelegramSendError) as exc_info:
            await notifier.send_text(452022640, "respuesta final")

        assert exc_info.value.definitive is True
        assert exc_info.value.description == "Bad Request: chat not found"
        assert len(requests) == 1

    async def test_send_text_classifies_4xx_as_definitive(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"ok": False, "description": "Bad Request"})

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))

        with pytest.raises(TelegramSendError) as exc_info:
            await notifier.send_text(452022640, "respuesta final")

        assert exc_info.value.definitive is True

    async def test_send_text_classifies_transport_failure_as_ambiguous(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down")

        notifier = TelegramNotifier(token="123456:ABC", client=self._client(handler))

        with pytest.raises(TelegramSendError) as exc_info:
            await notifier.send_text(452022640, "respuesta final")

        assert exc_info.value.definitive is False

    async def test_close_only_closes_notifier_owned_client(self) -> None:
        external_client = self._client(lambda _: httpx.Response(200, json={"ok": True}))
        external_notifier = TelegramNotifier(token="123456:ABC", client=external_client)

        await external_notifier.close()

        assert external_client.is_closed is False
        await external_client.aclose()
