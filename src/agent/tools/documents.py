"""Document tools — thin Agno tool adapters for DocumentService.

Plain Python functions with run_context injection by Agno.
"""

import mimetypes
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from agno.media import File, Image
from agno.run import RunContext

from src.agent.document_vision import DocumentVisionPreparationError, prepare_visual_pages
from src.domain.documents.service import DocumentService
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
    session = await get_session()
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
        return "No encontré documentos" + (f' que coincidan con "{query}".' if query else ".")

    lines = []
    for doc in docs:
        created = doc.created_at.strftime("%Y-%m-%d %H:%M")
        size_kb = doc.size_bytes / 1024
        lines.append(
            f"- `{doc.id}` | {doc.original_filename} ({size_kb:.0f} KB, {doc.mime_type}, {created})"
        )
    header = f"Encontré {len(docs)} documento(s)" + (f' sobre "{query}"' if query else "") + ":\n\n"
    return header + "\n".join(lines)


async def get_document(run_context: RunContext, document_id: str) -> str:
    """Get details about a specific document and its AI extraction.

    Use when the user asks about a document you've previously mentioned.

    Args:
        run_context: Injected by Agno.
        document_id: The document UUID (from search_documents results).
    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_document_service()

    try:
        doc_id = UUID(document_id)
    except ValueError:
        return f"ID de documento no válido: {document_id}"

    result = await service.get_document(user_ctx, doc_id)
    if not result:
        return f"Documento no encontrado: {document_id}"

    doc = result.document
    ext = result.extraction
    lines = [
        f"📄 **{doc.original_filename}**",
        f"   ID: `{doc.id}`",
        f"   Tipo: {doc.mime_type} | Tamaño: {doc.size_bytes / 1024:.0f} KB",
        f"   Recibido: {doc.created_at.strftime('%Y-%m-%d %H:%M')}",
    ]

    if ext and ext.extraction:
        e = ext.extraction
        lines.append(f"\n🤖 **Extracción IA** (confidence: {ext.confidence or 'N/A'})")
        if e.get("document_type"):
            lines.append(f"   Tipo detectado: {e['document_type']}")
        if e.get("summary"):
            lines.append(f"   Resumen: {e['summary']}")
    return "\n".join(lines)


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
