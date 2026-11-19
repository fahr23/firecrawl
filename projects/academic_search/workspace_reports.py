"""Deterministic review and export of the researcher's evidence and draft."""

from io import BytesIO
import re

from docx import Document
from docx.shared import Inches, Pt, RGBColor

from .config import Config
from .exporters import BibTeXExporter, RISExporter
from .models import Article, SearchResult


OUTLINES = {
    "original": ["Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusion"],
    "review": ["Abstract", "Review question", "Search and selection", "Evidence synthesis", "Limitations", "Conclusion"],
    "methods": ["Abstract", "Introduction", "Method", "Validation", "Limitations", "Conclusion"],
    "case_report": ["Abstract", "Background", "Case description", "Discussion", "Conclusion"],
}

INLINE_CITATION = re.compile(r"\[@([A-Za-z0-9_-]{1,32})\]")


def draft_reference_ids(draft):
    citations = draft.get("inline_citations", {})
    inline = (citations[key] for section in draft["sections"]
              for key in INLINE_CITATION.findall(section["text"]) if key in citations)
    claims = (key for claim in draft["claims"] for key in claim["references"])
    return list(dict.fromkeys([*inline, *claims]))


def inline_text(draft, text, numbers):
    citations = draft.get("inline_citations", {})

    def replace(match):
        number = numbers.get(citations.get(match[1]))
        return f"[{number}]" if number else "[Citation missing]"

    return INLINE_CITATION.sub(replace, text)


def _words(value):
    return len(re.findall(r"\b\w+(?:[-’']\w+)*\b", INLINE_CITATION.sub("", value)))


def review_manuscript(draft, reference_ids, target):
    requirements = draft["requirements"]
    sections = draft["sections"]
    abstract = next((section["text"] for section in sections if section["heading"].casefold() == "abstract"), "")
    body_count = sum(_words(s["text"]) for s in sections if s["heading"].casefold() != "abstract")
    abstract_count = _words(abstract)
    issues = []
    for section in sections:
        if not section["text"]:
            issues.append({"section": section["heading"], "message": "Section is still empty."})
        for key in dict.fromkeys(INLINE_CITATION.findall(section["text"])):
            if draft.get("inline_citations", {}).get(key) not in reference_ids:
                issues.append({"section": section["heading"], "message": f"Resolve the inline citation {key}."})
    for label, count, key in (("Main text", body_count, "word_limit"), ("Abstract", abstract_count, "abstract_limit")):
        limit = requirements.get(key)
        if limit and count > limit:
            issues.append({"section": label, "message": f"{count} words exceeds the recorded limit of {limit}."})
    for heading in requirements["abstract_headings"]:
        if not re.search(rf"(?im)^\s*#*\s*{re.escape(heading)}(?:\s*:|\s*$)", abstract):
            issues.append({"section": "Abstract", "message": f"Missing heading {heading}."})
    complete = {name.casefold() for name in requirements["declarations_done"]}
    for declaration in requirements["declarations_required"]:
        if declaration.casefold() not in complete:
            issues.append({"section": "Declarations", "message": f"{declaration} needs review."})
    if requirements["reporting_guideline"] and not requirements["reporting_checked"]:
        issues.append({"section": "Reporting", "message": f'Review against {requirements["reporting_guideline"]}.'})
    if target and not requirements["guideline_url"]:
        issues.append({"section": "Submission", "message": "Record the official author guidelines used for this review."})
    for claim in draft["claims"]:
        if not claim["references"] or any(key not in reference_ids for key in claim["references"]):
            issues.append({"section": claim["section"], "message": "Claim needs linked evidence.", "claim": claim["text"]})
        elif claim["review"] != "supported":
            issues.append({"section": claim["section"], "message": "Review how directly the cited papers support this claim.", "claim": claim["text"]})
    return {"word_count": body_count, "abstract_words": abstract_count, "issues": issues,
            "guideline_url": requirements["guideline_url"] or (target or {}).get("guidelines_url", ""),
            "method": "Checks use the recorded requirements and researcher evidence judgments."}


def _reference(paper):
    parts = [paper["title"], paper.get("authors"), paper.get("journal"), paper.get("year")]
    return " · ".join(str(part) for part in parts if part) + f' · {paper["url"]}'


