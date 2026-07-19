---
name: portfolio-holdings-enhancement-design
description: Valor Phase 2 持仓模块完善设计 spec，2026-07-19 brainstorming 产出，在 phase-2-portfolio-design 基础上补全手动增删/加减仓/单 Lot 编辑与持仓表展示
metadata:
  type: design-spec
  date: 2026-07-19
  status: draft
  phase: 2-enhancement
  parent: 2026-07-17-phase-2-portfolio-design
---

# Valor Phase 2 持仓模块完善设计 spec

## 0. 概述

Phase 2（持仓管理与资产配置）于 2026-07-17 完成，覆盖了组合 CRUD、CSV 导入、Analytics、Allocator、Rebalance 全链路。但在"持仓"Tab 实际使用中暴露若干缺口：

1. 持仓表格只显示 `代码/名称/持仓量/Lot数/操作`，缺现价/成本/盈亏/权重列
2. 没有原子化的"增持/减仓"操作 —— 用户只能整条 Holding 替换或追加 Lot
3. 没有单笔 Lot 的编辑/删除接口 —— 录错只能整条 Holding 删重建
4. 减仓没有流水记录 —— 无法追踪已实现盈亏与卖出历史

本 spec 在不动 Phase 2 现有 Strategy/Rebalance/Allocator 的前提下，扩展 Lot/SellLot 双轨模型与对应 API/UI，补齐以上能力。

### 0.1 决策摘要

| 维度 | 决策 |
|---|---|
| 目标页面 | `/portfolio/:id` 详情页"持仓" Tab |
| 减仓记录方式 | Lot + SellLot 双轨（Lot.quantity 反映残量，SellLot 独立流水） |
| 成本核算 | 移动加权平均（按比例扣减 Lot，cost_price 不变） |
| 整数分配 | Hamilton 最大余数法 |
| 手动添加表单 | 单 Lot 表单（多次买入多次提交） |
| 现价获取 | 进入 Tab 自动调 `/analytics` + 手动"刷新"按钮 |
| Lot 编辑 | 允许编辑 + 删除单笔 Lot |
| API 架构 | 方案 A：复用 Lot + 新增 SellLot / Lot CRUD 端点 |
| realized_pnl | 卖出时锁定存储，后续编辑 Lot 不重算 |

### 0.2 非目标（YAGNI）

- 不重构为 Trade 流水表（方案 B，工作量大且破坏 Phase 2 已稳定代码）
- 不做跨组合聚合持仓视图（保持 `/portfolio` 列表页只显示组合卡片）
- 不做实时行情推送（手动刷新足够）
- 不做股息/拆股/送股事件处理（属 Phase 4 范畴）
- 不做多账号/多币种（A 股单一账户人民币）
- 不做税损 harvesting / FIFO 切换（保留 Lot.quantity 字段足以支持未来扩展）
- 不动 CLI `--portfolio-cash/--portfolio-stock`（与 JSON 存储脱节的问题留待 Phase 3 agent 集成解决）
- 不引入 React Query（继续用 Zustand 手工管理，与现有 portfolio store 一致）

## 1. 数据模型扩展 (`python/valor/portfolio/models.py`)

### 1.1 新增 SellLot

```python
class SellLot(BaseModel):
    """单笔卖出记录（用于已实现盈亏追踪）"""
    sell_id: str
    sell_date: date
    quantity: int                    # 卖出股数
    sell_price: Decimal              # 卖出成交价
    fees: Decimal = Decimal("0")
    realized_pnl: Decimal            # 卖出时锁定的已实现盈亏
    avg_cost_at_sell: Decimal        # 卖出时的加权平均成本快照
    note: str | None = None
```

### 1.2 Holding 加字段

```python
class Holding(BaseModel):
    ticker: str
    name: str | None = None
    lots: list[Lot] = []
    sell_lots: list[SellLot] = []    # 新增：卖出流水
    side: Literal["long", "short"] = "long"
```

