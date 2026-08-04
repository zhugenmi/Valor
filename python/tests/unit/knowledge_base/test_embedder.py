"""Tests for embedder. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
import pytest

from valor.knowledge_base.embedder import get_embedder


@pytest.fixture(scope="module")
def embedder():
    try:
        return get_embedder()
    except Exception as exc:
        pytest.skip(f"embedder unavailable: {exc}")


def test_embedder_returns_512_dim(embedder):
    vec = embedder.embed("测试文本")
    assert len(vec) == 512


def test_embedder_batch(embedder):
    vecs = embedder.embed_batch(["第一段", "第二段"], batch_size=2)
    assert len(vecs) == 2
    assert all(len(v) == 512 for v in vecs)


def test_embedder_truncates_long_text(embedder):
    """bge-small-zh 限制 512 token，超长文本应 truncate 不报错。"""
    long_text = "测试" * 1000  # 2000 字
    vec = embedder.embed(long_text)
    assert len(vec) == 512


def test_embedder_similar_texts_have_high_cosine(embedder):
    import math

    v1 = embedder.embed("贵州茅台业绩增长")
    v2 = embedder.embed("茅台公司营收上升")
    # cosine similarity
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    cos = dot / (n1 * n2 + 1e-9)
    assert cos > 0.5