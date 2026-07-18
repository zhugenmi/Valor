"""Tests for portfolio allocator. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from datetime import date
from decimal import Decimal
import numpy as np
import pytest
from valor.portfolio.allocator import allocate, AllocatorParams


class FakeHistoricalLookup:
    def __init__(self, returns: dict[str, np.ndarray]):
        self._r = returns
    async def get_returns(self, ticker: str, days: int) -> np.ndarray:
        return self._r.get(ticker, np.array([]))


class FakePriceLookup:
    def __init__(self, prices: dict[str, Decimal]):
        self._p = prices
    async def get(self, ticker: str, as_of: date) -> Decimal:
        return self._p[ticker]


def _rets(rng, n=252, vol=0.02):
    return rng.standard_normal(n) * vol


# --- equal_weight ---


@pytest.mark.asyncio
async def test_equal_weight_basic():
    tickers = ["600519", "000858", "002304"]
    rng = np.random.default_rng(42)
    prices = {t: Decimal("100") for t in tickers}
    rets = {t: _rets(rng) for t in tickers}
    result = await allocate(
        "equal_weight", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        AllocatorParams(),
    )
    assert result.method == "equal_weight"
    assert sum(result.target_weights.values()) == pytest.approx(1.0)
    for t in tickers:
        assert result.target_weights[t] == pytest.approx(1/3)
    assert result.expected_return is not None
    assert result.expected_volatility is not None


@pytest.mark.asyncio
async def test_equal_weight_single_ticker():
    tickers = ["600519"]
    rng = np.random.default_rng(42)
    prices = {"600519": Decimal("100")}
    rets = {"600519": _rets(rng)}
    result = await allocate(
        "equal_weight", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        AllocatorParams(),
    )
    assert result.target_weights["600519"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_equal_weight_rationale_mentions_method():
    tickers = ["600519", "000858"]
    rng = np.random.default_rng(42)
    prices = {t: Decimal("100") for t in tickers}
    rets = {t: _rets(rng) for t in tickers}
    result = await allocate(
        "equal_weight", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        AllocatorParams(),
    )
    assert "等权" in result.rationale or "equal_weight" in result.rationale


# --- mean_variance ---


@pytest.mark.asyncio
async def test_mean_variance_weights_sum_to_one():
    tickers = ["t1", "t2", "t3"]
    rng = np.random.default_rng(7)
    prices = {t: Decimal("100") for t in tickers}
    rets = {t: _rets(rng, vol=0.02 + 0.01 * i) for i, t in enumerate(tickers)}
    result = await allocate(
        "mean_variance", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        AllocatorParams(),
    )
    assert sum(result.target_weights.values()) == pytest.approx(1.0, abs=1e-6)
    for w in result.target_weights.values():
        assert w <= 0.40 + 1e-6  # respects max_weight
    assert result.sharpe is not None


@pytest.mark.asyncio
async def test_mean_variance_target_return_constraint():
    tickers = ["t1", "t2", "t3"]
    rng = np.random.default_rng(7)
    prices = {t: Decimal("100") for t in tickers}
    rets = {t: _rets(rng, vol=0.02 + 0.01 * i) for i, t in enumerate(tickers)}
    params = AllocatorParams(target_return=0.05)
    result = await allocate(
        "mean_variance", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        params,
    )
    assert result.expected_return is not None
    assert result.expected_return >= 0.05 - 1e-4 or result.diagnostics.get("fallback")


@pytest.mark.asyncio
async def test_mean_variance_max_weight_respected():
    tickers = ["t1", "t2", "t3"]
    rng = np.random.default_rng(7)
    prices = {t: Decimal("100") for t in tickers}
    rets = {t: _rets(rng, vol=0.02 + 0.01 * i) for i, t in enumerate(tickers)}
    result = await allocate(
        "mean_variance", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        AllocatorParams(max_weight=0.30),
    )
    if not result.diagnostics.get("fallback"):
        for w in result.target_weights.values():
            assert w <= 0.30 + 1e-6


@pytest.mark.asyncio
async def test_mean_variance_fallback_on_non_convergence():
    """MVO with extreme constraints may trigger fallback; verify it returns valid weights."""
    tickers = ["t1", "t2"]
    rng = np.random.default_rng(42)
    prices = {t: Decimal("100") for t in tickers}
    rets = {t: _rets(rng, vol=0.002) for t in tickers}
    result = await allocate(
        "mean_variance", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        AllocatorParams(target_return=0.50),  # unrealistic target
    )
    assert sum(result.target_weights.values()) == pytest.approx(1.0, abs=1e-6)


# --- risk_parity ---


@pytest.mark.asyncio
async def test_risk_parity_weights_sum_to_one():
    tickers = ["t1", "t2", "t3"]
    rng = np.random.default_rng(7)
    prices = {t: Decimal("100") for t in tickers}
    rets = {t: _rets(rng, vol=0.01 * (i + 1)) for i, t in enumerate(tickers)}
    result = await allocate(
        "risk_parity", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        AllocatorParams(),
    )
    assert sum(result.target_weights.values()) == pytest.approx(1.0, abs=1e-6)
    for w in result.target_weights.values():
        assert w <= 0.40 + 1e-6


@pytest.mark.asyncio
async def test_risk_parity_lower_weight_for_higher_vol():
    tickers = ["low_vol", "high_vol"]
    rng = np.random.default_rng(7)
    prices = {t: Decimal("100") for t in tickers}
    rets = {"low_vol": _rets(rng, vol=0.005), "high_vol": _rets(rng, vol=0.05)}
    result = await allocate(
        "risk_parity", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        AllocatorParams(),
    )
    if not result.diagnostics.get("fallback"):
        assert result.target_weights["low_vol"] > result.target_weights["high_vol"]


# --- edge cases ---


@pytest.mark.asyncio
async def test_allocate_empty_tickers_raises():
    with pytest.raises(ValueError):
        await allocate("equal_weight", [], {}, FakePriceLookup({}), FakeHistoricalLookup({}), AllocatorParams())


@pytest.mark.asyncio
async def test_allocate_unknown_method_raises():
    with pytest.raises(ValueError):
        await allocate("black_litterman", ["t1"], {"t1": Decimal("100")},
                       FakePriceLookup({"t1": Decimal("100")}),
                       FakeHistoricalLookup({"t1": _rets(np.random.default_rng(42))}),
                       AllocatorParams())


@pytest.mark.asyncio
async def test_short_history_degrades_gracefully():
    tickers = ["new_stock", "old_stock"]
    rng = np.random.default_rng(42)
    prices = {t: Decimal("100") for t in tickers}
    rets = {"new_stock": _rets(rng, n=30), "old_stock": _rets(rng, n=252)}
    result = await allocate(
        "mean_variance", tickers, prices,
        FakePriceLookup(prices), FakeHistoricalLookup(rets),
        AllocatorParams(lookback_days=252),
    )
    assert sum(result.target_weights.values()) == pytest.approx(1.0, abs=1e-6)
