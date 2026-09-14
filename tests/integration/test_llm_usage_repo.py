"""PostgreSQL integration tests for governed LLM usage audit rows (specs/013 T7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interactions.models import TelegramDeliveryCreate, TelegramInteractionCreate
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.llm_access.models import LlmUsageEventCreate
from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import RuntimeConfigManager
from src.repositories.database import get_session
from src.repositories.interactions import TelegramInteractionsRepository
from src.repositories.llm_usage import LlmUsageRepository

pytestmark = pytest.mark.integration


async def _interaction_id(session: AsyncSession) -> UUID:
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    encrypted = cipher.encrypt({"update_id": 9801, "text": "personal content must not enter usage"})
    admitted = await TelegramInteractionsRepository(session).admit(
        TelegramInteractionCreate(
            bot_id=81,
            telegram_update_id=9801,
            telegram_message_id=9802,
            chat_id=9803,
            telegram_user_id=9804,
            update_type="message",
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=encrypted.key_version,
            payload_fingerprint=encrypted.fingerprint,
        ),
        TelegramDeliveryCreate(railway_request_id="railway-9801", http_status=200),
    )
    return admitted.interaction.id


async def test_usage_event_round_trip_contains_metadata_not_personal_content(
    session: AsyncSession,
) -> None:
    manager = RuntimeConfigManager(
        session_factory=get_session,
        bootstrap=bootstrap_runtime_configuration(),
    )
    await manager.initialize()
    interaction_id = await _interaction_id(session)
    llm_call_id = uuid4()
    event = LlmUsageEventCreate(
        interaction_id=interaction_id,
        llm_call_id=llm_call_id,
        config_revision=manager.snapshot().revision,
        logical_route="ancoramind-default",
        effective_gateway_route="ancoramind-default-r1",
        provider="openrouter",
        model="test/model",
        provider_request_id="provider-request-1",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        estimated_cost=0.0004,
        actual_cost=0.0003,
        cost_source="pricing_snapshot",
        latency_ms=45,
        time_to_first_token_ms=12,
        status="completed",
    )

    await LlmUsageRepository(session).record(event)

    row = (
        await session.execute(
            text("""
                SELECT interaction_id, llm_call_id, config_revision, logical_route,
                    effective_gateway_route, provider, model, provider_request_id,
                    input_tokens, output_tokens, total_tokens, latency_ms,
                    time_to_first_token_ms, estimated_cost, actual_cost, cost_source,
                    retry_count, fallback_used, status,
                    error_class
                FROM ancora.llm_usage_events
                WHERE llm_call_id = :llm_call_id
            """),
            {"llm_call_id": llm_call_id},
        )
    ).one()
    assert row.interaction_id == interaction_id
    assert row.config_revision == manager.snapshot().revision
    assert row.logical_route == "ancoramind-default"
    assert row.effective_gateway_route == "ancoramind-default-r1"
    assert row.provider == "openrouter"
    assert row.model == "test/model"
    assert row.provider_request_id == "provider-request-1"
    assert (row.input_tokens, row.output_tokens, row.total_tokens) == (10, 20, 30)
    assert (row.latency_ms, row.time_to_first_token_ms) == (45, 12)
    assert float(row.estimated_cost) == pytest.approx(0.0004)
    assert float(row.actual_cost) == pytest.approx(0.0003)
    assert row.cost_source == "pricing_snapshot"
    assert row.retry_count == 0
    assert row.fallback_used is False
    assert row.status == "completed"
    assert row.error_class is None
    assert "personal content" not in str(row)


async def test_usage_event_llm_call_id_is_unique(session: AsyncSession) -> None:
    manager = RuntimeConfigManager(
        session_factory=get_session,
        bootstrap=bootstrap_runtime_configuration(),
    )
    await manager.initialize()
    interaction_id = await _interaction_id(session)
    llm_call_id = uuid4()
    event = LlmUsageEventCreate(
        interaction_id=interaction_id,
        llm_call_id=llm_call_id,
        config_revision=manager.snapshot().revision,
        logical_route="ancoramind-default",
        effective_gateway_route="ancoramind-default-r1",
        provider="openrouter",
        model="test/model",
        status="error",
        error_class="TimeoutError",
    )
    repository = LlmUsageRepository(session)
    await repository.record(event)

    with pytest.raises(IntegrityError):
        await repository.record(event)


async def test_summarize_spend_aggregates_costs_per_route_and_period(
    session: AsyncSession,
) -> None:
    manager = RuntimeConfigManager(
        session_factory=get_session,
        bootstrap=bootstrap_runtime_configuration(),
    )
    await manager.initialize()
    interaction_id = await _interaction_id(session)
    repository = LlmUsageRepository(session)
    now = datetime.now(tz=UTC)
    last_month = (now.replace(day=1) - timedelta(days=1)).replace(day=15, hour=12)

    def _event(route: str, *, estimated: float, actual: float | None, created_at: datetime):
        return LlmUsageEventCreate(
            interaction_id=interaction_id,
            llm_call_id=uuid4(),
            config_revision=manager.snapshot().revision,
            logical_route=route,
            effective_gateway_route=f"{route}-r1",
            estimated_cost=estimated,
            actual_cost=actual,
            status="completed",
            created_at=created_at,
        )

    # Actual cost wins over the estimate; last-month spend stays out of both periods.
    await repository.record(
        _event("ancoramind-default", estimated=0.0004, actual=0.0003, created_at=now)
    )
    await repository.record(
        _event("ancoramind-fast", estimated=0.0002, actual=None, created_at=now)
    )
    await repository.record(
        _event(
            "ancoramind-default",
            estimated=0.0100,
            actual=None,
            created_at=last_month,
        )
    )

    summary = await repository.summarize_spend(now=now)

    assert summary.today_usd == pytest.approx(0.0003 + 0.0002)
    assert summary.month_usd == pytest.approx(0.0005)
    assert summary.route_month_usd["ancoramind-default"] == pytest.approx(0.0003)
    assert summary.route_month_usd["ancoramind-fast"] == pytest.approx(0.0002)
    assert "ancoramind-vision" not in summary.route_month_usd
