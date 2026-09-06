"""Tests for SupabaseDocumentStorage (ADR-002) and storage factory."""

import re
from unittest.mock import MagicMock

import pytest

from src.storage.factory import create_storage
from src.storage.local import LocalFileSystemStorage

# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def mock_supabase(monkeypatch):
    """Patch supabase.create_client so no real client is created."""
    client = MagicMock()
    monkeypatch.setattr("supabase.create_client", lambda url, key: client)
    return client


@pytest.fixture
def storage(mock_supabase):
    from src.storage.supabase_storage import SupabaseDocumentStorage

    return SupabaseDocumentStorage(
        supabase_url="https://fake.supabase.co",
        service_role_key="service-role-key",
        bucket="ancora-documents",
    )


# ── SupabaseDocumentStorage ───────────────────────────


class TestSupabaseStorageInit:
    def test_requires_credentials(self):
        from src.storage.supabase_storage import SupabaseDocumentStorage

        with pytest.raises(ValueError, match="SUPABASE_URL"):
            SupabaseDocumentStorage(supabase_url="", service_role_key="k")

    def test_creates_client_with_bucket(self, mock_supabase, storage):
        assert storage._bucket == "ancora-documents"
        mock_supabase.storage.from_.assert_called_with("ancora-documents")


class TestSupabaseStorageStore:
    async def test_store_uploads_and_returns_metadata(
        self, storage, mock_supabase
    ):
        result = await storage.store(b"PDFDATA", "factura.pdf", "application/pdf")

        key = result.storage_key
        assert re.fullmatch(r"\d{4}/\d{2}/[0-9a-f]{12}\.pdf", key)
        assert result.original_filename == "factura.pdf"
        assert result.mime_type == "application/pdf"
        assert result.size_bytes == 7

        upload = mock_supabase.storage.from_.return_value.upload
        upload.assert_called_once()
        args, kwargs = upload.call_args
        assert args[0] == key
        assert args[1] == b"PDFDATA"

    async def test_store_preserves_extension(self, storage, mock_supabase):
        result = await storage.store(b"x", "foto.JPG", "image/jpeg")
        assert result.storage_key.endswith(".JPG")


class TestSupabaseStorageGet:
    async def test_get_returns_bytes(self, storage, mock_supabase):
        mock_supabase.storage.from_.return_value.download.return_value = b"DATA"
        assert await storage.get("2026/09/abc123.pdf") == b"DATA"

    async def test_get_not_found_maps_to_filenotfounderror(
        self, storage, mock_supabase
    ):
        mock_supabase.storage.from_.return_value.download.side_effect = Exception(
            "Object not found: 2026/09/missing.pdf"
        )
        with pytest.raises(FileNotFoundError, match="missing.pdf"):
            await storage.get("2026/09/missing.pdf")

    async def test_get_other_errors_propagate(self, storage, mock_supabase):
        mock_supabase.storage.from_.return_value.download.side_effect = Exception(
            "connection reset"
        )
        with pytest.raises(Exception, match="connection reset"):
            await storage.get("2026/09/abc.pdf")

    async def test_get_rejects_traversal(self, storage):
        with pytest.raises(ValueError, match="Invalid storage key"):
            await storage.get("../secrets/key.pem")


class TestSupabaseStorageExistsDelete:
    async def test_exists_true(self, storage, mock_supabase):
        mock_supabase.storage.from_.return_value.list.return_value = [
            {"name": "abc.pdf"},
            {"name": "other.txt"},
        ]
        assert await storage.exists("2026/09/abc.pdf") is True

    async def test_exists_false(self, storage, mock_supabase):
        mock_supabase.storage.from_.return_value.list.return_value = [
            {"name": "other.txt"}
        ]
        assert await storage.exists("2026/09/abc.pdf") is False

    async def test_delete_noop_when_missing(self, storage, mock_supabase):
        mock_supabase.storage.from_.return_value.list.return_value = []
        await storage.delete("2026/09/abc.pdf")
        mock_supabase.storage.from_.return_value.remove.assert_not_called()

    async def test_delete_removes_when_present(self, storage, mock_supabase):
        mock_supabase.storage.from_.return_value.list.return_value = [
            {"name": "abc.pdf"}
        ]
        await storage.delete("2026/09/abc.pdf")
        mock_supabase.storage.from_.return_value.remove.assert_called_once_with(
            ["2026/09/abc.pdf"]
        )

    async def test_delete_rejects_traversal(self, storage):
        with pytest.raises(ValueError, match="Invalid storage key"):
            await storage.delete("../x")


# ── Storage factory ───────────────────────────────────


def _settings(**overrides):
    """Settings instance with env file interference neutralized."""
    from src.config import Settings

    settings = Settings(
        telegram_token="x", llm_provider="openai", _env_file=None
    )
    for field, value in overrides.items():
        setattr(settings, field, value)
    return settings


class TestStorageFactory:
    def test_local_by_default(self):
        s = _settings(document_storage_backend="local")
        assert isinstance(create_storage(s), LocalFileSystemStorage)

    def test_supabase_with_credentials(self, mock_supabase):
        from src.storage.supabase_storage import SupabaseDocumentStorage

        s = _settings(
            document_storage_backend="supabase",
            supabase_url="https://fake.supabase.co",
            supabase_service_role_key="k",
        )
        assert isinstance(create_storage(s), SupabaseDocumentStorage)

    def test_supabase_without_credentials_raises(self):
        s = _settings(document_storage_backend="supabase")
        with pytest.raises(ValueError, match="SUPABASE_URL"):
            create_storage(s)

    def test_unknown_backend_raises(self):
        s = _settings(document_storage_backend="s3")
        with pytest.raises(ValueError, match="Unknown DOCUMENT_STORAGE_BACKEND"):
            create_storage(s)
