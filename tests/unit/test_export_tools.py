"""Unit tests for export_document (BL-38 Fase 3) — mocked render/notifier,
same style as test_dream_tools.py. No PostgreSQL, no real Telegram call."""

from __future__ import annotations

from unittest.mock import AsyncMock

from agno.run import RunContext

from src.agent.document_export import DocumentExportError
from src.agent.tools import export as export_tools
from src.domain.interactions.processor import TelegramSendError


def _context(*, no_session_state: bool = False) -> RunContext:
    return RunContext(
        run_id="export-test",
        session_id="tg:test:1",
        user_id="452022640",
        session_state=None if no_session_state else {},
    )


async def test_export_document_renders_and_sends(monkeypatch):
    monkeypatch.setattr(export_tools, "render_markdown_to_pdf", lambda *a, **k: b"%PDF-fake")
    notifier = AsyncMock()
    notifier.send_document.return_value = 42
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)

    response = await export_tools.export_document(_context(), "# Hola", title="Mi lista")

    notifier.send_document.assert_awaited_once_with(452022640, b"%PDF-fake", "Mi_lista.pdf")
    notifier.close.assert_awaited_once()
    assert "enviado" in response.lower()
    assert "Mi_lista.pdf" in response


async def test_export_document_without_title_uses_a_default_filename(monkeypatch):
    monkeypatch.setattr(export_tools, "render_markdown_to_pdf", lambda *a, **k: b"%PDF-fake")
    notifier = AsyncMock()
    notifier.send_document.return_value = 1
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)

    await export_tools.export_document(_context(), "contenido")

    notifier.send_document.assert_awaited_once_with(452022640, b"%PDF-fake", "documento.pdf")


async def test_export_document_sanitizes_title_into_filename(monkeypatch):
    monkeypatch.setattr(export_tools, "render_markdown_to_pdf", lambda *a, **k: b"%PDF-fake")
    notifier = AsyncMock()
    notifier.send_document.return_value = 1
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)

    await export_tools.export_document(_context(), "x", title="../etc/passwd; rm -rf")

    filename = notifier.send_document.await_args.args[2]
    assert filename.endswith(".pdf")
    assert "/" not in filename
    assert ".." not in filename
    assert ";" not in filename


async def test_export_document_rejects_empty_markdown_without_calling_telegram(monkeypatch):
    def fake_render(*args, **kwargs):
        raise DocumentExportError("export_empty_output")

    monkeypatch.setattr(export_tools, "render_markdown_to_pdf", fake_render)
    notifier = AsyncMock()
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)

    response = await export_tools.export_document(_context(), "   ")

    notifier.send_document.assert_not_awaited()
    assert "No hay contenido" in response


async def test_export_document_reports_render_failure(monkeypatch):
    def fake_render(*args, **kwargs):
        raise DocumentExportError("export_render_failed")

    monkeypatch.setattr(export_tools, "render_markdown_to_pdf", fake_render)
    notifier = AsyncMock()
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)

    response = await export_tools.export_document(_context(), "contenido")

    notifier.send_document.assert_not_awaited()
    assert "No pude generar el PDF" in response


async def test_export_document_reports_telegram_send_failure_without_provider_detail(
    monkeypatch,
):
    monkeypatch.setattr(export_tools, "render_markdown_to_pdf", lambda *a, **k: b"%PDF-fake")
    notifier = AsyncMock()
    notifier.send_document.side_effect = TelegramSendError(
        "boom", definitive=True, description="PERSONAL PROVIDER DETAIL"
    )
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)

    response = await export_tools.export_document(_context(), "contenido")

    notifier.close.assert_awaited_once()
    assert "PERSONAL PROVIDER DETAIL" not in response
    assert "no pude enviarlo" in response.lower()


async def test_export_document_outside_private_chat_is_rejected(monkeypatch):
    notifier = AsyncMock()
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)
    context = RunContext(run_id="r", session_id="s", user_id="not-a-chat-id")

    response = await export_tools.export_document(context, "contenido")

    notifier.send_document.assert_not_awaited()
    assert "chat privado" in response.lower()


async def test_export_document_deduplicates_identical_calls_within_the_same_run(monkeypatch):
    """BL-38 follow-up: a tool call repeated within one agent.arun() never resends."""
    monkeypatch.setattr(export_tools, "render_markdown_to_pdf", lambda *a, **k: b"%PDF-fake")
    notifier = AsyncMock()
    notifier.send_document.return_value = 1
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)
    context = _context()

    first = await export_tools.export_document(context, "# Hola", title="Mi lista")
    second = await export_tools.export_document(context, "# Hola", title="Mi lista")

    notifier.send_document.assert_awaited_once()
    assert first == second


async def test_export_document_does_not_deduplicate_distinct_content(monkeypatch):
    monkeypatch.setattr(export_tools, "render_markdown_to_pdf", lambda *a, **k: b"%PDF-fake")
    notifier = AsyncMock()
    notifier.send_document.return_value = 1
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)
    context = _context()

    await export_tools.export_document(context, "# Hola", title="Primero")
    await export_tools.export_document(context, "# Adiós", title="Segundo")

    assert notifier.send_document.await_count == 2


async def test_export_document_without_session_state_never_deduplicates(monkeypatch):
    """A RunContext built without session_state degrades to today's behaviour (always sends)."""
    monkeypatch.setattr(export_tools, "render_markdown_to_pdf", lambda *a, **k: b"%PDF-fake")
    notifier = AsyncMock()
    notifier.send_document.return_value = 1
    monkeypatch.setattr(export_tools, "TelegramNotifier", lambda token: notifier)
    context = _context(no_session_state=True)

    await export_tools.export_document(context, "# Hola", title="Mi lista")
    await export_tools.export_document(context, "# Hola", title="Mi lista")

    assert notifier.send_document.await_count == 2
