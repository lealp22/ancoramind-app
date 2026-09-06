"""Document storage factory — selects backend from Settings (ADR-002).

DOCUMENT_STORAGE_BACKEND=local (default) | supabase
"""

import logging

from src.config import Settings
from src.storage.base import DocumentStorage

logger = logging.getLogger(__name__)


def create_storage(settings: Settings) -> DocumentStorage:
    """Build the document storage backend configured in the environment.

    Raises:
        ValueError: Unknown backend or missing Supabase credentials.
    """
    backend = settings.document_storage_backend.strip().lower()

    if backend == "local":
        from src.storage.local import LocalFileSystemStorage

        return LocalFileSystemStorage(base_path=settings.document_storage_path)

    if backend == "supabase":
        from src.storage.supabase_storage import SupabaseDocumentStorage

        logger.info(
            "Document storage backend: supabase (bucket=%s)",
            settings.supabase_storage_bucket,
        )
        return SupabaseDocumentStorage(
            supabase_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            bucket=settings.supabase_storage_bucket,
        )

    raise ValueError(
        f"Unknown DOCUMENT_STORAGE_BACKEND: {settings.document_storage_backend!r} "
        "(supported: local, supabase)"
    )
