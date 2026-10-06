"""Telegram attachment download adapter for the governed interaction processor.

The adapter is deliberately outside ``domain/``. It resolves a minimal,
encrypted Telegram file reference only after the durable interaction claim and
returns transient bytes; it never logs filenames, file identifiers, paths or
content.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Final

import httpx

from src.config import Settings
from src.domain.interactions.media import (
    AttachmentResolutionError,
    ResolvedTelegramMedia,
    TelegramAttachment,
)

_API_BASE: Final = "https://api.telegram.org"


class TelegramMediaResolver:
    """Resolve a single approved Telegram attachment through the Bot API."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._token = settings.telegram_token
        self._max_bytes = settings.max_file_size_mb * 1024 * 1024
        self._allowed_mime_types = settings.allowed_document_mime_types
        self._client = client or httpx.AsyncClient(timeout=20.0)
        self._owns_client = client is None

    async def resolve(self, attachment: TelegramAttachment) -> ResolvedTelegramMedia:
        """Download and validate one attachment without persisting its raw bytes."""
        if attachment.kind == "voice":
            raise AttachmentResolutionError("voice_requires_speech_dispatcher")
        if attachment.size_bytes is not None and attachment.size_bytes > self._max_bytes:
            raise AttachmentResolutionError("attachment_too_large")

        file_info = await self._get_file_info(attachment.file_id)
        file_path = file_info.get("file_path")
        file_size = file_info.get("file_size")
        if not isinstance(file_path, str) or not _safe_file_path(file_path):
            raise AttachmentResolutionError("telegram_file_path_invalid")
        if isinstance(file_size, int) and file_size > self._max_bytes:
            raise AttachmentResolutionError("attachment_too_large")

        try:
            response = await self._client.get(f"{_API_BASE}/file/bot{self._token}/{file_path}")
        except httpx.HTTPError as exc:
            raise AttachmentResolutionError("telegram_attachment_download_failed") from exc
        if response.status_code != 200:
            raise AttachmentResolutionError("telegram_attachment_download_rejected")
        content = response.content
        if not content:
            raise AttachmentResolutionError("telegram_attachment_empty")
        if len(content) > self._max_bytes:
            raise AttachmentResolutionError("attachment_too_large")

        mime_type = _resolve_mime_type(attachment, content)
        if mime_type not in self._allowed_mime_types:
            raise AttachmentResolutionError("attachment_mime_not_allowed")
        filename = _safe_filename(attachment.filename, mime_type)
        return ResolvedTelegramMedia(
            content=content,
            filename=filename,
            mime_type=mime_type,
            is_image=mime_type.startswith("image/"),
        )

    async def resolve_voice(self, attachment: TelegramAttachment, *, max_bytes: int) -> bytes:
        """Bound raw streaming bytes, including when Content-Length is absent/false."""
        if attachment.kind != "voice" or max_bytes <= 0:
            raise AttachmentResolutionError("voice_origin_not_allowed")
        if attachment.size_bytes is not None and attachment.size_bytes > max_bytes:
            raise AttachmentResolutionError("voice_too_large")
        info = await self._get_file_info(attachment.file_id)
        path = info.get("file_path")
        if not isinstance(path, str) or not _safe_file_path(path):
            raise AttachmentResolutionError("telegram_file_path_invalid")
        size = info.get("file_size")
        if isinstance(size, int) and size > max_bytes:
            raise AttachmentResolutionError("voice_too_large")
        content = bytearray()
        try:
            async with self._client.stream(
                "GET", f"{_API_BASE}/file/bot{self._token}/{path}"
            ) as response:
                if response.status_code != 200:
                    raise AttachmentResolutionError("telegram_attachment_download_rejected")
                async for chunk in response.aiter_raw():
                    if len(content) + len(chunk) > max_bytes:
                        raise AttachmentResolutionError("voice_too_large")
                    content.extend(chunk)
            if not content:
                raise AttachmentResolutionError("voice_empty_or_invalid")
            return bytes(content)
        except httpx.HTTPError:
            raise AttachmentResolutionError("telegram_attachment_download_failed") from None
        finally:
            content.clear()

    async def close(self) -> None:
        """Close only an internally-owned HTTP client."""
        if self._owns_client:
            await self._client.aclose()

    async def _get_file_info(self, file_id: str) -> dict[str, object]:
        try:
            response = await self._client.post(
                f"{_API_BASE}/bot{self._token}/getFile",
                json={"file_id": file_id},
            )
        except httpx.HTTPError as exc:
            raise AttachmentResolutionError("telegram_get_file_failed") from exc
        if response.status_code != 200:
            raise AttachmentResolutionError("telegram_get_file_rejected")
        try:
            body = response.json()
        except ValueError as exc:
            raise AttachmentResolutionError("telegram_get_file_invalid_response") from exc
        result = body.get("result") if isinstance(body, dict) else None
        if not body.get("ok") or not isinstance(result, dict):
            raise AttachmentResolutionError("telegram_get_file_invalid_response")
        return result


def _safe_file_path(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and not value.startswith("/")


def _resolve_mime_type(attachment: TelegramAttachment, content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    declared = (attachment.mime_type or "").strip().lower()
    if declared:
        return declared
    guessed = mimetypes.guess_type(attachment.filename or "")[0]
    return guessed or "application/octet-stream"


def _safe_filename(value: str | None, mime_type: str) -> str:
    if value:
        candidate = Path(value).name
        if candidate and candidate not in {".", ".."}:
            return candidate
    extension = mimetypes.guess_extension(mime_type) or ".bin"
    return f"telegram-document{extension}"