其他模型（`Lot` / `Portfolio` / `Strategy` / `RebalanceAction` / `RebalancePlan`）不变。

### 1.3 显示口径（前端 + Analytics 共用）

| 字段 | 计算公式 |
|---|---|
| 持仓数量 | `Σ(lot.quantity)` |
| 持仓成本 | `Σ(lot.cost_price × lot.quantity)` |
| 买入均价 | `持仓成本 / 持仓数量` |
| 现价 | `PriceLookup.get(ticker, today)` |
| 市值 | `持仓数量 × 现价` |
| 浮动盈亏 | `市值 - 持仓成本` |
| 浮动盈亏% | `浮动盈亏 / 持仓成本` |
| 累计已实现盈亏 | `Σ(sell_lot.realized_pnl)` |
| 个股仓位 | `市值 / 组合总市值` |

`analytics.py` 的 `PositionMetric` 已覆盖前 7 项；新增 `realized_pnl` 字段：

```python
class PositionMetric(BaseModel):
    # ... 现有字段 ...
    realized_pnl: Decimal = Decimal("0")  # 新增：累计已实现盈亏
```

### 1.4 ID 生成

- `sell_id` = `sell_<short_uuid>`（与 `lot_id` 同格式）

## 2. 后端 API 扩展 (`python/valor/server/routes/portfolio.py`)

### 2.1 新增端点（3 条）

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/portfolios/{pid}/holdings/{ticker}/sells` | 追加一笔 SellLot，按比例扣减 Lot.quantity |
| `PUT` | `/portfolios/{pid}/holdings/{ticker}/lots/{lot_id}` | 编辑单笔 Lot（open_date/cost_price/fees/quantity/note） |
| `DELETE` | `/portfolios/{pid}/holdings/{ticker}/lots/{lot_id}` | 删除单笔 Lot（quantity/cost 直接消失，不影响 SellLot） |

现有 17 条端点不变。

### 2.2 请求/响应示例

**POST `/portfolios/{pid}/holdings/{ticker}/sells`**

```json
// request
{
  "sell_date": "2026-07-19",
  "quantity": 100,
  "sell_price": "1820.00",
  "fees": "15.50",
  "note": "止盈"
}
// response (ApiResponse.ok)
{
  "code": 0,
  "data": {
    "sell_id": "sell_abc123",
    "sell_date": "2026-07-19",
    "quantity": 100,
    "sell_price": "1820.00",
    "fees": "15.50",
    "realized_pnl": "12984.50",
    "avg_cost_at_sell": "1689.50",
    "note": "止盈"
  }
}
```

**PUT `/portfolios/{pid}/holdings/{ticker}/lots/{lot_id}`**

```json
// request（部分字段，未传不动）
{
  "cost_price": "1695.00",
  "fees": "13.00"
}
// response: 返回更新后的整条 Holding（与现有 PUT /holdings/{ticker} 风格一致）
```

**DELETE `/portfolios/{pid}/holdings/{ticker}/lots/{lot_id}`**

```json
// response
{"code": 0, "data": {"deleted": "lot_abc123"}}
```

### 2.3 错误码

| 场景 | code | message |
|---|---|---|
| portfolio 不存在 | 404 | `portfolio not found: {pid}` |
| holding 不存在 | 404 | `holding not found: {ticker}` |
| lot 不存在 | 404 | `lot not found: {lot_id}` |
| 减仓量 > 持仓量 | 400 | `sell quantity exceeds position: requested={n}, available={m}` |
| 减仓量 <= 0 | 400 | `sell quantity must be positive` |
| 编辑 lot quantity 变成负数 | 400 | `lot quantity must be non-negative` |
| Decimal 解析失败 | 422 | FastAPI 默认 validation error |

### 2.4 现有端点的兼容性

- `POST /holdings`（新增 holding）：不动，请求体不传 `sell_lots`，后端默认空数组
- `PUT /holdings/{ticker}`（整条替换）：保留，但前端新 UI 不再使用（仅旧代码路径）
- `POST /holdings/{ticker}/lots`（追加 Lot）：保留，前端"增持"按钮可复用此端点（追加 Lot = 增持）

## 3. Storage 层扣减逻辑 (`python/valor/portfolio/storage.py`)

### 3.1 新增函数

```python
def deduct_lots_weighted(
    lots: list[Lot],
    quantity_to_sell: int,
) -> list[tuple[Lot, int]]:
    """按比例扣减 Lot，返回 [(lot, deducted_qty), ...]。
    
    使用 Hamilton 最大余数法分配整数：
    1. 各 lot 应扣 = quantity_to_sell × lot.quantity / total_quantity
    2. 取整数部分先扣
    3. 余数按小数部分降序，依次 +1 直到扣完
    
    不修改 cost_price（移动加权平均的均价不变）。
    """
