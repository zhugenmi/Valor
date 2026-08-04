"""File storage: save uploads, compute SHA256, delete. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import UploadFile


def compute_sha256(stream: bytes) -> str:
    return hashlib.sha256(stream).hexdigest()


async def save_upload(file: UploadFile, doc_id: str, files_dir: Path) -> tuple[str, int, Path]:
    """Save uploaded file to {files_dir}/{doc_id}/{filename}. Returns (sha256, size, path)."""
    content = await file.read()
    sha = compute_sha256(content)
    size = len(content)
    doc_dir = files_dir / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    file_path = doc_dir / (file.filename or f"{doc_id}.bin")
    file_path.write_bytes(content)
    return sha, size, file_path


def delete_file(file_path: Path) -> None:
    """Delete file and its parent directory if empty."""
    if file_path.exists():
        file_path.unlink()
    parent = file_path.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()