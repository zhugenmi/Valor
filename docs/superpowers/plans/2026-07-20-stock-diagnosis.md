# 股票诊断（会话化）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把组合详情页持仓行的"诊断"按钮从跳转 `/analysis` 改为开新会话，等价于用户问 ValorAgent "诊断股票xxx"；会话内实时呈现 9 节点诊断过程（可折叠），用最近交易日数据（先查库缺则补齐），并把用户在该组合中该股的持仓量 + 组合现金注入 portfolio_manager 给出组合决策；会话全量持久化到 SQLite。

**Architecture:** 后端在 `valor/server/routes/stream.py` 的 SSE 入口扩展 `portfolio_id` + `ticker` 字段，注入 `portfolio_manager` 所需的 `{cash, stock}`；新增 `valor/conversations/` 模块（SQLite 持久化 + REST API）替代 stubs。前端把 `/analysis` 页的 ProgressBar / AgentCard / DecisionPanel 抽到共享目录，会话 store 增加 `workflow_started` / `agent_completed` / `data_preflight` 事件分支，新增 `diagnosis_section` ChatItem 类型 + 折叠渲染器。

**Tech Stack:** Python 3.12 / FastAPI / LangGraph / SQLite（后端）；React 19 / Vite / TypeScript / Zustand / React Query / React Router v7（前端）。

## Global Constraints

- Python 代码 `from __future__ import annotations` 顶部强制；类型提示必填。
- 后端 Lint：`uv run ruff check valor/ tests/` 必须零警告。
- 后端测试：`uv run pytest tests/<file>::test_name -v` 单测，`uv run pytest tests/` 全测。
- 前端类型检查：`cd frontend && bun run typecheck` 必须通过。
- 提交规范：`feat(scope): ...` / `fix(scope): ...` / `refactor(scope): ...`，**不要**在 commit message 末尾加 `Co-Authored-By` 行（用户全局偏好）。
- gitignore 冲突用 `git add -f` 绕过，不修复 gitignore 配置。
- SSE 事件序列化复用 `valor/server/routes/stream.py` 现有 `_sse()` / `_clean_nan()` / `_serialize_state()`，不重写。
- 持仓上下文 schema 严格保持 `{cash: float, stock: int}`，不改 `portfolio_manager` prompt。
- 不动 `/analysis` 页面行为，仅抽取组件位置。

---

## 文件结构总览

### 新建

| 文件 | 责任 |
|---|---|
| `python/valor/conversations/__init__.py` | 模块导出 |
| `python/valor/conversations/models.py` | Pydantic 模型：`Conversation`、`ConversationMessage` |
| `python/valor/conversations/storage.py` | SQLite CRUD |
| `python/valor/conversations/routes.py` | FastAPI router，挂 `/api/v1/conversations` |
| `python/valor/server/portfolio_context.py` | `load_portfolio_context(portfolio_id, ticker) -> dict` |
| `python/valor/server/data_preflight.py` | `ensure_latest_trading_day_data(ticker) -> dict` |
| `python/tests/unit/test_conversations_storage.py` | 存储层测试 |
| `python/tests/api/test_conversations.py` | REST API 测试 |
| `python/tests/unit/test_portfolio_context.py` | 持仓上下文测试 |
| `python/tests/unit/test_data_preflight.py` | 预补齐测试 |
| `python/tests/unit/test_akshare_cache_latest_trading_day.py` | `get_latest_trading_day` 测试 |
| `python/tests/unit/test_intent_diagnosis.py` | 意图分类测试 |
| `frontend/src/app/analysis/components/ProgressBar.tsx` | 抽取 |
| `frontend/src/app/analysis/components/AgentCard.tsx` | 抽取 |
| `frontend/src/app/analysis/components/DecisionPanel.tsx` | 抽取 |
| `frontend/src/app/agent/components/agent-view/diagnosis-section.tsx` | 折叠诊断区块渲染器 |

### 修改

| 文件 | 改动 |
|---|---|
| `python/valor/adapters/data/akshare_cache.py` | 新增 `get_latest_trading_day()` |
| `python/valor/agents/market_data.py` | `end_date` 默认改用 `get_latest_trading_day()` |
| `python/valor/server/intent.py` | `_SYSTEM_PROMPT` 增加"诊断"示例 |
| `python/valor/server/routes/stream.py` | 接收 `portfolio_id` + `ticker`、注入持仓、发 `data_preflight`、持久化 |
| `python/valor/server/routes/stubs.py` | 删除会话相关 4 个端点 |
| `python/valor/server/main.py` | 挂载 `conversations_router` |
| `python/valor/server/db.py` | `_SCHEMA` 追加 `conversations` / `conversation_messages` 表 |
| `frontend/src/app/analysis/index.tsx` | 改为引用 `./components/...` |
| `frontend/src/types/agent.ts` | 增加 `diagnosis_section` 类型；扩展 `AgentStreamRequest` |
| `frontend/src/constants/agent.ts` | `AGENT_COMPONENT_TYPE` 追加 `diagnosis_section` |
| `frontend/src/lib/agent-store.ts` | 新增 `workflow_started` / `agent_completed` / `data_preflight` 分支 |
| `frontend/src/components/valuecell/renderer.tsx` | 注册 `DiagnosisSectionRenderer` |
| `frontend/src/app/portfolio/components/HoldingsTable.tsx` | 诊断按钮改 `navigate` |
| `frontend/src/app/agent/components/agent-view/common-agent-area.tsx` | 读取 `state.portfolioId` / `state.ticker` 注入 SSE body |
| `frontend/src/api/conversation.ts` | 响应 shape 对齐（如需） |

---

## Task 1: `get_latest_trading_day()` 工具函数

**Files:**
- Modify: `python/valor/adapters/data/akshare_cache.py`（文件末尾追加）
- Test: `python/tests/unit/test_akshare_cache_latest_trading_day.py`

**Interfaces:**
- Consumes: `query_trade_dates(start, end)` from `valor.adapters.data.baostock_client`
- Produces: `get_latest_trading_day(today: date | None = None) -> date` —— 返回 `<= today` 的最近一个 A 股交易日

- [ ] **Step 1: 写失败测试**

新建 `python/tests/unit/test_akshare_cache_latest_trading_day.py`：

```python
"""Tests for get_latest_trading_day. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd

from valor.adapters.data.akshare_cache import get_latest_trading_day


def _mock_trade_dates(start: date, end: date) -> pd.DataFrame:
    """Return a fake trade calendar where 2026-07-17 (Fri) is the last trading day
    on or before 2026-07-20 (Mon). 2026-07-18/19 are weekend."""
    rows = []
    d = pd.Timestamp(start)
    while d <= pd.Timestamp(end):
        is_trading = d.weekday() < 5  # Mon-Fri
        rows.append({"calendar_date": d.strftime("%Y-%m-%d"), "is_trading_day": int(is_trading)})
        d += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


def test_saturday_returns_friday():
    """周六 (2026-07-18) 诊断应返回周五 (2026-07-17)."""
    with patch(
        "valor.adapters.data.akshare_cache.query_trade_dates",
        side_effect=_mock_trade_dates,
    ):
        result = get_latest_trading_day(date(2026, 7, 18))
    assert result == date(2026, 7, 17)


def test_sunday_returns_friday():
    with patch(
        "valor.adapters.data.akshare_cache.query_trade_dates",
        side_effect=_mock_trade_dates,
    ):
        result = get_latest_trading_day(date(2026, 7, 19))
    assert result == date(2026, 7, 17)


def test_monday_returns_monday_if_trading():
    """周一 (2026-07-20) 是交易日，应返回自身."""
    with patch(
        "valor.adapters.data.akshare_cache.query_trade_dates",
        side_effect=_mock_trade_dates,
    ):
        result = get_latest_trading_day(date(2026, 7, 20))
    assert result == date(2026, 7, 20)


def test_none_defaults_to_today():
    """today=None 应使用 date.today()，不抛异常."""
    with patch(
        "valor.adapters.data.akshare_cache.query_trade_dates",
        side_effect=_mock_trade_dates,
    ):
        result = get_latest_trading_day()
    assert isinstance(result, date)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_akshare_cache_latest_trading_day.py -v
```
预期：`ImportError: cannot import name 'get_latest_trading_day'`

- [ ] **Step 3: 实现 `get_latest_trading_day`**

在 `python/valor/adapters/data/akshare_cache.py` 文件末尾追加：

```python
def get_latest_trading_day(today: Optional["date"] = None) -> "date":
    """Return the most recent A-share trading day on or before `today`.

    Looks back up to 30 calendar days to skip weekends/holidays. Falls back
    to the most recent weekday if the trade calendar fetch fails entirely.
    """
    from datetime import date as _date, timedelta

    today = today or _date.today()
    start = today - timedelta(days=30)
    try:
        df = query_trade_dates(start, today)
        if df is None or df.empty:
            raise RuntimeError("query_trade_dates returned empty")
        df["calendar_date"] = pd.to_datetime(df["calendar_date"])
        trading = df[df["is_trading_day"].astype(int) == 1]["calendar_date"].dt.normalize()
        trading_days = sorted(trading.tolist())
        today_ts = pd.Timestamp(today).normalize()
        for day in reversed(trading_days):
            if day <= today_ts:
                return day.date()
        # All trade dates in window are after today (unlikely); fall through
    except Exception as exc:
        logger.warning("⚠️ get_latest_trading_day 查询交易日历失败，降级最近工作日: %s", exc)

    # Fallback: most recent weekday <= today
    d = today
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d
```

