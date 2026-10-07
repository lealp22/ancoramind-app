"""Explicit opt-in live inference; isolated PostgreSQL, no Telegram or Agent."""

import os
import time
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from scripts.stt_smoke_config import smoke_inputs, validate_external_key
from src.agent.speech_access import GovernedSpeechAccess
from src.agent.voice_inspector import FFmpegVoiceInspector
from src.config import Settings
from src.domain.interactions.media import TelegramAttachment
from src.domain.llm_access.cost_governance import evaluate_cost_governance
from src.domain.llm_access.models import ExecutionBudget, ExecutionContext
from src.domain.runtime_config.models import RuntimeConfigSnapshot, config_checksum
from src.repositories.llm_usage import LlmUsageRepository
from src.repositories.runtime_config import RuntimeConfigRepository
from tests.integration.test_voice_processor import setup

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("ANCORA_STT_SMOKE_APPROVED") != "1",
        reason="live inference requires explicit approval; disabled by default",
    ),
]


async def test_live_governed_stt(session):
    audio_path, gateway, config = smoke_inputs(os.environ)
    key = os.environ.get("ANCORA_STT_SMOKE_VIRTUAL_KEY")
    if not key:
        pytest.fail("stt_smoke_virtual_key_required", pytrace=False)
    uncertain = os.environ.get("ANCORA_STT_SMOKE_BILLING_UNCERTAINTY_ACCEPTED") == "1"
    if uncertain:
        upstream = Settings().openrouter_api_key
        if not upstream:
            pytest.fail("stt_smoke_upstream_key_missing", pytrace=False)
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": "Bearer " + upstream},
            )
        if response.status_code != 200:
            pytest.fail("stt_smoke_external_limit_unverified", pytrace=False)
        validate_external_key(
            response.json().get("data", {}),
            Decimal(str(config.cost_governance.external_hard_limit_usd)),
        )
    # setup creates only encrypted synthetic admission in the isolated test DB.
    factory, service, _, _, interaction, _ = await setup(session)
    evaluate_cost_governance(
        config,
        await LlmUsageRepository(session).summarize_spend(),
    )
    revision = await RuntimeConfigRepository(session).create_revision(
        config,
        checksum=config_checksum(config),
        created_by="stt-smoke",
        reason="isolated synthetic STT smoke; not activated",
    )
    context = ExecutionContext(
        correlation_id=interaction.id,
        telegram_update_id=2,
        agno_run_id=str(uuid4()),
        agno_session_id="isolated-stt-smoke",
        config=RuntimeConfigSnapshot(
            revision=revision.revision,
            checksum=revision.checksum,
            source="database",
            config=config,
        ),
        budget=ExecutionBudget.from_config(
            config.execution_budget,
            started_at_monotonic=time.monotonic(),
        ),
    )
    content = audio_path.read_bytes()
    service._inspector = FFmpegVoiceInspector()
    if uncertain:
        inspected = await service._inspector.inspect(content)
        if inspected.duration_seconds > 15:
            pytest.fail("stt_smoke_short_audio_required", pytrace=False)
    service._stt = GovernedSpeechAccess(
        Settings(
            _env_file=None,
            litellm_proxy_enabled=True,
            litellm_proxy_base_url=gateway,
            litellm_proxy_virtual_key=key,
        ),
        factory,
    )

    async def download(_):
        return content

    service._download = download
    try:
        async with service.exclusive(interaction.id) as acquired:
            assert acquired
            transcript = await service.prepare(
                interaction,
                TelegramAttachment(kind="voice", file_id="synthetic"),
                context=context,
            )
            # Never print/assert the transcript value: failures must be metadata-only.
            assert bool(transcript and transcript.strip()), "stt_smoke_empty_result"
            transcript = None
        rows = (
            await session.execute(
                text(
                    "SELECT status, estimated_cost, actual_cost FROM ancora.llm_usage_events "
                    "WHERE interaction_id = :id"
                ),
                {"id": interaction.id},
            )
        ).fetchall()
        assert len(rows) == 1
        assert rows[0].status == "completed"
        assert context.budget.model_calls == 1
    finally:
        await session.execute(
            text(
                "UPDATE ancora.telegram_interactions SET status = 'failed_controlled' "
                "WHERE id = :id"
            ),
            {"id": interaction.id},
        )
        await session.commit()  # terminal trigger clears preparation ciphertext
