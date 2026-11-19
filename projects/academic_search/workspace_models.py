"""Typed input for the publishing tools stored in each research project."""

from datetime import date
import re
from typing import Dict, List, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .submission_sources import public_url


class WorkspaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def validate_link(cls, value, info):
        if info.field_name.endswith("_url") and info.field_name != "paper_url" and value and not public_url(value):
            raise ValueError("Use a valid HTTPS link.")
        return value


class DiscoveryRequest(WorkspaceModel):
    query: str = Field(min_length=2, max_length=300)
    field: str = Field(default="", pattern=r"^(?:[0-9]{1,12})?$")
    include_preprints: bool = False


class ReadingSource(WorkspaceModel):
    kind: Literal["search", "search-page", "journal", "discovery", "discovery-papers", "library"]
    run_id: str = Field(min_length=1, max_length=90)
    paper_url: str = Field(min_length=1, max_length=4000)


class ReadingNotes(WorkspaceModel):
    status: Literal["saved", "reading", "included", "excluded"] = "saved"
    design: str = Field(default="", max_length=500)
    population: str = Field(default="", max_length=500)
    dataset: str = Field(default="", max_length=800)
    method: str = Field(default="", max_length=3000)
    findings: str = Field(default="", max_length=3000)
    limitations: str = Field(default="", max_length=3000)
    locator: str = Field(default="", max_length=400)
    conflicts: List[str] = Field(default_factory=list, max_length=20)


class ResearchIdea(WorkspaceModel):
    question: str = Field(min_length=2, max_length=1000)
    rationale: str = Field(default="", max_length=3500)
    data_source: str = Field(default="", max_length=1000)
    method: str = Field(default="", max_length=2000)
    evidence: List[str] = Field(default_factory=list, max_length=30)
    counterevidence: List[str] = Field(default_factory=list, max_length=30)
    status: Literal["candidate", "reviewed", "selected"] = "candidate"
    data_access: Literal["to_check", "confirmed", "blocked"] = "to_check"
    constraints: str = Field(default="", max_length=2000)
    next_step: str = Field(default="", max_length=750)
    starting_point: str = Field(default="", max_length=1000)


class SubmissionOpportunity(WorkspaceModel):
    title: str = Field(min_length=2, max_length=280)
    venue: str = Field(default="", max_length=280)
    kind: Literal["regular", "special_issue", "conference", "workshop"] = "regular"
    source_url: str = Field(min_length=10, max_length=1500)
    submission_url: str = Field(default="", max_length=1500)
    guidelines_url: str = Field(default="", max_length=1500)
    scope: str = Field(default="", max_length=4000)
    article_types: str = Field(default="", max_length=1000)
    issn: str = Field(default="", pattern=r"^(?:\d{4}-\d{3}[0-9Xx])?$")
    status: Literal["unverified", "open", "upcoming", "closed"] = "unverified"
    evidence: str = Field(default="", max_length=1200)
    opens: Optional[date] = None
    deadline: Optional[date] = None
    deadline_time: str = Field(default="", pattern=r"^(?:(?:[01]\d|2[0-3]):[0-5]\d)?$")
    timezone: str = Field(default="", max_length=80)
    fees: str = Field(default="", max_length=500)
    fees_url: str = Field(default="", max_length=1500)
    index_name: str = Field(default="", max_length=250)
    index_year: Optional[int] = Field(default=None, ge=1800, le=2200)
    index_url: str = Field(default="", max_length=1500)
    verify_from_source: bool = False

    @model_validator(mode="after")
    def dates_and_verification(self):
        if self.opens and self.deadline and self.opens > self.deadline:
            raise ValueError("The opening date must be on or before the deadline.")
        if self.deadline_time and not (self.deadline and self.timezone):
            raise ValueError("Enter both a date and time zone for a deadline time.")
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except (ValueError, ZoneInfoNotFoundError):
                raise ValueError("Use an IANA time zone, such as Europe/Istanbul.") from None
        if self.status != "unverified" and not (self.verify_from_source or self.evidence):
            raise ValueError("Record the wording that confirms the status on the official page.")
        if self.index_name and not (self.index_year and self.index_url):
            raise ValueError("Provide the index year and official source for an index claim.")
        return self


class DraftSection(WorkspaceModel):
    heading: str = Field(min_length=1, max_length=100)
    text: str = Field(default="", max_length=30000)


class DraftClaim(WorkspaceModel):
    section: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1800)
    references: List[str] = Field(default_factory=list, max_length=20)
    locator: str = Field(default="", max_length=500)
    review: Literal["unreviewed", "supported", "mixed", "needs_evidence"] = "unreviewed"