并在文件顶部 `from datetime import datetime` 改为 `from datetime import date, datetime`（若 `date` 尚未导入）。同步更新 typing 使用处。

- [ ] **Step 4: 运行测试验证通过**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_akshare_cache_latest_trading_day.py -v
```
预期：4 passed

- [ ] **Step 5: Lint**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run ruff check valor/adapters/data/akshare_cache.py tests/unit/test_akshare_cache_latest_trading_day.py
```
预期：零警告

- [ ] **Step 6: 提交**

```bash
git add python/valor/adapters/data/akshare_cache.py python/tests/unit/test_akshare_cache_latest_trading_day.py
git commit -m "feat(data): add get_latest_trading_day helper"
```

---

## Task 2: `market_data_agent` 默认用最近交易日

**Files:**
- Modify: `python/valor/agents/market_data.py:24-32`
- Test: `python/tests/unit/test_market_data_agent_latest_day.py`

**Interfaces:**
- Consumes: `get_latest_trading_day` from Task 1
- Produces: `market_data_agent` 默认 `end_date` 为最近交易日（非 yesterday）

- [ ] **Step 1: 写失败测试**

新建 `python/tests/unit/test_market_data_agent_latest_day.py`：

```python
"""Test market_data_agent uses latest trading day for end_date. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from valor.agents.market_data import market_data_agent


def _build_state(end_date=None):
    return {
        "messages": [],
        "data": {
            "ticker": "600519",
            "start_date": None,
            "end_date": end_date,
        },
        "metadata": {"show_reasoning": False},
    }


def test_default_end_date_uses_latest_trading_day():
    """If data.end_date is None, agent should resolve to get_latest_trading_day(),
    not just yesterday. On 2026-07-18 (Sat) -> 2026-07-17 (Fri)."""
    fake_today = date(2026, 7, 18)
    captured = {}

    def _capture_state(_state):
        captured["end_date"] = _state["data"]["end_date"]
        return None

    with (
        patch("valor.agents.market_data.get_price_history", side_effect=_capture_state),
        patch("valor.agents.market_data.get_market_data", return_value=None),
        patch("valor.agents.market_data.get_financial_metrics", return_value=None),
        patch("valor.agents.market_data.get_financial_statements", return_value=None),
        patch("valor.agents.market_data.get_market_snapshot", return_value=None),
        patch(
            "valor.adapters.data.akshare_cache.get_latest_trading_day",
            return_value=date(2026, 7, 17),
        ),
        patch("valor.agents.market_data.datetime") as mock_dt,
    ):
        from datetime import datetime as real_dt
        mock_dt.now.return_value = real_dt(2026, 7, 18, 10, 0, 0)
        mock_dt.side_effect = real_dt
        mock_dt.strptime = real_dt.strptime

        market_data_agent(_build_state(end_date=None))

    assert captured["end_date"] == "2026-07-17"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_market_data_agent_latest_day.py -v
```
预期：FAIL，`captured["end_date"]` 实际是 `2026-07-17`（yesterday）→ 断言失败

- [ ] **Step 3: 修改 `market_data_agent`**

在 `python/valor/agents/market_data.py` 顶部 import 块追加：

```python
from valor.adapters.data.akshare_cache import get_latest_trading_day
```

替换 `market_data_agent` 函数第 24-32 行（默认 end_date 计算）为：

```python
    # Set default dates: use most recent A-share trading day (skips weekends/holidays)
    current_date = datetime.now()
    if data["end_date"]:
        end_date = data["end_date"]
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        latest = get_latest_trading_day(current_date.date())
        end_date = latest.strftime('%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')

    # Ensure end_date is not in the future
    today = current_date.date()
    if end_date_obj.date() > today:
        latest = get_latest_trading_day(today)
        end_date = latest.strftime('%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
```

（删除原 `yesterday` 变量及对应比较）

- [ ] **Step 4: 运行测试验证通过**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_market_data_agent_latest_day.py -v
```
预期：1 passed

- [ ] **Step 5: 跑相关回归测试**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_workflow.py -v
```
预期：无回归

- [ ] **Step 6: Lint + 提交**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run ruff check valor/agents/market_data.py tests/unit/test_market_data_agent_latest_day.py
git add python/valor/agents/market_data.py python/tests/unit/test_market_data_agent_latest_day.py
git commit -m "refactor(market_data): default end_date to latest trading day"
```

---

## Task 3: Intent classifier 识别"诊断"关键词

**Files:**
- Modify: `python/valor/server/intent.py:33-54`（`_SYSTEM_PROMPT`）
- Test: `python/tests/unit/test_intent_diagnosis.py`

**Interfaces:**
- Consumes: 无
- Produces: `classify_intent("诊断股票600519")` 返回 `IntentResult(intent="full_analysis", ticker="600519")`

- [ ] **Step 1: 写失败测试**

新建 `python/tests/unit/test_intent_diagnosis.py`：

```python
"""Test intent classifier recognizes 诊断 keyword. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from valor.server.intent import classify_intent


async def _mock_chat(**_kwargs):
    return '{"intent": "full_analysis", "ticker": "600519", "agent": null, "reply": null}'


async def test_diagnosis_keyword_triggers_full_analysis():
    with patch("valor.server.intent.get_llm_provider") as mock_provider:
        mock_provider.return_value.chat = AsyncMock(side_effect=_mock_chat)
        result = await classify_intent("诊断股票600519")
    assert result.intent == "full_analysis"
    assert result.ticker == "600519"
    assert result.agent is None


async def test_diagnosis_fallback_regex():
    """When LLM unavailable, regex fallback should still extract ticker."""
    with patch("valor.server.intent.get_llm_provider", side_effect=RuntimeError("no provider")):
        result = await classify_intent("诊断股票600519")
    assert result.intent == "full_analysis"
    assert result.ticker == "600519"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_intent_diagnosis.py -v
```
预期：第一个 test 可能 pass（mock 不依赖 prompt）；第二个 test 应 pass（regex fallback 已能识别）。若都 pass，则 prompt 已足够 — 跳到 Step 4。若失败，继续 Step 3。

- [ ] **Step 3: 在 prompt 中加入"诊断"示例**

修改 `python/valor/server/intent.py` 的 `_SYSTEM_PROMPT`，在 `full_analysis` 规则行追加示例：

```
- full_analysis：用户要求全面分析某只股票（如"分析600519"、"贵州茅台值得买吗"、"600519怎么样"、"诊断股票600519"）。ticker提取6位A股代码。
```

并在底部示例区追加一行：

```
输入"诊断股票600519" -> {"intent":"full_analysis","ticker":"600519","agent":null,"reply":null}
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_intent_diagnosis.py -v
```
预期：2 passed

- [ ] **Step 5: 跑现有 intent 测试回归**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_intent.py -v 2>/dev/null || echo "no existing test_intent.py, skip"
```

- [ ] **Step 6: Lint + 提交**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run ruff check valor/server/intent.py tests/unit/test_intent_diagnosis.py
git add python/valor/server/intent.py python/tests/unit/test_intent_diagnosis.py
git commit -m "feat(intent): recognize 诊断 keyword as full_analysis"
```

---

## Task 4: 持仓上下文加载器

**Files:**
- Create: `python/valor/server/portfolio_context.py`
- Test: `python/tests/unit/test_portfolio_context.py`

**Interfaces:**
- Consumes: `load_portfolio(portfolio_id)` from `valor.portfolio.storage`
- Produces: `load_portfolio_context(portfolio_id: str, ticker: str) -> dict` 返回 `{"cash": float, "stock": int}`；组合不存在时抛 `PortfolioNotFound`；ticker 不在 holdings 中时 `stock=0`

- [ ] **Step 1: 写失败测试**

新建 `python/tests/unit/test_portfolio_context.py`：

```python
"""Tests for portfolio_context loader. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from valor.portfolio.models import Holding, Lot, Portfolio
from valor.portfolio.storage import PortfolioNotFound
from valor.server.portfolio_context import load_portfolio_context


