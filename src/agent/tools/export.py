"""Document export tool — Markdown → PDF delivered as a Telegram attachment.

(BL-38 Fase 3) Automatic, no propose/execute (AGENTS.md §2.4 exception, same reasoning as
``analyze_document``): generating and sending the requesting user their own
PDF mutates no canonical data and reaches no one but them, over the same
channel they are already using. Known limitation of this increment: the
send happens mid-run, outside the processor's governed delivery/outbox
(specs/013) — a rare run failure right after a successful send could in
theory cause a duplicate PDF on an eventual retry, never a data-integrity
issue. Accepted explicitly, same "best-effort" posture already used for
Dream's transcript capture.
"""

from agno.run import RunContext

from src.agent.document_export import DocumentExportError, render_markdown_to_pdf
from src.config import Settings
from src.domain.interactions.processor import TelegramSendError
from src.notifications.telegram import TelegramNotifier
from src.security.user_context import UserContext

_ERROR_REPLIES = {
    "export_empty_output": "No hay contenido que exportar.",
    "export_markdown_too_long": "El contenido es demasiado largo para exportarlo a PDF.",
    "export_render_failed": "No pude generar el PDF. Intenta con un contenido más corto.",
}


async def export_document(
    run_context: RunContext, markdown_text: str, title: str | None = None
) -> str:
    """Render Markdown as a PDF and send it to the user as a Telegram document.

    Use when the user explicitly asks for a document/PDF of something
    already discussed:
    - "Pásamelo en PDF"
    - "Mándame esa lista como documento"
    - "Exporta este resumen a PDF"

    Compose the Markdown yourself from the conversation/previous tool
    results before calling this tool — it only renders and delivers, it
    never fetches data on its own.

    Args:
        run_context: Injected by Agno.
        markdown_text: The content to export, in Markdown.
        title: Optional document title, rendered as its own heading.

    """
    user_ctx = UserContext.from_run_context(run_context)
    try:
        chat_id = int(user_ctx.user_id)
    except (TypeError, ValueError):
        return "No puedo exportar documentos fuera de un chat privado de Telegram."

    settings = Settings()
    try:
        pdf = render_markdown_to_pdf(
            markdown_text,
            title=title,
            max_markdown_chars=settings.document_export_max_markdown_chars,
            max_pages=settings.document_export_max_pages,
            max_pdf_bytes=settings.document_export_max_pdf_bytes,
        )
    except DocumentExportError as exc:
        return _ERROR_REPLIES.get(exc.args[0], "No pude generar el PDF.")

    filename = _safe_filename(title)
    notifier = TelegramNotifier(settings.telegram_token)
    try:
        await notifier.send_document(chat_id, pdf, filename)
    except TelegramSendError:
        return "Generé el PDF pero no pude enviarlo por Telegram. Inténtalo de nuevo."
    finally:
        await notifier.close()
    return f"✅ Documento enviado (`{filename}`)."


def _safe_filename(title: str | None) -> str:
    if not title or not title.strip():
        return "documento.pdf"
    slug = "".join(c if c.isalnum() or c in " -_" else "" for c in title.strip())
    slug = slug.strip().replace(" ", "_")[:80]
    return f"{slug or 'documento'}.pdf"


__all__ = ["export_document"]
