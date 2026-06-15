"""
Tests for ticker → mkkMemberOid resolution used by the financialTable API flow.

instrument_identity_map is dependency-light (logging + typing), so it imports without
pulling the heavy scrapers package.
"""
from infrastructure.contracts.instrument_identity_map import (
    STATIC_MEMBER_OID_MAP,
    resolve_member_oid,
)


class FakeDB:
    def __init__(self, oid=None, raise_=False):
        self.oid = oid
        self.raise_ = raise_

    def query(self, sql, params=None):
        if self.raise_:
            raise RuntimeError("db down")
        if "mkk_member_oid" in sql and self.oid:
            return [{"mkk_member_oid": self.oid}]
        return []


def test_static_seed_resolves():
    assert resolve_member_oid("ASELS") == STATIC_MEMBER_OID_MAP["ASELS"]
    assert resolve_member_oid("asels") == STATIC_MEMBER_OID_MAP["ASELS"]


def test_unsupported_market_is_none():
    assert resolve_member_oid("AAPL", market="usa") is None


def test_unknown_ticker_is_none():
    assert resolve_member_oid("ZZZZ") is None


def test_db_value_takes_precedence():
    db = FakeDB(oid="db-oid-123")
    assert resolve_member_oid("ASELS", db_manager=db) == "db-oid-123"


def test_db_failure_falls_back_to_static():
    db = FakeDB(raise_=True)
    assert resolve_member_oid("ASELS", db_manager=db) == STATIC_MEMBER_OID_MAP["ASELS"]
