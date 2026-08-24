"""Local filesystem document storage — POC implementation.

Organizes files as: {base_path}/{YY}/{MM}/{uuid}.{ext}
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.storage.base import DocumentStorage, StoredDocument


class LocalFileSystemStorage(DocumentStorage):
    """Store documents on the local filesystem.

    Directory structure:
        {base_path}/
            2026/
                08/
                    {uuid}.pdf
                    {uuid}.jpg
    """

    def __init__(self, base_path: str = "./data/documents"):
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def _make_path(self, filename: str) -> Path:
        """Generate a storage path with date-based sharding."""
        now = datetime.now(tz=timezone.utc)
        month_dir = self._base / str(now.year) / f"{now.month:02d}"
        month_dir.mkdir(parents=True, exist_ok=True)

        # Unique filename to prevent collisions
        stem = uuid.uuid4().hex[:12]
        ext = Path(filename).suffix or ".bin"
        return month_dir / f"{stem}{ext}"

    async def store(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> StoredDocument:
        """Store document content to disk.

        Args:
            content: Raw file bytes.
            filename: Original user-provided filename.
            mime_type: Detected MIME type.

        Returns:
            StoredDocument with storage key and metadata.
        """
        dest = self._make_path(filename)
        dest.write_bytes(content)

        relative_key = str(dest.relative_to(self._base)).replace("\\", "/")

        return StoredDocument(
            storage_key=relative_key,
            original_filename=filename,
            mime_type=mime_type,
            size_bytes=len(content),
        )

    async def get(self, storage_key: str) -> bytes:
        """Retrieve document content from disk.

        Args:
            storage_key: Relative path within base directory.

        Returns:
            Raw file bytes.

        Raises:
            FileNotFoundError: If the document doesn't exist.
        """
        full_path = (self._base / storage_key).resolve()

        # Path traversal protection
        if not str(full_path).startswith(str(self._base.resolve())):
            raise ValueError(f"Invalid storage key: {storage_key}")

        if not full_path.exists():
            raise FileNotFoundError(f"Document not found: {storage_key}")

        return full_path.read_bytes()

    async def delete(self, storage_key: str) -> None:
        """Delete a document from disk.

        Args:
            storage_key: Relative path within base directory.
        """
        full_path = (self._base / storage_key).resolve()

        if not str(full_path).startswith(str(self._base.resolve())):
            raise ValueError(f"Invalid storage key: {storage_key}")

        if full_path.exists():
            full_path.unlink()

    async def exists(self, storage_key: str) -> bool:
        """Check if a document exists on disk."""
        full_path = (self._base / storage_key).resolve()
        if not str(full_path).startswith(str(self._base.resolve())):
            return False
        return full_path.exists()