def draft_export(draft, references, checks, target):
    lines = [f'# {draft["title"]}', "", f'Article type · {draft["article_type"].replace("_", " ")}']
    if target:
        lines += [f'Target venue · {target["title"]}', target["source_url"]]
    if checks["guideline_url"]:
        lines += ["Author guidelines · " + checks["guideline_url"]]
    numbers = {key: index for index, key in enumerate(references, 1)}
    for section in draft["sections"]:
        body = inline_text(draft, section["text"], numbers)
        lines += ["", f'## {section["heading"]}', "", body or "_Draft section pending._"]
    lines += ["", "## Claim and evidence log", ""]
    for claim in draft["claims"]:
        cited = ", ".join(f"[{numbers[key]}]" for key in claim["references"] if key in numbers) or "Evidence pending"
        facts = [claim["section"], claim["text"], cited, claim["locator"], claim["review"].replace("_", " ")]
        lines.append("- " + " · ".join(fact for fact in facts if fact))
    lines += ["", "## References", ""]
    for key, paper in references.items():
        lines.append(f'{numbers[key]}. {_reference(paper)}')
    lines += ["", "## Submission checklist", ""]
    for issue in checks["issues"]:
        issue_text = f'{issue["section"]} · {issue["message"]}'
        if issue.get("claim"):
            issue_text += f' · {issue["claim"]}'
        lines.append("- [ ] " + issue_text)
    if not checks["issues"]:
        lines.append("- [x] Recorded checks reviewed")
    return "\n".join(lines) + "\n"


def word_export(draft, references):
    document = Document()
    document.core_properties.title = draft["title"]
    for section in document.sections:
        section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Inches(1)
    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing = 1.5
    for name in ("Title", "Heading 1"):
        style = document.styles[name]
        style.font.name = "Times New Roman"
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.size = Pt(18 if name == "Title" else 14)
        borders = style.element.xpath("./w:pPr/w:pBdr")
        for border in borders:
            border.getparent().remove(border)
    document.add_heading(draft["title"], 0)
    numbers = {key: index for index, key in enumerate(references, 1)}
    for section in draft["sections"]:
        if section["text"].strip():
            document.add_heading(section["heading"], 1)
            for paragraph in re.split(r"\n\s*\n", inline_text(draft, section["text"].strip(), numbers)):
                document.add_paragraph(paragraph)
    if references:
        document.add_heading("References", 1)
        for key, paper in references.items():
            paragraph = document.add_paragraph(f"{numbers[key]}. {_reference(paper)}")
            paragraph.paragraph_format.left_indent = Inches(0.25)
            paragraph.paragraph_format.first_line_indent = Inches(-0.25)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def reference_export(papers, style):
    fields = {"title", "authors", "journal", "year", "doi", "url", "source", "keywords"}
    articles = [Article(**{key: value for key, value in paper.items() if key in fields}) for paper in papers]
    exporter = BibTeXExporter(Config()) if style == "bibtex" else RISExporter(Config())
    return exporter.export_to_string(SearchResult(query="Project references", articles=articles))


def dossier_export(profile, rules, activities, reading):
    route = "Doçentlik" if profile["route"] == "docentlik" else "Professorship"
    lines = [f"# {route} dossier", "", f'{profile["field"]} · {profile["period"]}', profile["criteria_url"]]
    if profile["institution"]:
        lines.append(f'{profile["institution"]} · {profile["position"]}')
    lines += ["", "## Criteria and evidence", ""]
    for rule in rules:
        lines += [f'### {rule["title"]}', "", f'{rule["clause"]} · {rule["official_url"]}',
                  f'Researcher status · {rule["status"].replace("_", " ")}']
        if rule["notes"]:
            lines.append(rule["notes"])
        for key in rule["activity_ids"]:
            activity = activities[key]
            paper = activity.get("paper") or reading.get(activity["reading_id"], {})
            evidence = activity["evidence_url"] or paper.get("url") or "Evidence link pending"
            details = [activity["kind"], activity["publication_type"], activity["author_role"], activity["publication_status"]]
            if activity["index_name"]:
                details.extend([f'{activity["index_name"]} ({activity["index_year"]})', activity["index_url"]])
            lines.append("- " + " · ".join(filter(None, [
                activity["title"], activity["evidence_date"] or "Date pending", evidence, *details, activity["notes"],
            ])))
        if not rule["activity_ids"]:
            lines.append("- [ ] Activity evidence pending")
        lines.append("")
    linked = {key for rule in rules for key in rule["activity_ids"]}
    unlinked = [activity for key, activity in activities.items() if key not in linked]
    if unlinked:
        lines += ["## Activities awaiting a criterion", ""]
        lines += [f'- {activity["title"]} · {activity["kind"]}' for activity in unlinked]
    return "\n".join(lines) + "\n"
