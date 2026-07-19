# Portfolio Holdings Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 2 portfolio module with manual add/delete, append/reduce, single-Lot edit/delete, and a 9-column holdings table showing current price / avg cost / P&L / weight.

**Architecture:** Extend `Lot`/`SellLot` dual-track model with weighted-average deduction (Hamilton largest-remainder integer allocation). Add 3 backend endpoints (`POST /sells`, `PUT/DELETE /lots/{lot_id}`). Frontend `HoldingsTable` consumes existing `/analytics` endpoint + newLot/SellLot APIs through Zustand store.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, fcntl file locks; React 19, TypeScript, Zustand, shadcn/ui, Tailwind.

## Global Constraints

- Python 3.12 + Pydantic v2; money uses `Decimal` (never `float`)
- Existing route prefix `/api/v1/portfolios`; responses use `valor.server.envelope.ok()`
- JSON file storage with `fcntl.flock` (no SQL for portfolio data)
- A-share color convention: `text-red-500` = gain, `text-green-500` = loss
- TDD: failing test → implement → passing test → commit
- Lint: `uv run ruff check valor/ tests/` 0 errors
- No new dependencies (scipy / pandas / Decimal already available)
- `realized_pnl` is locked at sell time; subsequent Lot edits do not recompute it
- Spec: `docs/superpowers/specs/2026-07-19-portfolio-holdings-enhancement-design.md`

---

## Task 1: Backend models - SellLot + Holding.sell_lots + PositionMetric.realized_pnl

**Files:**
- Modify: `python/valor/portfolio/models.py`
- Modify: `python/valor/portfolio/analytics.py:23-35` (PositionMetric class)
- Test: `python/tests/unit/test_portfolio_models.py` (extend)

**Interfaces:**
- Consumes: existing `Lot`, `Holding`, `PositionMetric`
- Produces: `SellLot` class (fields: `sell_id`, `sell_date`, `quantity`, `sell_price`, `fees`, `realized_pnl`, `avg_cost_at_sell`, `note`); `Holding.sell_lots: list[SellLot] = []`; `PositionMetric.realized_pnl: Decimal = Decimal("0")`

- [ ] **Step 1: Write failing test for SellLot + Holding.sell_lots**

Append to `python/tests/unit/test_portfolio_models.py`:

```python
from valor.portfolio.models import SellLot, Holding, Lot
from decimal import Decimal
from datetime import date

def test_sell_lot_creation():
    s = SellLot(
        sell_id="sell_abc",
        sell_date=date(2026, 7, 19),
        quantity=100,
        sell_price=Decimal("1820.00"),
        fees=Decimal("15.50"),
        realized_pnl=Decimal("12984.50"),
        avg_cost_at_sell=Decimal("1689.50"),
    )
    assert s.sell_id == "sell_abc"
    assert s.quantity == 100
    assert s.realized_pnl == Decimal("12984.50")

def test_holding_has_sell_lots_default_empty():
    h = Holding(ticker="600519", lots=[])
    assert h.sell_lots == []

def test_holding_with_sell_lots():
    h = Holding(
        ticker="600519",
        lots=[Lot(lot_id="l1", open_date=date(2024, 1, 1), quantity=100, cost_price=Decimal("1689.50"))],
        sell_lots=[SellLot(
            sell_id="s1", sell_date=date(2026, 7, 19), quantity=50,
            sell_price=Decimal("1820.00"), fees=Decimal("5.00"),
            realized_pnl=Decimal("6500.00"), avg_cost_at_sell=Decimal("1689.50"),
        )],
    )
    assert len(h.sell_lots) == 1
    assert h.sell_lots[0].sell_id == "s1"

def test_position_metric_has_realized_pnl_default_zero():
    from valor.portfolio.analytics import PositionMetric
    pm = PositionMetric(
        ticker="600519", name="贵州茅台", quantity=100,
        cost_price=Decimal("1689.50"), current_price=Decimal("1800.00"),
        market_value=Decimal("180000.00"), cost_value=Decimal("168950.00"),
        unrealized_pnl=Decimal("11050.00"), unrealized_pnl_pct=0.065, weight=1.0,
    )
    assert pm.realized_pnl == Decimal("0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/unit/test_portfolio_models.py::test_sell_lot_creation -v`
Expected: FAIL with `ImportError: cannot import name 'SellLot'`

- [ ] **Step 3: Add SellLot to models.py**

Edit `python/valor/portfolio/models.py`. After the `Lot` class (line 15), add:

```python
class SellLot(BaseModel):
    """单笔卖出记录（用于已实现盈亏追踪）"""
    sell_id: str
    sell_date: date
    quantity: int
    sell_price: Decimal
    fees: Decimal = Decimal("0")
    realized_pnl: Decimal
    avg_cost_at_sell: Decimal
    note: str | None = None
```

Then modify the `Holding` class (line 18-22) to add `sell_lots`:

```python
class Holding(BaseModel):
    """单一股票持仓 = 多个 Lot 的聚合"""
    ticker: str
    name: str | None = None
    lots: list[Lot] = []
    sell_lots: list[SellLot] = []
    side: Literal["long", "short"] = "long"
```

- [ ] **Step 4: Add realized_pnl to PositionMetric**

Edit `python/valor/portfolio/analytics.py:23-35`. After `beta: float | None = None` (line 35), add:

```python
    realized_pnl: Decimal = Decimal("0")
```

(Full updated class for clarity):
```python
class PositionMetric(BaseModel):
    ticker: str
    name: str | None
    quantity: int
    cost_price: Decimal
    current_price: Decimal
    market_value: Decimal
    cost_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: float
    weight: float
    sector: str | None = None
    beta: float | None = None
    realized_pnl: Decimal = Decimal("0")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd python && uv run pytest tests/unit/test_portfolio_models.py -v`
Expected: PASS (all 4 new tests + existing tests)

- [ ] **Step 6: Lint and commit**

```bash
cd python && uv run ruff check valor/portfolio/models.py valor/portfolio/analytics.py
git add python/valor/portfolio/models.py python/valor/portfolio/analytics.py python/tests/unit/test_portfolio_models.py
git commit -m "feat(portfolio): add SellLot model, Holding.sell_lots, PositionMetric.realized_pnl"
```

---

## Task 2: Backend storage - gen_sell_id + deduct_lots_weighted

**Files:**
- Modify: `python/valor/portfolio/storage.py` (add `gen_sell_id` after `gen_lot_id` at line 38; add `deduct_lots_weighted` after `_find_holding_index` at line 136)
- Test: `python/tests/unit/test_portfolio_storage_sells.py` (new file)

**Interfaces:**
- Consumes: `Lot` from `valor.portfolio.models`
- Produces: `gen_sell_id() -> str`; `deduct_lots_weighted(lots: list[Lot], quantity_to_sell: int) -> list[tuple[Lot, int]]` (mutates `lot.quantity` in place; returns `[(lot, deducted_qty), ...]`); raises `ValueError` if `quantity_to_sell > total` or `<= 0`

- [ ] **Step 1: Write failing tests**

Create `python/tests/unit/test_portfolio_storage_sells.py`:

```python
"""Tests for sell-lot storage operations. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from datetime import date, datetime
from decimal import Decimal
import pytest
from valor.portfolio.models import Holding, Lot, Portfolio, SellLot
from valor.portfolio.storage import (
    DATA_DIR, deduct_lots_weighted, gen_sell_id, set_data_dir,
)


@pytest.fixture
def tmp_dir(tmp_path, monkeypatch):
    set_data_dir(tmp_path)
    yield tmp_path
    set_data_dir(DATA_DIR)


def test_gen_sell_id_prefix():
    sid = gen_sell_id()
    assert sid.startswith("sell_")


def _lot(lid: str, qty: int, cost: str = "1689.50") -> Lot:
    return Lot(lot_id=lid, open_date=date(2024, 1, 1), quantity=qty, cost_price=Decimal(cost))


def test_deduct_single_lot_partial():
    lot = _lot("l1", 100)
    alloc = deduct_lots_weighted([lot], 30)
    assert alloc == [(lot, 30)]
    assert lot.quantity == 70


def test_deduct_single_lot_full():
    lot = _lot("l1", 100)
    alloc = deduct_lots_weighted([lot], 100)
    assert alloc == [(lot, 100)]
    assert lot.quantity == 0


def test_deduct_multi_lots_proportional():
    l1 = _lot("l1", 100)
    l2 = _lot("l2", 100)
    alloc = deduct_lots_weighted([l1, l2], 50)
    deducted = {lot.lot_id: d for lot, d in alloc}
    assert deducted["l1"] == 25
    assert deducted["l2"] == 25
    assert l1.quantity == 75
    assert l2.quantity == 75


def test_deduct_hamilton_remainder_distribution():
    """3 lots (100, 100, 100), sell 10 -> 3+3+3=9, remainder 1 goes to first lot."""
    l1 = _lot("l1", 100)
    l2 = _lot("l2", 100)
    l3 = _lot("l3", 100)
    alloc = deduct_lots_weighted([l1, l2, l3], 10)
    deducted = {lot.lot_id: d for lot, d in alloc}
    total = sum(deducted.values())
    assert total == 10
    # All lots get 3, then remainder 1 distributed by largest remainder
    # 10*100/300 = 3.333..., remainders all 0.333, first one gets the +1
    assert deducted["l1"] == 4
    assert deducted["l2"] == 3
    assert deducted["l3"] == 3


def test_deduct_exceeds_total_raises():
    lot = _lot("l1", 100)
    with pytest.raises(ValueError, match="exceeds"):
        deduct_lots_weighted([lot], 150)


def test_deduct_zero_or_negative_raises():
    lot = _lot("l1", 100)
    with pytest.raises(ValueError, match="positive"):
        deduct_lots_weighted([lot], 0)
    with pytest.raises(ValueError, match="positive"):
        deduct_lots_weighted([lot], -10)


def test_deduct_cost_price_unchanged():
    """移动加权平均：扣减 lot.quantity 不改 cost_price。"""
    lot = _lot("l1", 100, "1689.50")
    deduct_lots_weighted([lot], 30)
    assert lot.cost_price == Decimal("1689.50")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/unit/test_portfolio_storage_sells.py -v`
