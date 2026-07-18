from datetime import date, datetime
from decimal import Decimal
import numpy as np
import pytest
from valor.portfolio.models import Portfolio, Holding, Lot
from valor.portfolio.analytics import compute_analytics


class FakePriceLookup:
    def __init__(self, prices: dict[str, Decimal]):
        self._p = prices
    async def get(self, ticker: str, as_of: date) -> Decimal:
        return self._p[ticker]


def _portfolio(holdings):
    return Portfolio(portfolio_id="pf1", name="t", cash=Decimal("50000"),
                     holdings=holdings,
                     created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17))


@pytest.mark.asyncio
async def test_single_holding_pnl():
    h = Holding(ticker="600519", name="贵州茅台",
                lots=[Lot(lot_id="l1", open_date=date(2024, 1, 1), quantity=100,
                          cost_price=Decimal("1689.50"), fees=Decimal("12.50"))])
    p = _portfolio([h])
    result = await compute_analytics(p, FakePriceLookup({"600519": Decimal("1750.20")}))
    pos = result.positions[0]
    assert pos.quantity == 100
    assert pos.market_value == Decimal("175020.00")
    assert pos.cost_value == Decimal("168962.50")
    assert pos.unrealized_pnl == Decimal("6057.50")
    assert pos.weight == 1.0


@pytest.mark.asyncio
async def test_multi_lot_aggregation():
    h = Holding(ticker="600519", lots=[
        Lot(lot_id="l1", open_date=date(2024, 1, 1), quantity=60, cost_price=Decimal("1600")),
        Lot(lot_id="l2", open_date=date(2024, 2, 1), quantity=40, cost_price=Decimal("1800")),
    ])
    p = _portfolio([h])
    result = await compute_analytics(p, FakePriceLookup({"600519": Decimal("1700")}))
    assert result.positions[0].quantity == 100
    assert result.positions[0].cost_value == Decimal("168000")
    assert result.positions[0].market_value == Decimal("170000")


@pytest.mark.asyncio
async def test_weights_normalized():
    h1 = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=100, cost_price=Decimal("10"))])
    h2 = Holding(ticker="000858", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=200, cost_price=Decimal("10"))])
    p = _portfolio([h1, h2])
    result = await compute_analytics(p, FakePriceLookup({"600519": Decimal("10"), "000858": Decimal("10")}))
    assert result.positions[0].weight == pytest.approx(1/3)
    assert result.positions[1].weight == pytest.approx(2/3)
    assert result.total_market_value == Decimal("3000")


@pytest.mark.asyncio
async def test_concentration_hhi_equal_weight():
    holdings = [Holding(ticker=f"t{i}", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=100, cost_price=Decimal("10"))]) for i in range(5)]
    p = _portfolio(holdings)
    result = await compute_analytics(p, FakePriceLookup({f"t{i}": Decimal("10") for i in range(5)}))
    assert result.concentration.herfindahl_index == pytest.approx(0.2)
    assert result.concentration.effective_holdings == pytest.approx(5.0)
    assert result.concentration.top1_weight == pytest.approx(0.2)
    assert result.concentration.top5_weight == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_concentration_single_holding():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=100, cost_price=Decimal("10"))])
    p = _portfolio([h])
    result = await compute_analytics(p, FakePriceLookup({"600519": Decimal("10")}))
    assert result.concentration.herfindahl_index == pytest.approx(1.0)
    assert result.concentration.effective_holdings == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_total_assets_includes_cash():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=100, cost_price=Decimal("10"))])
    p = _portfolio([h])
    result = await compute_analytics(p, FakePriceLookup({"600519": Decimal("20")}))
    assert result.total_market_value == Decimal("2000")
    assert result.cash == Decimal("50000")
    assert result.total_assets == Decimal("52000")


class FakeSectorLookup:
    def __init__(self, sectors: dict[str, str]):
        self._s = sectors
    async def get(self, ticker: str) -> str | None:
        return self._s.get(ticker)


class FakeHistoricalLookup:
    def __init__(self, returns: dict[str, np.ndarray]):
        self._r = returns
    async def get_returns(self, ticker: str, days: int) -> np.ndarray:
        return self._r[ticker]


@pytest.mark.asyncio
async def test_sector_exposure():
    h1 = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=100, cost_price=Decimal("10"))])
    h2 = Holding(ticker="000858", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=100, cost_price=Decimal("10"))])
    h3 = Holding(ticker="601398", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=100, cost_price=Decimal("10"))])
    p = _portfolio([h1, h2, h3])
    sectors = {"600519": "白酒", "000858": "白酒", "601398": "银行"}
    result = await compute_analytics(
        p, FakePriceLookup({"600519": Decimal("10"), "000858": Decimal("10"), "601398": Decimal("10")}),
        sector_lookup=FakeSectorLookup(sectors),
    )
    assert result.sector_exposure["白酒"] == pytest.approx(2/3)
    assert result.sector_exposure["银行"] == pytest.approx(1/3)


@pytest.mark.asyncio
async def test_portfolio_beta():
    h1 = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=100, cost_price=Decimal("10"))])
    h2 = Holding(ticker="000858", lots=[Lot(lot_id="l", open_date=date(2024,1,1), quantity=100, cost_price=Decimal("10"))])
    p = _portfolio([h1, h2])
    rng = np.random.default_rng(42)
    bench = rng.standard_normal(252) * 0.015
    noise1 = rng.standard_normal(252) * 0.005
    noise2 = rng.standard_normal(252) * 0.005
    rets = {"000300": bench, "600519": 1.2 * bench + noise1, "000858": 0.8 * bench + noise2}
    result = await compute_analytics(
        p, FakePriceLookup({"600519": Decimal("10"), "000858": Decimal("10")}),
        historical_lookup=FakeHistoricalLookup(rets),
    )
    assert result.portfolio_beta is not None
    assert 0.8 < result.portfolio_beta < 1.2
