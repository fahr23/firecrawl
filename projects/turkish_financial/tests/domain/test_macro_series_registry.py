"""
Unit tests for the FA-11 macro series alias registry.

Pure lookups — no DB, no network. Documents the current verification state:
every alias is supported but unverified (raises NotImplementedError) until
someone confirms its EVDS code against the live catalog.
"""
import pytest

from domain.services.macro_series_registry import (
    SUPPORTED_ALIASES,
    get_spec,
    resolve_series_code,
    supports_alias,
)


class TestSupportedAliases:
    def test_all_five_f23_aliases_present(self):
        assert set(SUPPORTED_ALIASES) == {
            "CPI_INDEX", "POLICY_RATE", "USD_TRY", "EUR_TRY", "GOLD_TRY_GRAM",
        }

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
    @pytest.mark.parametrize("alias", ["CPI_INDEX", "POLICY_RATE", "USD_TRY", "EUR_TRY", "GOLD_TRY_GRAM"])
    def test_unverified_alias_raises_not_implemented(self, alias):
        """Every alias is unverified today (see module docstring) — this test
        documents that state and should start failing (in the good way, by
        returning a real code) once someone fills in an evds_code."""
        with pytest.raises(NotImplementedError):
            resolve_series_code(alias)

    def test_unknown_alias_raises_key_error(self):
        with pytest.raises(KeyError):
            resolve_series_code("NOT_A_REAL_ALIAS")