Expected: FAIL with `ImportError: cannot import name 'deduct_lots_weighted'`

- [ ] **Step 3: Implement gen_sell_id**

Edit `python/valor/portfolio/storage.py`. After `gen_lot_id` (line 38), add:

```python
def gen_sell_id() -> str:
    return f"sell_{uuid.uuid4().hex[:8]}"
```

- [ ] **Step 4: Implement deduct_lots_weighted**

Edit `python/valor/portfolio/storage.py`. After `_find_holding_index` (line 136), add:

```python
def deduct_lots_weighted(
    lots: list[Lot], quantity_to_sell: int
) -> list[tuple[Lot, int]]:
    """按移动加权平均扣减各 Lot.quantity（cost_price 不变）。

    用 Hamilton 最大余数法分配整数：
    1. 各 lot 应扣 = quantity_to_sell × lot.quantity / total_quantity
    2. 整数部分先扣
    3. 余数按小数部分降序依次 +1 直到扣完

    修改 lot.quantity 于原地。返回 [(lot, deducted_qty), ...]。
    """
    if quantity_to_sell <= 0:
        raise ValueError("sell quantity must be positive")
    total = sum(lot.quantity for lot in lots)
    if quantity_to_sell > total:
        raise ValueError(
            f"sell quantity exceeds position: requested={quantity_to_sell}, available={total}"
        )

    # 浮点配额 + 整数部分
    quotas = [
        (lot, quantity_to_sell * lot.quantity / total) for lot in lots
    ]
    int_alloc = [(lot, int(q)) for lot, q in quotas]
    allocated = sum(d for _, d in int_alloc)
    remainder = quantity_to_sell - allocated

    # 按小数部分降序，依次 +1
    remainders = sorted(
        range(len(quotas)),
        key=lambda i: quotas[i][1] - int(quotas[i][1]),
        reverse=True,
    )
    for i in remainders[:remainder]:
        lot, d = int_alloc[i]
        int_alloc[i] = (lot, d + 1)

    # 应用扣减
    result: list[tuple[Lot, int]] = []
    for lot, d in int_alloc:
        if d > 0:
            lot.quantity -= d
            result.append((lot, d))
    return result
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd python && uv run pytest tests/unit/test_portfolio_storage_sells.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 6: Lint and commit**

```bash
cd python && uv run ruff check valor/portfolio/storage.py tests/unit/test_portfolio_storage_sells.py
git add python/valor/portfolio/storage.py python/tests/unit/test_portfolio_storage_sells.py
git commit -m "feat(portfolio): add gen_sell_id and deduct_lots_weighted (Hamilton allocation)"
```

---

## Task 3: Backend storage - add_sell

**Files:**
- Modify: `python/valor/portfolio/storage.py` (add `add_sell` after `add_holding` at line 147)
- Test: `python/tests/unit/test_portfolio_storage_sells.py` (extend)

**Interfaces:**
- Consumes: `deduct_lots_weighted`, `SellLot`, `Portfolio`, `Holding`, `Lot`
- Produces: `add_sell(portfolio_id: str, ticker: str, sell_lot: SellLot) -> Portfolio` -- computes `avg_cost_at_sell` and `realized_pnl` if not provided (or overrides if provided), deducts lots, appends sell_lot. Raises `HoldingNotFound`, `ValueError` (sell qty > position).

- [ ] **Step 1: Write failing tests**

Append to `python/tests/unit/test_portfolio_storage_sells.py`:

```python
from valor.portfolio.storage import (
    add_holding, add_sell, load_portfolio, save_portfolio, HoldingNotFound,
)


def _seed_portfolio(pid: str = "pf_t") -> Portfolio:
    p = Portfolio(
        portfolio_id=pid, name="t",
        created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17),
    )
    save_portfolio(p)
    return p


def _seed_holding(pid: str, ticker: str, lots: list[Lot], name: str = "贵州茅台") -> None:
    add_holding(pid, Holding(ticker=ticker, name=name, lots=lots))


def test_add_sell_basic():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])

    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=30,
        sell_price=Decimal("1820.00"), fees=Decimal("15.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    updated = add_sell("pf_t", "600519", sell)
    h = updated.holdings[0]
    assert len(h.sell_lots) == 1
    assert h.sell_lots[0].quantity == 30
    # lot quantity reduced
    assert h.lots[0].quantity == 70
    # cost_price unchanged
    assert h.lots[0].cost_price == Decimal("1689.50")
    # sell_id auto-generated
    assert h.sell_lots[0].sell_id.startswith("sell_")
    # avg_cost_at_sell = 1689.50 (single lot)
    assert h.sell_lots[0].avg_cost_at_sell == Decimal("1689.50")
    # realized_pnl = 30 * (1820 - 1689.50) - 15 = 3915 - 15 = 3900.00
    assert h.sell_lots[0].realized_pnl == Decimal("3900.00")


def test_add_sell_multi_lot_weighted_avg():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [
        _lot("l1", 100, "1689.50"),  # cost 168950
        _lot("l2", 100, "1800.00"),  # cost 180000
    ])  # total cost 349950, qty 200, avg 1749.75

    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=100,
        sell_price=Decimal("1900.00"), fees=Decimal("20.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    updated = add_sell("pf_t", "600519", sell)
    s = updated.holdings[0].sell_lots[0]
    assert s.avg_cost_at_sell == Decimal("1749.75")
    # realized_pnl = 100 * (1900 - 1749.75) - 20 = 15025 - 20 = 15005.00
    assert s.realized_pnl == Decimal("15005.00")
    # each lot reduced by 50 (proportional)
    assert updated.holdings[0].lots[0].quantity == 50
    assert updated.holdings[0].lots[1].quantity == 50


def test_add_sell_exceeds_position_raises():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])

    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=150,
        sell_price=Decimal("1820.00"), fees=Decimal("0"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    with pytest.raises(ValueError, match="exceeds"):
        add_sell("pf_t", "600519", sell)


def test_add_sell_holding_not_found():
    _seed_portfolio()
    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=10,
        sell_price=Decimal("1820.00"), fees=Decimal("0"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    with pytest.raises(HoldingNotFound):
        add_sell("pf_t", "000001", sell)


def test_add_sell_full_position_empties_lots():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])

    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=100,
        sell_price=Decimal("1820.00"), fees=Decimal("15.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    updated = add_sell("pf_t", "600519", sell)
    h = updated.holdings[0]
    # lot quantity now 0, but lot still present (will be filtered on save)
    # sell_lot present
    assert len(h.sell_lots) == 1
    assert h.sell_lots[0].quantity == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/unit/test_portfolio_storage_sells.py::test_add_sell_basic -v`
Expected: FAIL with `ImportError: cannot import name 'add_sell'`

- [ ] **Step 3: Implement add_sell**

Edit `python/valor/portfolio/storage.py`. After `add_holding` (line 147), add:

```python
def add_sell(portfolio_id: str, ticker: str, sell_lot: SellLot) -> Portfolio:
    """追加 SellLot 并按比例扣减 Lot.quantity。

    自动计算 avg_cost_at_sell 与 realized_pnl（覆盖传入的零值）。
    """
    from valor.portfolio.models import SellLot as _SellLot  # noqa: F401 (avoid circular)
    p = load_portfolio(portfolio_id)
    idx = _find_holding_index(p, ticker)
    if idx < 0:
        raise HoldingNotFound(ticker)
    h = p.holdings[idx]
    total_qty = sum(lot.quantity for lot in h.lots)
    if sell_lot.quantity > total_qty:
        raise ValueError(
            f"sell quantity exceeds position: requested={sell_lot.quantity}, available={total_qty}"
        )
    # 计算加权平均成本（扣减前）
    total_cost = sum(lot.quantity * lot.cost_price for lot in h.lots)
    avg_cost = total_cost / Decimal(total_qty) if total_qty else Decimal("0")
    sell_lot.avg_cost_at_sell = avg_cost
    sell_lot.realized_pnl = (
        Decimal(sell_lot.quantity) * (sell_lot.sell_price - avg_cost)
        - sell_lot.fees
    )
    # 扣减 Lot
    deduct_lots_weighted(h.lots, sell_lot.quantity)
    # 过滤 quantity=0 的 lot（保持文件干净）
    h.lots = [lot for lot in h.lots if lot.quantity > 0]
    # 生成 sell_id（若空）
    if not sell_lot.sell_id:
        sell_lot.sell_id = gen_sell_id()
    h.sell_lots.append(sell_lot)
    save_portfolio(p)
    return p
```

Also update the import at the top of `storage.py` (line 10):
```python
from valor.portfolio.models import Holding, Lot, Portfolio, SellLot, Strategy
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/unit/test_portfolio_storage_sells.py -v`
Expected: PASS (all 13 tests)

- [ ] **Step 5: Lint and commit**

```bash
cd python && uv run ruff check valor/portfolio/storage.py tests/unit/test_portfolio_storage_sells.py
git add python/valor/portfolio/storage.py python/tests/unit/test_portfolio_storage_sells.py
git commit -m "feat(portfolio): add_sell computes realized_pnl and deducts lots by weighted avg"
```

---

## Task 4: Backend storage - update_lot

**Files:**
- Modify: `python/valor/portfolio/storage.py` (add `LotNotFound`, `update_lot` after `add_sell`)
- Test: `python/tests/unit/test_portfolio_storage_sells.py` (extend)

**Interfaces:**
- Consumes: `Portfolio`, `Holding`, `Lot`
- Produces: `LotNotFound` exception; `update_lot(portfolio_id, ticker, lot_id, patch: dict) -> Portfolio` -- patches fields (open_date/cost_price/fees/quantity/note); if `quantity` becomes 0, removes the lot; after removal, if `lots` empty AND `sell_lots` empty, deletes the holding.

- [ ] **Step 1: Write failing tests**

Append to `python/tests/unit/test_portfolio_storage_sells.py`:

```python
from valor.portfolio.storage import LotNotFound, update_lot


def test_update_lot_partial_fields():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    updated = update_lot("pf_t", "600519", "l1", {"cost_price": Decimal("1700.00"), "fees": Decimal("12.50")})
    lot = updated.holdings[0].lots[0]
    assert lot.cost_price == Decimal("1700.00")
    assert lot.fees == Decimal("12.50")
    # unchanged fields
    assert lot.quantity == 100
    assert lot.open_date == date(2024, 1, 1)


def test_update_lot_quantity_to_zero_removes_lot():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [
        _lot("l1", 100, "1689.50"),
        _lot("l2", 50, "1700.00"),
    ])
    updated = update_lot("pf_t", "600519", "l1", {"quantity": 0})
    assert len(updated.holdings[0].lots) == 1
    assert updated.holdings[0].lots[0].lot_id == "l2"


