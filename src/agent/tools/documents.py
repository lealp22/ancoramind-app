"""Document tools — thin Agno tool adapters for DocumentService.

Plain Python functions with run_context injection by Agno.
"""

import mimetypes
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from agno.media import File, Image
from agno.run import RunContext

from src.agent.document_vision import (
    DocumentVisionPreparationError,
    extract_pdf_text_markdown,
    has_extractable_text,
    prepare_visual_pages,
)
from src.agent.tools.sessions import closes_sessions, track_session
from src.agent.tools.untrusted_results import (
    MAX_FILENAME_CHARS,
    MAX_RESULT_RECORDS,
    MAX_SUMMARY_CHARS,
    bounded_text,
    render_retrieved_records,
)
from src.agent.tools.validation import internal_error_reply, invalid_proposal_reply, parse_uuid
from src.domain.documents.extraction import DocumentVisualPage
from src.domain.documents.service import DocumentService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.documents import DocumentsRepository
from src.security.user_context import UserContext
from src.storage.base import DocumentStorage


def _get_storage() -> DocumentStorage:
    """Build the configured storage backend (ADR-002)."""
    from src.config import Settings
    from src.storage.factory import create_storage

    return create_storage(Settings())


async def _get_document_service() -> DocumentService:
    """Create a DocumentService with fresh DB session.

    Extraction inference goes through the T9 ``AgnoDocumentExtractionAdapter``
    backed by LLMAccess: inside a governed run it shares that run's snapshot,
    budget, cost and trace (usage audited under the interaction); on the
    transitional AgentOS path it runs on a standalone bootstrap-scoped governed
    context without usage rows (no interaction exists to reference).
    """
    from src.agent.document_extraction import AgnoDocumentExtractionAdapter
    from src.agent.llm_access import AgnoLLMAccess, LlmUsageRecorder
    from src.config import Settings

    settings = Settings()
    session = track_session(await get_session())
    llm_access = AgnoLLMAccess(
        settings=settings,
        usage_recorder=LlmUsageRecorder(get_session).record,
    )
    standalone_llm_access = AgnoLLMAccess(settings=settings, usage_recorder=None)
    return DocumentService(
        repository=DocumentsRepository(session),
        storage=_get_storage(),
        extraction_port=AgnoDocumentExtractionAdapter(
            llm_access=llm_access,
            standalone_llm_access=standalone_llm_access,
        ),
    )


async def _get_actions_repo() -> ActionProposalsRepository:
    session = track_session(await get_session())
    return ActionProposalsRepository(session)



