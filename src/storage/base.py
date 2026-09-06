"""Document storage — abstraction over filesystem / S3 / MinIO / R2.

Protocol-based design. Only LocalFileSystemStorage implemented for POC.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class StoredDocument:
    """Result of storing a document."""

    storage_key: str
    """Unique key/path in the storage backend."""

    original_filename: str
    """User-provided filename."""

    mime_type: str
    """Detected MIME type."""

    size_bytes: int
    """File size in bytes."""


class DocumentStorage(Protocol):
    """Protocol for document storage backends.

    Implementations: LocalFileSystemStorage, S3Storage, MinIOStorage, etc.
    """

    async def store(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> StoredDocument:
        """Store a document and return its metadata."""
        ...

    async def get(self, storage_key: str) -> bytes:
        """Retrieve a document's content by its storage key."""
        ...

    async def delete(self, storage_key: str) -> None:
        """Delete a document by its storage key."""
        ...

    async def exists(self, storage_key: str) -> bool:
        """Check if a document exists."""
        ...
