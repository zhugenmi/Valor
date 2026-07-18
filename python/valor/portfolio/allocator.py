"""Portfolio allocation algorithms. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations
from decimal import Decimal
from typing import Literal
import numpy as np
from pydantic import BaseModel
from valor.portfolio.analytics import PriceLookup, HistoricalLookup


class AllocatorParams(BaseModel):
    lookback_days: int = 252
    risk_free_rate: float = 0.025
    target_return: float | None = None
    max_weight: float = 0.40
    min_weight: float = 0.0
    benchmark: str = "000300"


class AllocationResult(BaseModel):
    method: Literal["equal_weight", "mean_variance", "risk_parity"]
    target_weights: dict[str, float]
    expected_return: float | None
    expected_volatility: float | None
    sharpe: float | None
    rationale: str
    diagnostics: dict


async def _gather_returns(
    tickers: list[str], historical: HistoricalLookup, days: int
) -> dict[str, np.ndarray]:
    out = {}
    for t in tickers:
        r = await historical.get_returns(t, days)
        out[t] = r if len(r) > 0 else np.array([0.0])
    return out


def _annualize(returns_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    exp_ret = returns_matrix.mean(axis=1) * 252
    cov = np.atleast_2d(np.cov(returns_matrix)) * 252
    return exp_ret, cov


async def allocate(
    method: Literal["equal_weight", "mean_variance", "risk_parity"],
    tickers: list[str],
    prices: dict[str, Decimal],
    price_lookup: PriceLookup,
    historical_lookup: HistoricalLookup,
    params: AllocatorParams,
) -> AllocationResult:
    if not tickers:
        raise ValueError("tickers must not be empty")
    n = len(tickers)
    rets = await _gather_returns(tickers, historical_lookup, params.lookback_days)
    series = [rets[t][-params.lookback_days:] for t in tickers]
    min_len = min(len(s) for s in series)
    matrix = np.array([s[-min_len:] for s in series])
    exp_ret, cov = _annualize(matrix)
    if method == "equal_weight":
        w = np.ones(n) / n
        rationale = f"等权分配：{n} 只标的各 {1/n:.2%}"
        diagnostics = {"fallback": False}
    elif method == "mean_variance":
        w, diagnostics = _mean_variance(exp_ret, cov, params)
        rationale = _mvo_rationale(w, exp_ret, cov, params, diagnostics)
    elif method == "risk_parity":
        w, diagnostics = _risk_parity(cov, params)
        rationale = _rp_rationale(w, cov, diagnostics)
    else:
        raise ValueError(f"unknown method: {method}")
    port_ret = float(w @ exp_ret)
    port_vol = float(np.sqrt(w @ cov @ w))
    sharpe = (port_ret - params.risk_free_rate) / port_vol if port_vol > 0 else None
    return AllocationResult(
        method=method,
        target_weights={t: float(wi) for t, wi in zip(tickers, w)},
        expected_return=port_ret, expected_volatility=port_vol,
        sharpe=sharpe, rationale=rationale, diagnostics=diagnostics,
    )


def _mean_variance(exp_ret, cov, params: AllocatorParams) -> tuple[np.ndarray, dict]:
    from scipy.optimize import minimize
    n = len(exp_ret)
    def neg_sharpe(w, er, c, rf):
        r = w @ er
        v = np.sqrt(w @ c @ w)
        return -(r - rf) / v if v > 0 else 1e10
    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    if params.target_return is not None:
        constraints.append({"type": "ineq", "fun": lambda w: w @ exp_ret - params.target_return})
    bounds = [(params.min_weight, params.max_weight)] * n
    result = minimize(neg_sharpe, np.ones(n)/n, args=(exp_ret, cov, params.risk_free_rate),
                      method="SLSQP", bounds=bounds, constraints=constraints,
                      options={"maxiter": 500, "ftol": 1e-9})
    if not result.success:
        return np.ones(n)/n, {"fallback": True, "reason": result.message, "iterations": result.nit}
    return result.x, {"fallback": False, "converged": result.success, "iterations": result.nit}


def _risk_parity(cov, params: AllocatorParams) -> tuple[np.ndarray, dict]:
    from scipy.optimize import minimize
    n = cov.shape[0]
    def risk_contributions(w, c):
        vol = np.sqrt(w @ c @ w)
        marginal = c @ w / vol if vol > 0 else np.zeros(n)
        return w * marginal
    def objective(w, c):
        rc = risk_contributions(w, c)
        target = rc.mean()
        return ((rc - target) ** 2).sum()
    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    bounds = [(params.min_weight, params.max_weight)] * n
    result = minimize(objective, np.ones(n)/n, args=(cov,),
                      method="SLSQP", bounds=bounds, constraints=constraints,
                      options={"maxiter": 500, "ftol": 1e-9})
    if not result.success:
        return np.ones(n)/n, {"fallback": True, "reason": result.message, "iterations": result.nit}
    return result.x, {"fallback": False, "converged": result.success, "iterations": result.nit}


def _mvo_rationale(w, exp_ret, cov, params, diag):
    method_desc = "最大化夏普" if params.target_return is None else f"约束期望收益 ≥ {params.target_return:.2%}"
    if diag.get("fallback"):
        return f"均值方差优化未收敛（{diag.get('reason', '未知')}），回退到等权"
    top = sorted(zip(range(len(w)), w), key=lambda x: -x[1])[:3]
    desc = "、".join(f"{wi:.1%}" for _, wi in top)
    return f"均值方差优化（{method_desc}），前三大权重：{desc}"


def _rp_rationale(w, cov, diag):
    if diag.get("fallback"):
        return f"风险平价优化未收敛（{diag.get('reason', '未知')}），回退到等权"
    return f"风险平价：各资产风险贡献等分，{len(w)} 只标的"