```

### 3.2 新增 storage 接口

```python
def add_sell(
    portfolio_id: str,
    ticker: str,
    sell_lot: SellLot,
    data_dir: Path,
) -> Portfolio:
    """追加 SellLot 并按比例扣减 Lot.quantity。
    
    步骤：
    1. load portfolio, find holding
    2. 验证 sell_lot.quantity <= Σ(lot.quantity)
    3. 算 avg_cost_at_sell = Σ(lot.cost_price × lot.quantity) / Σ(lot.quantity)
    4. 算 realized_pnl = sell_lot.quantity × (sell_lot.sell_price - avg_cost_at_sell) - sell_lot.fees
    5. 调 deduct_lots_weighted 扣减 lot.quantity
    6. append sell_lot 到 holding.sell_lots
    7. save portfolio
    """

def update_lot(
    portfolio_id: str,
    ticker: str,
    lot_id: str,
    patch: dict,
    data_dir: Path,
) -> Portfolio:
    """部分更新单笔 Lot。patch 支持的字段：open_date/cost_price/fees/quantity/note。
    
    注意：编辑 lot 不影响已有 SellLot 的 realized_pnl（已锁定）。
    """

def remove_lot(
    portfolio_id: str,
    ticker: str,
    lot_id: str,
    data_dir: Path,
) -> Portfolio:
    """删除单笔 Lot。若该 holding 的 lots 变空且 sell_lots 也空，则删除整个 holding。"""
