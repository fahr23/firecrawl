#!/usr/bin/env python3
"""
Run 3 Clarivate Web of Science searches and save results.
"""

import sys
import os
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_academic_search.providers import ClarivateSearcher
from api_academic_search.config import Config
from api_academic_search.engine import create_engine
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

SEARCHES = [
    {
        "name": "agent_based_co2_mitigation_deep_learning",
        "query": "TS=(agent based) AND TS=(CO2) AND TS=(deep learning)",
        "label": "Agent Based CO2 Mitigation Deep Learning"
    },
    {
        "name": "co2_emission_mitigation_scenario_based",
        "query": "TS=(CO2 emission) AND TS=(mitigation) AND TS=(scenario based)",
        "label": "CO2 Emission Mitigations Scenario Based"
    },
    {
        "name": "renewable_energy_agent_based",
        "query": "TS=(renewable energy) AND TS=(agent based)",
        "label": "Renewable Energy Agent Based"
    },
]

def run_search(searcher, engine, search_config, max_results=100):
    """Run a single search, save results."""
    query = search_config["query"]
    name = search_config["name"]
    label = search_config["label"]
    
    print(f"\n{'='*80}")
    print(f"  SEARCH: {label}")
    print(f"  Query:  {query}")
    print(f"{'='*80}\n")
    
    # Search WoS sorted by citations
    result = searcher.search(
        query,
        max_results=max_results,
        sort_by="citations"
    )
    
    print(f"  Total found in Web of Science: {result.total_found:,}")
    print(f"  Retrieved: {len(result.articles)}")
    
    if not result.articles:
        print("  No results found.")
        return
    
    # Show top 10
    print(f"\n  Top {min(10, len(result.articles))} by Citations:")
    print(f"  {'-'*70}")
    for i, article in enumerate(result.articles[:10], 1):
        cites = f"[{article.citation_count} cites]" if article.citation_count is not None else ""
        print(f"  {i:3d}. {article.title[:70]}...")
        print(f"       {article.authors[:60]}... ({article.year}) {cites}")
        if article.doi:
            print(f"       DOI: {article.doi}")
        print()
    
    # Enrich abstracts
    print("  Enriching abstracts...")
    result = engine.enrich_abstracts(result)
    with_abstracts = sum(1 for a in result.articles if a.abstract)
    print(f"  Abstracts: {with_abstracts}/{len(result.articles)}")
    
    # Save results
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_academic_search", "results")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"wos_{name}_{timestamp}"
    save_dir = os.path.join(base_dir, folder_name)
    os.makedirs(save_dir, exist_ok=True)
    
    formats = {
        'json': 'json',
        'csv': 'csv',
        'markdown': 'md',
        'bibtex': 'bib'
    }
    
    print(f"\n  Saving to: {save_dir}")
    for fmt, ext in formats.items():
        filepath = os.path.join(save_dir, f"{folder_name}.{ext}")
        try:
            engine.export(result, filepath, format=fmt)
            print(f"    ✓ {fmt.upper()}: {folder_name}.{ext}")
        except Exception as e:
            print(f"    ✗ {fmt}: {e}")
    
    print(f"\n  Summary: {result.total_found:,} total | {len(result.articles)} retrieved | {with_abstracts} with abstracts")
    return result


def main():
    print("\n" + "="*80)
    print("  CLARIVATE WEB OF SCIENCE - BATCH SEARCH")
    print("  3 searches sorted by citations")
    print("="*80)
    
    config = Config()
    searcher = ClarivateSearcher(config)
    engine = create_engine()
    
    if not searcher.is_available:
        print("ERROR: Clarivate API key not configured!")
        sys.exit(1)
    
    print(f"\n  API Key: ...{config.api.clarivate_api_key[-8:]}")
    print(f"  Max results per search: 100")
    
    results = {}
    for search_config in SEARCHES:
        try:
            result = run_search(searcher, engine, search_config, max_results=100)
            results[search_config["name"]] = result
        except Exception as e:
            print(f"\n  ERROR in '{search_config['label']}': {e}")
    
    # Final summary
    print(f"\n\n{'='*80}")
    print(f"  FINAL SUMMARY")
    print(f"{'='*80}\n")
    
    for search_config in SEARCHES:
        name = search_config["name"]
        label = search_config["label"]
        result = results.get(name)
        if result:
            abstracts = sum(1 for a in result.articles if a.abstract)
            print(f"  {label}:")
            print(f"    Total found: {result.total_found:,}")
            print(f"    Retrieved:   {len(result.articles)}")
            print(f"    Abstracts:   {abstracts}")
            if result.articles:
                top = result.articles[0]
                cites = f" ({top.citation_count} citations)" if top.citation_count else ""
                print(f"    Top paper:   {top.title[:60]}...{cites}")
            print()
        else:
            print(f"  {label}: FAILED\n")
    
    print("  All searches complete!")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