def _build_portfolio(cash: float, holdings: list[Holding]) -> Portfolio:
    return Portfolio(
        portfolio_id="pf_test1",
        name="test",
        cash=Decimal(str(cash)),
        holdings=holdings,
        lots=[],
        sell_lots=[],
        strategies=[],
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def _build_holding(ticker: str, qty: int) -> Holding:
    return Holding(ticker=ticker, name=ticker, quantity=qty, lots=[], sell_lots=[])


def test_returns_cash_and_stock_quantity():
    pf = _build_portfolio(50000.0, [_build_holding("600519", 100), _build_holding("000001", 200)])
    with patch("valor.server.portfolio_context.load_portfolio", return_value=pf):
        result = load_portfolio_context("pf_test1", "600519")
    assert result == {"cash": 50000.0, "stock": 100}


def test_ticker_not_in_holdings_returns_zero_stock():
    pf = _build_portfolio(50000.0, [_build_holding("000001", 200)])
    with patch("valor.server.portfolio_context.load_portfolio", return_value=pf):
        result = load_portfolio_context("pf_test1", "600519")
    assert result == {"cash": 50000.0, "stock": 0}


def test_portfolio_not_found_propagates():
    with patch(
        "valor.server.portfolio_context.load_portfolio",
        side_effect=PortfolioNotFound("pf_missing"),
    ):
        with pytest.raises(PortfolioNotFound):
            load_portfolio_context("pf_missing", "600519")


def test_aggregates_quantity_across_lots():
    """quantity comes from Holding.quantity which already aggregates lots; verify
    we read that field, not the lots array."""
    h = _build_holding("600519", 350)
    pf = _build_portfolio(0.0, [h])
    with patch("valor.server.portfolio_context.load_portfolio", return_value=pf):
        result = load_portfolio_context("pf_test1", "600519")
    assert result["stock"] == 350
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_portfolio_context.py -v
```
预期：`ImportError: No module named 'valor.server.portfolio_context'`

- [ ] **Step 3: 实现**

新建 `python/valor/server/portfolio_context.py`：

```python
"""Load portfolio context for the workflow's portfolio_manager node.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial.
"""
from __future__ import annotations

from decimal import Decimal

from valor.portfolio.storage import PortfolioNotFound, load_portfolio


def load_portfolio_context(portfolio_id: str, ticker: str) -> dict:
    """Return {'cash': float, 'stock': int} for the given portfolio + ticker.

    Raises PortfolioNotFound if portfolio_id doesn't exist.
    stock is the holding's quantity for ticker (0 if not held).
    """
    pf = load_portfolio(portfolio_id)
    cash = float(pf.cash) if isinstance(pf.cash, Decimal) else float(pf.cash or 0.0)
    stock = 0
    for h in pf.holdings:
        if h.ticker == ticker:
            stock = int(h.quantity or 0)
            break
    return {"cash": cash, "stock": stock}


__all__ = ["load_portfolio_context", "PortfolioNotFound"]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_portfolio_context.py -v
```
预期：4 passed

- [ ] **Step 5: Lint + 提交**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run ruff check valor/server/portfolio_context.py tests/unit/test_portfolio_context.py
git add python/valor/server/portfolio_context.py python/tests/unit/test_portfolio_context.py
git commit -m "feat(server): add portfolio context loader"
```

---

## Task 5: 最近交易日预补齐

**Files:**
- Create: `python/valor/server/data_preflight.py`
- Test: `python/tests/unit/test_data_preflight.py`

**Interfaces:**
- Consumes: `get_latest_trading_day` (Task 1) + `get_price_history_df` from `valor.adapters.data.akshare_cache`
- Produces: `ensure_latest_trading_day_data(ticker: str) -> dict` 返回 `{"trading_day": "YYYY-MM-DD", "filled": bool}`。`filled=True` 表示本次实际拉取了数据，`False` 表示缓存已命中

- [ ] **Step 1: 写失败测试**

新建 `python/tests/unit/test_data_preflight.py`：

```python
"""Tests for data_preflight. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from valor.server.data_preflight import ensure_latest_trading_day_data


def test_returns_filled_false_when_cache_has_latest_day():
    """Cache already contains 2026-07-17 -> filled=False, no fetch."""
    cached_df = pd.DataFrame({"date": [pd.Timestamp("2026-07-17")]})
    with (
        patch(
            "valor.server.data_preflight.get_latest_trading_day",
            return_value=date(2026, 7, 17),
        ),
        patch("valor.server.data_preflight.cache") as mock_cache,
    ):
        mock_cache.fetch_records.return_value = [{"date": "2026-07-17"}]
        result = ensure_latest_trading_day_data("600519")
    assert result == {"trading_day": "2026-07-17", "filled": False}


def test_returns_filled_true_when_cache_missing():
    """Cache doesn't have 2026-07-17 -> trigger get_price_history_df, filled=True."""
    with (
        patch(
            "valor.server.data_preflight.get_latest_trading_day",
            return_value=date(2026, 7, 17),
        ),
        patch("valor.server.data_preflight.cache") as mock_cache,
        patch("valor.server.data_preflight.get_price_history_df") as mock_fetch,
    ):
        mock_cache.fetch_records.return_value = []
        mock_fetch.return_value = pd.DataFrame({"date": [pd.Timestamp("2026-07-17")]})
        result = ensure_latest_trading_day_data("600519")
    assert result == {"trading_day": "2026-07-17", "filled": True}
    # Verify fetch was called with a window ending at 2026-07-17
    args, kwargs = mock_fetch.call_args
    assert kwargs.get("end_date") or args[2]  # end_date positional or kw


def test_returns_filled_true_even_if_fetch_returns_empty():
    """If fetch returns empty (source unavailable), still report filled=True so
    the UI knows we attempted. Workflow may then run with stale cache."""
    with (
        patch(
            "valor.server.data_preflight.get_latest_trading_day",
            return_value=date(2026, 7, 17),
        ),
        patch("valor.server.data_preflight.cache") as mock_cache,
        patch("valor.server.data_preflight.get_price_history_df", return_value=pd.DataFrame()),
    ):
        mock_cache.fetch_records.return_value = []
        result = ensure_latest_trading_day_data("600519")
    assert result == {"trading_day": "2026-07-17", "filled": True}
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_data_preflight.py -v
```
预期：`ImportError: No module named 'valor.server.data_preflight'`

- [ ] **Step 3: 实现**

新建 `python/valor/server/data_preflight.py`：

```python
"""Pre-flight check: ensure latest trading day's K-line data exists in cache.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict

from valor.adapters.data.akshare_cache import (
    HISTORY_TABLE,
    cache,
    get_latest_trading_day,
    get_price_history_df,
)


def ensure_latest_trading_day_data(ticker: str) -> Dict[str, object]:
    """Check if latest trading day's K-line for `ticker` is cached; fetch if missing.

    Returns:
        {"trading_day": "YYYY-MM-DD", "filled": bool}
        - filled=True: data was missing, we attempted to fetch
        - filled=False: cache already had the latest trading day
    """
    latest = get_latest_trading_day()
    latest_str = latest.strftime("%Y-%m-%d")

    cached = cache.fetch_records(
        table=HISTORY_TABLE,
        filters={"symbol": ticker, "date": latest_str},
        limit=1,
    )
    if cached:
        return {"trading_day": latest_str, "filled": False}

    # Trigger incremental fetch over a 10-day window ending at latest
    start = latest - timedelta(days=10)
    try:
        get_price_history_df(
            symbol=ticker,
            start_date=datetime.combine(start, datetime.min.time()),
            end_date=datetime.combine(latest, datetime.min.time()),
        )
    except Exception:
        # Best-effort; workflow will run with whatever cache exists
        pass
    return {"trading_day": latest_str, "filled": True}


__all__ = ["ensure_latest_trading_day_data"]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_data_preflight.py -v
```
预期：3 passed

- [ ] **Step 5: Lint + 提交**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run ruff check valor/server/data_preflight.py tests/unit/test_data_preflight.py
git add python/valor/server/data_preflight.py python/tests/unit/test_data_preflight.py
git commit -m "feat(server): add latest trading day pre-flight check"
```

---

## Task 6: 会话持久化存储层

**Files:**
- Create: `python/valor/conversations/__init__.py`、`python/valor/conversations/models.py`、`python/valor/conversations/storage.py`
- Modify: `python/valor/server/db.py`（追加 schema）
- Test: `python/tests/unit/test_conversations_storage.py`

**Interfaces:**
- Consumes: `get_conn` from `valor.server.db`
- Produces:
  - `Conversation` Pydantic 模型
  - `ConversationMessage` Pydantic 模型
  - `create_conversation(conv: Conversation) -> None`
  - `append_message(msg: ConversationMessage) -> None`
  - `list_conversations(limit=50) -> list[Conversation]`
  - `get_messages(conversation_id: str) -> list[ConversationMessage]`
  - `delete_conversation(conversation_id: str) -> bool`
  - `update_conversation_status(conversation_id: str, status: str) -> None`

- [ ] **Step 1: 写失败测试**

新建 `python/tests/unit/test_conversations_storage.py`：

```python
"""Tests for conversations storage. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from valor.conversations.models import Conversation, ConversationMessage
from valor.conversations.storage import (
    append_message,
    create_conversation,
    delete_conversation,
    get_messages,
    list_conversations,
    update_conversation_status,
)


def _conn_factory():
    """Use in-memory SQLite per-test."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture
def fresh_db():
    """Patch get_conn to yield an in-memory DB with schema applied."""
    schema = """
    CREATE TABLE conversations (
      id TEXT PRIMARY KEY,
      agent_name TEXT NOT NULL,
      title TEXT,
      status TEXT NOT NULL,
      portfolio_id TEXT,
      ticker TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE conversation_messages (
      id TEXT PRIMARY KEY,
      conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
      role TEXT NOT NULL,
      event_type TEXT,
      content TEXT,
      created_at TEXT NOT NULL,
      seq INTEGER NOT NULL
    );
    """
    conn = sqlite3.connect(":memory:") if False else _conn_factory()
    conn.executescript(schema)
    yield conn
    conn.close()


def _patch_conn(fresh_db):
    from contextlib import contextmanager

    @contextmanager
    def fake_conn():
        yield fresh_db

    return patch("valor.conversations.storage.get_conn", fake_conn)


def test_create_and_list_conversation(fresh_db):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title="诊断 600519",
        status="active", portfolio_id="pf_1", ticker="600519",
        created_at=now, updated_at=now,
    )
    with _patch_conn(fresh_db):
        create_conversation(conv)
        result = list_conversations()
    assert len(result) == 1
    assert result[0].id == "c1"
    assert result[0].portfolio_id == "pf_1"
    assert result[0].ticker == "600519"


