"""Document export tool — Markdown → PDF delivered as a Telegram attachment.

(BL-38 Fase 3) Automatic, no propose/execute (AGENTS.md §2.4 exception, same reasoning as
``analyze_document``): generating and sending the requesting user their own
PDF mutates no canonical data and reaches no one but them, over the same
channel they are already using. The send happens mid-run, outside the
processor's governed delivery/outbox (specs/013) — but there is no run-level
retry to duplicate it against: ``retries=0`` on the governed Agent, Telegram
admission is at-most-once before the Agent ever runs, and a crash mid-run
is marked ``failed_ambiguous`` rather than replayed (specs/013). The real
risk is intra-run: the model invoking this tool twice for the same request.
Guarded via ``run_context.session_state`` (BL-38 follow-up, 2026-10-11) — a
plain dict scoped to this single ``agent.arun()`` call, never persisted.
"""

import hashlib

from agno.run import RunContext

from src.agent.document_export import DocumentExportError, render_markdown_to_pdf
from src.config import Settings
from src.domain.interactions.processor import TelegramSendError
from src.notifications.telegram import TelegramNotifier
from src.security.user_context import UserContext

_SENT_EXPORTS_KEY = "sent_exports"

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

    sent_exports: dict[str, str] | None = (
        run_context.session_state.setdefault(_SENT_EXPORTS_KEY, {})
        if run_context.session_state is not None
        else None
    )
    dedup_key = hashlib.sha256(f"{title or ''}\n{markdown_text}".encode()).hexdigest()
    if sent_exports is not None and dedup_key in sent_exports:
        return sent_exports[dedup_key]

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
    reply = f"✅ Documento enviado (`{filename}`)."
    if sent_exports is not None:
        sent_exports[dedup_key] = reply
    return reply


def _safe_filename(title: str | None) -> str:
    if not title or not title.strip():
        return "documento.pdf"
    slug = "".join(c if c.isalnum() or c in " -_" else "" for c in title.strip())
    slug = slug.strip().replace(" ", "_")[:80]
    return f"{slug or 'documento'}.pdf"


__all__ = ["export_document"]
