# 股票诊断（会话化）设计

日期：2026-07-20

## 目标

在组合详情页点击某只股票的"诊断"按钮，跳转到一个**新会话**，等价于用户向 ValorAgent 问"诊断股票xxx"。诊断默认使用最近一个交易日的数据（先查库、缺则补齐），并基于用户当前组合的持仓上下文给出组合决策。诊断过程在会话内实时呈现，可整体折叠。

## 用户已确认决策

| 决策点 | 选择 |
|---|---|
| 持仓上下文范围 | 仅 `cash` + 该 ticker 在该组合中的 `quantity`（复用 `portfolio_manager` 现有 schema） |
| UI 呈现 | 会话内独立"诊断区块"，含 ProgressBar + 9 个可折叠 AgentCard + DecisionPanel，整体可折叠 |
| 会话持久化 | 完整持久化（SQLite，会话+消息） |
| 最近交易日逻辑 | 显式 `get_latest_trading_day()` + SSE 流开头的 pre-flight 预补齐 |
| 现有 `/analysis` 页 | 保留不动，仅修改"诊断"按钮跳转目标 |
| 整体方案 | 抽取 `/analysis` 组件为共享 + SQLite 持久化 |

## 架构与数据流

### 触发链路

```
[组合详情页 HoldingsTable] 诊断按钮
  └─ navigate('/agent/ValorAgent', state: {
       inputValue: '诊断股票600519',
       portfolioId: 'pf_xxx',
       ticker: '600519'
     })
     └─ CommonAgentArea 组装 SSE 请求:
        POST /api/v1/agents/stream
        body: {
          query: '诊断股票600519',
          agent_name: 'ValorAgent',
          conversation_id: null,
          portfolio_id: 'pf_xxx',   // 新增
          ticker: '600519'          // 新增
        }
```

### SSE 流程（扩展现有 `stream.py`）

1. `conversation_started` — 持久化新会话 + 用户消息
2. `thread_started`
3. **（新增）** `data_preflight` — 调 `get_latest_trading_day()`；若该交易日数据不在库，调 akshare 补齐；emit `{trading_day, filled}`
4. `workflow_started` — 9 节点工作流启动
5. `agent_completed × 9` — 每节点 emit；`bull_bear_debate` 拆 3 个子事件；每条持久化为 assistant 消息
6. `workflow_completed` — 提取 `portfolio_manager` 决策，含 `current_position`（来自真实持仓）
7. `done` — 标记会话 `status=completed`

### 持仓上下文注入

`stream.py` 在调用 `stream_analysis()` 前：
- 读 `portfolio_id` 加载组合（复用 `valor/portfolio/storage.py`）
- 在 holdings 中找到 `ticker` 对应 `quantity`（没有则为 0）
- 取组合 `cash`
- 构造 `portfolio = {"cash": float, "stock": int}` 传入工作流，替代硬编码

## 前端改动

### 路由与导航

- `HoldingsTable.tsx:254` 诊断按钮：从 `<Link to="/analysis?ticker=...">` 改为 `<button onClick={() => navigate('/agent/ValorAgent', { state: { inputValue, portfolioId, ticker } })}>`
- `common-agent-area.tsx` 读取 `state.portfolioId` / `state.ticker`，加入 SSE 请求体

### 共享组件抽取

把 `frontend/src/app/analysis/index.tsx` 内的 UI 抽到 `frontend/src/app/analysis/components/`：
- `ProgressBar.tsx`
- `AgentCard.tsx`（含折叠）
- `DecisionPanel.tsx`
- `constants.ts`（已有的 `AGENT_ORDER` 等不动）

`/analysis` 页改为引用这些组件；行为不变。

### 会话 store 扩展

`frontend/src/lib/agent-store.ts` 的 `processSSEEvent` 新增事件分支：
- `workflow_started` — 创建一个 `diagnosis_section` 类型的 ChatItem，含 9 个 agent 槽位 + 决策槽位
- `agent_completed` — 找到当前 `diagnosis_section`，更新对应 agent 槽位（pending/running/completed + 数据）
- `workflow_completed` — 填充决策槽位
- `data_preflight` — 更新 `diagnosis_section` 顶部状态条（"正在补齐 2026-07-17 数据…"）

新增 `DiagnosisSectionRenderer` 组件，渲染一个可整体折叠的卡片，内部含 ProgressBar + AgentCard × 9 + DecisionPanel。

### 会话持久化接入

`frontend/src/api/conversation.ts` 中现有 hooks 当前打 stub。改为真实调用：
- `useGetConversationList` — `GET /api/v1/conversations/`
- `useGetConversationHistory` — `GET /api/v1/conversations/{id}/history`，返回的消息经 `dispatchAgentStoreHistory` 灌入 store
- `useDeleteConversation` — `DELETE /api/v1/conversations/{id}`
- 进入 `/agent/ValorAgent?id=xxx` 时若 `id` 非空，先加载历史

