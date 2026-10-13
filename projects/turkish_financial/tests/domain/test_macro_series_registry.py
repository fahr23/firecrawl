"""
Unit tests for the FA-11 macro series alias registry.

Pure lookups — no DB, no network. Documents the current verification state:
every alias is supported but unverified (raises NotImplementedError) until
someone confirms its EVDS code against the live catalog.
"""
import pytest

from domain.services.macro_series_registry import (
    FA11_ALIASES,
    FA12_ALIASES,
    SUPPORTED_ALIASES,
    get_spec,
    resolve_series_code,
    supports_alias,
)


class TestSupportedAliases:
    def test_all_five_f23_aliases_present(self):
        assert set(FA11_ALIASES) == {
            "CPI_INDEX", "POLICY_RATE", "USD_TRY", "EUR_TRY", "GOLD_TRY_GRAM",
        }

    def test_fa12_aliases_present_and_disjoint_from_fa11(self):
        assert set(FA12_ALIASES) == {
            "GOV_BOND_YIELD_2Y", "GOV_BOND_YIELD_10Y", "DEPOSIT_RATE",
            "LOAN_RATE", "REER", "PPI_INDEX", "CAPACITY_UTILIZATION",
        }
        assert set(FA11_ALIASES) & set(FA12_ALIASES) == set()

    def test_cds_and_energy_are_not_in_the_registry(self):
        """ADR D7 gates CDS/energy on a licensing decision — never built around
        a guessed source."""
        assert "CDS_5Y" not in SUPPORTED_ALIASES
        assert "BRENT" not in SUPPORTED_ALIASES
        assert "NATURAL_GAS" not in SUPPORTED_ALIASES

    def test_supported_aliases_is_union_of_fa11_and_fa12(self):
        assert set(SUPPORTED_ALIASES) == set(FA11_ALIASES) | set(FA12_ALIASES)

    def test_supports_alias_is_case_insensitive(self):
        assert supports_alias("cpi_index") is True
        assert supports_alias("CPI_INDEX") is True

    def test_unknown_alias_unsupported(self):
        assert supports_alias("NOT_A_REAL_ALIAS") is False


class TestGetSpec:
    def test_known_alias_has_metadata(self):
        spec = get_spec("CPI_INDEX")
        assert spec.unit == "index"
        assert spec.frequency == "monthly"
        assert spec.publisher == "TÜİK"

    def test_unknown_alias_returns_none(self):
        assert get_spec("NOT_A_REAL_ALIAS") is None


class TestResolveSeriesCode:
    @pytest.mark.parametrize("alias", SUPPORTED_ALIASES)
    def test_unverified_alias_raises_not_implemented(self, alias):
        """Every alias is unverified today (see module docstring) — this test
        documents that state and should start failing (in the good way, by
        returning a real code) once someone fills in an evds_code."""
        with pytest.raises(NotImplementedError):
            resolve_series_code(alias)

    def test_unknown_alias_raises_key_error(self):
        with pytest.raises(KeyError):
            resolve_series_code("NOT_A_REAL_ALIAS")
