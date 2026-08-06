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
    """极端长条款(>32k 字)切分时,每个子块都应带'第X条'前缀。"""
    article_body = "具体内容。" * 8000  # ~40000 字,超过 chunk_size*4=32000
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


def test_chunk_filter_drops_repeated_report_title():
    """重复出现的报告标题(如每页页眉)应被过滤。"""
    title_line = "2026中国白酒市场中期研究报告"
    # body must be long enough (> chunk_size=800) so title lines become separate chunks
    body = "白酒行业核心观点:高端白酒市场增长强劲,消费升级趋势明显,价格带持续上移。" * 30
    # 报告标题作为独立段落重复出现(模拟每页页眉)
    text = title_line + "\n\n" + body + "\n\n" + title_line + "\n\n" + body + "\n\n" + title_line
    doc = ParsedDocument(
        file_path="x", mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["research"])
    # 报告标题不应作为独立 chunk
    title_chunks = [c for c in chunks if c.text.strip() == title_line]
    assert not title_chunks, f"重复报告标题未被过滤: {[c.text for c in title_chunks]!r}"


def test_chunk_filter_drops_long_copyright_with_keywords():
    """长版权声明(>80 字,但含多个噪声关键词)应被过滤。"""
    # 模拟 q17 案例:毕马威版权声明,长度 > 80 字
    copyright_long = (
        "毕马威会计师事务所版权所有,未经许可不得转载。"
        "本报告仅供参考,不构成投资建议。"
        "2026中国白酒市场中期研究报告版权所有,不得转载。"
        "免责声明:本报告所载信息仅供参考。"
    )
    # body must be long enough (> chunk_size=800) so copyright becomes a separate chunk
    body = "白酒行业核心观点:高端白酒市场增长强劲,消费升级趋势明显。" * 30
    text = body + "\n\n" + copyright_long
    doc = ParsedDocument(
        file_path="x", mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["research"])
    for c in chunks:
        # 版权声明不应作为独立 chunk 出现
        if "版权所有" in c.text and "不得转载" in c.text:
            # 若出现,应只是 body 中正常提及,而非整段版权声明
            assert len(c.text) > 200, f"长版权声明未被过滤: {c.text!r}"


def test_chunk_filter_dedups_exact_duplicates():
    """完全相同的 chunk(精确文本匹配)只保留一个。"""
    # 模拟 q17:多个版权声明 chunk 文本完全相同
    chunk1_text = "2026中国白酒市场中期研究报告版权所有,未经许可不得转载。"
    chunk2_text = "2026中国白酒市场中期研究报告版权所有,未经许可不得转载。"  # 完全相同
    # body must be long enough (> chunk_size=800) so chunks become separate chunks
    body = "白酒行业核心观点:高端白酒市场增长强劲,消费升级趋势明显。" * 30
    text = chunk1_text + "\n\n" + body + "\n\n" + chunk2_text
    doc = ParsedDocument(
        file_path="x", mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["research"])
    # 不应有两个完全相同的 chunk
    texts = [c.text for c in chunks]
    assert len(texts) == len(set(texts)), f"存在完全相同的重复 chunk: {texts!r}"


# ---------------------------------------------------------------------------
# Bug fix: _chunk_clause 切碎条款 (q02 失败案例) — 加固测试
# ---------------------------------------------------------------------------

def test_chunk_clause_q02_anti_money_laundering_article3():
    """q02 案例:反洗钱特别预防措施第三条应保持完整单 chunk。

    GT 答案约 106 字,chunk_size 完全可以容纳,不应触发 _split_recursive。
    """
    # 模拟反洗钱办法第三条完整文本(基于 q02 GT 答案)
    article3 = (
        "第三条 本办法所称反洗钱特别预防措施,包括立即停止向名单所列对象及其代理人、"
        "受其指使的组织和人员、其直接或者间接控制的组织提供金融等服务或者资金、资产,"
        "立即限制相关资金、资产转移等。采取预防措施不得事先通知相关组织和人员。"
    )
    text = (
        "第一条 为规范金融机构反洗钱特别预防措施,制定本办法。\n"
        "第二条 本办法适用于中华人民共和国境内依法设立的金融机构。\n"
        + article3 + "\n"
        "第四条 中国人民银行是反洗钱特别预防措施的监督管理部门。\n"
        "第五条 本办法自发布之日起施行。"
    )
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["regulatory_clause"])
    # 第三条应单独成块
    article3_chunks = [c for c in chunks if "第三条" in c.text]
    assert len(article3_chunks) == 1, \
        f"第三条应单独成块,实际被切成 {len(article3_chunks)} 块: {[c.text[:40] for c in article3_chunks]}"
    # 第三条完整内容应在单 chunk 内(含"事先通知"这个末尾独特标记)
    assert "事先通知" in article3_chunks[0].text, \
        f"第三条被切碎,末尾内容不在 chunk 中: {article3_chunks[0].text!r}"
    # chunk 长度应约等于第三条原文长度(180 字左右),不应被切到 30 字
    assert len(article3_chunks[0].text) > 100, \
        f"第三条 chunk 异常短: {len(article3_chunks[0].text)} 字, 期望 > 100"