def test_update_lot_quantity_to_zero_deletes_holding_when_no_sell_lots():
    """lot 全空 + sell_lots 空 -> holding 删除。"""
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    updated = update_lot("pf_t", "600519", "l1", {"quantity": 0})
    assert len(updated.holdings) == 0


def test_update_lot_quantity_to_zero_keeps_holding_when_has_sell_lots():
    """lot 全空 + sell_lots 非空 -> holding 保留（已清仓）。"""
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    # 先卖 50 留下 sell_lot
    add_sell("pf_t", "600519", SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=50,
        sell_price=Decimal("1820.00"), fees=Decimal("5.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    ))
    # 再 update 余下 50 -> 0
    updated = update_lot("pf_t", "600519", "l1", {"quantity": 0})
    assert len(updated.holdings) == 1
    assert len(updated.holdings[0].sell_lots) == 1
    assert len(updated.holdings[0].lots) == 0


def test_update_lot_not_found():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    with pytest.raises(LotNotFound):
        update_lot("pf_t", "600519", "l_missing", {"quantity": 50})


def test_update_lot_holding_not_found():
    _seed_portfolio()
    with pytest.raises(HoldingNotFound):
        update_lot("pf_t", "000001", "l1", {"quantity": 50})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/unit/test_portfolio_storage_sells.py::test_update_lot_partial_fields -v`
Expected: FAIL with `ImportError: cannot import name 'LotNotFound'`

- [ ] **Step 3: Implement LotNotFound + update_lot**

Edit `python/valor/portfolio/storage.py`. After `HoldingNotFound` (line 124), add:

```python
class LotNotFound(Exception):
    pass
```

After `add_sell` (added in Task 3), add:

```python
def _cleanup_holding_if_empty(p: Portfolio, idx: int) -> None:
    """若 holding.lots 与 sell_lots 都为空，从 portfolio 移除该 holding。"""
    h = p.holdings[idx]
    if not h.lots and not h.sell_lots:
        p.holdings.pop(idx)


def update_lot(
    portfolio_id: str, ticker: str, lot_id: str, patch: dict
) -> Portfolio:
    """部分更新单笔 Lot。patch 支持字段：open_date/cost_price/fees/quantity/note。
    quantity 改为 0 时自动移除该 lot；若 holding 同时变空（lots+sell_lots）则删除 holding。
    编辑 lot 不影响已有 SellLot.realized_pnl（已锁定）。
    """
    p = load_portfolio(portfolio_id)
    idx = _find_holding_index(p, ticker)
    if idx < 0:
        raise HoldingNotFound(ticker)
    h = p.holdings[idx]
    lot_index = next((i for i, lot in enumerate(h.lots) if lot.lot_id == lot_id), -1)
    if lot_index < 0:
        raise LotNotFound(lot_id)
    lot = h.lots[lot_index]
    for key, value in patch.items():
        if hasattr(lot, key) and value is not None:
            setattr(lot, key, value)
    # quantity 改为 0 -> 移除
    if lot.quantity == 0:
        h.lots.pop(lot_index)
        _cleanup_holding_if_empty(p, idx)
    save_portfolio(p)
    return p
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/unit/test_portfolio_storage_sells.py -v`
Expected: PASS (all 19 tests)

- [ ] **Step 5: Lint and commit**

```bash
cd python && uv run ruff check valor/portfolio/storage.py tests/unit/test_portfolio_storage_sells.py
git add python/valor/portfolio/storage.py python/tests/unit/test_portfolio_storage_sells.py
git commit -m "feat(portfolio): update_lot with patch + auto-cleanup empty holdings"
```

---

## Task 5: Backend storage - remove_lot

**Files:**
- Modify: `python/valor/portfolio/storage.py` (add `remove_lot` after `update_lot`)
- Test: `python/tests/unit/test_portfolio_storage_sells.py` (extend)

**Interfaces:**
- Consumes: `Portfolio`, `Holding`, `Lot`, `LotNotFound`, `_cleanup_holding_if_empty`
- Produces: `remove_lot(portfolio_id, ticker, lot_id) -> Portfolio` -- removes the lot; if holding becomes empty (no lots + no sell_lots), removes the holding.

- [ ] **Step 1: Write failing tests**

Append to `python/tests/unit/test_portfolio_storage_sells.py`:

```python
from valor.portfolio.storage import remove_lot


def test_remove_lot_basic():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [
        _lot("l1", 100, "1689.50"),
        _lot("l2", 50, "1700.00"),
    ])
    updated = remove_lot("pf_t", "600519", "l1")
    assert len(updated.holdings[0].lots) == 1
    assert updated.holdings[0].lots[0].lot_id == "l2"


def test_remove_last_lot_no_sell_lots_deletes_holding():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    updated = remove_lot("pf_t", "600519", "l1")
    assert len(updated.holdings) == 0


def test_remove_last_lot_with_sell_lots_keeps_holding():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    add_sell("pf_t", "600519", SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=50,
        sell_price=Decimal("1820.00"), fees=Decimal("5.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    ))
    # After sell, l1.quantity=50. Now remove it entirely.
    updated = remove_lot("pf_t", "600519", "l1")
    assert len(updated.holdings) == 1
    assert len(updated.holdings[0].sell_lots) == 1
    assert len(updated.holdings[0].lots) == 0


def test_remove_lot_not_found():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    with pytest.raises(LotNotFound):
        remove_lot("pf_t", "600519", "l_missing")


def test_remove_lot_holding_not_found():
    _seed_portfolio()
    with pytest.raises(HoldingNotFound):
        remove_lot("pf_t", "000001", "l1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/unit/test_portfolio_storage_sells.py::test_remove_lot_basic -v`
Expected: FAIL with `ImportError: cannot import name 'remove_lot'`

- [ ] **Step 3: Implement remove_lot**

Edit `python/valor/portfolio/storage.py`. After `update_lot` (added in Task 4), add:

```python
def remove_lot(portfolio_id: str, ticker: str, lot_id: str) -> Portfolio:
    """删除单笔 Lot。若 holding.lots 与 sell_lots 都变空，则删除整个 holding。"""
    p = load_portfolio(portfolio_id)
    idx = _find_holding_index(p, ticker)
    if idx < 0:
        raise HoldingNotFound(ticker)
    h = p.holdings[idx]
    lot_index = next((i for i, lot in enumerate(h.lots) if lot.lot_id == lot_id), -1)
    if lot_index < 0:
        raise LotNotFound(lot_id)
    h.lots.pop(lot_index)
    _cleanup_holding_if_empty(p, idx)
    save_portfolio(p)
    return p
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/unit/test_portfolio_storage_sells.py -v`
Expected: PASS (all 24 tests)

- [ ] **Step 5: Lint and commit**

```bash
cd python && uv run ruff check valor/portfolio/storage.py tests/unit/test_portfolio_storage_sells.py
git add python/valor/portfolio/storage.py python/tests/unit/test_portfolio_storage_sells.py
git commit -m "feat(portfolio): remove_lot with auto-cleanup empty holdings"
```

---

## Task 6: Backend analytics - realized_pnl aggregation

**Files:**
- Modify: `python/valor/portfolio/analytics.py:81-87` (PositionMetric construction)
- Test: `python/tests/unit/test_portfolio_analytics.py` (extend)

**Interfaces:**
- Consumes: `Holding.sell_lots` from Task 1
- Produces: `PositionMetric.realized_pnl` = `Σ(sell_lot.realized_pnl)` per ticker

- [ ] **Step 1: Write failing test**

Append to `python/tests/unit/test_portfolio_analytics.py`:

```python
@pytest.mark.asyncio
async def test_compute_analytics_realized_pnl_aggregation():
    """SellLot.realized_pnl 应聚合到 PositionMetric.realized_pnl。"""
    from datetime import date, datetime
    from decimal import Decimal
    from unittest.mock import AsyncMock
    from valor.portfolio.models import Portfolio, Holding, Lot, SellLot
    from valor.portfolio.analytics import compute_analytics

    p = Portfolio(
        portfolio_id="pf_t", name="t", benchmark="000300",
        cash=Decimal("0"),
        created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17),
        holdings=[
            Holding(
                ticker="600519", name="贵州茅台",
                lots=[Lot(lot_id="l1", open_date=date(2024, 1, 1), quantity=70, cost_price=Decimal("1689.50"))],
                sell_lots=[
                    SellLot(sell_id="s1", sell_date=date(2026, 7, 1), quantity=30,
                            sell_price=Decimal("1820.00"), fees=Decimal("15.00"),
                            realized_pnl=Decimal("3900.00"), avg_cost_at_sell=Decimal("1689.50")),
                    SellLot(sell_id="s2", sell_date=date(2026, 7, 10), quantity=0,
                            sell_price=Decimal("0"), fees=Decimal("0"),
                            realized_pnl=Decimal("100.00"), avg_cost_at_sell=Decimal("0")),
                ],
            ),
        ],
    )
    price_lookup = AsyncMock()
    price_lookup.get = AsyncMock(return_value=Decimal("1800.00"))
    result = await compute_analytics(p, price_lookup)
    pos = result.positions[0]
    # 3900 + 100 = 4000
    assert pos.realized_pnl == Decimal("4000.00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/unit/test_portfolio_analytics.py::test_compute_analytics_realized_pnl_aggregation -v`
Expected: FAIL with `assert Decimal("0") == Decimal("4000.00")` (realized_pnl defaults to 0, not aggregated)

- [ ] **Step 3: Implement realized_pnl aggregation**

Edit `python/valor/portfolio/analytics.py`. Modify the `compute_analytics` function. After computing `pnl` (around line 80) and before `positions.append(...)`, add the realized_pnl aggregation. Replace the `positions.append(...)` block (lines 81-87):

```python
        realized = sum(
            (s.realized_pnl for s in h.sell_lots),
            Decimal("0"),
        )
        positions.append(PositionMetric(
            ticker=h.ticker, name=h.name, quantity=qty, cost_price=avg_cost,
            current_price=price, market_value=market_value, cost_value=cost_value,
            unrealized_pnl=pnl,
            unrealized_pnl_pct=float(pnl / cost_value) if cost_value else 0.0,
            weight=0.0,
            realized_pnl=realized,
        ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/unit/test_portfolio_analytics.py -v`
Expected: PASS (all existing + new test)

- [ ] **Step 5: Lint and commit**

```bash
cd python && uv run ruff check valor/portfolio/analytics.py tests/unit/test_portfolio_analytics.py
git add python/valor/portfolio/analytics.py python/tests/unit/test_portfolio_analytics.py
git commit -m "feat(portfolio): aggregate SellLot.realized_pnl into PositionMetric"
```

---

## Task 7: Backend routes - POST /sells

**Files:**
- Modify: `python/valor/server/routes/portfolio.py` (add route after `add_lot` at line 199)
- Test: `python/tests/api/test_portfolio_routes.py` (extend)

**Interfaces:**
- Consumes: `storage.add_sell`, `SellLot` model
- Produces: `POST /api/v1/portfolios/{pid}/holdings/{ticker}/sells` endpoint. Request body: `SellLotInput` (sell_date, quantity, sell_price, fees, note). Response: the created `SellLot` (with computed `realized_pnl`, `avg_cost_at_sell`, `sell_id`).

- [ ] **Step 1: Write failing tests**

Append to `python/tests/api/test_portfolio_routes.py`:

```python
# --- Sell Lots ---


def _seed_holding(app_client, pid, ticker="600519", qty=100, cost="1689.50"):
    """Helper: add a holding with one lot via API."""
    app_client.post(
        f"/api/v1/portfolios/{pid}/holdings",
        json={
            "ticker": ticker,
            "name": "贵州茅台",
            "side": "long",
            "lots": [{
                "lot_id": "",
                "open_date": "2024-01-01",
                "quantity": qty,
                "cost_price": cost,
                "fees": "0",
            }],
        },
    )


def test_add_sell_success(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid)
    resp = app_client.post(
        f"/api/v1/portfolios/{pid}/holdings/600519/sells",
        json={
            "sell_date": "2026-07-19",
            "quantity": 30,
            "sell_price": "1820.00",
            "fees": "15.00",
            "note": "止盈",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["sell_id"].startswith("sell_")
    assert data["quantity"] == 30
    assert data["avg_cost_at_sell"] == "1689.50"
    # 30 * (1820 - 1689.50) - 15 = 3900.00
    assert data["realized_pnl"] == "3900.0000" or Decimal(data["realized_pnl"]) == Decimal("3900.00")


def test_add_sell_exceeds_position_400(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid, qty=100)
    resp = app_client.post(
        f"/api/v1/portfolios/{pid}/holdings/600519/sells",
        json={"sell_date": "2026-07-19", "quantity": 200, "sell_price": "1820.00", "fees": "0"},
    )
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"]


def test_add_sell_holding_not_found_404(app_client):
    pid = _seed(app_client)
    resp = app_client.post(
        f"/api/v1/portfolios/{pid}/holdings/000001/sells",
        json={"sell_date": "2026-07-19", "quantity": 10, "sell_price": "10.00", "fees": "0"},
    )
    assert resp.status_code == 404


def test_add_sell_portfolio_not_found_404(app_client):
    resp = app_client.post(
        "/api/v1/portfolios/pf_missing/holdings/600519/sells",
        json={"sell_date": "2026-07-19", "quantity": 10, "sell_price": "10.00", "fees": "0"},
    )
    assert resp.status_code == 404
```

Also add at top of file (if not already imported):
```python
from decimal import Decimal
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/api/test_portfolio_routes.py::test_add_sell_success -v`
Expected: FAIL with 404 (route not registered)

- [ ] **Step 3: Implement POST /sells endpoint**

Edit `python/valor/server/routes/portfolio.py`. Update the import on line 8 to include `SellLot`:
```python
from valor.portfolio.models import Portfolio, Holding, Lot, SellLot, Strategy
```

After `add_lot` (line 199), add:

```python
class SellLotInput(BaseModel):
    sell_date: date
    quantity: int
    sell_price: Decimal
    fees: Decimal = Decimal("0")
    note: str | None = None


@router.post("/{pid}/holdings/{ticker}/sells")
async def add_sell(pid: str, ticker: str, body: SellLotInput):
    try:
        p = storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    # find holding
    holding = next((h for h in p.holdings if h.ticker == ticker), None)
    if holding is None:
        raise HTTPException(status_code=404, detail="holding not found")
    sell = SellLot(
        sell_id="",
        sell_date=body.sell_date,
        quantity=body.quantity,
        sell_price=body.sell_price,
        fees=body.fees,
        note=body.note,
        realized_pnl=Decimal("0"),
        avg_cost_at_sell=Decimal("0"),
    )
    try:
        updated = storage.add_sell(pid, ticker, sell)
    except storage.HoldingNotFound:
        raise HTTPException(status_code=404, detail="holding not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # return the latest sell_lot
    h = next(x for x in updated.holdings if x.ticker == ticker)
    return ok(h.sell_lots[-1].model_dump(mode="json"))
```

Also add `date` to the import at line 3:
```python
from datetime import date, datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/api/test_portfolio_routes.py -v -k sell`
Expected: PASS (all 4 sell tests)

- [ ] **Step 5: Lint and commit**

```bash
cd python && uv run ruff check valor/server/routes/portfolio.py tests/api/test_portfolio_routes.py
git add python/valor/server/routes/portfolio.py python/tests/api/test_portfolio_routes.py
git commit -m "feat(portfolio): POST /holdings/{ticker}/sells endpoint"
```

---

## Task 8: Backend routes - PUT /lots/{lot_id}

**Files:**
- Modify: `python/valor/server/routes/portfolio.py` (add route after `add_sell` from Task 7)
- Test: `python/tests/api/test_portfolio_routes.py` (extend)

**Interfaces:**
- Consumes: `storage.update_lot`, `LotNotFound`
- Produces: `PUT /api/v1/portfolios/{pid}/holdings/{ticker}/lots/{lot_id}` endpoint. Request body: `LotPatch` (open_date/cost_price/fees/quantity/note, all optional). Response: the updated `Holding`.

- [ ] **Step 1: Write failing tests**

Append to `python/tests/api/test_portfolio_routes.py`:

```python
# --- Lot CRUD ---


def test_update_lot_success(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid)
    # get the lot_id
    p = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    lot_id = p["holdings"][0]["lots"][0]["lot_id"]
    resp = app_client.put(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/{lot_id}",
        json={"cost_price": "1700.00", "fees": "12.50"},
    )
    assert resp.status_code == 200
    h = resp.json()["data"]["holdings"][0] if "holdings" in resp.json()["data"] else None
    # API returns updated Portfolio; find the holding
    updated_p = resp.json()["data"]
    updated_h = next(x for x in updated_p["holdings"] if x["ticker"] == "600519")
    lot = next(x for x in updated_h["lots"] if x["lot_id"] == lot_id)
    assert lot["cost_price"] == "1700.00"
    assert lot["fees"] == "12.50"
    assert lot["quantity"] == 100  # unchanged


def test_update_lot_quantity_to_zero_removes(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid, qty=100)
    p = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    lot_id = p["holdings"][0]["lots"][0]["lot_id"]
    resp = app_client.put(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/{lot_id}",
        json={"quantity": 0},
    )
    assert resp.status_code == 200
    # holding should be deleted (no sell_lots)
    assert len(resp.json()["data"]["holdings"]) == 0


def test_update_lot_not_found_404(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid)
    resp = app_client.put(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/lot_missing",
        json={"quantity": 50},
    )
    assert resp.status_code == 404


def test_update_lot_holding_not_found_404(app_client):
    pid = _seed(app_client)
    resp = app_client.put(
        f"/api/v1/portfolios/{pid}/holdings/000001/lots/lot_x",
        json={"quantity": 50},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/api/test_portfolio_routes.py::test_update_lot_success -v`
Expected: FAIL with 404 (route not registered)

- [ ] **Step 3: Implement PUT /lots/{lot_id} endpoint**

Edit `python/valor/server/routes/portfolio.py`. After the `add_sell` route (from Task 7), add:

```python
class LotPatch(BaseModel):
    open_date: date | None = None
    quantity: int | None = None
    cost_price: Decimal | None = None
    fees: Decimal | None = None
    note: str | None = None


@router.put("/{pid}/holdings/{ticker}/lots/{lot_id}")
async def update_lot(pid: str, ticker: str, lot_id: str, body: LotPatch):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        updated = storage.update_lot(pid, ticker, lot_id, patch)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    except storage.HoldingNotFound:
        raise HTTPException(status_code=404, detail="holding not found")
    except storage.LotNotFound:
        raise HTTPException(status_code=404, detail="lot not found")
    return ok(updated.model_dump(mode="json"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/api/test_portfolio_routes.py -v -k "lot"`
Expected: PASS (all 4 lot update tests + any existing lot tests)

- [ ] **Step 5: Lint and commit**

```bash
cd python && uv run ruff check valor/server/routes/portfolio.py tests/api/test_portfolio_routes.py
git add python/valor/server/routes/portfolio.py python/tests/api/test_portfolio_routes.py
git commit -m "feat(portfolio): PUT /holdings/{ticker}/lots/{lot_id} endpoint"
```

---

## Task 9: Backend routes - DELETE /lots/{lot_id}

**Files:**
- Modify: `python/valor/server/routes/portfolio.py` (add route after `update_lot` from Task 8)
- Test: `python/tests/api/test_portfolio_routes.py` (extend)

**Interfaces:**
- Consumes: `storage.remove_lot`, `LotNotFound`
- Produces: `DELETE /api/v1/portfolios/{pid}/holdings/{ticker}/lots/{lot_id}` endpoint. Response: `{"deleted": lot_id}`.

- [ ] **Step 1: Write failing tests**

Append to `python/tests/api/test_portfolio_routes.py`:

```python
def test_delete_lot_success(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid, qty=100)
    p = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    lot_id = p["holdings"][0]["lots"][0]["lot_id"]
    resp = app_client.delete(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/{lot_id}",
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == lot_id
    # holding auto-deleted (no sell_lots)
    p2 = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    assert len(p2["holdings"]) == 0


def test_delete_lot_keeps_holding_when_has_sell_lots(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid, qty=100)
    # 先卖 50
    app_client.post(
        f"/api/v1/portfolios/{pid}/holdings/600519/sells",
        json={"sell_date": "2026-07-19", "quantity": 50, "sell_price": "1820.00", "fees": "5.00"},
    )
    # 此时 lot.quantity=50
    p = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    lot_id = p["holdings"][0]["lots"][0]["lot_id"]
    resp = app_client.delete(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/{lot_id}",
    )
    assert resp.status_code == 200
    # holding 保留（有 sell_lots）
    p2 = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    assert len(p2["holdings"]) == 1
    assert len(p2["holdings"][0]["sell_lots"]) == 1
    assert len(p2["holdings"][0]["lots"]) == 0


def test_delete_lot_not_found_404(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid)
    resp = app_client.delete(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/lot_missing",
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/api/test_portfolio_routes.py::test_delete_lot_success -v`
Expected: FAIL with 404 (route not registered)

- [ ] **Step 3: Implement DELETE /lots/{lot_id} endpoint**

Edit `python/valor/server/routes/portfolio.py`. After `update_lot` (from Task 8), add:

```python
@router.delete("/{pid}/holdings/{ticker}/lots/{lot_id}")
async def delete_lot(pid: str, ticker: str, lot_id: str):
    try:
        storage.remove_lot(pid, ticker, lot_id)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    except storage.HoldingNotFound:
        raise HTTPException(status_code=404, detail="holding not found")
    except storage.LotNotFound:
        raise HTTPException(status_code=404, detail="lot not found")
    return ok({"deleted": lot_id})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/api/test_portfolio_routes.py -v`
Expected: PASS (all existing + 11 new tests across Tasks 7-9)

- [ ] **Step 5: Lint and commit**

```bash
cd python && uv run ruff check valor/server/routes/portfolio.py tests/api/test_portfolio_routes.py
git add python/valor/server/routes/portfolio.py python/tests/api/test_portfolio_routes.py
git commit -m "feat(portfolio): DELETE /holdings/{ticker}/lots/{lot_id} endpoint"
```

---

## Task 10: Frontend types + API client

**Files:**
- Modify: `frontend/src/app/portfolio/types.ts`
- Modify: `frontend/src/api/portfolio.ts`

**Interfaces:**
- Consumes: existing types
- Produces: `SellLot` interface; `Holding.sell_lots?: SellLot[]`; `PositionMetric.realized_pnl: string`; `portfolioApi.addSell` / `updateLot` / `deleteLot` methods.

- [ ] **Step 1: Add SellLot type and extend Holding/PositionMetric**

Edit `frontend/src/app/portfolio/types.ts`. After the `Lot` interface (line 8), add:

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
```

Modify `Holding` (lines 10-15) to add `sell_lots`:

```typescript
export interface Holding {
  ticker: string;
  name?: string | null;
  lots: Lot[];
  sell_lots?: SellLot[];
  side: "long" | "short";
}
```

Modify `PositionMetric` (lines 49-62) to add `realized_pnl`:

```typescript
export interface PositionMetric {
  ticker: string;
  name?: string | null;
  quantity: number;
  cost_price: string;
  current_price: string;
  market_value: string;
  cost_value: string;
  unrealized_pnl: string;
  unrealized_pnl_pct: number;
  weight: number;
  sector?: string | null;
  beta?: number | null;
  realized_pnl?: string;
}
```

- [ ] **Step 2: Add 3 new API methods**

Edit `frontend/src/api/portfolio.ts`. Update import (line 1-10) to include `SellLot`:

```typescript
import type {
  Holding,
  ImportResult,
  Lot,
  Portfolio,
  PortfolioAnalytics,
  PortfolioSummary,
  RebalancePlan,
  SellLot,
  Strategy,
} from "@/app/portfolio/types";
import { apiClient } from "@/lib/api-client";
```

After `addLot` (line 59), add:

```typescript
  addSell: (
    pid: string,
    ticker: string,
    sell: Omit<SellLot, "sell_id" | "realized_pnl" | "avg_cost_at_sell">,
  ) => apiClient.post<SellLot>(`${BASE}/${pid}/holdings/${ticker}/sells`, sell),
  updateLot: (
    pid: string,
    ticker: string,
    lotId: string,
    patch: Partial<Omit<Lot, "lot_id">>,
  ) =>
    apiClient.put<Portfolio>(
      `${BASE}/${pid}/holdings/${ticker}/lots/${lotId}`,
      patch,
    ),
  deleteLot: (pid: string, ticker: string, lotId: string) =>
    apiClient.delete<{ deleted: string }>(
      `${BASE}/${pid}/holdings/${ticker}/lots/${lotId}`,
    ),
```

- [ ] **Step 3: Type check**

Run: `cd frontend && bun run build 2>&1 | head -20` (or `bunx tsc --noEmit`)
Expected: no type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/portfolio/types.ts frontend/src/api/portfolio.ts
git commit -m "feat(portfolio-fe): add SellLot type + addSell/updateLot/deleteLot API methods"
```

---

## Task 11: Frontend store - analytics

**Files:**
- Modify: `frontend/src/app/portfolio/store.ts`

**Interfaces:**
- Consumes: `portfolioApi.analytics`, `PortfolioAnalytics` type
- Produces: `analytics: PortfolioAnalytics | null`, `analyticsLoading: boolean`, `fetchAnalytics(pid)`. `fetchDetail` now also fetches analytics in parallel.

- [ ] **Step 1: Extend PortfolioState**

Edit `frontend/src/app/portfolio/store.ts`. Update imports (line 2-3):

```typescript
import { create } from "zustand";
import { type CreatePortfolioInput, portfolioApi } from "@/api/portfolio";
import type { Portfolio, PortfolioAnalytics, PortfolioSummary } from "./types";
```

Update `PortfolioState` interface (lines 5-15):

```typescript
interface PortfolioState {
  list: PortfolioSummary[];
  current: Portfolio | null;
  analytics: PortfolioAnalytics | null;
  analyticsLoading: boolean;
  loading: boolean;
  error: string | null;
  fetchList: () => Promise<void>;
  fetchDetail: (id: string) => Promise<void>;
  fetchAnalytics: (id: string) => Promise<void>;
  create: (input: CreatePortfolioInput) => Promise<string>;
  remove: (id: string) => Promise<void>;
  clearError: () => void;
}
```

Update the store creation (lines 17-61):

```typescript
export const usePortfolioStore = create<PortfolioState>((set) => ({
  list: [],
  current: null,
  analytics: null,
  analyticsLoading: false,
  loading: false,
  error: null,
  fetchList: async () => {
    set({ loading: true, error: null });
    try {
      const data = await portfolioApi.list();
      set({ list: data, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  fetchDetail: async (id) => {
    set({ loading: true, error: null });
    try {
      const [p, a] = await Promise.all([
        portfolioApi.get(id),
        portfolioApi.analytics(id).catch(() => null),
      ]);
      set({ current: p, analytics: a, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  fetchAnalytics: async (id) => {
    set({ analyticsLoading: true });
    try {
      const a = await portfolioApi.analytics(id);
      set({ analytics: a, analyticsLoading: false });
    } catch (e) {
      set({ analyticsLoading: false, error: (e as Error).message });
    }
  },
  create: async (input) => {
    const p = await portfolioApi.create(input);
    set((s) => ({
      list: [
        ...s.list,
        {
          portfolio_id: p.portfolio_id,
          name: p.name,
          benchmark: p.benchmark,
          cash: p.cash,
          updated_at: p.updated_at,
        },
      ],
    }));
    return p.portfolio_id;
  },
  remove: async (id) => {
    await portfolioApi.delete(id);
    set((s) => ({ list: s.list.filter((p) => p.portfolio_id !== id) }));
  },
  clearError: () => set({ error: null }),
}));
```

- [ ] **Step 2: Type check**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: no type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/portfolio/store.ts
git commit -m "feat(portfolio-fe): store fetches analytics in parallel with detail"
```

---

## Task 12: Frontend format helpers

**Files:**
- Create: `frontend/src/lib/format.ts`

**Interfaces:**
- Consumes: nothing
- Produces: `formatMoney(value: string | number, opts?) -> string`; `formatPnlClass(value: string | number) -> string` (returns `"text-red-500"` for gain, `"text-green-500"` for loss, `""` for zero); `formatPercent(value: number, digits?) -> string`

- [ ] **Step 1: Create format.ts**

Create `frontend/src/lib/format.ts`:

```typescript
export function formatMoney(
  value: string | number,
  opts: { digits?: number; currency?: string } = {},
): string {
  const { digits = 2, currency = "¥" } = opts;
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return "-";
  return `${currency}${n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function formatPnlClass(value: string | number): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n) || n === 0) return "";
  return n > 0 ? "text-red-500" : "text-green-500";
}

export function formatPercent(value: number, digits = 2): string {
  if (Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}
```

- [ ] **Step 2: Type check**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: no type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/format.ts
git commit -m "feat(portfolio-fe): add format helpers for money/pnl/percent"
```

---

## Task 13: Frontend HoldingsTable - 9 columns + Lot/SellLot expand

**Files:**
- Modify: `frontend/src/app/portfolio/components/HoldingsTable.tsx`

**Interfaces:**
- Consumes: `usePortfolioStore` (analytics), `formatMoney`/`formatPnlClass`/`formatPercent`, `Holding`/`Lot`/`SellLot` types, `portfolioApi.deleteLot`
- Produces: 9-column table: 展开/代码/名称/持仓量/买入均价/现价/浮动盈亏/个股仓位/操作. Expandable row shows Lot table (with edit/delete buttons) and SellLot table (if any). Action buttons: 诊断/增持/减仓/删除.

- [ ] **Step 1: Rewrite HoldingsTable.tsx**

Replace entire contents of `frontend/src/app/portfolio/components/HoldingsTable.tsx`:

```typescript
import {
  ChevronDown,
  ChevronRight,
  Pencil,
  Plus,
  Stethoscope,
  Trash2,
  Minus,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { portfolioApi } from "@/api/portfolio";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatMoney, formatPnlClass, formatPercent } from "@/lib/format";
import { usePortfolioStore } from "../store";
import type { Holding, Lot, SellLot } from "../types";

interface Props {
  pid: string;
  holdings: Holding[];
  onAppend: (ticker: string, name: string | null) => void;
  onReduce: (ticker: string, name: string | null) => void;
  onEditLot: (ticker: string, lot: Lot) => void;
}

export default function HoldingsTable({
  pid,
  holdings,
  onAppend,
  onReduce,
  onEditLot,
}: Props) {
  const { analytics, fetchDetail, fetchAnalytics } = usePortfolioStore();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(ticker: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  function metricFor(ticker: string) {
    return analytics?.positions.find((p) => p.ticker === ticker);
  }

  async function removeHolding(ticker: string) {
    if (!confirm(`删除持仓 ${ticker}？此操作会移除所有 Lot 与 SellLot 记录。`)) return;
    await portfolioApi.deleteHolding(pid, ticker);
    await fetchDetail(pid);
  }

  async function removeLot(ticker: string, lotId: string) {
    if (!confirm(`删除 Lot ${lotId.slice(0, 8)}？`)) return;
    await portfolioApi.deleteLot(pid, ticker, lotId);
    await fetchDetail(pid);
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8"></TableHead>
          <TableHead>代码</TableHead>
          <TableHead>名称</TableHead>
          <TableHead className="text-right">持仓量</TableHead>
          <TableHead className="text-right">买入均价</TableHead>
          <TableHead className="text-right">现价</TableHead>
          <TableHead className="text-right">浮动盈亏</TableHead>
          <TableHead className="text-right">个股仓位</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {holdings.map((h) => {
          const m = metricFor(h.ticker);
          const qty = h.lots.reduce((s, l) => s + l.quantity, 0);
          const expandedRow = expanded.has(h.ticker);
          return (
            <>
              <TableRow key={h.ticker}>
                <TableCell
                  onClick={() => toggle(h.ticker)}
                  className="cursor-pointer"
                >
                  {expandedRow ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </TableCell>
                <TableCell className="font-mono">{h.ticker}</TableCell>
                <TableCell>{h.name || "-"}</TableCell>
                <TableCell className="text-right">{qty}</TableCell>
                <TableCell className="text-right">
                  {m ? formatMoney(m.cost_price) : "-"}
                </TableCell>
                <TableCell className="text-right">
                  {m ? formatMoney(m.current_price) : "-"}
                </TableCell>
                <TableCell
                  className={`text-right ${m ? formatPnlClass(m.unrealized_pnl) : ""}`}
                >
                  {m ? `${formatMoney(m.unrealized_pnl)} (${formatPercent(m.unrealized_pnl_pct)})` : "-"}
                </TableCell>
                <TableCell className="text-right">
                  {m ? formatPercent(m.weight) : "-"}
                </TableCell>
                <TableCell className="space-x-1 text-right">
                  <Button variant="ghost" size="icon" asChild title="诊断">
                    <Link to={`/analysis?ticker=${h.ticker}`}>
                      <Stethoscope className="h-4 w-4" />
                    </Link>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="增持"
                    onClick={() => onAppend(h.ticker, h.name ?? null)}
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="减仓"
                    onClick={() => onReduce(h.ticker, h.name ?? null)}
                    disabled={qty === 0}
                  >
                    <Minus className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="删除持仓"
                    onClick={() => removeHolding(h.ticker)}
                  >
                    <Trash2 className="h-4 w-4 text-red-500" />
                  </Button>
                </TableCell>
              </TableRow>
              {expandedRow && (
                <>
                  {h.lots.map((lot) => (
                    <TableRow key={lot.lot_id} className="bg-gray-50">
                      <TableCell></TableCell>
                      <TableCell colSpan={8} className="text-gray-700 text-sm">
                        <div className="flex items-center justify-between">
                          <span>
                            Lot {lot.lot_id.slice(0, 8)}：{lot.open_date} ·{" "}
                            {lot.quantity} 股 @ ¥{lot.cost_price}
                            {Number(lot.fees) > 0 && ` · 手续费 ¥${lot.fees}`}
                            {lot.note && ` · ${lot.note}`}
                          </span>
                          <span className="space-x-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              title="编辑 Lot"
                              onClick={() => onEditLot(h.ticker, lot)}
                            >
                              <Pencil className="h-3 w-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              title="删除 Lot"
                              onClick={() => removeLot(h.ticker, lot.lot_id)}
                            >
                              <Trash2 className="h-3 w-3 text-red-500" />
                            </Button>
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {(h.sell_lots ?? []).map((s: SellLot) => (
                    <TableRow key={s.sell_id} className="bg-amber-50">
                      <TableCell></TableCell>
                      <TableCell colSpan={8} className="text-gray-700 text-sm">
                        卖出 {s.sell_id.slice(0, 8)}：{s.sell_date} ·{" "}
                        {s.quantity} 股 @ ¥{s.sell_price}
                        {Number(s.fees) > 0 && ` · 手续费 ¥${s.fees}`} ·
                        已实现盈亏{" "}
                        <span className={formatPnlClass(s.realized_pnl)}>
                          ¥{s.realized_pnl}
                        </span>
                        {s.note && ` · ${s.note}`}
                      </TableCell>
                    </TableRow>
                  ))}
                  {h.lots.length === 0 && (h.sell_lots ?? []).length === 0 && (
                    <TableRow className="bg-gray-50">
                      <TableCell></TableCell>
                      <TableCell colSpan={8} className="text-gray-400 text-sm">
                        已清仓（无 Lot 与 SellLot 记录）
                      </TableCell>
                    </TableRow>
                  )}
                </>
              )}
            </>
          );
        })}
        {holdings.length === 0 && (
          <TableRow>
            <TableCell colSpan={9} className="py-8 text-center text-gray-500">
              暂无持仓，点击「导入 CSV」或「新增持仓」
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 2: Type check**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: type errors referencing missing `ReduceForm` / `EditLotForm` (created in Tasks 15-16) or unused imports. Address only the unused imports; the form wiring will be added in Task 17.

If errors are only about missing onAppend/onReduce/onEditLot handlers, leave for Task 17 to wire.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/portfolio/components/HoldingsTable.tsx
git commit -m "feat(portfolio-fe): HoldingsTable 9 columns + Lot/SellLot expand + actions"
```

---

## Task 14: Frontend HoldingForm - mode prop

**Files:**
- Modify: `frontend/src/app/portfolio/components/HoldingForm.tsx`

**Interfaces:**
- Consumes: `portfolioApi.addHolding`, `portfolioApi.addLot`, `usePortfolioStore.fetchDetail`
- Produces: `HoldingForm` with new props: `mode: "create" | "append"`, `ticker?: string`, `name?: string | null`. When `mode="append"`, hides ticker/name inputs and calls `addLot` instead of `addHolding`.

- [ ] **Step 1: Rewrite HoldingForm.tsx**

Replace entire contents of `frontend/src/app/portfolio/components/HoldingForm.tsx`:

```typescript
import { useEffect, useState } from "react";
import { portfolioApi } from "@/api/portfolio";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePortfolioStore } from "../store";

interface Props {
  pid: string;
  open: boolean;
  onClose: () => void;
  mode: "create" | "append";
  ticker?: string;
  name?: string | null;
}

export default function HoldingForm({
  pid,
  open,
  onClose,
  mode,
  ticker,
  name,
}: Props) {
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [tickerInput, setTickerInput] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [quantity, setQuantity] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [openDate, setOpenDate] = useState("");
  const [fees, setFees] = useState("0");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (open) {
      setTickerInput(mode === "append" ? ticker ?? "" : "");
      setNameInput(mode === "append" ? name ?? "" : "");
      setQuantity("");
      setCostPrice("");
      setOpenDate(new Date().toISOString().slice(0, 10));
      setFees("0");
      setNote("");
    }
  }, [open, mode, ticker, name]);

  const isCreate = mode === "create";

  async function submit() {
    const t = (isCreate ? tickerInput.trim().padStart(6, "0") : ticker ?? "").trim();
    if (!t || !quantity || !costPrice) return;
    const lotPayload = {
      lot_id: "",
      open_date: openDate || new Date().toISOString().slice(0, 10),
      quantity: Number(quantity),
      cost_price: costPrice,
      fees: fees || "0",
      note: note.trim() || null,
    };
    if (isCreate) {
      await portfolioApi.addHolding(pid, {
        ticker: t,
        name: nameInput.trim() || undefined,
        side: "long",
        lots: [lotPayload],
      });
    } else {
      await portfolioApi.addLot(pid, t, lotPayload);
    }
    await fetchDetail(pid);
    onClose();
  }

  const valid = (isCreate ? !!tickerInput.trim() : !!ticker) && !!quantity && !!costPrice;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isCreate ? "新增持仓" : `增持 ${ticker}`}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {isCreate && (
            <>
              <div>
                <Label>股票代码</Label>
                <Input
                  value={tickerInput}
                  onChange={(e) => setTickerInput(e.target.value)}
                  placeholder="600519"
                />
              </div>
              <div>
                <Label>名称（可选）</Label>
                <Input
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                />
              </div>
            </>
          )}
          <div>
            <Label>买入日期</Label>
            <Input
              value={openDate}
              onChange={(e) => setOpenDate(e.target.value)}
              type="date"
            />
          </div>
          <div>
            <Label>数量</Label>
            <Input
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>成本价</Label>
            <Input
              value={costPrice}
              onChange={(e) => setCostPrice(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>手续费（默认 0）</Label>
            <Input
              value={fees}
              onChange={(e) => setFees(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>备注（可选）</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={!valid}>
            {isCreate ? "添加" : "增持"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Type check**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: type errors only in `detail.tsx` (which still passes old props). Will be fixed in Task 17.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/portfolio/components/HoldingForm.tsx
git commit -m "feat(portfolio-fe): HoldingForm supports create/append modes"
```

---

## Task 15: Frontend ReduceForm

**Files:**
- Create: `frontend/src/app/portfolio/components/ReduceForm.tsx`

**Interfaces:**
- Consumes: `portfolioApi.addSell`, `usePortfolioStore.fetchDetail`, `Holding`
- Produces: `ReduceForm` component with props `{ pid, open, onClose, ticker, name?, maxQuantity }`. Fields: 卖出日期/数量/卖出价/手续费/备注. Submits via `addSell`.

- [ ] **Step 1: Create ReduceForm.tsx**

Create `frontend/src/app/portfolio/components/ReduceForm.tsx`:

```typescript
import { useEffect, useState } from "react";
import { portfolioApi } from "@/api/portfolio";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePortfolioStore } from "../store";

interface Props {
  pid: string;
  open: boolean;
  onClose: () => void;
  ticker: string;
  name?: string | null;
  maxQuantity: number;
}

export default function ReduceForm({
  pid,
  open,
  onClose,
  ticker,
  name,
  maxQuantity,
}: Props) {
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [sellDate, setSellDate] = useState("");
  const [quantity, setQuantity] = useState("");
  const [sellPrice, setSellPrice] = useState("");
  const [fees, setFees] = useState("0");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setSellDate(new Date().toISOString().slice(0, 10));
      setQuantity("");
      setSellPrice("");
      setFees("0");
      setNote("");
      setError(null);
    }
  }, [open]);

  async function submit() {
    const qty = Number(quantity);
    if (!qty || qty <= 0) {
      setError("数量必须为正数");
      return;
    }
    if (qty > maxQuantity) {
      setError(`数量超过持仓量 ${maxQuantity}`);
      return;
    }
    if (!sellPrice) {
      setError("请填写卖出价");
      return;
    }
    try {
      await portfolioApi.addSell(pid, ticker, {
        sell_date: sellDate,
        quantity: qty,
        sell_price: sellPrice,
        fees: fees || "0",
        note: note.trim() || null,
      });
      await fetchDetail(pid);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>减仓 {ticker}{name ? ` · ${name}` : ""}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="text-gray-500 text-sm">
            当前持仓 {maxQuantity} 股
          </div>
          <div>
            <Label>卖出日期</Label>
            <Input
              value={sellDate}
              onChange={(e) => setSellDate(e.target.value)}
              type="date"
            />
          </div>
          <div>
            <Label>卖出数量</Label>
            <Input
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>卖出价</Label>
            <Input
              value={sellPrice}
              onChange={(e) => setSellPrice(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>手续费（默认 0）</Label>
            <Input
              value={fees}
              onChange={(e) => setFees(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>备注（可选）</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <div className="text-red-500 text-sm">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit}>确认减仓</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Type check**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: no new type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/portfolio/components/ReduceForm.tsx
git commit -m "feat(portfolio-fe): ReduceForm for selling positions"
```

---

## Task 16: Frontend EditLotForm

**Files:**
- Create: `frontend/src/app/portfolio/components/EditLotForm.tsx`

**Interfaces:**
- Consumes: `portfolioApi.updateLot`, `usePortfolioStore.fetchDetail`, `Lot`
- Produces: `EditLotForm` with props `{ pid, open, onClose, ticker, lot }`. Fields: 开仓日/数量/成本价/手续费/备注. Submits via `updateLot`.

- [ ] **Step 1: Create EditLotForm.tsx**

Create `frontend/src/app/portfolio/components/EditLotForm.tsx`:

```typescript
import { useEffect, useState } from "react";
import { portfolioApi } from "@/api/portfolio";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePortfolioStore } from "../store";
import type { Lot } from "../types";

interface Props {
  pid: string;
  open: boolean;
  onClose: () => void;
  ticker: string;
  lot: Lot | null;
}

export default function EditLotForm({
  pid,
  open,
  onClose,
  ticker,
  lot,
}: Props) {
  const fetchDetail = usePortfolioStore((s) => s.fetchDetail);
  const [openDate, setOpenDate] = useState("");
  const [quantity, setQuantity] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [fees, setFees] = useState("0");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && lot) {
      setOpenDate(lot.open_date);
      setQuantity(String(lot.quantity));
      setCostPrice(lot.cost_price);
      setFees(lot.fees);
      setNote(lot.note ?? "");
      setError(null);
    }
  }, [open, lot]);

  if (!lot) return null;

  async function submit() {
    if (!lot) return;
    const qty = Number(quantity);
    if (Number.isNaN(qty) || qty < 0) {
      setError("数量必须 >= 0");
      return;
    }
    try {
      await portfolioApi.updateLot(pid, ticker, lot.lot_id, {
        open_date: openDate,
        quantity: qty,
        cost_price: costPrice,
        fees: fees || "0",
        note: note.trim() || null,
      });
      await fetchDetail(pid);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑 Lot {lot.lot_id.slice(0, 8)}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>开仓日</Label>
            <Input
              value={openDate}
              onChange={(e) => setOpenDate(e.target.value)}
              type="date"
            />
          </div>
          <div>
            <Label>数量</Label>
            <Input
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>成本价</Label>
            <Input
              value={costPrice}
              onChange={(e) => setCostPrice(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>手续费</Label>
            <Input
              value={fees}
              onChange={(e) => setFees(e.target.value)}
              type="number"
            />
          </div>
          <div>
            <Label>备注</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <div className="text-red-500 text-sm">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Type check**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: no new type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/portfolio/components/EditLotForm.tsx
git commit -m "feat(portfolio-fe): EditLotForm for editing single Lot"
```

---

## Task 17: Frontend detail.tsx - wire forms + refresh button

**Files:**
- Modify: `frontend/src/app/portfolio/detail.tsx`

**Interfaces:**
- Consumes: `HoldingForm` (with mode), `ReduceForm`, `EditLotForm`, `HoldingsTable` (new props), `usePortfolioStore.fetchAnalytics`
- Produces: Detail page with refresh button; wires append/reduce/edit-lot flows; passes analytics to HoldingsTable via store.

- [ ] **Step 1: Rewrite detail.tsx**

Replace entire contents of `frontend/src/app/portfolio/detail.tsx`:

```typescript
import { Plus, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import AnalyticsPanel from "./components/AnalyticsPanel";
import CSVImport from "./components/CSVImport";
import EditLotForm from "./components/EditLotForm";
import HoldingForm from "./components/HoldingForm";
import HoldingsTable from "./components/HoldingsTable";
import ReduceForm from "./components/ReduceForm";
import RebalancePanel from "./components/RebalancePanel";
import StrategyList from "./components/StrategyList";
import { usePortfolioStore } from "./store";
import type { Lot } from "./types";

export default function PortfolioDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { current, fetchDetail, fetchAnalytics, analyticsLoading } =
    usePortfolioStore();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [appendTarget, setAppendTarget] = useState<{
    ticker: string;
    name: string | null;
  } | null>(null);
  const [reduceTarget, setReduceTarget] = useState<{
    ticker: string;
    name: string | null;
    maxQty: number;
  } | null>(null);
  const [editLotTarget, setEditLotTarget] = useState<{
    ticker: string;
    lot: Lot;
  } | null>(null);

  useEffect(() => {
    if (id) fetchDetail(id);
  }, [id, fetchDetail]);

  if (!current || !id) return <div className="p-6">加载中...</div>;

  function qtyOf(ticker: string): number {
    const h = current?.holdings.find((x) => x.ticker === ticker);
    if (!h) return 0;
    return h.lots.reduce((s, l) => s + l.quantity, 0);
  }

  return (
    <div className={cn("mx-auto max-w-6xl p-6")}>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-bold text-2xl">{current.name}</h1>
          <div className="text-gray-500 text-sm">
            基准 {current.benchmark} · 现金 ¥
            {Number(current.cash).toLocaleString()} · 持仓{" "}
            {current.holdings.length} 只
          </div>
        </div>
      </div>
      <Tabs defaultValue="holdings">
        <TabsList>
          <TabsTrigger value="holdings">持仓</TabsTrigger>
          <TabsTrigger value="analytics">分析</TabsTrigger>
          <TabsTrigger value="strategies">策略</TabsTrigger>
          <TabsTrigger value="rebalance">调仓</TabsTrigger>
        </TabsList>
        <TabsContent value="holdings" className="space-y-4">
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => id && fetchAnalytics(id)}
              disabled={analyticsLoading}
            >
              <RefreshCw
                className={cn("mr-1 h-4 w-4", analyticsLoading && "animate-spin")}
              />
              {analyticsLoading ? "刷新中..." : "刷新行情"}
            </Button>
            <CSVImport pid={id} />
            <Button size="sm" onClick={() => setShowCreateForm(true)}>
              <Plus className={cn("mr-1 h-4 w-4")} /> 新增持仓
            </Button>
          </div>
          <HoldingsTable
            pid={id}
            holdings={current.holdings}
            onAppend={(ticker, name) => setAppendTarget({ ticker, name })}
            onReduce={(ticker, name) =>
              setReduceTarget({ ticker, name, maxQty: qtyOf(ticker) })
            }
            onEditLot={(ticker, lot) => setEditLotTarget({ ticker, lot })}
          />
          <HoldingForm
            pid={id}
            open={showCreateForm}
            onClose={() => setShowCreateForm(false)}
            mode="create"
          />
          <HoldingForm
            pid={id}
            open={appendTarget !== null}
            onClose={() => setAppendTarget(null)}
            mode="append"
            ticker={appendTarget?.ticker}
            name={appendTarget?.name}
          />
          <ReduceForm
            pid={id}
            open={reduceTarget !== null}
            onClose={() => setReduceTarget(null)}
            ticker={reduceTarget?.ticker ?? ""}
            name={reduceTarget?.name}
            maxQuantity={reduceTarget?.maxQty ?? 0}
          />
          <EditLotForm
            pid={id}
            open={editLotTarget !== null}
            onClose={() => setEditLotTarget(null)}
            ticker={editLotTarget?.ticker ?? ""}
            lot={editLotTarget?.lot ?? null}
          />
        </TabsContent>
        <TabsContent value="analytics">
          <AnalyticsPanel pid={id} />
        </TabsContent>
        <TabsContent value="strategies">
          <StrategyList pid={id} />
        </TabsContent>
        <TabsContent value="rebalance">
          <RebalancePanel pid={id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

- [ ] **Step 2: Type check**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: no type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/portfolio/detail.tsx
git commit -m "feat(portfolio-fe): wire HoldingForm/ReduceForm/EditLotForm + refresh button"
```

---

## Task 18: Manual verification

**Files:** none

- [ ] **Step 1: Start dev servers**

```bash
./start.sh
```
Wait for backend (port 8000) and frontend (port 1420) to be ready.

- [ ] **Step 2: Open browser to http://localhost:1420/portfolio**

- [ ] **Step 3: Create a portfolio**

Click "新建" -> name: "测试组合" -> submit. Click into the new portfolio.

- [ ] **Step 4: Verify acceptance criterion 2 - Manual add**

Click "新增持仓" -> fill ticker=600519, name=贵州茅台, 数量=100, 成本价=1689.50, 开仓日=2024-03-15. Submit. Verify table shows new row with: 代码 600519, 名称 贵州茅台, 持仓量 100, 买入均价 ¥1,689.50, 现价 (fetched), 浮动盈亏 (with red/green color), 个股仓位 100%.

- [ ] **Step 5: Verify acceptance criterion 3 - Append (增持)**

Click row's "+" (增持) button. Verify form title "增持 600519", no ticker/name inputs visible. Fill 数量=50, 成本价=1750.00, 开仓日=2024-04-20. Submit. Verify:
- 持仓量 = 150
- 买入均价 = (100*1689.50 + 50*1750) / 150 = (168950 + 87500) / 150 = 1709.67

- [ ] **Step 6: Verify acceptance criterion 4 - Reduce (减仓)**

Click row's "-" (减仓) button. Verify form title "减仓 600519 · 贵州茅台", shows "当前持仓 150 股". Fill 卖出数量=50, 卖出价=1820.00, 卖出日期=2026-07-19, 手续费=15.00. Submit. Verify:
- 持仓量 = 100
- 买入均价 unchanged (1709.67 - cost_price per lot not modified)
- Expand row: shows SellLot entry with realized_pnl (red color)

- [ ] **Step 7: Verify acceptance criterion 5 - Edit Lot**

Expand the row. Click pencil icon next to a Lot. Change 成本价 to 1800.00. Submit. Verify:
- 买入均价 updates to (100*1800 + 50*1750) / 150 = (180000 + 87500) / 150 = 1783.33
- SellLot.realized_pnl unchanged (locked at sell time)

- [ ] **Step 8: Verify acceptance criterion 6 - Delete Lot**

Expand row. Click trash icon next to a Lot. Confirm. Verify:
- 持仓量 decreases by that lot's quantity
- If last lot and no sell_lots -> row disappears
- If has sell_lots -> row stays (already-清仓 state)

- [ ] **Step 9: Verify acceptance criterion 7 - Delete Holding**

Click row's trash icon. Confirm. Verify row disappears.

- [ ] **Step 10: Verify acceptance criterion 8 - CSV import**

Click "导入 CSV", select a CSV file with format `ticker,name,quantity,cost_price,open_date`. Verify import succeeds and table refreshes.

- [ ] **Step 11: Verify acceptance criterion 9 - Refresh button**

Click "刷新行情". Verify spinner spins briefly, then 现价/浮动盈亏/个股仓位 update with latest values.

- [ ] **Step 12: Verify acceptance criterion 1 - Auto-load**

Navigate away from portfolio detail, then back. Verify the 持仓 Tab auto-loads with all 9 columns populated within 3 seconds (assuming行情 API works).

- [ ] **Step 13: Final lint and test run**

```bash
cd python && uv run pytest tests/unit/test_portfolio_storage_sells.py tests/api/test_portfolio_routes.py tests/unit/test_portfolio_analytics.py -v
cd python && uv run ruff check valor/portfolio/ valor/server/routes/portfolio.py
cd frontend && bunx tsc --noEmit
```
Expected: all tests pass, 0 lint errors.

- [ ] **Step 14: Final commit (if any fixups needed)**

```bash
git status
# If any uncommitted changes:
git add -A
git commit -m "chore: verification fixups"
```

---

## Self-Review

### Spec coverage

- §1 数据模型扩展 → Task 1 (SellLot, Holding.sell_lots, PositionMetric.realized_pnl)
- §2 后端 API 扩展 → Tasks 7/8/9 (3 new endpoints) + Tasks 2-5 (storage layer)
- §3 Storage 层扣减逻辑 → Tasks 2 (deduct_lots_weighted), 3 (add_sell), 4 (update_lot), 5 (remove_lot)
- §4 前端改造 → Tasks 10 (types+API), 11 (store), 12 (format), 13 (HoldingsTable), 14 (HoldingForm mode), 15 (ReduceForm), 16 (EditLotForm), 17 (detail.tsx)
- §5 错误处理与边界 → covered in storage tests (Task 3-5) and route tests (Tasks 7-9)
- §6 测试策略 → covered in Tasks 1-9 (unit + API tests)
- §7 验收标准 → Task 18 manual verification (9 criteria)
- §8 实现顺序 → Tasks 1-17 follow the spec's order (models → storage → analytics → routes → frontend types → store → format → table → forms → integration)
- §9 与 Phase 3 的衔接 → no action needed (compatibility preserved)
- §10 风险与缓解 → Hamilton allocation tested in Task 2, realized_pnl lock tested in Task 3/6, empty holding cleanup tested in Task 4/5

All spec sections covered. No gaps.

### Placeholder scan

No TBD/TODO/placeholders. All steps have concrete code or commands.

### Type consistency

- `SellLot` fields consistent across models.py (Task 1), test_portfolio_models.py (Task 1), test_portfolio_storage_sells.py (Task 2-5), routes/portfolio.py (Task 7), types.ts (Task 10), api/portfolio.ts (Task 10), ReduceForm.tsx (Task 15)
- `add_sell` signature: `(portfolio_id: str, ticker: str, sell_lot: SellLot) -> Portfolio` -- consistent across storage.py (Task 3) and routes/portfolio.py (Task 7)
- `update_lot` signature: `(portfolio_id, ticker, lot_id, patch: dict) -> Portfolio` -- consistent across storage.py (Task 4) and routes/portfolio.py (Task 8)
- `remove_lot` signature: `(portfolio_id, ticker, lot_id) -> Portfolio` -- consistent across storage.py (Task 5) and routes/portfolio.py (Task 9)
- Frontend `portfolioApi.addSell` / `updateLot` / `deleteLot` (Task 10) match backend endpoints (Tasks 7-9)
- `Holding.sell_lots?: SellLot[]` (Task 10) consistent with usage in HoldingsTable (Task 13)
- `PositionMetric.realized_pnl?: string` (Task 10) consistent with analytics.py (Task 6)

No type inconsistencies.
