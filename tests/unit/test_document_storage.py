"""Unit tests for local filesystem storage."""

import os
import tempfile

import pytest

from src.storage.local import LocalFileSystemStorage


@pytest.fixture
def storage(tmp_path):
    return LocalFileSystemStorage(base_path=str(tmp_path / "docs"))


class TestLocalFileSystemStorage:
    async def test_store_and_get(self, storage):
        content = b"Hello, document!"
        result = await storage.store(content, "test.txt", "text/plain")
        assert result.original_filename == "test.txt"
        assert result.mime_type == "text/plain"
        assert result.size_bytes == len(content)
        assert result.storage_key.endswith(".txt")

        retrieved = await storage.get(result.storage_key)
        assert retrieved == content

    async def test_exists(self, storage):
        result = await storage.store(b"data", "f.txt", "text/plain")
        assert await storage.exists(result.storage_key) is True
        assert await storage.exists("nonexistent.txt") is False

    async def test_delete(self, storage):
        result = await storage.store(b"data", "f.txt", "text/plain")
        assert await storage.exists(result.storage_key) is True
        await storage.delete(result.storage_key)
        assert await storage.exists(result.storage_key) is False

    async def test_path_traversal_protection(self, storage):
        with pytest.raises(ValueError, match="Invalid storage key"):
            await storage.get("../../../etc/passwd")

    async def test_file_not_found(self, storage):
        with pytest.raises(FileNotFoundError):
            await storage.get("nonexistent/file.txt")

    async def test_unique_filenames(self, storage):
        r1 = await storage.store(b"a", "file.txt", "text/plain")
        r2 = await storage.store(b"b", "file.txt", "text/plain")
        assert r1.storage_key != r2.storage_key