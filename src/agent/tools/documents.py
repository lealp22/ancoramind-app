"""Document tools — thin Agno tool adapters for DocumentService.

Plain Python functions with run_context injection by Agno.
"""

import os
from uuid import UUID

from agno.run import RunContext

from src.domain.documents.service import DocumentService
from src.repositories.database import get_session
from src.repositories.documents import DocumentsRepository
from src.security.user_context import UserContext
from src.storage.local import LocalFileSystemStorage

_storage = LocalFileSystemStorage(
    base_path=os.environ.get("DOCUMENT_STORAGE_PATH", "./data/documents")
)


async def _get_document_service():
    """Create a DocumentService with fresh DB session."""
    from agno.models.openai import OpenAIChat
    session = await get_session()
    return DocumentService(
        repository=DocumentsRepository(session),
        storage=_storage,
        model=OpenAIChat(id="gpt-4o-mini"),
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
            f"- `{doc.id}` | {doc.original_filename} "
            f"({size_kb:.0f} KB, {doc.mime_type}, {created})"
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
        if e.get("suggested_actions"):
            lines.append(f"   💡 Acciones sugeridas: {', '.join(e['suggested_actions'])}")
    return "\n".join(lines)
async def analyze_document(run_context: RunContext, files: list | None = None) -> str:
    """Process a newly received attachment through the document pipeline.

    Called when user sends a document via Telegram. Agno provides the
    downloaded file via the `files` built-in parameter.
    Pipeline: store original → register → AI extract → return summary.

    Args:
        run_context: Injected by Agno.
        files: Downloaded file objects from Agno (built-in parameter).
    """
    if not files:
        return "No se recibió ningún archivo para analizar."

    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_document_service()
    results = []

    for file_obj in files:
        filepath = getattr(file_obj, "filepath", None) or getattr(file_obj, "path", None)
        filename = getattr(file_obj, "original_filename", None) or os.path.basename(str(filepath or "unknown"))
        mime_type = getattr(file_obj, "mime_type", None) or "application/octet-stream"

        if not filepath or not os.path.exists(str(filepath)):
            results.append(f"⚠️ No se pudo leer: {filename}")
            continue

        content = open(str(filepath), "rb").read()
        result = await service.ingest(user_ctx, content, filename, mime_type)
        doc = result.document
        ext = result.extraction

        lines = [f"📄 **{doc.original_filename}** recibido y archivado.", f"   ID: `{doc.id}`"]
        if ext and ext.extraction:
            e = ext.extraction
            if e.get("document_type"):
                lines.append(f"   Tipo: {e['document_type']}")
            if e.get("summary"):
                lines.append(f"   {e['summary']}")
            if e.get("suggested_actions"):
                lines.append(f"   💡 Acciones sugeridas: {', '.join(e['suggested_actions'])}")
        results.append("\n".join(lines))

    return "\n\n".join(results)