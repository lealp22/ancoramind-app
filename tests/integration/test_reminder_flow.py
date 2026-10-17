"""BL-1/M5: real tool, consent, executor and worker on isolated PostgreSQL.

Only model selection and Telegram transport are simulated. These tests do not
certify live Telegram delivery, model semantics or exactly-once outbound sends.
"""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
from agno.run import RunContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.tools.reminders import propose_reminder
from src.domain.interactions.processor import InteractionProcessor
from src.domain.interactions.reply import AgentReply
from src.domain.llm_access.context import execution_context_scope
from src.domain.reminders.worker import RemindersWorker
from src.notifications.telegram import TelegramNotifier
from src.repositories.database import get_session
from src.repositories.reminders import RemindersRepository
from tests.integration.test_interaction_processor import (
    FakeSender,
    _accepted_callback,
    _accepted_interaction,
    _cipher,
    _fake_context,
)

pytestmark = pytest.mark.integration


class ReminderToolRunner:
    """Replace only the model's choice, invoking the actual proposed capability."""

    def __init__(self, trigger_at: str) -> None:
        self.trigger_at = trigger_at
        self.calls = 0

    async def run(self, input_text: str, **kwargs: object) -> AgentReply:
        self.calls += 1
        with execution_context_scope(_fake_context(kwargs["provenance"])):
            reply = await propose_reminder(
                RunContext(run_id="synthetic-run", user_id="88", session_id="tg:ancoramind:77"),
                title="Recordatorio sintético",
                trigger_at=self.trigger_at,
            )
        return AgentReply(answer="", proposal_text=reply)


@pytest.mark.parametrize(
    ("confirm", "first_status"), [(True, 200), (True, 503), (False, 200)]
)
async def test_reminder_proposal_consent_and_worker_delivery(
    session: AsyncSession, monkeypatch, confirm: bool, first_status: int
) -> None:
    monkeypatch.setenv("USER_TIMEZONE", "Europe/Madrid")
    local = (datetime.now(tz=UTC) - timedelta(minutes=2)).astimezone(ZoneInfo("Europe/Madrid"))
    local = local.replace(tzinfo=None, microsecond=0)
    runner = ReminderToolRunner(local.isoformat())
    cipher = _cipher()
    await _accepted_interaction(session, cipher, update_id=910)
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )
    requests: list[dict[str, object]] = []

    def telegram(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/botsynthetic-token/sendMessage"
        requests.append(json.loads(request.content))
        status = first_status if len(requests) == 1 else 200
        return httpx.Response(status, json={"ok": status == 200, "result": {"message_id": 900}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as client:
        worker = RemindersWorker(get_session, TelegramNotifier("synthetic-token", client=client))
        assert await processor.run_once() == 1
        (proposal_id,) = (
            await session.execute(
                text("SELECT id FROM ancora.action_proposals WHERE user_id=:uid"), {"uid": "88"}
            )
        ).one()
        assert isinstance(proposal_id, UUID)
        assert await RemindersRepository(session).list_by_user("88") == []
        assert await worker.run_once() == 0
        assert requests == []
        yes, no = sender.button_rows[-1][0]
        button = yes if confirm else no
        await _accepted_callback(session, cipher, 911, callback_data=button.callback_data)
        assert await processor.run_once() == 1
        reminders = await RemindersRepository(session).list_by_user("88")
        if confirm:
            (reminder,) = reminders
            assert reminder.source_action_id == proposal_id
            expected_utc = local.replace(tzinfo=ZoneInfo("Europe/Madrid")).astimezone(UTC)
            assert reminder.trigger_at == expected_utc
            assert reminder.status == "pending"
            assert await worker.run_once() == (1 if first_status == 200 else 0)
            if first_status != 200:
                (pending,) = await RemindersRepository(session).list_by_user("88")
                assert pending.status == "pending" and pending.fired_at is None
                assert await worker.run_once() == 1
            (fired,) = await RemindersRepository(session).list_by_user("88")
            assert fired.status == "fired" and fired.fired_at is not None
            assert all(item["chat_id"] == 88 for item in requests)
            assert all(local.strftime("%d/%m/%Y %H:%M") in item["text"] for item in requests)
            assert all("parse_mode" not in item for item in requests)
        else:
            assert reminders == []
        count = len(requests)
        assert await worker.run_once() == 0
        # A second button press is a new update, not new consent for an old action.
        await _accepted_callback(session, cipher, 912, callback_data=button.callback_data)
        assert await processor.run_once() == 1
        assert await worker.run_once() == 0
        assert len(requests) == count
        assert len(await RemindersRepository(session).list_by_user("88")) == int(confirm)
        assert runner.calls == 1
        assert await session.scalar(
            text("SELECT status FROM ancora.action_proposals WHERE id=:id AND user_id=:uid"),
            {"id": proposal_id, "uid": "88"},
        ) == ("executed" if confirm else "discarded")
