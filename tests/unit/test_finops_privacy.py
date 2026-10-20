"""Privacy contract for the FinOps panel (specs/043 T5).

The repository must never read content-bearing columns and the assembled
reports must never carry Telegram, chat or session identifiers.
"""

from __future__ import annotations

import ast
import inspect
import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from src.domain.finops.models import (
    CostTotals,
    LatencyStats,
    ProposalOutcome,
    UserCost,
)
from src.domain.finops.service import FinopsService
from src.repositories import finops as finops_repo

FORBIDDEN_COLUMNS = (
    "payload_ciphertext",
    "payload_fingerprint",
    "payload_hash",
    "arguments_fingerprint",
    "idempotency_key",
    "failure_reason",
    "agno_session_id",
    "agno_run_id",
    "chat_id",
    "storage_key",
    "content",
)
# ``payload`` as a whole word (``payload_*`` columns are listed above).
_PAYLOAD_WORD = re.compile(r"\bpayload\b", re.IGNORECASE)


def _sql_literals() -> str:
    """Only string constants other than docstrings: the SQL fragments."""
    tree = ast.parse(inspect.getsource(finops_repo))
    docstrings = {
        id(n.body[0].value)
        for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and n.body
        and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
    }
    parts = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
    ]
    return "\n".join(parts)


def test_repository_sql_never_references_content_bearing_columns() -> None:
    source = _sql_literals()
    for column in FORBIDDEN_COLUMNS:
        assert column not in source, column
    assert not _PAYLOAD_WORD.search(source)


def test_repository_only_reads_the_three_approved_tables() -> None:
    tables = set(re.findall(r"ancora\.(\w+)", _sql_literals()))
    assert tables == {"llm_usage_events", "telegram_interactions", "action_proposals"}


def test_repository_is_read_only() -> None:
    source = _sql_literals().upper()
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE", "ALTER ", "DROP "):
        assert verb not in source, verb


def _reader() -> AsyncMock:
    reader = AsyncMock()
    reader.totals.return_value = CostTotals(cost_usd=1.0, calls=1)
    reader.daily.return_value = []
    reader.by_user.return_value = [
        ("918273645", UserCost(user="", cost_usd=1.0, total_tokens=1, calls=1, interactions=1))
    ]
    reader.by_route_model.return_value = []
    reader.by_cost_source.return_value = []
    reader.interactions_by_status.return_value = []
    reader.tool_calls_total.return_value = 0
    reader.proposals.return_value = [
        ProposalOutcome(tool_name="create_note", status="executed", consent_mode="x", count=1)
    ]
    reader.latency.return_value = LatencyStats()
    return reader


async def test_reports_do_not_expose_telegram_or_session_identifiers() -> None:
    service = FinopsService(_reader(), pseudonym_key="k")
    since = datetime(2026, 10, 1, tzinfo=UTC)
    serialized = (await service.finops_report(since, 30)).model_dump_json() + (
        await service.quality_report(since, 30)
    ).model_dump_json()
    assert "918273645" not in serialized
    for field in ("telegram_user_id", "chat_id", "agno_session_id", "agno_run_id"):
        assert field not in serialized
