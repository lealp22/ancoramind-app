"""Supabase Storage document storage — managed backend (ADR-002).

Same key layout as LocalFileSystemStorage: {YY}/{MM}/{uuid12}.{ext}
so documents/ records remain backend-agnostic in shape.

Blocking supabase-py calls are wrapped in asyncio.to_thread.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from src.storage.base import DocumentStorage, StoredDocument


class SupabaseDocumentStorage(DocumentStorage):
    """Store documents in a private Supabase Storage bucket.

    Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY. The service role key
    bypasses RLS — server-side use only, never expose to clients or Git.
    """

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        bucket: str = "ancora-documents",
    ):
        if not supabase_url or not service_role_key:
            raise ValueError(
                "SupabaseDocumentStorage requires SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY"
            )
        from supabase import create_client  # deferred: optional dependency

        self._bucket = bucket
        self._client = create_client(supabase_url, service_role_key)
        self._storage = self._client.storage.from_(bucket)

    def _make_key(self, filename: str) -> str:
        """Generate a date-sharded storage key (same layout as local)."""
        now = datetime.now(tz=UTC)
        stem = uuid.uuid4().hex[:12]
        ext = PurePosixPath(filename).suffix or ".bin"
        return f"{now.year}/{now.month:02d}/{stem}{ext}"

    @staticmethod
    def _split_dir(key: str) -> tuple[str, str]:
        """Split '2026/09/abc.pdf' into ('2026/09', 'abc.pdf')."""
        parts = PurePosixPath(key).parts
        if len(parts) < 2:
            return "", parts[0] if parts else ""
        return "/".join(parts[:-1]), parts[-1]

    @staticmethod
    def _validate_key(storage_key: str) -> None:
        """Reject keys that escape the bucket namespace."""
        if not storage_key or ".." in PurePosixPath(storage_key).parts:
            raise ValueError(f"Invalid storage key: {storage_key}")

    async def store(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> StoredDocument:
        """Upload document bytes to the bucket."""
        key = self._make_key(filename)
        await asyncio.to_thread(
            self._storage.upload,
            key,
            content,
            {"content-type": mime_type},
        )
        return StoredDocument(
            storage_key=key,
            original_filename=filename,
            mime_type=mime_type,
            size_bytes=len(content),
        )

    async def get(self, storage_key: str) -> bytes:
        """Download document bytes from the bucket."""
        self._validate_key(storage_key)
        try:
            return await asyncio.to_thread(self._storage.download, storage_key)
        except Exception as exc:
            message = str(exc).lower()
            if "not found" in message or "does not exist" in message:
                raise FileNotFoundError(
                    f"Document not found: {storage_key}"
                ) from exc
            raise

    async def delete(self, storage_key: str) -> None:
        """Remove the object from the bucket (no-op if already gone)."""
        self._validate_key(storage_key)
        if not await self.exists(storage_key):
            return
        await asyncio.to_thread(self._storage.remove, [storage_key])

    async def exists(self, storage_key: str) -> bool:
        """Check whether the object exists in the bucket."""
        self._validate_key(storage_key)
        folder, name = self._split_dir(storage_key)
        try:
            entries = await asyncio.to_thread(self._storage.list, folder)
        except Exception:
            return False
        return any(entry.get("name") == name for entry in entries or [])
