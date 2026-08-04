"""Tests for storage. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""

import pytest

from valor.knowledge_base.storage import compute_sha256, delete_file, save_upload


class _FakeUpload:
    def __init__(self, content: bytes, filename: str):
        self._content = content
        self.filename = filename
        self._read = False

    async def read(self) -> bytes:
        if not self._read:
            self._read = True
            return self._content
        return b""


@pytest.mark.asyncio
async def test_save_upload_writes_file_and_returns_sha(tmp_path):
    upload = _FakeUpload(b"hello world", "test.pdf")
    sha, size, path = await save_upload(upload, "doc1", tmp_path)
    assert path.exists()
    assert path.name == "test.pdf"
    assert size == 11
    assert sha == compute_sha256(b"hello world")


@pytest.mark.asyncio
async def test_save_upload_creates_doc_dir(tmp_path):
    upload = _FakeUpload(b"x", "a.pdf")
    _, _, path = await save_upload(upload, "d2", tmp_path)
    assert path.parent.name == "d2"


@pytest.mark.asyncio
async def test_delete_file_removes_dir(tmp_path):
    upload = _FakeUpload(b"x", "a.pdf")
    _, _, path = await save_upload(upload, "d3", tmp_path)
    assert path.parent.exists()
    delete_file(path)
    assert not path.exists()
    assert not path.parent.exists()


def test_compute_sha256_deterministic():
    assert compute_sha256(b"abc") == compute_sha256(b"abc")
    assert compute_sha256(b"abc") != compute_sha256(b"abd")