@closes_sessions
async def search_documents(run_context: RunContext, query: str | None = None) -> str:
    """Search your personal documents by filename.

    Use when the user asks about documents they've sent:
    - "Busca la factura del taller"
    - "¿Qué documentos tengo de agosto?"

    Args:
        run_context: Injected by Agno.
        query: Optional search term (matches filename).
    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_document_service()
    docs = await service.search_documents(user_ctx, query)

    if not docs:
        return (
            "No encontré documentos que coincidan con la búsqueda."
            if query
            else "No encontré documentos."
        )

    records: list[dict[str, object]] = []
    for doc in docs[:MAX_RESULT_RECORDS]:
        filename, truncated = bounded_text(doc.original_filename, MAX_FILENAME_CHARS)
        records.append(
            {
                "source": "canonical_document",
                "id": str(doc.id),
                "filename": filename,
                "filename_truncated": truncated,
                "mime_type": doc.mime_type[:127],
                "size_bytes": doc.size_bytes,
                "created_at": doc.created_at.isoformat(),
            }
        )
    return render_retrieved_records("search_documents", records, len(docs))


@closes_sessions
async def get_document(run_context: RunContext, document_id: str) -> str:
    """Get details about a specific document and its AI extraction.

    Use when the user asks about a document you've previously mentioned.

    Args:
        run_context: Injected by Agno.
        document_id: The document UUID (from search_documents results).
    """
    user_ctx = UserContext.from_run_context(run_context)

    try:
        doc_id = UUID(document_id)
    except ValueError:
        return "ID de documento no válido."

    service = await _get_document_service()
    result = await service.get_document(user_ctx, doc_id)
    if not result:
        return "Documento no encontrado."

    doc = result.document
    filename, filename_truncated = bounded_text(doc.original_filename, MAX_FILENAME_CHARS)
    record: dict[str, object] = {
        "source": "canonical_document",
        "id": str(doc.id),
        "filename": filename,
        "filename_truncated": filename_truncated,
        "mime_type": doc.mime_type[:127],
        "size_bytes": doc.size_bytes,
        "created_at": doc.created_at.isoformat(),
    }
    ext = result.extraction
    if ext and ext.extraction:
        extracted: dict[str, object] = {
            "source": "ai_extraction_unverified",
            "confidence": ext.confidence,
        }
        kind = ext.extraction.get("document_type")
        if isinstance(kind, str):
            extracted["document_type"], extracted["document_type_truncated"] = (
                bounded_text(kind, MAX_FILENAME_CHARS)
            )
        summary = ext.extraction.get("summary")
        if isinstance(summary, str):
            extracted["summary"], extracted["summary_truncated"] = bounded_text(
                summary, MAX_SUMMARY_CHARS
            )
        record["extraction"] = extracted
    return render_retrieved_records("get_document", [record], 1)


def _image_mime_type(content: bytes, declared: str | None) -> str:
    """Return a safe image MIME type from declaration or common signatures."""
    if declared and declared.startswith("image/"):
        return declared
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _media_filename(media: File | Image, mime_type: str, index: int) -> str:
    """Derive a stable, non-user-controlled fallback filename for Agno media."""
    filename = getattr(media, "filename", None) or getattr(media, "name", None)
    if filename:
        return Path(str(filename)).name

    filepath = getattr(media, "filepath", None)
    if filepath:
        return Path(str(filepath)).name

    extension = mimetypes.guess_extension(mime_type) or ".bin"
    media_id = getattr(media, "id", None) or str(index)
    return f"telegram-media-{media_id}{extension}"


@closes_sessions
async def analyze_document(
    run_context: RunContext,
    images: Sequence[Image] | None = None,
    files: Sequence[File] | None = None,
) -> str:
    """Process a newly received attachment through the document pipeline.

    Called when user sends media via Telegram. Agno injects photos through
    `images` and document attachments through `files`.
    Pipeline: store original → register → AI extract → return summary.

    Args:
        run_context: Injected by Agno.
        images: Telegram photos converted to Agno Image objects (injected).
        files: Telegram documents converted to Agno File objects (injected).
    """
    media_items: list[File | Image] = [*(images or []), *(files or [])]
    if not media_items:
        return "No se recibió ningún archivo para analizar."

    from src.config import Settings

    user_ctx = UserContext.from_run_context(run_context)
    settings = Settings()
    service = await _get_document_service()
    results = []

    for index, media in enumerate(media_items, start=1):
        content = await media.aget_content_bytes()
        if not content:
            results.append(f"⚠️ No se pudo leer el adjunto {index}.")
            continue

        declared_mime = getattr(media, "mime_type", None)
        preliminary_filename = _media_filename(
            media,
            declared_mime or "application/octet-stream",
            index,
        )
        mime_type = (
            _image_mime_type(content, declared_mime)
            if isinstance(media, Image)
            else declared_mime
            or mimetypes.guess_type(preliminary_filename)[0]
            or "application/octet-stream"
        )
        filename = _media_filename(media, mime_type, index)
        visual_pages: tuple[DocumentVisualPage, ...] = ()
        extracted_text: str | None = None
        if mime_type == "application/pdf":
            try:
                if has_extractable_text(content):
                    extracted_text = extract_pdf_text_markdown(
                        content,
                        max_pages=settings.document_vision_max_pdf_pages,
                    )
                else:
                    visual_pages = prepare_visual_pages(
                        content,
                        mime_type,
                        max_pdf_pages=settings.document_vision_max_pdf_pages,
                    )
            except DocumentVisionPreparationError:
                visual_pages = ()
        else:
            try:
                visual_pages = prepare_visual_pages(
                    content,
                    mime_type,
                    max_pdf_pages=settings.document_vision_max_pdf_pages,
                )
            except DocumentVisionPreparationError:
                visual_pages = ()
        result = await service.ingest(
            user_ctx,
            content,
            filename,
            mime_type,
            visual_pages=visual_pages,
            extracted_text=extracted_text,
        )
        ext = result.extraction

        lines = ["✅ Documento recibido y archivado correctamente."]
        if ext and ext.extraction:
            e = ext.extraction
            if e.get("document_type"):
                lines.append(f"   Tipo: {e['document_type']}")
            if e.get("summary"):
                lines.append(f"   {e['summary']}")
        results.append("\n".join(lines))

    return "\n\n".join(results)


@closes_sessions
async def propose_document_delete(run_context: RunContext, document_id: str) -> str:
    """PROPOSE deleting a stored document and its extraction — requires confirmation.

    Use when the user wants to remove a document they previously sent:
    - "Borra la factura del taller"
    - "Elimina ese documento, no quiero que lo guardes"

    Args:
        run_context: Injected by Agno.
        document_id: The document UUID (from search_documents/get_document results).
    """
    user_ctx = UserContext.from_run_context(run_context)
    parsed_id = parse_uuid(document_id, "documento")
    if isinstance(parsed_id, str):
        return parsed_id

    service = await _get_document_service()
    result = await service.get_document(user_ctx, parsed_id)
    if not result:
        return f"No se encontró el documento `{document_id}`."

    filename, _ = bounded_text(result.document.original_filename, MAX_FILENAME_CHARS)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="delete_document",
        payload={"document_id": str(parsed_id)},
    )
    return (
        f"🗑️ **Propuesta de borrado** (`{proposal['id']}`)\n"
        f"   Documento: {filename}\n"
        "\n¿Confirmas que lo elimine? Esta acción no se puede deshacer."
    )


@closes_sessions
async def execute_document_delete(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed document-delete proposal.

    Only call after the user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from propose_document_delete.
    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm_or_use_confirmed(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = await _get_document_service()
    try:
        document_id = UUID(payload["document_id"])
        deleted = await service.delete_document(user_ctx, document_id)
        if not deleted:
            return f"No se encontró el documento `{payload['document_id']}`."
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
        return f"✅ Documento eliminado (`{payload['document_id']}`)."
    except (KeyError, TypeError, ValueError) as e:
        return invalid_proposal_reply("execute_document_delete", e)
    except Exception as e:
        return internal_error_reply("execute_document_delete", e)

