"""
Macro series alias registry — FA-11 §4 "macro" kind.

F23 sends an upper-case alias (e.g. "CPI_INDEX") and `market=tr`; the provider
owns the alias → EVDS series-code mapping so F23 never hard-codes an EVDS
code. `source_series_code` is always returned in the macro envelope so F23
can see exactly which upstream series answered the request.

*** VERIFICATION REQUIRED BEFORE PRODUCTION USE ***
The EVDS codes below are placeholders (`None`). Confirming the exact series
code for each alias needs the EVDS catalog browse (api.tcmb.gov.tr/kategori),
which requires an authenticated EVDS API key session — not available while
writing this module. `resolve_series_code()` raises `NotImplementedError` for
any alias still unverified, which — because `TCMBScraper.scrape()` catches
that inside its existing fail-closed path (FA-00) — surfaces to callers as an
honest `unavailable`, never a wrong series silently served as right.

To verify and activate an alias: look up its series code in the EVDS catalog
(https://evds2.tcmb.gov.tr/index.php?/evds/serieMarket), fill in the string
below, and update the matching unit test in
tests/domain/test_macro_series_registry.py to assert the real code.
"""
from __future__ import annotations

from typing import NamedTuple, Optional


class MacroSeriesSpec(NamedTuple):
    evds_code: Optional[str]  # None until verified against the live EVDS catalog
    unit: str
    frequency: str  # "monthly" | "daily" | "quarterly"
    publisher: str  # "TÜİK" | "TCMB"


# F23's fixed FA-11 alias set (provider-wait-list §2 `macro` kind). Every
# alias is upper-case, matching how F23 sends it.
_REGISTRY: dict[str, MacroSeriesSpec] = {
    "CPI_INDEX": MacroSeriesSpec(evds_code=None, unit="index", frequency="monthly", publisher="TÜİK"),
    "POLICY_RATE": MacroSeriesSpec(evds_code=None, unit="percent", frequency="daily", publisher="TCMB"),
    "USD_TRY": MacroSeriesSpec(evds_code=None, unit="TRY", frequency="daily", publisher="TCMB"),
    "EUR_TRY": MacroSeriesSpec(evds_code=None, unit="TRY", frequency="daily", publisher="TCMB"),
    "GOLD_TRY_GRAM": MacroSeriesSpec(evds_code=None, unit="TRY", frequency="daily", publisher="TCMB"),
}

# FA-12 M3 additions: TL government bond yields, deposit/loan rates, REER, PPI.
# CDS and energy (Brent, natural gas) are deliberately excluded — ADR D7 gates
# them on confirming a source whose terms allow storage, an owner licensing
# decision, not something to build around with a guessed source.
_FA12_REGISTRY: dict[str, MacroSeriesSpec] = {
    "GOV_BOND_YIELD_2Y": MacroSeriesSpec(evds_code=None, unit="percent", frequency="daily", publisher="TCMB"),
    "GOV_BOND_YIELD_10Y": MacroSeriesSpec(evds_code=None, unit="percent", frequency="daily", publisher="TCMB"),
    "DEPOSIT_RATE": MacroSeriesSpec(evds_code=None, unit="percent", frequency="monthly", publisher="TCMB"),
    "LOAN_RATE": MacroSeriesSpec(evds_code=None, unit="percent", frequency="monthly", publisher="TCMB"),
    "REER": MacroSeriesSpec(evds_code=None, unit="index", frequency="monthly", publisher="TCMB"),
    "PPI_INDEX": MacroSeriesSpec(evds_code=None, unit="index", frequency="monthly", publisher="TÜİK"),
    "CAPACITY_UTILIZATION": MacroSeriesSpec(evds_code=None, unit="percent", frequency="monthly", publisher="TCMB"),
}
_REGISTRY.update(_FA12_REGISTRY)

SUPPORTED_ALIASES: tuple[str, ...] = tuple(_REGISTRY.keys())
FA11_ALIASES: tuple[str, ...] = (
    "CPI_INDEX", "POLICY_RATE", "USD_TRY", "EUR_TRY", "GOLD_TRY_GRAM",
)
FA12_ALIASES: tuple[str, ...] = tuple(_FA12_REGISTRY.keys())


def supports_alias(alias: str) -> bool:
    return (alias or "").strip().upper() in _REGISTRY


def get_spec(alias: str) -> Optional[MacroSeriesSpec]:
    return _REGISTRY.get((alias or "").strip().upper())


def resolve_series_code(alias: str) -> str:
    """
    Return the verified EVDS series code for `alias`.

    Raises:
        KeyError: `alias` is not one of F23's supported macro aliases.
        NotImplementedError: `alias` is supported but its EVDS code has not
            been verified yet (see module docstring) — callers must treat
            this the same as "unavailable", never fall back to a guess.
    """
    spec = _REGISTRY[(alias or "").strip().upper()]
    if spec.evds_code is None:
        raise NotImplementedError(
            f"EVDS series code for alias '{alias}' is not yet verified against "
            "the live EVDS catalog — see domain/services/macro_series_registry.py"
        )
    return spec.evds_code