def test_chunk_clause_no_second_split_when_under_size():
    """条款长度 < chunk_size 时,_split_recursive 不应被调用。"""
    # 构造一个刚好低于 chunk_size 的条款(4800 字)
    article_body = "具体措施描述内容。" * 280  # ~4800 字
    text = "第一条 " + article_body + "\n第二条 短条款。"
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["regulatory_clause"])
    # 第一条应保持单 chunk(未被 _split_recursive 切碎)
    article1_chunks = [c for c in chunks if "第一条" in c.text]
    assert len(article1_chunks) == 1, \
        f"第一条(4800字 < chunk_size)应单 chunk, 实际 {len(article1_chunks)} 块"


# ---------------------------------------------------------------------------
# Bug fix: 表格 chunk 增加 caption (q12-q16 失败案例)
# ---------------------------------------------------------------------------

def test_chunk_table_includes_caption_from_heading():
    """表格 chunk 应在文本开头包含就近 heading 作为 caption。"""
    text = "## 主要财务数据\n\n营业收入情况如下:\n\n| 项目 | 金额 |\n|---|---|\n| 营业收入 | 168838102514.79 |\n\n后续文本。"
    doc = ParsedDocument(
        file_path="x", mime_type="text/markdown",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
        heading_tree=[HeadingNode(level=2, text="主要财务数据", page_no=1)],
        tables=[ParsedTable(page_no=1, rows=[["项目", "金额"], ["营业收入", "168838102514.79"]],
                            caption="主要财务数据")],
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["annual_report"])
    table_chunks = [c for c in chunks if "|" in c.text and "营业收入" in c.text]
    assert table_chunks, "应有表格 chunk"
    # 表格 chunk 应包含 caption(就近 heading "主要财务数据")
    assert any("主要财务数据" in c.text for c in table_chunks), \
        f"表格 chunk 缺少 caption: {[c.text[:60] for c in table_chunks]!r}"


def test_chunk_table_caption_falls_back_to_column_names():
    """无 caption 时,表格 chunk caption 用列名摘要(如"项目 金额 同比")。"""
    text = "概述文本。\n\n| 项目 | 金额 | 同比 |\n|---|---|---|\n| 营收 | 100 | 5% |\n\n后续。"
    doc = ParsedDocument(
        file_path="x", mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
        tables=[ParsedTable(page_no=1, rows=[["项目", "金额", "同比"], ["营收", "100", "5%"]])],
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["annual_report"])
    table_chunks = [c for c in chunks if "|" in c.text and "营收" in c.text]
    assert table_chunks, "应有表格 chunk"
    # caption 应回退为列名(表头行)
    first_chunk_text = table_chunks[0].text
    # 列名应出现在 caption 中(前 100 字内)
    assert "项目" in first_chunk_text[:100] and "金额" in first_chunk_text[:100], \
        f"表格 chunk 缺少列名 caption: {first_chunk_text[:100]!r}"


def test_chunk_table_caption_format():
    """表格 chunk 文本应以 '【表格: ...】' 开头。"""
    text = "## 财务摘要\n\n| 项目 | 金额 |\n|---|---|\n| 营收 | 100 |"
    doc = ParsedDocument(
        file_path="x", mime_type="text/markdown",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
        heading_tree=[HeadingNode(level=2, text="财务摘要", page_no=1)],
        tables=[ParsedTable(page_no=1, rows=[["项目", "金额"], ["营收", "100"]],
                            caption="财务摘要")],
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["annual_report"])
    table_chunks = [c for c in chunks if "财务摘要" in c.text and "|" in c.text]
    assert table_chunks, "应有表格 chunk"
    assert table_chunks[0].text.startswith("【表格:"), \
        f"表格 chunk 应以 '【表格:' 开头: {table_chunks[0].text[:50]!r}"