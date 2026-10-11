"""Simulated, I/O-free tool catalog for the isolated BL-8 physical eval executor.

These functions mirror the production tools referenced by ``evals/*/cases.json``
by name and docstring, so a real governed Agent's tool-selection behavior is
representative of production. They never import ``src.repositories``,
``src.storage``, or any production tool module (specs/018 T1 isolation): all
state is in-memory, scoped to one :class:`SyntheticProposalStore` instance per
eval case run, and seeded only from the eval case's own trusted fixture data
(``EvalCase.synthetic_context``) by :mod:`src.agent.eval_physical_executor`
— never from anything a simulated model produces at runtime.

Reusing ``src.agent.tools.untrusted_results`` here is deliberate: it is a
pure, stateless text-shaping helper (bounding/truncation/explicit
``"untrusted_data"`` labeling), not a production tool with I/O, so reusing it
keeps the simulated read tools faithful to the real security boundary the
``security`` eval category exercises — a case is only a meaningful test if
the simulated tool actually embeds the adversarial fixture text in its reply,
the same way the real tool would surface attacker-controlled content.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from agno.run import RunContext

from src.agent.tool_catalog import proposal_only_tools
from src.agent.tools.untrusted_results import (
    MAX_SUMMARY_CHARS,
    bounded_text,
    render_retrieved_records,
)


@dataclass
class SyntheticProposalStore:
    """In-memory pending-proposal state for exactly one isolated eval run.

    Represents pending proposals only; model calls cannot confirm them.
    Entries are seeded by the executor from the eval
    case's own trusted fixture (never from simulated-model output) or created
    by a simulated ``propose_*`` tool call during the run. Never shared
    across cases.
    """

    _pending: dict[str, str] = field(default_factory=dict)
    _counter: int = 0

    def seed(self, proposal_id: str, kind: str) -> None:
        """Register a proposal as already pending, from trusted fixture data."""
        self._pending[proposal_id] = kind

    def create(self, kind: str) -> str:
        """Simulate a ``propose_*`` tool call: create a new pending entry."""
        self._counter += 1
        proposal_id = f"eval-proposal-{kind}-{self._counter}"
        self._pending[proposal_id] = kind
        return proposal_id

    def confirm(self, proposal_id: str) -> bool:
        """Retired legacy confirmation; a model-owned call grants no authority."""
        return False


def _fixture_text(fixtures: Mapping[str, object], *keys: str, default: str) -> str:
    for key in keys:
        value = fixtures.get(key)
        if isinstance(value, str) and value:
            return value
    return default


def _fixture_int(fixtures: Mapping[str, object], key: str, default: int) -> int:
    value = fixtures.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def build_eval_tools(
    store: SyntheticProposalStore,
    context_fixtures: Mapping[str, object] | None = None,
) -> list[Any]:
    """Return one fresh simulated tool catalog bound to ``store``/``context_fixtures``.

    ``context_fixtures`` is the eval case's ``synthetic_context``: it supplies
    the untrusted content a real tool would have retrieved (e.g. a note or
    document excerpt), so the simulated read tools can embed it in their
    reply through the same untrusted-data envelope the production tools use.
    Fixture keys that only inform a human-judged ``response_criteria`` (not
    graded by this deterministic harness — see
    :mod:`src.agent.eval_physical_executor`) are intentionally not simulated.
    """
    fixtures: Mapping[str, object] = context_fixtures or {}

    async def search_notes(run_context: RunContext, query: str | None = None) -> str:
        """Search personal notes previously stored by the user."""
        text, truncated = bounded_text(
            _fixture_text(
                fixtures, "untrusted_note", default="Nota de prueba sin contenido adversarial."
            ),
            MAX_SUMMARY_CHARS,
        )
        record = {
            "source": "note",
            "id": "eval-note-1",
            "content": text,
            "content_truncated": truncated,
        }
        return render_retrieved_records("search_notes", [record], 1)

    async def propose_note(run_context: RunContext, content: str) -> str:
        """PROPOSE storing a personal note — requires user confirmation."""
        proposal_id = store.create("note")
        return f"Propuesta de nota creada (`{proposal_id}`). ¿Confirmas?"

    async def search_documents(run_context: RunContext, query: str | None = None) -> str:
        """Search personal documents by filename."""
        text, truncated = bounded_text(
            _fixture_text(fixtures, "untrusted_filename", default="factura_sintetica.pdf"),
            MAX_SUMMARY_CHARS,
        )
        record = {
            "source": "canonical_document",
            "id": "eval-document-1",
            "filename": text,
            "filename_truncated": truncated,
        }
        return render_retrieved_records("search_documents", [record], 1)

    async def get_document(run_context: RunContext, document_id: str) -> str:
        """Get details about a specific document and its AI extraction."""
        text, truncated = bounded_text(
            _fixture_text(
                fixtures,
                "untrusted_document_summary",
                "untrusted_document_excerpt",
                default="Factura sintética sin contenido adversarial.",
            ),
            MAX_SUMMARY_CHARS,
        )
        record: dict[str, object] = {
            "source": "canonical_document",
            "id": "eval-document-1",
            "extraction": {
                "source": "ai_extraction_unverified",
                "summary": text,
                "summary_truncated": truncated,
            },
        }
        return render_retrieved_records("get_document", [record], 1)

    async def analyze_document(
        run_context: RunContext,
        images: Any = None,
        files: Any = None,
    ) -> str:
        """Process a newly received attachment through the document pipeline."""
        return "✅ Documento recibido y archivado correctamente."

    async def find_vehicle(run_context: RunContext, reference: str | None = None) -> str:
        """Find a vehicle by make, model, nickname, or registration."""
        match_count = _fixture_int(fixtures, "vehicle_matches", 1)
        if match_count <= 1:
            vehicle_id = _fixture_text(fixtures, "resolved_vehicle", default="eval-vehicle-1")
            return f"🚗 **Ford Mondeo** (`{vehicle_id}`)"
        lines = [f"🚗 **Vehículo {i}** (`eval-vehicle-{i}`)" for i in range(1, match_count + 1)]
        return "Varios vehículos coinciden:\n" + "\n".join(lines)

    async def propose_vehicle(
        run_context: RunContext,
        make: str,
        model: str,
        year: int | None = None,
        registration: str | None = None,
        nickname: str | None = None,
    ) -> str:
        """PROPOSE registering a new vehicle — requires user confirmation."""
        proposal_id = store.create("vehicle")
        return f"Propuesta de registro de vehículo creada (`{proposal_id}`). ¿Confirmas?"

    async def propose_vehicle_maintenance(
        run_context: RunContext,
        vehicle_id: str,
        date_str: str,
        description: str,
    ) -> str:
        """PROPOSE a vehicle maintenance record — requires user confirmation."""
        proposal_id = store.create("vehicle_maintenance")
        return f"Propuesta de mantenimiento creada (`{proposal_id}`). ¿Confirmas?"

    async def propose_reminder(run_context: RunContext, title: str, trigger_at: str) -> str:
        """PROPOSE a reminder — requires user confirmation."""
        proposal_id = store.create("reminder")
        return f"Propuesta de recordatorio creada (`{proposal_id}`). ¿Confirmas?"

    async def propose_calendar_event(run_context: RunContext, title: str, start_at: str) -> str:
        """PROPOSE a calendar event — requires user confirmation (EXTERNAL_ACTION)."""
        proposal_id = store.create("calendar_event")
        return f"Propuesta de evento creada (`{proposal_id}`). ¿Confirmas?"

    return proposal_only_tools(
        [
            search_notes,
            propose_note,
            search_documents,
            get_document,
            analyze_document,
            find_vehicle,
            propose_vehicle,
            propose_vehicle_maintenance,
            propose_reminder,
            propose_calendar_event,
        ]
    )


__all__ = ["SyntheticProposalStore", "build_eval_tools"]