class DraftRequirements(WorkspaceModel):
    guideline_url: str = Field(default="", max_length=1500)
    word_limit: Optional[int] = Field(default=None, ge=1, le=100000)
    abstract_limit: Optional[int] = Field(default=None, ge=1, le=10000)
    abstract_headings: List[str] = Field(default_factory=list, max_length=12)
    declarations_required: List[str] = Field(default_factory=list, max_length=20)
    declarations_done: List[str] = Field(default_factory=list, max_length=20)
    reporting_guideline: str = Field(default="", max_length=500)
    reporting_url: str = Field(default="", max_length=1500)
    reporting_checked: bool = False


class Manuscript(WorkspaceModel):
    title: str = Field(min_length=2, max_length=500)
    article_type: Literal["original", "review", "methods", "case_report"] = "original"
    idea_id: str = Field(default="", max_length=90)
    submission_id: str = Field(default="", max_length=90)
    sections: List[DraftSection] = Field(default_factory=list, max_length=16)
    claims: List[DraftClaim] = Field(default_factory=list, max_length=100)
    requirements: DraftRequirements = Field(default_factory=DraftRequirements)
    stage: Literal["outline", "drafting", "review", "ready", "submitted", "published"] = "outline"
    next_action: str = Field(default="", max_length=350)
    action_due: Optional[date] = None
    inline_citations: Dict[str, str] = Field(default_factory=dict, max_length=100)

    @field_validator("inline_citations")
    @classmethod
    def citation_keys(cls, value):
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", key)
               or not re.fullmatch(r"[A-Za-z0-9_-]{1,90}", reference) for key, reference in value.items()):
            raise ValueError("Inline citations require a named key and a saved reading reference.")
        return value


class DossierProfile(WorkspaceModel):
    route: Literal["docentlik", "professorship"]
    field: str = Field(min_length=1, max_length=250)
    period: str = Field(min_length=1, max_length=120)
    institution: str = Field(default="", max_length=300)
    position: str = Field(default="", max_length=300)
    criteria_url: str = Field(min_length=10, max_length=1500)

    @model_validator(mode="after")
    def require_target(self):
        if self.route == "professorship" and not (self.institution and self.position):
            raise ValueError("Enter the institution and position for a professorship dossier.")
        return self


class DossierActivity(WorkspaceModel):
    title: str = Field(min_length=1, max_length=500)
    kind: Literal["publication", "teaching", "supervision", "project", "service", "other"]
    evidence_url: str = Field(default="", max_length=1500)
    evidence_date: Optional[date] = None
    reading_id: str = Field(default="", max_length=90)
    publication_type: str = Field(default="", max_length=120)
    author_role: str = Field(default="", max_length=200)
    publication_status: Literal["", "submitted", "accepted", "published", "indexed"] = ""
    index_name: str = Field(default="", max_length=200)
    index_year: Optional[int] = Field(default=None, ge=1800, le=2200)
    index_url: str = Field(default="", max_length=1500)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def require_index_source(self):
        if self.index_name and not (self.index_year and self.index_url):
            raise ValueError("Provide the index year and official source for an index claim.")
        return self


class DossierRule(WorkspaceModel):
    title: str = Field(min_length=1, max_length=500)
    clause: str = Field(min_length=1, max_length=500)
    official_url: str = Field(min_length=10, max_length=1500)
    activity_ids: List[str] = Field(default_factory=list, max_length=50)
    portfolio_activity_ids: List[str] = Field(default_factory=list, max_length=50)
    status: Literal["needs_evidence", "in_review", "reviewed"] = "needs_evidence"
    notes: str = Field(default="", max_length=3000)


class SubmissionTracking(WorkspaceModel):
    title: str = Field(min_length=2, max_length=280)
    manuscript_id: str = Field(default="", max_length=90)
    opportunity_id: str = Field(default="", max_length=90)
    status: Literal["planned", "submitted", "in_review", "revision_requested", "resubmitted",
                    "accepted", "rejected", "withdrawn", "published"] = "planned"
    submitted_on: Optional[date] = None
    revision_due: Optional[date] = None
    reference: str = Field(default="", max_length=350)
    reviewer_comments: str = Field(default="", max_length=16000)
    notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def check_dates(self):
        if self.submitted_on and self.revision_due and self.revision_due < self.submitted_on:
            raise ValueError("The revision deadline must be on or after the submission date.")
        return self
