"""Unit tests for the governed document-embedding adapter (specs/026/BL-44)."""

from __future__ import annotations

from src.agent.document_embeddings import GovernedDocumentEmbeddingAdapter
from src.agent.emergency_stop_runtime import get_emergency_stop_manager
from src.config import Settings


async def test_embed_fails_closed_when_emergency_stop_is_active() -> None:
    """BL-44/specs/031: the embedding path must respect the manual stop too."""
    manager = get_emergency_stop_manager()
    manager.activate(actor="jesus", reason="cost spike")
    try:
        adapter = GovernedDocumentEmbeddingAdapter(Settings())

        outcome = await adapter.embed("texto cualquiera")

        assert outcome.embedding is None
        assert outcome.status == "failed"
        assert outcome.error_class == "EmergencyStopActive"
    finally:
        manager.deactivate(actor="jesus", reason="test cleanup")
