# Valor

> **Va**lue **l**ong-term **or**ientation — 个人专业理财助理，专注 A 股投资分析与决策。

Valor 是一个**本地可自托管**的个人专业理财助理，以 Web 应用形式运行（浏览器访问），核心能力：

- **个股诊断**：12 个 AI Agent 协同分析（技术 / 基本面 / 估值 / 情绪 / 宏观 / 多空辩论 / 风险），输出 buy/sell/hold 决策
- **SSE 流式分析**：前端实时推送每个 Agent 的分析信号与决策进展
- **Agent 工作流**：基于 LangGraph 编排，流程可视化可追溯
- **数据层**：AkShare 主 + Tushare / Baostock 字段级 fallback，SQLite TTL 缓存
- **LLM 适配**：多 Provider 支持（OpenAI 兼容 / Gemini / Ollama / 智能路由），可切换
- **38 个 API 路由**：涵盖分析、流式推送、行情、系统管理、用户配置等
- **持仓管理 / 资产配置 / 回测**（Phase 2+）

## 项目结构

```
valor/
├── frontend/              # React + Vite + TypeScript
│   ├── src/
│   │   ├── app/           # 页面路由（home, market, agent, setting, **analysis**, portfolio）
│   │   ├── api/           # 后端 API 调用封装（含 useStreamAnalysis SSE）
│   │   ├── hooks/         # useSSE、useDebounce 等
│   │   ├── components/    # 通用组件（shadcn/ui + valuecell）
│   │   ├── store/         # Zustand 状态管理
│   │   ├── i18n/          # 中/英文
│   │   ├── types/         # TypeScript 类型定义
│   │   ├── routes.ts      # 前端路由
│   │   └── root.tsx       # 应用入口
│   ├── package.json       # bun
│   └── vite.config.ts
│
├── python/                # Python 后端（uv + 3.12）
│   ├── valor/
│   │   ├── core/          # 共享 Pydantic schema / Protocol
│   │   ├── adapters/
│   │   │   ├── llm/       # LLM Provider（OpenAI-compat / Gemini / Ollama / Router）
│   │   │   └── data/      # 数据适配器（AkShare / Tushare / Baostock + Router）
│   │   ├── agents/        # 12 个 Agent + LangGraph 工作流
│   │   ├── server/        # FastAPI 服务（11 routers, 38 routes）
│   │   │   └── routes/    # health, auth, stream, analysis, stock, models, system, ...
│   │   ├── network/       # 代理轮询
│   │   ├── utils/         # 日志、序列化、LLM 客户端
│   │   ├── cli/           # 命令行入口
│   │   └── tools/         # 数据获取与格式化工具
│   ├── tests/             # 单元 / 集成 / golden 测试（97 tests）
│   └── pyproject.toml
│
├── docs/                  # 设计文档与计划
└── AGENTS.md              # Agent 开发指南
```

## 快速开始

### 前提