def test_append_message_and_get_messages(fresh_db):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title=None,
        status="active", portfolio_id=None, ticker=None,
        created_at=now, updated_at=now,
    )
    with _patch_conn(fresh_db):
        create_conversation(conv)
        m1 = ConversationMessage(
            id="m1", conversation_id="c1", role="user", event_type="message",
            content="诊断股票600519", created_at=now, seq=1,
        )
        m2 = ConversationMessage(
            id="m2", conversation_id="c1", role="assistant", event_type="agent_completed",
            content='{"agent":"technicals"}', created_at=now, seq=2,
        )
        append_message(m1)
        append_message(m2)
        msgs = get_messages("c1")
    assert [m.seq for m in msgs] == [1, 2]
    assert msgs[0].content == "诊断股票600519"


def test_delete_conversation_cascades_messages(fresh_db):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title=None,
        status="active", portfolio_id=None, ticker=None,
        created_at=now, updated_at=now,
    )
    with _patch_conn(fresh_db):
        create_conversation(conv)
        append_message(ConversationMessage(
            id="m1", conversation_id="c1", role="user", event_type="message",
            content="hi", created_at=now, seq=1,
        ))
        deleted = delete_conversation("c1")
        assert deleted is True
        assert get_messages("c1") == []


def test_update_status(fresh_db):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title=None,
        status="active", portfolio_id=None, ticker=None,
        created_at=now, updated_at=now,
    )
    with _patch_conn(fresh_db):
        create_conversation(conv)
        update_conversation_status("c1", "completed")
        listed = list_conversations()
    assert listed[0].status == "completed"


def test_delete_nonexistent_returns_false(fresh_db):
    with _patch_conn(fresh_db):
        assert delete_conversation("nope") is False
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_conversations_storage.py -v
```
预期：`ImportError: No module named 'valor.conversations'`

- [ ] **Step 3: 创建 `valor/conversations/__init__.py`**

```python
"""Conversation persistence module. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.conversations.models import Conversation, ConversationMessage
from valor.conversations.storage import (
    append_message,
    create_conversation,
    delete_conversation,
    get_messages,
    list_conversations,
    update_conversation_status,
)

__all__ = [
    "Conversation",
    "ConversationMessage",
    "create_conversation",
    "append_message",
    "list_conversations",
    "get_messages",
    "delete_conversation",
    "update_conversation_status",
]
```

- [ ] **Step 4: 创建 `valor/conversations/models.py`**

```python
"""Pydantic models for conversation persistence. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from pydantic import BaseModel


class Conversation(BaseModel):
    id: str
    agent_name: str
    title: str | None = None
    status: str = "active"  # 'active' | 'completed' | 'failed'
    portfolio_id: str | None = None
    ticker: str | None = None
    created_at: str
    updated_at: str


class ConversationMessage(BaseModel):
    id: str
    conversation_id: str
    role: str  # 'user' | 'assistant' | 'system'
    event_type: str | None = None
    content: str | None = None
    created_at: str
    seq: int


__all__ = ["Conversation", "ConversationMessage"]
```

- [ ] **Step 5: 创建 `valor/conversations/storage.py`**

```python
"""SQLite CRUD for conversations. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import List

from valor.conversations.models import Conversation, ConversationMessage
from valor.server.db import get_conn


def create_conversation(conv: Conversation) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO conversations
               (id, agent_name, title, status, portfolio_id, ticker, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv.id, conv.agent_name, conv.title, conv.status,
             conv.portfolio_id, conv.ticker, conv.created_at, conv.updated_at),
        )


def append_message(msg: ConversationMessage) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO conversation_messages
               (id, conversation_id, role, event_type, content, created_at, seq)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (msg.id, msg.conversation_id, msg.role, msg.event_type,
             msg.content, msg.created_at, msg.seq),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), msg.conversation_id),
        )


def list_conversations(limit: int = 50) -> List[Conversation]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY datetime(updated_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [Conversation.model_validate(dict(r)) for r in rows]


def get_messages(conversation_id: str) -> List[ConversationMessage]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY seq ASC",
            (conversation_id,),
        ).fetchall()
    return [ConversationMessage.model_validate(dict(r)) for r in rows]


def delete_conversation(conversation_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        return cur.rowcount > 0


def update_conversation_status(conversation_id: str, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(UTC).isoformat(), conversation_id),
        )


__all__ = [
    "create_conversation",
    "append_message",
    "list_conversations",
    "get_messages",
    "delete_conversation",
    "update_conversation_status",
]
```

- [ ] **Step 6: 追加 SQLite schema**

在 `python/valor/server/db.py` 的 `_SCHEMA` 字符串末尾追加（在最后一个 `);` 之后）：

```sql

CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    agent_name   TEXT NOT NULL,
    title        TEXT,
    status       TEXT NOT NULL,
    portfolio_id TEXT,
    ticker       TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    event_type      TEXT,
    content         TEXT,
    created_at      TEXT NOT NULL,
    seq             INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON conversation_messages(conversation_id, seq);
```

- [ ] **Step 7: 运行测试验证通过**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/unit/test_conversations_storage.py -v
```
预期：5 passed

- [ ] **Step 8: Lint + 提交**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run ruff check valor/conversations/ tests/unit/test_conversations_storage.py valor/server/db.py
git add python/valor/conversations/ python/tests/unit/test_conversations_storage.py python/valor/server/db.py
git commit -m "feat(conversations): SQLite persistence layer"
```

---

## Task 7: 会话 REST API

**Files:**
- Create: `python/valor/conversations/routes.py`
- Test: `python/tests/api/test_conversations.py`

**Interfaces:**
- Consumes: 全部来自 Task 6 的 storage 函数
- Produces: FastAPI router with endpoints
  - `GET /api/v1/conversations/` -> `{code:0, data: {conversations: [...], total: int}, msg:'ok'}`
  - `GET /api/v1/conversations/{id}/history` -> `{code:0, data: {conversation_id, items: [...]}, msg:'ok'}`
  - `DELETE /api/v1/conversations/{id}` -> `{code:0, data: None, msg:'ok'}`

- [ ] **Step 1: 写失败测试**

新建 `python/tests/api/test_conversations.py`：

```python
"""Tests for conversations REST API. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from valor.conversations.models import Conversation, ConversationMessage
from valor.server.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_list_conversations_empty(client):
    with patch("valor.conversations.routes.list_conversations", return_value=[]):
        resp = client.get("/api/v1/conversations/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"conversations": [], "total": 0}


def test_list_conversations_returns_items(client):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title="诊断 600519",
        status="completed", portfolio_id="pf_1", ticker="600519",
        created_at=now, updated_at=now,
    )
    with patch("valor.conversations.routes.list_conversations", return_value=[conv]):
        resp = client.get("/api/v1/conversations/")
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["conversations"][0]["id"] == "c1"


def test_get_history(client):
    now = datetime.now(UTC).isoformat()
    msgs = [
        ConversationMessage(id="m1", conversation_id="c1", role="user",
                             event_type="message", content="hi",
                             created_at=now, seq=1),
    ]
    with patch("valor.conversations.routes.get_messages", return_value=msgs):
        resp = client.get("/api/v1/conversations/c1/history")
    body = resp.json()
    assert body["data"]["conversation_id"] == "c1"
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["content"] == "hi"


def test_delete_conversation(client):
    with patch("valor.conversations.routes.delete_conversation", return_value=True):
        resp = client.delete("/api/v1/conversations/c1")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/api/test_conversations.py -v
