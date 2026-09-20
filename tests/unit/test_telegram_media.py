"""Unit tests for the governed Telegram attachment resolver."""

from __future__ import annotations

import httpx
import pytest

from src.agent.telegram_media import TelegramMediaResolver
from src.config import Settings
from src.domain.interactions.media import AttachmentResolutionError, TelegramAttachment


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.telegram.org")


async def test_resolver_downloads_and_validates_a_photo_without_filename() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "photos/a.jpg"}})
        return httpx.Response(200, content=b"\xff\xd8\xffJPEG")

    resolver = TelegramMediaResolver(
        Settings(telegram_token="123:token", _env_file=None),
        client=_client(handler),
    )

    media = await resolver.resolve(TelegramAttachment(kind="photo", file_id="opaque-id"))

    assert media.content == b"\xff\xd8\xffJPEG"
    assert media.mime_type == "image/jpeg"
    assert media.filename.endswith((".jpg", ".jpeg", ".jpe"))
    assert media.is_image is True


async def test_resolver_rejects_disallowed_mime_before_returning_bytes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "docs/a.exe"}})
        return httpx.Response(200, content=b"MZ")

    resolver = TelegramMediaResolver(
        Settings(telegram_token="123:token", _env_file=None),
        client=_client(handler),
    )

    with pytest.raises(AttachmentResolutionError, match="attachment_mime_not_allowed"):
        await resolver.resolve(
            TelegramAttachment(
                kind="document",
                file_id="opaque-id",
                filename="untrusted.exe",
                mime_type="application/octet-stream",
            )
        )


async def test_resolver_rejects_declared_oversize_before_network() -> None:
    resolver = TelegramMediaResolver(
        Settings(telegram_token="123:token", max_file_size_mb=1, _env_file=None),
        client=_client(lambda _: pytest.fail("network must not be called")),
    )

    with pytest.raises(AttachmentResolutionError, match="attachment_too_large"):
        await resolver.resolve(
            TelegramAttachment(kind="document", file_id="opaque-id", size_bytes=1_048_577)
        )