```

### 3.3 文件锁与原子性

复用现有 `_locked_write` 上下文管理器（`storage.py:50-57`）。三个新函数都在锁内完成 load-modify-save。

### 3.4 数据迁移

旧 JSON 文件没有 `sell_lots` 字段。Pydantic v2 默认值 `[]` 自动兼容，无需显式迁移脚本。首次 load 后再 save 即写入新字段。

## 4. 前端改造 (`frontend/src/app/portfolio/`)

### 4.1 HoldingsTable.tsx 改造

**列扩展**（从 5 列扩到 9 列）：

| 列 | 来源 | 备注 |
|---|---|---|
| 展开/折叠 | UI | 点击展开 Lot + SellLot 明细 |
| 代码 | holding.ticker | |
| 名称 | holding.name | |
| 持仓数量 | Σ(lot.quantity) | |
| 买入均价 | 持仓成本 / 持仓数量 | 保留 2 位小数 |
| 现价 | analytics.positions[i].current_price | 红/绿着色 |
| 浮动盈亏 | analytics.positions[i].unrealized_pnl | 金额 + % |
| 个股仓位 | analytics.positions[i].weight × 100% | 进度条 |
| 操作 | UI | 诊断/增持/减仓/删除 |

**展开行内容**：

- Lot 表：开仓日 / 数量 / 成本价 / 手续费 / 备注 / 编辑 / 删除
- SellLot 表（如有）：卖出日 / 数量 / 卖出价 / 手续费 / 已实现盈亏 / 备注

**数据获取**：

- 进入 Tab 时并行调 `portfolioApi.listHoldings(pid)` 与 `portfolioApi.analytics(pid)`
- 用 ticker 做 key 合并两份数据
- 顶部加"刷新"按钮触发 `analytics` 重拉
- 复用现有 Zustand store 的 `current` 字段，新增 `analytics` 字段缓存

**空状态**：

- 无 holding：显示"暂无持仓，点击「新增持仓」或「导入 CSV」"
- 有 holding 但 `analytics` 加载中：表格骨架屏
- `analytics` 加载失败：表格显示静态字段 + 顶部红色横幅"行情加载失败，[重试]"

### 4.2 表单组件

**HoldingForm.tsx（改造）**：保持单 Lot 表单，字段不变（代码/名称/买入日期/数量/成本价/手续费/备注）。新增 `mode: "create" | "append"` prop：

- `mode="create"`：完整表单（含代码/名称），提交时调 `addHolding`（若 ticker 已存在则 fallback 到 `addLot`）
- `mode="append"`：隐藏代码/名称字段（用当前行 ticker/name 预填），仅录入 Lot 字段，提交调 `addLot`

行内"增持"按钮打开 `HoldingForm mode="append"`；顶部"新增持仓"按钮打开 `HoldingForm mode="create"`。

**新增 ReduceForm.tsx**：

- 字段：卖出日期 / 卖出数量 / 卖出价 / 手续费 / 备注
- 校验：数量 > 0 且 ≤ 当前持仓量
- 提交调 `portfolioApi.addSell(pid, ticker, payload)`
- 成功后刷新 holdings + analytics

**新增 EditLotForm.tsx**：

- 字段：开仓日 / 数量 / 成本价 / 手续费 / 备注
- 提交调 `portfolioApi.updateLot(pid, ticker, lotId, payload)`

### 4.3 API 客户端 (`frontend/src/api/portfolio.ts`)

新增三个方法：

```typescript
addSell: (pid: string, ticker: string, sell: Omit<SellLot, "sell_id" | "realized_pnl" | "avg_cost_at_sell">) =>
  apiClient.post<SellLot>(`${BASE}/${pid}/holdings/${ticker}/sells`, sell),
updateLot: (pid: string, ticker: string, lotId: string, patch: Partial<Omit<Lot, "lot_id">>) =>
  apiClient.put<Holding>(`${BASE}/${pid}/holdings/${ticker}/lots/${lotId}`, patch),
deleteLot: (pid: string, ticker: string, lotId: string) =>
  apiClient.delete<{ deleted: string }>(`${BASE}/${pid}/holdings/${ticker}/lots/${lotId}`),
```

### 4.4 类型定义 (`frontend/src/app/portfolio/types.ts`)

```typescript
export interface SellLot {
  sell_id: string;
  sell_date: string;
  quantity: number;
  sell_price: string;
  fees: string;
  realized_pnl: string;
  avg_cost_at_sell: string;
  note?: string | null;
}