```
预期：FAIL（路由不存在，404）

- [ ] **Step 3: 实现 router**

新建 `python/valor/conversations/routes.py`：

```python
"""REST API routes for conversations. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from fastapi import APIRouter

from valor.conversations.storage import (
    delete_conversation as _delete_conversation,
    get_messages,
    list_conversations,
)

router = APIRouter(prefix="/api/v1", tags=["Conversations"])


@router.get("/conversations/")
async def list_conversations_route():
    items = list_conversations()
    return {
        "code": 0,
        "data": {
            "conversations": [c.model_dump() for c in items],
            "total": len(items),
        },
        "msg": "ok",
    }


@router.get("/conversations/{conversation_id}/history")
async def conversation_history_route(conversation_id: str):
    msgs = get_messages(conversation_id)
    return {
        "code": 0,
        "data": {
            "conversation_id": conversation_id,
            "items": [m.model_dump() for m in msgs],
        },
        "msg": "ok",
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_route(conversation_id: str):
    _delete_conversation(conversation_id)
    return {"code": 0, "data": None, "msg": "ok"}


# Stub retained for frontend compatibility
@router.get("/conversations/{conversation_id}/scheduled-task-results")
async def conversation_scheduled_results_route(conversation_id: str):
    return {
        "code": 0,
        "data": {"conversation_id": conversation_id, "items": []},
        "msg": "ok",
    }


@router.get("/conversations/scheduled-task-results")
async def all_scheduled_results_route():
    return {"code": 0, "data": {"agents": []}, "msg": "ok"}


__all__ = ["router"]
```

- [ ] **Step 4: 运行测试验证失败（路由未挂载）**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/api/test_conversations.py -v
```
预期：仍 404（router 未挂载到 main.py）。Step 5 在 Task 8 完成。但为了独立测试，临时挂载验证：

执行 `cd /home/zhugenmi/work/FinTech/valor/python && uv run python -c "from valor.server.main import app; from valor.conversations.routes import router; app.include_router(router); from fastapi.testclient import TestClient; c = TestClient(app); print(c.get('/api/v1/conversations/').json())"`，应输出 `{code:0,...}`。或者跳到 Task 8 完成后再跑。

实际工作流：Task 7 仅创建文件 + 单独验证 router 自身可工作；Task 8 完成挂载后再跑全套测试。

- [ ] **Step 5: Lint + 提交**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run ruff check valor/conversations/routes.py tests/api/test_conversations.py
git add python/valor/conversations/routes.py python/tests/api/test_conversations.py
git commit -m "feat(conversations): REST API routes"
```

---

## Task 8: 挂载 conversations router + 移除 stubs

**Files:**
- Modify: `python/valor/server/main.py`（include_router）
- Modify: `python/valor/server/routes/stubs.py`（删除会话相关 5 个端点）
- Test: 复用 Task 7 的 `tests/api/test_conversations.py`

**Interfaces:**
- Consumes: `router` from `valor.conversations.routes`
- Produces: `/api/v1/conversations/*` 端点从 stub 切换到真实实现

- [ ] **Step 1: 修改 `main.py` 挂载 router**

打开 `python/valor/server/main.py`，在现有 `from valor.server.routes.xxx import yyy_router` 区域追加：

```python
from valor.conversations.routes import router as conversations_router
```

并在 `app.include_router(...)` 区域追加：

```python
app.include_router(conversations_router)
```

- [ ] **Step 2: 从 `stubs.py` 删除会话端点**

打开 `python/valor/server/routes/stubs.py`，删除以下区块（约第 77-110 行）：

```python
# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

CONVERSATIONS_LIST = {
    "conversations": [],
    "total": 0,
}


@router.get("/conversations/")
async def list_conversations():
    return {"code": 0, "data": CONVERSATIONS_LIST, "msg": "ok"}


@router.get("/conversations/{conversation_id}/history")
async def conversation_history(conversation_id: str):
    return {"code": 0, "data": {"conversation_id": conversation_id, "items": []}, "msg": "ok"}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    return {"code": 0, "data": None, "msg": "ok"}


@router.get("/conversations/{conversation_id}/scheduled-task-results")
async def conversation_scheduled_results(conversation_id: str):
    return {"code": 0, "data": {"conversation_id": conversation_id, "items": []}, "msg": "ok"}


@router.get("/conversations/scheduled-task-results")
async def all_scheduled_results():
    return {"code": 0, "data": {"agents": []}, "msg": "ok"}
```

- [ ] **Step 3: 运行 Task 7 测试验证通过**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/api/test_conversations.py -v
```
预期：4 passed

- [ ] **Step 4: 跑全测确认无回归**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/ -x
```
预期：无新增失败

- [ ] **Step 5: Lint + 提交**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run ruff check valor/server/main.py valor/server/routes/stubs.py
git add python/valor/server/main.py python/valor/server/routes/stubs.py
git commit -m "refactor(server): mount conversations router, remove stubs"
```

---

## Task 9: 扩展 SSE endpoint

**Files:**
- Modify: `python/valor/server/routes/stream.py`
- Test: `python/tests/api/test_stream_diagnosis.py`

**Interfaces:**
- Consumes: Tasks 4, 5, 6, 8
- Produces:
  - SSE body 新增 `portfolio_id: str | None` 和 `ticker: str | None`
  - 在 `full_analysis` 分支前发 `data_preflight` 事件
  - 调用 `stream_analysis(...)` 时传 `portfolio={"cash":float, "stock":int}`（来自 Task 4）
  - 每个 SSE 事件后调 `append_message(...)` 持久化
  - 会话结束时 `update_conversation_status(conversation_id, "completed" | "failed")`

- [ ] **Step 1: 写失败测试**

新建 `python/tests/api/test_stream_diagnosis.py`：

```python
"""Integration test for diagnosis SSE flow. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from valor.server.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _parse_sse(text: str):
    """Parse SSE text into list of {event, data} dicts."""
    events = []
    for block in text.split("\n\n"):
        if not block.startswith("data: "):
            continue
        import json
        payload = json.loads(block[len("data: "):])
        events.append(payload)
    return events


def test_diagnosis_injects_portfolio_and_emits_preflight(client):
    """POST /agents/stream with portfolio_id+ticker should:
    1. Emit data_preflight event with trading_day + filled
    2. Pass real portfolio to stream_analysis
    3. Persist messages
    """
    body = {
        "query": "诊断股票600519",
        "agent_name": "ValorAgent",
        "portfolio_id": "pf_test1",
        "ticker": "600519",
    }

    fake_intent = MagicMock()
    fake_intent.intent = "full_analysis"
    fake_intent.ticker = "600519"
    fake_intent.agent = None

    def _fake_stream_analysis(**kwargs):
        # Yield one chunk to simulate workflow
        yield {"market_data": {"data": {"ticker": "600519"}}}

    with (
        patch("valor.server.routes.stream.classify_intent", return_value=fake_intent),
        patch(
            "valor.server.routes.stream.load_portfolio_context",
            return_value={"cash": 50000.0, "stock": 100},
        ) as mock_load_pf,
        patch(
            "valor.server.routes.stream.ensure_latest_trading_day_data",
            return_value={"trading_day": "2026-07-17", "filled": False},
        ) as mock_preflight,
        patch(
            "valor.server.routes.stream.stream_analysis",
            side_effect=_fake_stream_analysis,
        ) as mock_stream,
        patch("valor.server.routes.stream.create_conversation") as mock_create,
        patch("valor.server.routes.stream.append_message") as mock_append,
        patch("valor.server.routes.stream.update_conversation_status") as mock_update,
    ):
        resp = client.post("/api/v1/agents/stream", json=body, stream=True)
        text = resp.read_text()

    events = _parse_sse(text)
    event_names = [e["event"] for e in events]

    # 1. preflight emitted
    assert "data_preflight" in event_names
    preflight_event = next(e for e in events if e["event"] == "data_preflight")
    assert preflight_event["data"]["trading_day"] == "2026-07-17"
    assert preflight_event["data"]["filled"] is False

    # 2. portfolio context loaded with correct args
    mock_load_pf.assert_called_once_with("pf_test1", "600519")

    # 3. stream_analysis called with portfolio dict
    _, kwargs = mock_stream.call_args
    assert kwargs.get("portfolio") == {"cash": 50000.0, "stock": 100}

    # 4. conversation created + messages appended + status updated
    mock_create.assert_called_once()
    assert mock_append.call_count >= 2  # at least user msg + one agent event
    mock_update.assert_called()


def test_diagnosis_without_portfolio_id_uses_defaults(client):
    """Without portfolio_id, should NOT call load_portfolio_context; portfolio
    falls back to current default {cash:100000, stock:0}."""
    body = {
        "query": "分析600519",
        "agent_name": "ValorAgent",
    }
    fake_intent = MagicMock()
    fake_intent.intent = "full_analysis"
    fake_intent.ticker = "600519"

    def _fake_stream(**kwargs):
        yield {"market_data": {"data": {"ticker": "600519"}}}

    with (
        patch("valor.server.routes.stream.classify_intent", return_value=fake_intent),
        patch("valor.server.routes.stream.load_portfolio_context") as mock_load,
        patch(
            "valor.server.routes.stream.ensure_latest_trading_day_data",
            return_value={"trading_day": "2026-07-17", "filled": False},
        ),
        patch("valor.server.routes.stream.stream_analysis", side_effect=_fake_stream),
        patch("valor.server.routes.stream.create_conversation"),
        patch("valor.server.routes.stream.append_message"),
        patch("valor.server.routes.stream.update_conversation_status"),
    ):
        resp = client.post("/api/v1/agents/stream", json=body, stream=True)
        resp.read_text()

    mock_load.assert_not_called()


