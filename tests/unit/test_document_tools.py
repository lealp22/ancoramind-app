"""Unit tests for document tool media injection from Agno/Telegram."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from agno.media import File, Image
from agno.run import RunContext

from src.agent.tools import documents as document_tools
from src.domain.documents.models import Document, DocumentWithExtraction


def _run_context() -> RunContext:
    return RunContext(
        run_id="run-document-test",
        session_id="tg:ancoramind:452022640:test",
        user_id="452022640",
    )


def _ingest_result(filename: str, mime_type: str, size: int):
    return DocumentWithExtraction(
        document=Document(
            id=uuid4(),
            user_id="452022640",
            storage_key=f"2026/09/{filename}",
            original_filename=filename,
            mime_type=mime_type,
            size_bytes=size,
            created_at=datetime.now(tz=UTC),
        ),
        extraction=None,
    )


async def test_analyze_document_receives_telegram_photo(monkeypatch):
    service = AsyncMock()
    service.ingest.side_effect = lambda user, content, filename, mime: (
        _ingest_result(filename, mime, len(content))
    )

    async def get_service():
        return service

    monkeypatch.setattr(document_tools, "_get_document_service", get_service)
    image = Image(content=b"\xff\xd8\xffJPEGDATA", id="telegram-photo")

    response = await document_tools.analyze_document(
        _run_context(),
        images=[image],
    )

    args = service.ingest.await_args.args
    assert args[0].user_id == "452022640"
    assert args[1] == b"\xff\xd8\xffJPEGDATA"
    assert args[2].startswith("telegram-media-telegram-photo")
    assert args[2].endswith((".jpg", ".jpeg", ".jpe"))
    assert args[3] == "image/jpeg"
    assert "recibido y archivado" in response


async def test_analyze_document_receives_telegram_file_and_sanitizes_name(
    monkeypatch,
):
    service = AsyncMock()
    service.ingest.side_effect = lambda user, content, filename, mime: (
        _ingest_result(filename, mime, len(content))
    )

    async def get_service():
        return service

    monkeypatch.setattr(document_tools, "_get_document_service", get_service)
    file = File(content=b"%PDF-1.4", filename="../../factura.pdf")

    await document_tools.analyze_document(_run_context(), files=[file])

    args = service.ingest.await_args.args
    assert args[1] == b"%PDF-1.4"
    assert args[2] == "factura.pdf"
    assert args[3] == "application/pdf"


async def test_analyze_document_without_media_does_not_create_service(monkeypatch):
    get_service = AsyncMock()
    monkeypatch.setattr(document_tools, "_get_document_service", get_service)

    response = await document_tools.analyze_document(_run_context())

    assert response == "No se recibió ningún archivo para analizar."
    get_service.assert_not_awaited()
