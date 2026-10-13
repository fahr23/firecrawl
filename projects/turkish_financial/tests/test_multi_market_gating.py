"""
Tests for the supports_market / supports_kap_market split (multi-market support).

supports_market() is the general "this provider addresses the market at all"
check used by market-data kinds (bist/usa/coin all serve real price data).
supports_kap_market() is the narrower BIST-only check used by every KAP-rooted
kind (fundamental, sentiment, events, corporate_actions, classification,
ownership, dividends, earnings_calendar) — there is no KAP equivalent for
usa/coin, so those must keep failing closed even though the general gate now
passes.
"""
from infrastructure.contracts.instrument_identity_map import (
    resolve_member_oid,
    resolve_name_patterns,
    static_name_patterns,
    supports_kap_market,
    supports_market,
)


class TestSupportsMarket:
    def test_all_three_markets_pass_the_general_gate(self):
        assert supports_market("bist") is True
        assert supports_market("usa") is True
        assert supports_market("coin") is True

    def test_case_insensitive(self):
        assert supports_market("USA") is True
        assert supports_market("Coin") is True

    def test_unknown_market_fails(self):
        assert supports_market("tokyo") is False
        assert supports_market("") is False
        assert supports_market(None) is False


class TestSupportsKapMarket:
    def test_only_bist_passes_the_kap_gate(self):
        assert supports_kap_market("bist") is True
        assert supports_kap_market("usa") is False
        assert supports_kap_market("coin") is False

    def test_case_insensitive(self):
        assert supports_kap_market("BIST") is True


class TestKapFunctionsStayBistOnly:
    """Every KAP-specific resolver must keep failing closed for usa/coin even
    though the general supports_market() gate now accepts them."""

    def test_resolve_name_patterns_empty_for_usa_and_coin(self):
        assert resolve_name_patterns("AAPL", "usa") == []
        assert resolve_name_patterns("BTC", "coin") == []

    def test_static_name_patterns_none_for_usa_and_coin(self):
        assert static_name_patterns("AAPL", "usa") is None
        assert static_name_patterns("BTC", "coin") is None

    def test_resolve_member_oid_none_for_usa_and_coin(self):
        assert resolve_member_oid("AAPL", market="usa") is None
        assert resolve_member_oid("BTC", market="coin") is None

    def test_bist_still_resolves_normally(self):
        assert resolve_name_patterns("THYAO", "bist") != []
