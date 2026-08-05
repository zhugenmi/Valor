"""Tests for chunker. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.knowledge_base.chunker import chunk_document
from valor.knowledge_base.constants import CHUNK_STRATEGIES
from valor.knowledge_base.parser import (
    HeadingNode,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
)


def _doc_with_text(text: str) -> ParsedDocument:
    return ParsedDocument(
        file_path="x", mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
    )


def test_chunk_general_keeps_chunk_size():
    text = "段一。" * 200  # 800 字
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["general"])
    assert len(chunks) >= 2
    for c in chunks:
        assert c.text  # non-empty
        assert c.seq >= 0


def test_chunk_research_with_headings():
    text = "# 摘要\n核心观点：增长强劲。\n\n# 财务预测\n2024 年营收预计 1500 亿。"
    doc = ParsedDocument(
        file_path="x", mime_type="text/markdown",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
        heading_tree=[HeadingNode(level=1, text="摘要", page_no=1),
                       HeadingNode(level=1, text="财务预测", page_no=1)],
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["research"])
    # 至少 2 个 chunk（按 heading 切）
    assert len(chunks) >= 2
    # 第一个 chunk 应该包含"摘要"上下文
    assert "摘要" in (chunks[0].heading_path or "") or "核心观点" in chunks[0].text


def test_chunk_clause_by_article():
    text = "第一条 为规范市场秩序，制定本规定。第二条 适用范围包括所有上市公司。第三条 本规定自发布之日起施行。"
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["regulatory_clause"])
    assert len(chunks) >= 3
    assert "第一条" in chunks[0].text
    assert "第二条" in chunks[1].text
    assert "第三条" in chunks[2].text


def test_chunk_table_aware_separates_tables():
    text = "概述文本。\n\n| 项目 | 金额 |\n|---|---|\n| 营收 | 100 |\n\n后续文本。"
    doc = ParsedDocument(
        file_path="x", mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
        tables=[ParsedTable(page_no=1, rows=[["项目", "金额"], ["营收", "100"]])],
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["annual_report"])
    # 应该有表格 chunk 和文本 chunk
    has_table_chunk = any("|" in c.text or "营收" in c.text for c in chunks)
    assert has_table_chunk


def test_chunk_assigns_seq_unique():
    text = "段一。" * 100 + "段二。" * 100
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["general"])
    seqs = [c.seq for c in chunks]
    assert len(seqs) == len(set(seqs))  # unique


# ---------------------------------------------------------------------------
# Bug fix: _chunk_clause 切碎条款 (q02 失败案例)
# ---------------------------------------------------------------------------

def test_chunk_clause_long_article_not_split():
    """长条款(>2000 字)应保持完整单 chunk,不被 _split_recursive 切碎。"""
    # 反洗钱办法第三条等长条款典型长度 2000-4000 字
    article_body = "金融机构应当履行以下义务。" + "具体措施包括内容描述。" * 200  # ~2200 字
    # 末尾独特标记,用于验证条款完整性
    article_body = article_body + "末尾独特标记ENDMARKER。"
    text = "第一条 短条款。\n第二条 短条款。\n第三条 " + article_body + "\n第四条 短条款。"
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["regulatory_clause"])
    # 找到第三条所在 chunk
    article3 = [c for c in chunks if "第三条" in c.text]
    assert len(article3) == 1, f"第三条应单独成块,实际被切成 {len(article3)} 块"
    # 第三条完整内容(含末尾标记)应在单 chunk 内,验证未被切碎
    assert "末尾独特标记ENDMARKER" in article3[0].text, \
        f"第三条被切碎,末尾内容不在 chunk 中: {article3[0].text[-50:]!r}"


def test_chunk_clause_oversized_article_keeps_prefix():
    """极端长条款(>5000 字)切分时,每个子块都应带'第X条'前缀。"""
    article_body = "具体内容。" * 1200  # ~6000 字,超过 chunk_size=5000
    text = "第一条 " + article_body
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["regulatory_clause"])
    assert len(chunks) >= 2, "超长条款应被切分"
    # 每个子块都应带"第一条"前缀(归属可识别)
    for c in chunks:
        assert "第一条" in c.text, f"子块缺少条款前缀: {c.text[:30]!r}"


# ---------------------------------------------------------------------------
# Bug fix: 噪声 chunk 过滤 (q17 失败案例)
# ---------------------------------------------------------------------------

def test_chunk_filter_drops_copyright_notice():
    """版权声明作为独立 chunk 时应被过滤。"""
    # body 足够长,确保被切成多个 chunk;末尾版权声明作为独立段落
    body = "白酒行业研究核心观点:高端白酒市场增长强劲,消费升级趋势明显,价格带持续上移。" * 20  # ~900 字
    copyright_notice = "版权所有,未经许可不得转载。"
    disclaimer = "免责声明:本报告仅供参考,不构成投资建议。"
    text = body + "\n\n" + copyright_notice + "\n\n" + disclaimer
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["general"])
    for c in chunks:
        assert "版权所有" not in c.text, f"版权声明未被过滤: {c.text!r}"
        assert "免责声明" not in c.text, f"免责声明未被过滤: {c.text!r}"


def test_chunk_filter_drops_short_repeated_header():
    """重复出现的短页眉/页脚应被过滤。"""
    header = "— 1 —"
    body = "正文内容,这是有意义的段落,包含足够长的语义信息以避免被噪声过滤。" * 20  # ~600 字
    # 用 \n\n 分隔,让 header 作为独立短段落
    text = header + "\n\n" + body + "\n\n" + header + "\n\n" + body + "\n\n" + header
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["general"])
    # 短页眉不应作为独立 chunk 出现
    for c in chunks:
        assert c.text.strip() != header, f"页眉未被过滤: {c.text!r}"


def test_chunk_filter_keeps_normal_short_chunk():
    """正常短 chunk(如表格 chunk)不应被误杀。"""
    text = "概述文本。\n\n| 项目 | 金额 |\n|---|---|\n| 营收 | 100 |\n\n后续文本。"
    doc = ParsedDocument(
        file_path="x", mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
        tables=[ParsedTable(page_no=1, rows=[["项目", "金额"], ["营收", "100"]])],
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["annual_report"])
    # 表格 chunk 应保留
    has_table = any("营收" in c.text or "|" in c.text for c in chunks)
    assert has_table, "表格 chunk 被误杀"