- **Python** ≥ 3.12 + [uv](https://docs.astral.sh/uv/)
- **Bun** ≥ 1.3（前端构建）
- 可选：AkShare 环境（Linux 需要安装 `tkinter` 等依赖）

### 1. 后端

```bash
cd python

# 安装依赖
uv sync --extra dev

# 配置环境变量
cp .env.example .env
# 编辑 .env，设置 LLM 密钥：
#   VALOR_OPENAI_API_KEY=sk-xxx
#   VALOR_OPENAI_BASE_URL=https://xxx
#   VALOR_OPENAI_MODEL=gpt-4o

# 验证：CLI 模式拉取数据
uv run python -m valor.cli.main --ticker 600519

# 运行 Agent 工作流（完整分析）
uv run python -m valor.cli.main --ticker 600519 --run
```

### 2. 前端

```bash
cd frontend

# 安装依赖
bun install

# 开发模式启动（默认端口 1420，API 代理到后端 8000）
bun dev
```

### 3. 全栈开发

打开两个终端：

```bash
# 终端 1：后端
cd python && uv run uvicorn valor.server.main:app --reload --port 8000

# 终端 2：前端
cd frontend && bun dev
```

浏览器访问 `http://localhost:1420`。

## Agent 工作流

12 个 Agent 按 LangGraph 工作流编排：

```
市场数据（market_data）
    │
    ▼（并行扇出）
技术分析 → 基本面 → 估值 → 情绪 → 宏观
    │
    ▼
多头研究员 ←→ 空头研究员
    │
    ▼
辩论室（多空辩论 + LLM 第三方评分）
    │
    ▼
风险管理（头寸/波动率/Beta）
    │
    ▼
投资组合经理（最终决策：buy/sell/hold）
```

运行 `--run` 后，CLI 输出每个 Agent 的信号（bullish/bearish/neutral）、置信度和推理过程，以及最终决策。

## SSE 流式分析

前端分析页通过 `POST /api/v1/agents/stream` 发起 SSE 连接，后端实时推送以下事件：

| 事件 | 说明 |
|---|---|
| `token` | LLM 推理 token 流 |
| `agent_completed` | 单个 Agent 分析完成，携带信号和推理 |
| `workflow_started` | 12 Agent 工作流启动 |
| `workflow_completed` | 工作流结束，携带最终决策 |
| `error` | 异常信息 |

每个 Agent 卡片实时展示其状态（分析中 / 完成 / 错误）和输出信号，最终决策面板汇总所有信号并给出 buy/sell/hold 建议。

## CLI 用法

```bash
# 数据获取模式
uv run python -m valor.cli.main --ticker 600519
uv run python -m valor.cli.main --ticker 000001 --start-date 2026-01-01 --end-date 2026-07-16

# Agent 分析模式
uv run python -m valor.cli.main --ticker 600519 --run
uv run python -m valor.cli.main --ticker 600519 --run --show-reasoning

# 指定模型
uv run python -m valor.cli.main --ticker 600519 --run --model gpt-4o

# 指定持仓（影响风险管理）
uv run python -m valor.cli.main --ticker 600519 --run --portfolio-cash 100000 --portfolio-stock 100
```

## 测试

```bash
cd python

# 全部测试（97 tests）
uv run pytest

# 单元测试
uv run pytest tests/unit/

# API 路由测试
uv run pytest tests/api/

# Golden 测试（数据快照回放）
uv run pytest tests/golden/

# lint 检查
uv run ruff check valor/ tests/
```

## 环境变量

详见 `python/.env.example`。关键变量：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `VALOR_LLM_PROVIDER` | LLM Provider 优先级 | `openai_compat` |
| `VALOR_OPENAI_API_KEY` | OpenAI 兼容 API 密钥 | - |
| `VALOR_OPENAI_BASE_URL` | 自定义 API 地址 | `https://api.openai.com/v1` |
| `VALOR_OPENAI_MODEL` | 模型名 | `gpt-4o` |
| `VALOR_CACHE_DIR` | SQLite 缓存目录 | `.cache` |
| `TUSHARE_TOKEN` | Tushare Pro token（可选） | - |
| `AKSHARE_PROXY_*` | AkShare 代理配置（可选） | - |

## 开发路线

| Phase | 内容 | 状态 |
|---|---|---|
| 1A | Python 后端基础（数据层 + LLM 适配 + CLI） | ✅ 完成 |
| 1B | 12 Agent + LangGraph 工作流 | ✅ 完成 |
| 1C | FastAPI 服务 + 11 路由（38 端点） | ✅ 完成 |
| 1D | 前端分析页 + SSE 流式 Agent 事件 | ✅ 完成 |
| 2 | 持仓管理与资产配置 | 📋 计划 |
| 3 | Agent 驱动回测 | 📋 计划 |
| 4 | Pro 回测（ML/RL 策略 + 基金/债券数据） | 📋 计划 |

## License

GPL-3.0-or-later WITH GPL-3.0-NonCommercial。