def test_diagnosis_portfolio_not_found_emits_system_failed(client):
    """If portfolio_id doesn't exist, should emit system_failed and not run workflow."""
    from valor.portfolio.storage import PortfolioNotFound

    body = {
        "query": "诊断股票600519",
        "agent_name": "ValorAgent",
        "portfolio_id": "pf_missing",
        "ticker": "600519",
    }
    fake_intent = MagicMock()
    fake_intent.intent = "full_analysis"
    fake_intent.ticker = "600519"

    with (
        patch("valor.server.routes.stream.classify_intent", return_value=fake_intent),
        patch(
            "valor.server.routes.stream.load_portfolio_context",
            side_effect=PortfolioNotFound("pf_missing"),
        ),
        patch("valor.server.routes.stream.stream_analysis") as mock_stream,
        patch("valor.server.routes.stream.create_conversation"),
        patch("valor.server.routes.stream.append_message"),
        patch("valor.server.routes.stream.update_conversation_status") as mock_update,
    ):
        resp = client.post("/api/v1/agents/stream", json=body, stream=True)
        text = resp.read_text()

    events = _parse_sse(text)
    event_names = [e["event"] for e in events]
    assert "system_failed" in event_names
    mock_stream.assert_not_called()
    # Status updated to 'failed'
    statuses = [c.args[1] for c in mock_update.call_args_list]
    assert "failed" in statuses
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/api/test_stream_diagnosis.py -v
```
预期：FAIL（`load_portfolio_context` 未导入、`portfolio_id` 未读取、`data_preflight` 事件未发）

- [ ] **Step 3: 修改 `stream.py` 顶部 import**

在 `python/valor/server/routes/stream.py` 顶部追加：

```python
from valor.conversations.models import Conversation, ConversationMessage
from valor.conversations.storage import (
    append_message,
    create_conversation,
    update_conversation_status,
)
from valor.portfolio.storage import PortfolioNotFound
from valor.server.data_preflight import ensure_latest_trading_day_data
from valor.server.portfolio_context import load_portfolio_context
```

- [ ] **Step 4: 修改 `agent_stream` 函数读取新字段**

定位 `async def agent_stream(body: dict):` 内的请求解析段（约 line 224-230），在末尾追加：

```python
    portfolio_id: str | None = body.get("portfolio_id") or None
    request_ticker: str | None = body.get("ticker") or None
```

- [ ] **Step 5: 在 `_stream()` 内 `conversation_started` 后持久化会话**

定位 `yield _sse("conversation_started", {"conversation_id": conversation_id})` 之后，追加：

```python
        # Persist conversation
        now_iso = datetime.now(UTC).isoformat()
        create_conversation(Conversation(
            id=conversation_id,
            agent_name=agent_name,
            title=query[:30] if query else None,
            status="active",
            portfolio_id=portfolio_id,
            ticker=request_ticker,
            created_at=now_iso,
            updated_at=now_iso,
        ))
        # User message
        _msg_seq = 0

        def _persist(role: str, event_type: str, content: str) -> None:
            nonlocal _msg_seq
            _msg_seq += 1
            append_message(ConversationMessage(
                id=f"msg-{uuid.uuid4()}",
                conversation_id=conversation_id,
                role=role,
                event_type=event_type,
                content=content,
                created_at=datetime.now(UTC).isoformat(),
                seq=_msg_seq,
            ))
```

（顶部需 `from datetime import UTC, datetime` import，已有则跳过）

并把用户消息 yield 后追加 `_persist("user", "message", query)`：

```python
        yield _sse("message", {
            "role": "user",
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "task_id": "",
            "item_id": f"user-{uuid.uuid4()}",
            "metadata": {},
            "payload": {"content": query},
        })
        _persist("user", "message", query)
```

- [ ] **Step 6: 在 `full_analysis` 分支前注入持仓 + 发 preflight**

定位 `else:  # full_analysis - new streaming path` 紧邻其上，添加持仓解析 + preflight：

```python
            # Resolve portfolio context (real holdings if portfolio_id provided)
            if portfolio_id and request_ticker:
                try:
                    portfolio = load_portfolio_context(portfolio_id, request_ticker)
                except PortfolioNotFound:
                    yield _sse("system_failed", {
                        "role": "system",
                        "conversation_id": conversation_id,
                        "thread_id": thread_id,
                        "task_id": "",
                        "item_id": "",
                        "metadata": {},
                        "payload": {"content": f"组合不存在: {portfolio_id}"},
                    })
                    update_conversation_status(conversation_id, "failed")
                    yield _sse("done", {"conversation_id": conversation_id, "thread_id": thread_id})
                    return
            else:
                portfolio = {"cash": 100000.0, "stock": 0}

            # Pre-flight: ensure latest trading day data cached
            preflight = ensure_latest_trading_day_data(ticker)
            yield _sse("data_preflight", {
                "conversation_id": conversation_id,
                "thread_id": thread_id,
                "trading_day": preflight["trading_day"],
                "filled": preflight["filled"],
            })
            _persist("system", "data_preflight", json.dumps(preflight, ensure_ascii=False))
```

- [ ] **Step 7: 把 `portfolio` 传给 `stream_analysis`**

定位 `stream_analysis(...)` 调用（约 line 418-423），修改为：

```python
                    for chunk in stream_analysis(
                        ticker=ticker,
                        start_date=start_date,
                        end_date=end_date,
                        portfolio=portfolio,
                        stage_callback=_stage_callback,
                    ):
                        _put(("chunk", chunk))
                    _put(("done", None))
```

（`stream_analysis` 在 `workflow.py:321` 已支持 `portfolio` 参数，直接透传给 `_build_initial_state`）

- [ ] **Step 8: 每条 SSE 事件后持久化**

在 `agent_completed`、`workflow_completed`、`system_failed` 等 yield 语句之后追加 `_persist("assistant", "<event_type>", json.dumps(<data>))`。例如：

```python
                        else:
                            yield _sse("agent_completed", {
                                "conversation_id": conversation_id,
                                "thread_id": thread_id,
                                "agent": node_name,
                                "state": state_delta,
                            })
                            _persist("assistant", "agent_completed",
                                     json.dumps({"agent": node_name, "state": state_delta},
                                                default=_json_default, ensure_ascii=False))
```

`workflow_completed` 之后：

```python
                final_decision = _extract_final_decision(accumulated_state)
                yield _sse("workflow_completed", {
                    "conversation_id": conversation_id,
                    "thread_id": thread_id,
                    "final_decision": final_decision,
                })
                _persist("assistant", "workflow_completed",
                         json.dumps({"final_decision": final_decision},
                                    default=_json_default, ensure_ascii=False))
                update_conversation_status(conversation_id, "completed")
```

`system_failed`（两处）后追加 `update_conversation_status(conversation_id, "failed")`。

- [ ] **Step 9: 运行测试验证通过**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/api/test_stream_diagnosis.py -v
```
预期：3 passed

- [ ] **Step 10: 跑全测确认无回归**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run pytest tests/ -x --ignore=tests/golden
```
预期：无回归（golden 测试可能需要单独处理快照）

- [ ] **Step 11: Lint + 提交**

```bash
cd /home/zhugenmi/work/FinTech/valor/python && uv run ruff check valor/server/routes/stream.py tests/api/test_stream_diagnosis.py
git add python/valor/server/routes/stream.py python/tests/api/test_stream_diagnosis.py
git commit -m "feat(stream): inject portfolio context, preflight, persistence"
```

---

## Task 10: 抽取 `/analysis` 共享组件

**Files:**
- Create: `frontend/src/app/analysis/components/ProgressBar.tsx`、`AgentCard.tsx`、`DecisionPanel.tsx`
- Modify: `frontend/src/app/analysis/index.tsx`（改为 import）

**Interfaces:**
- Consumes: 现有 `frontend/src/app/analysis/ProgressBar.tsx`、`AgentCard.tsx`、`DecisionPanel.tsx`、`constants.ts`
- Produces: 同名导出在 `frontend/src/app/analysis/components/` 下

- [ ] **Step 1: 确认源文件**

```bash
ls /home/zhugenmi/work/FinTech/valor/frontend/src/app/analysis/
```
预期：`AdvancedParams.tsx`、`AgentCard.tsx`、`DecisionPanel.tsx`、`ProgressBar.tsx`、`constants.ts`、`index.tsx`

- [ ] **Step 2: 创建 `components/` 目录并移动文件**

```bash
mkdir -p /home/zhugenmi/work/FinTech/valor/frontend/src/app/analysis/components
git mv frontend/src/app/analysis/ProgressBar.tsx frontend/src/app/analysis/components/ProgressBar.tsx
git mv frontend/src/app/analysis/AgentCard.tsx frontend/src/app/analysis/components/AgentCard.tsx
git mv frontend/src/app/analysis/DecisionPanel.tsx frontend/src/app/analysis/components/DecisionPanel.tsx
git mv frontend/src/app/analysis/constants.ts frontend/src/app/analysis/components/constants.ts
```

- [ ] **Step 3: 更新各组件内部 import 路径**

打开 `frontend/src/app/analysis/components/AgentCard.tsx`（及其他被移动文件），把对 `./constants` 的引用保持不变（同目录）；把对 `../constants` 的引用改为 `./constants`。检查并修复任何 `@/app/analysis/constants` 引用。

```bash
grep -rn "from \"@/app/analysis/constants\"\|from \"\.\./constants\"" frontend/src/app/analysis/components/
```
预期：无输出（若有则 sed 修复或手动 Edit）

- [ ] **Step 4: 更新 `index.tsx` 的 import**

打开 `frontend/src/app/analysis/index.tsx`，把：

```tsx
import AgentCard from "./AgentCard";
import {
  AGENT_ORDER,
  type AgentState,
  type Decision,
  SUB_AGENT_KEYS,
} from "./constants";
import DecisionPanel from "./DecisionPanel";
import ProgressBar from "./ProgressBar";
```

改为：

```tsx
import AgentCard from "./components/AgentCard";
import {
  AGENT_ORDER,
  type AgentState,
  type Decision,
  SUB_AGENT_KEYS,
} from "./components/constants";
import DecisionPanel from "./components/DecisionPanel";
import ProgressBar from "./components/ProgressBar";
```

- [ ] **Step 5: 类型检查 + 启动 dev server 验证 /analysis 页**

