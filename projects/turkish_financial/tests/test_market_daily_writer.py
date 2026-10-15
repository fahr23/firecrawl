"""DatabaseManager market writers -> typed market_daily rows (no DB; fake connection)."""
from datetime import date

from database.db_manager import DatabaseManager


class FakeCursor:
    def __init__(self, sink):
        self.sink = sink

    def executemany(self, sql, rows):
        self.sink.append((sql, list(rows)))


class FakeConn:
    def __init__(self, sink):
        self.sink = sink
        self.committed = False

    def cursor(self):
        return FakeCursor(self.sink)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def _manager(sink):
    db = DatabaseManager.__new__(DatabaseManager)  # skip pool/schema setup
    conn = FakeConn(sink)
    db.get_connection = lambda: conn
    db.return_connection = lambda c: None
    return db


def test_bist_item_maps_to_typed_columns():
    sink = []
    ok = _manager(sink).upsert_isyatirim_market_history(" thyao ", [{
        "trading_date": "08-05-2026", "close_try": 285.5, "high_try": 288.0, "low_try": 282.0,
        "average_price_try": 284.2, "volume_try": 1.25e9, "market_cap_try": 3.9e11,
        "free_float_market_cap_try": 1.5e11, "shares_outstanding": 1.365e9, "usd_try": 40.1,
        "close_usd": 7.12, "market_cap_usd": 9.7e9, "free_float_market_cap_usd": 3.7e9, "index_value": 10234.5,
    }])
    assert ok
    sql, rows = sink[0]
    assert "INSERT INTO market_daily" in sql and "instrument_id_for(%s, %s)" in sql
    market, code, trading_date, *values = rows[0]
    assert (market, code, trading_date) == ("bist", " thyao ", date(2026, 5, 8))  # normalised in SQL
    cols = sql.split("trading_date, ")[1].split(", currency")[0].split(", ")
    stored = dict(zip(cols, values[: len(cols)]))
    assert stored["close"] == 285.5 and stored["vwap"] == 284.2
    assert stored["turnover"] == 1.25e9  # volume_try is value traded, not units
    assert values[len(cols):] == ["TRY", "isyatirim"]


def test_coin_volume_is_turnover_and_bad_dates_are_skipped():
    sink = []
    ok = _manager(sink).upsert_coingecko_market_history("bitcoin", [
        {"trading_date": "2026-05-08", "close": 83000.0, "market_cap": 1.6e12, "volume": 3.2e10},
        {"trading_date": "08/05/2026", "close": 1.0},
    ])
    assert ok
    sql, rows = sink[0]
    assert len(rows) == 1
    cols = sql.split("trading_date, ")[1].split(", currency")[0].split(", ")
    stored = dict(zip(cols, rows[0][3:3 + len(cols)]))
    assert stored == {"close": 83000.0, "market_cap": 1.6e12, "turnover": 3.2e10}


def test_nothing_parsable_writes_nothing():
    sink = []
    assert _manager(sink).upsert_yahoo_market_history("AAPL", [{"trading_date": "bad"}]) is False
    assert sink == []