export interface Holding {
  ticker: string;
  name?: string | null;
  lots: Lot[];
  sell_lots?: SellLot[];  // 新增，可选以兼容旧后端
  side: "long" | "short";
}
```

`PositionMetric` 加 `realized_pnl: string`。

### 4.5 Zustand store (`frontend/src/app/portfolio/store.ts`)

`PortfolioState` 新增字段：

```typescript
interface PortfolioState {
  // ... 现有 ...
  analytics: PortfolioAnalytics | null;
  analyticsLoading: boolean;
  fetchAnalytics: (pid: string) => Promise<void>;
}
```

`fetchDetail` 改为并行拉 `get(pid)` + `analytics(pid)`。

### 4.6 组件复用

- 表单弹窗：复用 shadcn `Dialog` + `Input` + `Label` + `Button`
- 表格：复用 shadcn `Table`（原生 `<table>` 包装）
- 数字格式化：新增 `lib/format.ts`（保留现有 analysis 模块的格式化函数，提取共用）
- 颜色：浮亏绿（`text-emerald-600`）、浮盈红（`text-rose-600`）—— A 股习惯

## 5. 错误处理与边界

### 5.1 前端

- 表单字段级校验：数量必须正整数、价格必须 > 0、日期不可晚于今天
- 提交失败：toast 显示后端 message，表单不关闭
- 网络失败：retry 按钮
- 删除 Lot/Holding：shadcn AlertDialog 二次确认
- 减仓后 holding 持仓为 0：自动从列表移除（后端 `remove_lot` 已处理，前端轮询刷新）

### 5.2 后端

- 文件锁失败：返回 500 + 日志记录（不静默）
- Decimal 精度：金额保留 4 位小数内部计算，2 位显示
- `deduct_lots_weighted` 输入校验：`quantity_to_sell` 必须 ≤ `Σ(lot.quantity)`，否则 raise
- `update_lot` 的 `quantity` 字段若被改为 0：自动从 holding.lots 移除该 lot，并触发"lots 空判定"（见下条）
- 删除/扣空最后一笔 Lot 后：
  - 若 `holdings[i].sell_lots` 也为空 -> 自动删除整个 Holding（避免空 Holding 残留）
  - 若 `holdings[i].sell_lots` 非空 -> 保留 Holding（保留卖出历史用于审计），但 UI 表格中以"已清仓"标记
- `update_lot` 改 `cost_price` 后：不影响已有 SellLot.realized_pnl（已锁定），但影响后续 SellLot 的 avg_cost_at_sell

### 5.3 并发

- 同一 portfolio 的写操作串行化（已有 `fcntl.flock`）
- 不同 portfolio 不互锁
- 读操作不加锁（容忍偶发的读写不一致，单机单用户场景可接受）

## 6. 测试策略

### 6.1 单元测试（`tests/unit/`）

**新增 `test_portfolio_storage_sells.py`**：

- `deduct_lots_weighted`：
  - 单 Lot 扣减（扣完 / 扣部分）
  - 多 Lot 按比例扣减（整数分配正确）
  - Hamilton 余数分配（小数部分降序）
  - 扣减量 = 总持仓（清仓）
  - 扣减量 > 总持仓（raise）
  - 扣减量 = 0（raise）
- `add_sell`：
  - 计算 avg_cost_at_sell 正确
  - 计算 realized_pnl 正确（含 fees）
  - 扣减后 lot.quantity 残量正确
  - sell_lots 列表追加正确
  - 锁定后编辑 lot 不影响 realized_pnl
- `update_lot`：
  - 部分字段更新（未传字段不动）
  - quantity 改为 0 自动移除 lot
  - 改 cost_price 不影响已有 SellLot
- `remove_lot`：
  - 删除中间 lot
  - 删完 lot 且无 sell_lots -> holding 自动删除
  - 删完 lot 但有 sell_lots -> holding 保留

**扩展 `test_portfolio_analytics.py`**：

- `realized_pnl` 字段聚合正确
- 减仓后浮动盈亏与已实现盈亏分离

### 6.2 API 测试（`tests/api/test_portfolio_routes.py`）

新增 3 条端点各覆盖 happy path + 错误路径：

- POST `/sells`：成功 / 持仓不足 / quantity 非正 / portfolio 不存在 / holding 不存在
- PUT `/lots/{lot_id}`：成功 / lot 不存在 / quantity 改 0 / 部分字段
- DELETE `/lots/{lot_id}`：成功 / lot 不存在 / 删完自动清 holding

### 6.3 前端测试

HoldingsTable 改造较重，新增组件测试（若项目已有 vitest 配置则用，否则手动验证）：

- 表格列渲染正确
- 展开/折叠交互
- 增持/减仓/编辑/删除按钮跳转正确表单
- 空状态/加载中/错误状态显示

### 6.4 测试纪律

- TDD：先写失败测试再实现
- 无网络依赖：mock DataRouter
- Decimal 精度：`quantize(Decimal("0.01"))` 比较
- 覆盖率目标：新增代码 ≥ 90%

### 6.5 测试命令

```bash
uv run pytest tests/unit/test_portfolio_storage_sells.py -v
uv run pytest tests/api/test_portfolio_routes.py -v
uv run ruff check valor/portfolio/ valor/server/routes/portfolio.py
```

## 7. 验收标准

1. **持仓表格**：进入"持仓" Tab 自动展示 9 列（含现价/均价/盈亏/仓位），3 秒内出数据
2. **手动新增**：点"新增持仓"填表单 -> 表格出现新行
3. **增持**：行内"增持"按钮 -> 弹窗填数量/价格/日期 -> 提交 -> 持仓量增加、均价更新
4. **减仓**：行内"减仓"按钮 -> 弹窗填数量/价格/日期 -> 提交 -> 持仓量减少、SellLot 入库、累计已实现盈亏显示
5. **编辑 Lot**：展开 Lot -> "编辑" -> 改成本价 -> 提交 -> 均价更新
6. **删除 Lot**：展开 Lot -> "删除" -> 二次确认 -> 持仓量减少
7. **删除 Holding**：行内"删除" -> 二次确认 -> 行消失
8. **CSV 导入**：保留现有功能，导入后表格刷新
9. **刷新按钮**：点击 -> 现价/盈亏/仓位重新计算
10. **测试**：`uv run pytest tests/unit/test_portfolio_storage_sells.py tests/api/test_portfolio_routes.py` 全绿
11. **Lint**：`uv run ruff check valor/portfolio/ valor/server/routes/portfolio.py` 0 错误

## 8. 实现顺序（建议）

1. 后端：`models.py` 加 `SellLot` + `Holding.sell_lots` + `PositionMetric.realized_pnl`
2. 后端：`storage.py` 加 `deduct_lots_weighted` + `add_sell` + `update_lot` + `remove_lot`（TDD）
3. 后端：`analytics.py` 算 `realized_pnl`
4. 后端：`routes/portfolio.py` 加 3 条新端点（TDD）
5. 前端：`types.ts` 加 `SellLot` + 扩展 `Holding` / `PositionMetric`
6. 前端：`api/portfolio.ts` 加 3 个新方法
7. 前端：`store.ts` 加 `analytics` 字段 + `fetchAnalytics`
8. 前端：`HoldingsTable.tsx` 扩列 + 展开行 + 操作按钮
9. 前端：`ReduceForm.tsx` + `EditLotForm.tsx`
10. 前端：`HoldingForm.tsx` 兼容 ticker 已存在的追加 Lot 路径
11. 手动验证 9 条验收标准

## 9. 与 Phase 3 的衔接

- `SellLot` 模型可作为 Phase 3 agent 回测的"交易流水输入"
- `realized_pnl` 聚合可复用于回测净值评估
- `deduct_lots_weighted` 算法可被 backtester 复用做虚拟减仓
- 不动 CLI `--portfolio-cash/--portfolio-stock`，Phase 3 再统一处理 agent workflow 与 JSON 存储的衔接

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Hamilton 整数分配在边界场景出错（如 N > 总量） | 输入校验 + 单测覆盖所有边界 |
| 编辑 Lot 后历史 SellLot 的 avg_cost_at_sell 与当前不一致 | 文档说明"realized_pnl 锁定不重算"；UI 显示 SellLot 时附"当时均价"列 |
| 减仓到 0 后 holding 自动删除，用户丢失"曾经持仓过"记录 | 保留 SellLot 流水；未来可加"历史持仓"视图 |
| analytics 调用慢（多 ticker 串行取价） | Phase 2 已有 DataRouter 缓存；本 spec 不优化，留待未来并发取价 |
| 前端 9 列表格在窄屏溢出 | 关键列固定（代码/名称/数量/操作），其他列水平滚动 |
| 旧 JSON 文件无 sell_lots 字段 | Pydantic 默认 `[]` 自动兼容，无需迁移 |
| 减仓时 lot.quantity 扣成 0 但保留空 lot | storage 层自动过滤 quantity=0 的 lot，不入文件 |