```bash
cd /home/zhugenmi/work/FinTech/valor/frontend && bun run typecheck
```
预期：通过

```bash
cd /home/zhugenmi/work/FinTech/valor && ./start.sh backend &
sleep 5
cd /home/zhugenmi/work/FinTech/valor/frontend && bun dev &
```
浏览器打开 `http://localhost:1420/analysis`，输入 600519 点分析，确认 UI 行为不变。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/app/analysis/
git commit -m "refactor(analysis): extract shared components to components/"
```

---

## Task 11: 扩展 agent types + agent-store 处理 workflow 事件

**Files:**
- Modify: `frontend/src/constants/agent.ts`（追加 `diagnosis_section` 到 `AGENT_COMPONENT_TYPE`）
- Modify: `frontend/src/types/agent.ts`（扩展 `AgentEventMap` 增加 `data_preflight`；扩展 `AgentStreamRequest` 增加 `portfolio_id` / `ticker`）
- Modify: `frontend/src/lib/agent-store.ts`（新增 `workflow_started` / `agent_completed` / `data_preflight` 分支）
- Modify: `frontend/src/components/valuecell/renderer.tsx`（注册 `diagnosis_section` renderer — 实际组件在 Task 12 创建，此处先注册占位）

**Interfaces:**
- Consumes: `WorkflowStartedEventData` / `AgentCompletedEventData` / `WorkflowCompletedEventData` 已存在
- Produces:
  - `data_preflight` 事件类型
  - `diagnosis_section` ChatItem 类型，含 `agents: Record<string, AgentState>` 和 `decision: Decision | null` 和 `preflight: {trading_day, filled} | null`

- [ ] **Step 1: 扩展 `AGENT_COMPONENT_TYPE`**

打开 `frontend/src/constants/agent.ts`，把 `AGENT_COMPONENT_TYPE` 数组改为：

```ts
export const AGENT_COMPONENT_TYPE = [
  "markdown",
  "reasoning",
  "tool_call",
  "subagent_conversation",
  "scheduled_task_controller",
  "decision",
  "diagnosis_section",
  ...AGENT_SECTION_COMPONENT_TYPE,
  ...AGENT_MULTI_SECTION_COMPONENT_TYPE,
] as const;
```

- [ ] **Step 2: 扩展 `AgentEventMap` 增加 `data_preflight`**

打开 `frontend/src/types/agent.ts`，在 `WorkflowCompletedEventData` 接口后追加：

```ts
export interface DataPreflightEventData {
  conversation_id: string;
  thread_id: string;
  trading_day: string;
  filled: boolean;
}
```

在 `AgentEventMap` 内 `workflow_completed` 之后追加：

```ts
  data_preflight: DataPreflightEventData;
```

- [ ] **Step 3: 扩展 `AgentStreamRequest`**

把：

```ts
export type AgentStreamRequest = {
  query: string;
  agent_name: string;
} & Partial<Pick<BaseEventData, "conversation_id" | "thread_id">>;
```

改为：

```ts
export type AgentStreamRequest = {
  query: string;
  agent_name: string;
  portfolio_id?: string;
  ticker?: string;
} & Partial<Pick<BaseEventData, "conversation_id" | "thread_id">>;
```

- [ ] **Step 4: 在 `agent-store.ts` 新增事件分支**

打开 `frontend/src/lib/agent-store.ts`，在顶部 import 追加：

```ts
import {
  AGENT_ORDER,
  type AgentState,
  type Decision,
  SUB_AGENT_KEYS,
} from "@/app/analysis/components/constants";
```

在 `processSSEEvent` 的 `switch` 内 `case "workflow_completed"` 之前追加：

```ts
    case "workflow_started": {
      // Create a diagnosis_section ChatItem with all 9 agent slots pending
      const agents: Record<string, AgentState> = {};
      for (const name of AGENT_ORDER) {
        agents[name] = { status: "pending", output: null };
      }
      handleChatItemEvent(
        draft,
        {
          role: "agent",
          conversation_id: data.conversation_id,
          thread_id: data.thread_id,
          task_id: "",
          item_id: `diagnosis-${data.conversation_id}`,
          metadata: {},
          component_type: "diagnosis_section",
          payload: {
            content: JSON.stringify({
              ticker: data.ticker,
              agents,
              decision: null,
              preflight: null,
              currentAgent: AGENT_ORDER[0],
            }),
          },
        },
        "replace",
      );
      break;
    }

    case "data_preflight": {
      // Update the diagnosis_section's preflight field
      const { conversation, task } = ensurePath(draft, data);
      for (const item of task.items) {
        if (item.component_type === "diagnosis_section") {
          try {
            const parsed = JSON.parse(item.payload.content);
            parsed.preflight = { trading_day: data.trading_day, filled: data.filled };
            item.payload.content = JSON.stringify(parsed);
          } catch {
            // skip
          }
        }
      }
      break;
    }

    case "agent_completed": {
      // Update the diagnosis_section's agent slot
      const { task } = ensurePath(draft, data);
      for (const item of task.items) {
        if (item.component_type !== "diagnosis_section") continue;
        try {
          const parsed = JSON.parse(item.payload.content);
          const dotIdx = data.agent.indexOf(".");
          if (dotIdx > 0) {
            const parent = data.agent.slice(0, dotIdx);
            const sub = data.agent.slice(dotIdx + 1);
            const current = parsed.agents[parent] ?? { status: "running", output: null };
            const subStates = { ...(current.subStates ?? {}), [sub]: data.state };
            const allSubs = SUB_AGENT_KEYS[parent] ?? [];
            const allDone = allSubs.every((k: string) => k in subStates);
            parsed.agents[parent] = { ...current, status: allDone ? "completed" : "running", subStates };
          } else {
            parsed.agents[data.agent] = { status: "completed", output: data.state };
          }
          // Update currentAgent to next pending
          parsed.currentAgent = (() => {
            for (const name of AGENT_ORDER) {
              const s = parsed.agents[name];
              if (!s || s.status === "pending") return name;
              if (s.status === "running") return name;
            }
            return null;
          })();
          item.payload.content = JSON.stringify(parsed);
        } catch {
          // skip
        }
      }
      break;
    }
```

并在现有 `case "workflow_completed"` 内，除了创建 decision item 外，**同时**回填 diagnosis_section 的 decision 字段：

```ts
    case "workflow_completed": {
      if (!data.final_decision) break;
      // 1. Existing: render as a decision card in the main thread
      handleChatItemEvent(
        draft,
        {
          role: "agent",
          conversation_id: data.conversation_id,
          thread_id: data.thread_id,
          task_id: "",
          item_id: "final-decision",
          metadata: {},
          component_type: "decision",
          payload: { content: JSON.stringify(data.final_decision) },
        },
        "replace",
      );
      // 2. Also fill the diagnosis_section's decision slot
      const { task } = ensurePath(draft, data);
      for (const item of task.items) {
        if (item.component_type === "diagnosis_section") {
          try {
            const parsed = JSON.parse(item.payload.content);
            parsed.decision = data.final_decision;
            parsed.currentAgent = null;
            item.payload.content = JSON.stringify(parsed);
          } catch {
            // skip
          }
        }
      }
      break;
    }
```

- [ ] **Step 5: 类型检查**

```bash
cd /home/zhugenmi/work/FinTech/valor/frontend && bun run typecheck
```
预期：通过（注意：`diagnosis_section` renderer 此时还未注册，但类型层面已 OK；renderer 在 Task 12 完成后才会真正渲染）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/constants/agent.ts frontend/src/types/agent.ts frontend/src/lib/agent-store.ts
git commit -m "feat(agent-store): handle workflow_started/agent_completed/data_preflight events"
```

---

## Task 12: 创建 `DiagnosisSectionRenderer` 组件

**Files:**
- Create: `frontend/src/app/agent/components/agent-view/diagnosis-section.tsx`
- Modify: `frontend/src/components/valuecell/renderer.tsx`（注册 renderer）
- Modify: `frontend/src/constants/agent.ts`（`COMPONENT_RENDERER_MAP` 加映射）

**Interfaces:**
- Consumes: `ProgressBar`、`AgentCard`、`DecisionPanel` from `@/app/analysis/components/`
- Produces: 默认导出一个 React 组件，props 为 `{ content: string }`，content 是 JSON 序列化的 `{ticker, agents, decision, preflight, currentAgent}`

- [ ] **Step 1: 创建组件**

新建 `frontend/src/app/agent/components/agent-view/diagnosis-section.tsx`：

