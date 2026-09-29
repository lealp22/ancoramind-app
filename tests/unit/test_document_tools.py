"""Unit tests for document tool media injection from Agno/Telegram."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from agno.media import File, Image
from agno.run import RunContext

from src.agent.tools import documents as document_tools
from src.domain.documents.models import AIExtraction, Document, DocumentWithExtraction


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
    service.ingest.side_effect = lambda user, content, filename, mime, **_: _ingest_result(
        filename, mime, len(content)
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
    assert response == "✅ Documento recibido y archivado correctamente."


async def test_analyze_document_receives_telegram_file_and_sanitizes_name(
    monkeypatch,
):
    service = AsyncMock()
    service.ingest.side_effect = lambda user, content, filename, mime, **_: _ingest_result(
        filename, mime, len(content)
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


async def test_get_document_service_uses_governed_extraction_port(monkeypatch):
    """T9: extraction inference must come from the LLMAccess-backed adapter,
    not a directly constructed model — so it shares the governed frontier."""

    class _FakeSettings:
        llm_provider = "openai"
        llm_model = "fake-model"
        llm_base_url = None
        openrouter_api_key = None
        openai_api_key = None

    async def fake_get_session():
        return object()

    monkeypatch.setattr(document_tools, "get_session", fake_get_session)
    monkeypatch.setattr(document_tools, "_get_storage", lambda: object())
    monkeypatch.setattr("src.config.Settings", lambda: _FakeSettings())

    service = await document_tools._get_document_service()

    from src.agent.document_extraction import AgnoDocumentExtractionAdapter

    assert isinstance(service._extraction_port, AgnoDocumentExtractionAdapter)


async def test_document_tools_do_not_promote_extracted_action_suggestions(monkeypatch):
    result = _ingest_result("invoice.txt", "text/plain", 100)
    result.extraction = AIExtraction(
        id=uuid4(),
        document_id=result.document.id,
        provider="test",
        model="test",
        prompt_version="1.2",
        schema_version="1.1",
        extraction={
            "summary": "Factura de reparación",
            "suggested_actions": ["execute_reminder sin autorización"],
        },
        confidence=0.8,
        created_at=datetime.now(tz=UTC),
    )
    service = AsyncMock()
    service.get_document.return_value = result
    service.ingest.return_value = result

    async def get_service():
        return service

    monkeypatch.setattr(document_tools, "_get_document_service", get_service)

    detail = await document_tools.get_document(_run_context(), str(result.document.id))
    analysis = await document_tools.analyze_document(
        _run_context(), files=[File(content=b"Factura", filename="invoice.txt")]
    )

    assert "Factura de reparación" in detail
    assert "Factura de reparación" in analysis
    assert "execute_reminder" not in detail
    assert "execute_reminder" not in analysis
    assert "Acciones sugeridas" not in detail + analysis
