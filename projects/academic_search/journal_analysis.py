"""Deterministic, reproducible analysis for journal exploration and fit reports."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence


PROFILE_VERSION = "journal-profile-token-frequency-v1"
ARTICLE_ALIGNMENT_VERSION = "journal-topic-overlap-v1"
FIT_VERSION = "token-cosine-fit-v1"

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9-]{2,}")
_STOPWORDS = {
    "about", "after", "also", "among", "analysis", "and", "are", "article",
    "based", "been", "being", "between", "both", "but", "can", "data", "does",
    "during", "each", "for", "from", "had", "has", "have", "into", "its",
    "may", "more", "most", "not", "our", "paper", "results", "research", "show",
    "study", "such", "than", "that", "the", "their", "these", "they", "this",
    "through", "using", "was", "were", "which", "with", "within", "without",
}


def tokens(value: str) -> List[str]:
    """Return normalized content tokens for transparent lexical comparison."""
    return [
        token.lower()
        for token in _TOKEN_RE.findall(value or "")
        if token.lower() not in _STOPWORDS
    ]


def _paper_text(paper: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(paper.get("title") or ""),
            str(paper.get("abstract") or ""),
            " ".join(str(item) for item in (paper.get("keywords") or [])),
        ]
    )


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(value * right.get(term, 0) for term, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def annotate_topic_alignment(
    papers: Sequence[Dict[str, Any]], topics: Sequence[str]
) -> List[Dict[str, Any]]:
    """Add deterministic topic coverage to serialized provider records."""
    topic_tokens = list(dict.fromkeys(tokens(" ".join(topics))))
    annotated: List[Dict[str, Any]] = []
    for paper in papers:
        title_tokens = set(tokens(str(paper.get("title") or "")))
        body_tokens = set(tokens(_paper_text(paper)))
        matched = [term for term in topic_tokens if term in body_tokens]
        title_matches = sum(1 for term in topic_tokens if term in title_tokens)
        coverage = len(matched) / len(topic_tokens) if topic_tokens else 0.0
        title_bonus = title_matches / len(topic_tokens) if topic_tokens else 0.0
        score = round(min(100.0, (coverage * 80.0) + (title_bonus * 20.0)), 1)
        annotated.append({
            **paper,
            "alignment": {
                "score": score,
                "matched_terms": matched,
                "provenance": f"derived:{ARTICLE_ALIGNMENT_VERSION}",
            },
        })
    annotated.sort(
        key=lambda item: (
            item["alignment"]["score"],
            int(item.get("year")) if str(item.get("year") or "").isdigit() else 0,
        ),
        reverse=True,
    )
    return annotated


def build_journal_profile(papers: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize the supplied result snapshot without claiming full coverage."""
    term_counts: Counter[str] = Counter()
    keyword_counts: Counter[str] = Counter()
    year_counts: Counter[str] = Counter()
    for paper in papers:
        term_counts.update(tokens(_paper_text(paper)))
        for keyword in paper.get("keywords") or []:
            normalized = " ".join(tokens(str(keyword)))
            if normalized:
                keyword_counts[normalized] += 1
        year = str(paper.get("year") or "").strip()
        if year.isdigit():
            year_counts[year] += 1

    topic_counts = keyword_counts or term_counts
    return {
        "paper_count": len(papers),
        "top_topics": [
            {"term": term, "count": count}
            for term, count in topic_counts.most_common(12)
        ],
        "top_terms": [
            {"term": term, "count": count}
            for term, count in term_counts.most_common(20)
        ],
        "publications_by_year": [
            {"year": year, "count": year_counts[year]}
            for year in sorted(year_counts, reverse=True)
        ],
        "provenance": f"derived:{PROFILE_VERSION}",
        "coverage_note": (
            "Profile derived only from the saved result snapshot; it is not a complete "
            "description of the journal's full publication history."
        ),
    }


def manuscript_fit(
    title: str,
    abstract: str,
    keywords: Iterable[str],
    papers: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare manuscript text with one immutable journal-search snapshot."""
    manuscript_text = " ".join([title, abstract, " ".join(keywords)])
    manuscript_terms = Counter(tokens(manuscript_text))
    journal_terms: Counter[str] = Counter()
    closest = []
    for paper in papers:
        paper_terms = Counter(tokens(_paper_text(paper)))
        journal_terms.update(paper_terms)
        score = round(_cosine(manuscript_terms, paper_terms) * 100.0, 1)
        closest.append({
            "title": paper.get("title"),
            "url": paper.get("url"),
            "doi": paper.get("doi"),
            "year": paper.get("year"),
            "score": score,
        })

    closest.sort(key=lambda item: item["score"], reverse=True)
    top_closest = closest[:5]
    corpus_score = _cosine(manuscript_terms, journal_terms) * 100.0
    comparison_scores = [item["score"] for item in top_closest[:3]]
    closest_score = sum(comparison_scores) / len(comparison_scores) if comparison_scores else 0.0
    overall = round((corpus_score * 0.55) + (closest_score * 0.45), 1)

    important_journal_terms = [term for term, _ in journal_terms.most_common(80)]
    matched = [term for term in important_journal_terms if term in manuscript_terms][:15]
    missing = [term for term in important_journal_terms if term not in manuscript_terms][:10]
    if overall >= 65:
        summary = "Strong lexical scope overlap with this saved journal sample."
    elif overall >= 35:
        summary = "Moderate lexical scope overlap with this saved journal sample."
    else:
        summary = "Limited lexical scope overlap with this saved journal sample."

    return {
        "overall_score": overall,
        "corpus_score": round(corpus_score, 1),
        "closest_papers_score": round(closest_score, 1),
        "matched_terms": matched,
        "potential_gaps": missing,
        "closest_papers": top_closest,
        "summary": summary,
        "provenance": f"derived:{FIT_VERSION}",
        "disclaimer": (
            "This is a transparent lexical scope comparison, not an editorial judgment "
            "or prediction of manuscript acceptance."
        ),
    }