```tsx
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { useState, type FC } from "react";
import {
  AGENT_ORDER,
  type AgentState,
  type Decision,
  SUB_AGENT_KEYS,
} from "@/app/analysis/components/constants";
import AgentCard from "@/app/analysis/components/AgentCard";
import DecisionPanel from "@/app/analysis/components/DecisionPanel";
import ProgressBar from "@/app/analysis/components/ProgressBar";

interface DiagnosisSectionContent {
  ticker: string;
  agents: Record<string, AgentState>;
  decision: Decision | null;
  preflight: { trading_day: string; filled: boolean } | null;
  currentAgent: string | null;
}

interface DiagnosisSectionRendererProps {
  content: string;
}

const DiagnosisSectionRenderer: FC<DiagnosisSectionRendererProps> = ({ content }) => {
  const [collapsed, setCollapsed] = useState(false);
  let parsed: DiagnosisSectionContent;
  try {
    parsed = JSON.parse(content) as DiagnosisSectionContent;
  } catch {
    return null;
  }

  const completedAgents = AGENT_ORDER.filter(
    (name) => parsed.agents[name]?.status === "completed",
  );
  const isStreaming = parsed.currentAgent !== null;

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700">
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center justify-between p-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800"
      >
        <div className="flex items-center gap-2">
          {collapsed ? (
            <ChevronRight className="size-4" />
          ) : (
            <ChevronDown className="size-4" />
          )}
          <span className="font-medium">
            股票诊断 · {parsed.ticker}
          </span>
          {parsed.preflight && (
            <span className="text-xs text-gray-500">
              数据日: {parsed.preflight.trading_day}
              {parsed.preflight.filled ? "（已补齐）" : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {isStreaming && <Loader2 className="size-3 animate-spin" />}
          <span>
            {completedAgents.length}/{AGENT_ORDER.length}
          </span>
        </div>
      </button>

      {!collapsed && (
        <div className="border-t border-gray-200 p-3 dark:border-gray-700">
          {isStreaming && (
            <ProgressBar
              currentAgent={parsed.currentAgent}
              completedAgents={completedAgents}
            />
          )}
          <div className="mt-2 flex flex-col gap-2">
            {AGENT_ORDER.map((name) => (
              <AgentCard
                key={name}
                name={name}
                state={parsed.agents[name]}
                isActive={parsed.currentAgent === name}
              />
            ))}
          </div>
          <DecisionPanel decision={parsed.decision} />
        </div>
      )}
    </div>
  );
};

export default DiagnosisSectionRenderer;
```

- [ ] **Step 2: 注册 renderer**

打开 `frontend/src/components/valuecell/renderer.tsx`，在顶部 import 区追加：

```tsx
import DiagnosisSectionRenderer from "@/app/agent/components/agent-view/diagnosis-section";
```

在 renderer map 中追加（具体变量名按文件实际）：

```tsx
  diagnosis_section: DiagnosisSectionRenderer,
```

- [ ] **Step 3: 类型检查**

```bash
cd /home/zhugenmi/work/FinTech/valor/frontend && bun run typecheck
```
预期：通过

- [ ] **Step 4: 提交**

```bash
git add frontend/src/app/agent/components/agent-view/diagnosis-section.tsx frontend/src/components/valuecell/renderer.tsx
git commit -m "feat(agent): DiagnosisSectionRenderer with collapsible workflow view"
```

---

## Task 13: 接线诊断按钮 + SSE body 字段

**Files:**
- Modify: `frontend/src/app/portfolio/components/HoldingsTable.tsx:254-258`
- Modify: `frontend/src/app/agent/components/agent-view/common-agent-area.tsx:145-167`

**Interfaces:**
- Consumes: Tasks 11（`AgentStreamRequest` 新字段）、12（DiagnosisSection 已注册）
- Produces:
  - 诊断按钮 `navigate('/agent/ValorAgent', { state: { inputValue, portfolioId, ticker } })`
  - `common-agent-area.tsx` 读取 `state.portfolioId` / `state.ticker` 并加入 `AgentStreamRequest`

- [ ] **Step 1: 修改 `HoldingsTable.tsx` 诊断按钮**

打开 `frontend/src/app/portfolio/components/HoldingsTable.tsx`，顶部确认 import：

```tsx
import { useNavigate } from "react-router";
```

若没有则添加（`Link` 可保留或删除若不再用）。

在组件函数体内（与其他 hooks 同级）追加：

```tsx
const navigate = useNavigate();
```

定位第 254-258 行的诊断按钮，替换为：

```tsx
<Button
  variant="ghost"
  size="icon"
  title="诊断"
  onClick={() =>
    navigate("/agent/ValorAgent", {
      state: {
        inputValue: `诊断股票${h.ticker}`,
        portfolioId: pid,
        ticker: h.ticker,
      },
    })
  }
>
  <Stethoscope className="h-4 w-4" />
</Button>
```

确认 `pid` 在组件作用域内可见——`HoldingsTable` 已通过 props 接收 `pid`（见 `frontend/src/app/portfolio/components/HoldingsTable.tsx:124-130` 解构，父组件 `detail.tsx:207-208` 传 `pid={id}`），直接用即可。

- [ ] **Step 2: 修改 `common-agent-area.tsx` 读取 state**

打开 `frontend/src/app/agent/components/agent-view/common-agent-area.tsx`，定位 `const inputValueFromLocation = useLocation().state?.inputValue;`（约 line 53），下方追加：

```tsx
const portfolioIdFromLocation = useLocation().state?.portfolioId;
const tickerFromLocation = useLocation().state?.ticker;
```

并增加 ref 保存（避免 useEffect 闭包丢失）：

```tsx
const portfolioIdRef = useRef<string | undefined>(portfolioIdFromLocation);
const tickerRef = useRef<string | undefined>(tickerFromLocation);
useEffect(() => {
  portfolioIdRef.current = portfolioIdFromLocation;
  tickerRef.current = tickerFromLocation;
}, [portfolioIdFromLocation, tickerFromLocation]);
```

顶部 import 增加 `useRef`。

- [ ] **Step 3: 修改 `sendMessage` 注入 portfolio_id + ticker**

定位 `sendMessage` 函数内 `const request: AgentStreamRequest = {...}`，改为：

```tsx
const request: AgentStreamRequest = {
  query: message,
  agent_name: agentName,
  conversation_id: conversationId,
  portfolio_id: portfolioIdRef.current,
  ticker: tickerRef.current,
};
```

- [ ] **Step 4: 清理 state 时机调整**

定位现有清理 `navigate(".", { replace: true, state: {} });`（约 line 179）。该清理会清掉 inputValue 也清掉 portfolioId/ticker — 这是期望行为（避免后续消息再带上同一持仓）。保持不变。

- [ ] **Step 5: 类型检查**

```bash
cd /home/zhugenmi/work/FinTech/valor/frontend && bun run typecheck
```
预期：通过

- [ ] **Step 6: 提交**

```bash
git add frontend/src/app/portfolio/components/HoldingsTable.tsx frontend/src/app/agent/components/agent-view/common-agent-area.tsx
git commit -m "feat(portfolio): wire 诊断 button to new conversation with portfolio context"
```

---

## Task 14: 端到端手动验证

**Files:** 无代码改动，仅运行验证

- [ ] **Step 1: 启动全栈**

```bash
cd /home/zhugenmi/work/FinTech/valor && ./start.sh
```
等待 backend :8000 + frontend :1420 就绪。

- [ ] **Step 2: 准备测试数据**

确保至少有一个 portfolio，包含至少一个 holding（如 600519）。可通过 UI 创建或直接写 `python/data/portfolios/pf_xxx.json`。

- [ ] **Step 3: 验证诊断按钮跳会话**

浏览器打开 `http://localhost:1420/portfolio/<id>`，点击某持仓行的"诊断"按钮（听诊器图标）。

预期：
- 跳转到 `/agent/ValorAgent`
- URL 暂无 `?id=`，SSE 开始后变为 `?id=<新 conversation_id>`
- 输入框自动填入"诊断股票600519"并发送

- [ ] **Step 4: 验证 SSE 流式过程**

预期会话内依次出现：
1. 用户消息 "诊断股票600519"
2. 一个折叠卡片"股票诊断 · 600519"，顶部状态条显示"数据日: 2026-07-17"（或当日最近交易日）
3. ProgressBar 显示当前节点
4. 9 个 AgentCard 依次从 pending -> running -> completed（bull_bear_debate 有 3 个子阶段）
5. DecisionPanel 显示最终决策，含 `current_position`（真实持仓量）

- [ ] **Step 5: 验证持久化**

刷新页面（F5）。

预期：会话内容恢复，诊断区块以完成态显示（无 spinner），决策仍可见。

- [ ] **Step 6: 验证会话列表**

打开侧边栏会话列表（若有），或直接 `curl http://localhost:8000/api/v1/conversations/`。

预期：返回包含刚才诊断会话的列表，`portfolio_id` 和 `ticker` 字段已填充。

- [ ] **Step 7: 验证删除会话**

`curl -X DELETE http://localhost:8000/api/v1/conversations/<id>`。

预期：返回 `{code:0}`，再次列表查询时该会话消失。

- [ ] **Step 8: 验证 /analysis 页未受影响**

打开 `http://localhost:1420/analysis`，输入 ticker 点分析。

预期：行为与改造前一致（ProgressBar + AgentCard + DecisionPanel 正常显示）。

- [ ] **Step 9: 验证普通聊天未受影响**

在 `/agent/ValorAgent` 直接输入"你好"。

预期：返回 chat 意图回复，不触发工作流，不显示诊断区块。

- [ ] **Step 10: 提交（若有修复）**

若手动验证发现 bug 并修复，则：

```bash
git add -A
git commit -m "fix(<scope>): <issue>"
```

若无 bug，则无需提交。

---

## 完成标志

所有 14 个 task 完成后：
- 后端测试全绿：`cd python && uv run pytest tests/ -x --ignore=tests/golden`
- 后端 lint 零警告：`cd python && uv run ruff check valor/ tests/`
- 前端类型检查通过：`cd frontend && bun run typecheck`
- 手动验证 10 步全部符合预期
