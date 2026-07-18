from datetime import date
from decimal import Decimal
from valor.portfolio.loader import detect_format, parse_eastmoney_csv, parse_generic_csv

GENERIC_CSV = """ticker,name,quantity,cost_price,open_date,fees
600519,贵州茅台,100,1689.50,2024-03-15,12.50
000858,五粮液,200,158.20,2024-05-10,8.00
"""

def test_generic_basic():
    holdings = parse_generic_csv(GENERIC_CSV.encode("utf-8"))
    assert len(holdings) == 2
    assert holdings[0].ticker == "600519"
    assert holdings[0].name == "贵州茅台"
    assert holdings[0].lots[0].quantity == 100
    assert holdings[0].lots[0].cost_price == Decimal("1689.50")
    assert holdings[0].lots[0].open_date == date(2024, 3, 15)
    assert holdings[0].lots[0].fees == Decimal("12.50")

def test_generic_optional_columns_missing():
    csv = b"ticker,quantity,cost_price\n600519,100,1689.50\n"
    holdings = parse_generic_csv(csv)
    assert holdings[0].name is None
    assert len(holdings[0].lots) == 1
    assert holdings[0].lots[0].fees == Decimal("0")

def test_generic_ticker_zfill():
    csv = b"ticker,quantity,cost_price\n519,100,1.50\n"
    holdings = parse_generic_csv(csv)
    assert holdings[0].ticker == "000519"

def test_generic_thousands_separator():
    csv = b"ticker,quantity,cost_price\n600519,1,000,1689.50\n"
    holdings = parse_generic_csv(csv)
    assert holdings[0].lots[0].quantity == 1000

def test_generic_case_insensitive_header():
    csv = b"TICKER,QUANTITY,COST_PRICE\n600519,100,1689.50\n"
    holdings = parse_generic_csv(csv)
    assert len(holdings) == 1

def test_generic_bad_row_skipped():
    csv = b"ticker,quantity,cost_price\n600519,100,1689.50\n000858,notanumber,158.20\n"
    holdings = parse_generic_csv(csv)
    assert len(holdings) == 1
    assert holdings[0].ticker == "600519"


EASTMONEY_CSV = "证券代码,证券名称,持仓数量,成本价,证券市值,浮动盈亏,盈亏比例\n600519,贵州茅台,100,1689.50,175020.00,6070.00,3.59\n000858,五粮液,200,158.20,31640.00,920.00,2.91\n合计,,,,,6990.00,\n".encode("gbk")


def test_detect_eastmoney():
    assert detect_format(EASTMONEY_CSV) == "eastmoney"


def test_detect_generic():
    assert detect_format(GENERIC_CSV.encode("utf-8")) == "generic"


def test_eastmoney_parse():
    holdings = parse_eastmoney_csv(EASTMONEY_CSV)
    assert len(holdings) == 2
    assert holdings[0].ticker == "600519"
    assert holdings[0].name == "贵州茅台"
    assert holdings[0].lots[0].quantity == 100
    assert holdings[0].lots[0].cost_price == Decimal("1689.50")


def test_eastmoney_skips_total_row():
    holdings = parse_eastmoney_csv(EASTMONEY_CSV)
    assert all(h.ticker != "合计" for h in holdings)


def test_eastmoney_thousands_in_quantity():
    csv = "证券代码,证券名称,持仓数量,成本价\n600519,茅台,1,000,1689.50\n".encode("gbk")
    holdings = parse_eastmoney_csv(csv)
    assert holdings[0].lots[0].quantity == 1000