## 后端改动

### 1. `valor/adapters/data/akshare_cache.py`

新增：
```python
def get_latest_trading_day(today: date | None = None) -> date:
    """返回 <= today 的最近一个 A 股交易日。"""
```
基于现有 `query_trade_dates()` 实现。

### 2. `valor/agents/market_data.py`

`end_date` 默认值从 `yesterday` 改为 `get_latest_trading_day()`。

### 3. `valor/server/intent.py`

`_SYSTEM_PROMPT` 的 `full_analysis` 规则中加一条示例：`"诊断股票600519" -> full_analysis, ticker=600519`。

### 4. `valor/server/routes/stream.py`

- 请求 schema 新增 `portfolio_id: str | None`、`ticker: str | None`
- 在 `full_analysis` 分支：
  1. 若有 `portfolio_id` + `ticker`，加载组合、查持仓数量、组装 `portfolio` dict
  2. 调 `get_latest_trading_day()`，emit `data_preflight` 事件；若该交易日 K 线不在库，触发 `get_price_history_df(symbol, end_date=latest)` 补齐
  3. 调 `stream_analysis(..., portfolio=portfolio)`
- 每条 SSE 事件持久化到 `conversation_messages` 表

### 5. 新增 `valor/conversations/` 模块

- `storage.py` — SQLite CRUD（用 `valor/server/db.py` 的连接）
- `models.py` — Pydantic：`Conversation`、`ConversationMessage`
- `routes.py` — FastAPI router，挂到 `/api/v1/conversations`

#### SQLite Schema

```sql
CREATE TABLE conversations (
  id TEXT PRIMARY KEY,
  agent_name TEXT NOT NULL,
  title TEXT,                    -- 默认取首条用户消息前 30 字
  status TEXT NOT NULL,          -- 'active' | 'completed' | 'failed'
  portfolio_id TEXT,             -- 关联组合（诊断会话有值）
  ticker TEXT,                   -- 关联股票（诊断会话有值）
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE conversation_messages (
  id TEXT PRIMARY KEY,           -- uuid
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,            -- 'user' | 'assistant' | 'system'
  event_type TEXT,               -- SSE 事件类型：message / agent_completed / workflow_completed / ...
  content TEXT,                  -- 文本内容或 JSON 序列化的 payload
  created_at TEXT NOT NULL,
  seq INTEGER NOT NULL           -- 同会话内自增，用于排序
);
CREATE INDEX idx_messages_conv ON conversation_messages(conversation_id, seq);
```

#### REST API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/conversations/` | 列表（分页、按 `updated_at` 倒序） |
| GET | `/api/v1/conversations/{id}/history` | 消息列表（按 `seq` 升序） |
| DELETE | `/api/v1/conversations/{id}` | 删除会话 + 级联消息 |
| GET | `/api/v1/conversations/{id}/scheduled-task-results` | 维持 stub 行为（返回空） |

`stubs.py` 中的会话相关端点移除，由新 router 替代。

### 6. `valor/server/main.py`

挂载 `conversations_router`，前缀 `/api/v1`。

## 错误处理

- `portfolio_id` 无效或组合不存在：emit `system_failed` 事件 `{error: '组合不存在'}`，会话标记 `failed`，不跑工作流
- pre-flight 补齐失败（akshare 不可用）：emit `system_failed`，会话标记 `failed`
- 工作流节点异常：维持现有行为（异常被捕获并 emit `system_failed`），会话标记 `failed`
- 持仓数量查询：组合中无该 ticker 时 `quantity=0`，不阻塞流程

## 测试

### 后端

- `tests/unit/test_akshare_cache.py::test_get_latest_trading_day` — 周六/周日/节假日场景
- `tests/unit/test_intent.py::test_diagnosis_keyword` — "诊断股票600519" 应判为 `full_analysis`
- `tests/api/test_stream.py::test_diagnosis_with_portfolio` — 带 `portfolio_id` + `ticker` 的 SSE 请求，验证 `portfolio` 正确注入
- `tests/api/test_conversations.py` — CRUD + history 加载
- `tests/unit/test_workflow.py` — 已有测试不应回归

### 前端

- 手动验证：组合详情页点诊断 → 跳会话 → 实时看到 9 节点过程 → 决策含真实持仓数量
- 手动验证：刷新会话页能恢复历史
- `bun run typecheck` 通过

## 不在本次范围

- `/analysis` 页面本身不动（仅抽取组件，行为不变）
- 历史会话搜索/全文检索
- 多会话并发限流
- 会话消息的 markdown 渲染增强（保持现状）
- 非诊断场景（普通聊天）的中间 agent 流式可视化（仅诊断场景渲染 AgentCard，普通 `single_analysis` 不渲染）
