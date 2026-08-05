"""Embedder using bge-small-zh-v1.5 (512 dim). License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import os
import threading

# Default to offline mode so sentence-transformers uses local cache instead of
# hitting huggingface.co on every load (network may be unreachable in dev envs).
# User can override by exporting HF_HUB_OFFLINE=0 before starting the server.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

_EMBEDDER: "Embedder | None" = None
_LOCK = threading.Lock()


class Embedder:
    """Wrapper around sentence-transformers bge-small-zh-v1.5."""

    def __init__(self, model_name: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer

        model_name = model_name or os.getenv("VALOR_KB_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
        self._model = SentenceTransformer(model_name)
        self._dim = 512

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        """Embed a single text. Model auto-truncates to max_seq_length=512."""
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Embed a batch of texts."""
        if not texts:
            return []
        vecs = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vecs]


def get_embedder() -> Embedder:
    """Lazy singleton embedder."""
    global _EMBEDDER
    if _EMBEDDER is None:
        with _LOCK:
            if _EMBEDDER is None:
                _EMBEDDER = Embedder()
    return _EMBEDDER