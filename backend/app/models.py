from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "low", "medium", "high", "critical"]
# "community" findings (the scam database) are added by the frontend before a report is saved.
Category = Literal["content", "contact", "company", "document", "country", "ai", "community"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
# An offer letter, or a short job ad / SMS / chat message, which is checked with gentler rules.
Kind = Literal["letter", "message", "visa"]


class Finding(BaseModel):
    id: str
    title: str
    detail: str
    severity: Severity
    category: Category
    # Positive points raise the risk score, negative points lower it (trust signals).
    points: int


class Entities(BaseModel):
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    money: list[str] = Field(default_factory=list)
    fee_mentions: list[str] = Field(default_factory=list)
    payment_accounts: list[str] = Field(default_factory=list)
    company_name: str | None = None
    job_title: str | None = None
    agency_name: str | None = None
    agency_licence: str | None = None
    company_registration_number: str | None = None
    agency_emails: list[str] = Field(default_factory=list)


class SourceComparison(BaseModel):
    field: str
    letter_value: str
    source_value: str
    status: Literal["MATCHED", "MISMATCH", "UNVERIFIED"]
    detail: str


class SourceCheck(BaseModel):
    """Evidence from a named source; a record match never authenticates the offer itself."""

    check: Literal["employer", "agency", "website", "discovery", "email", "sponsorship", "sponsor_registry", "care_provider"]
    status: Literal["MATCHED", "MISMATCH", "NOT_FOUND", "UNAVAILABLE", "UNVERIFIED", "NOT_APPLICABLE"]
    subject: str
    source_name: str
    source_url: str
    checked_at: str
    detail: str
    record_name: str | None = None
    record_id: str | None = None
    record_status: str | None = None
    source_updated_at: str | None = None
    checked_pages: list[str] = Field(default_factory=list)
    comparisons: list[SourceComparison] = Field(default_factory=list)


class Fingerprint(BaseModel):
    """MinHash of the letter's wording, used to recognise reused scam templates (see fingerprint.py)."""

    signature: list[int]
    bands: list[str]


class AIVerdict(BaseModel):
    """Structured output requested from Claude."""

    risk_level: RiskLevel
    confidence: int = Field(ge=0, le=100, description="Self-reported model confidence, not calibrated detection accuracy")
    summary: str = Field(description="2-3 plain-language sentences for a job seeker")
    red_flags: list[str]
    trust_signals: list[str]
    company_name: str | None
    job_title: str | None
    country: str | None = Field(description="Country where the job is located")


ScamStatus = Literal["UNREVIEWED", "SUSPECTED_SCAM", "REPORTED_SCAM", "CONFIRMED_SCAM", "CLEARED"]


class MemoryMatch(BaseModel):
    status: Literal["CONFIRMED_SCAM", "REPORTED_SCAM", "SUSPECTED_SCAM"]
    matching_details: list[str] = Field(default_factory=list, max_length=10)
    template_similarity: float | None = Field(default=None, ge=0, le=1)
    case_count: int = Field(ge=1)
    contact_and_template: bool = False


class OfferConfirmation(BaseModel):
    status: Literal["CONFIRMED", "DENIED", "REVOKED"]
    employer_contact: str
    source_url: str
    offer_reference: str
    job_title: str
    confirmed_at: str
    recorded_at: str
    note: str


class VerificationItem(BaseModel):
    id: str
    label: str
    status: Literal["SUPPORTED", "CONFLICT", "UNVERIFIED", "NOT_APPLICABLE"]
    detail: str


class VerificationSummary(BaseModel):
    level: Literal["LIMITED", "PARTIAL", "COMPLETE"]
    resolved: int
    required: int
    items: list[VerificationItem]


class AnalysisReport(BaseModel):
    file_name: str
    kind: Kind
    risk_level: RiskLevel
    score: int
    country: str | None
    country_name: str | None
    company_name: str | None
    job_title: str | None
    summary: str
    findings: list[Finding]
    advice: list[str]
    verify_links: list[dict[str, str]]
    entities: Entities
    text_excerpt: str
    extraction_method: str
    ai_used: bool
    warnings: list[str]
    # Checks that could not run on this letter, so users aren't told more was checked than really was.
    checks_not_run: list[str]
    fingerprint: Fingerprint | None
    source_checks: list[SourceCheck] = Field(default_factory=list)
    scam_status: ScamStatus | None = None
    review_note: str | None = None
    reviewed_at: str | None = None
    memory_matches: list[MemoryMatch] = Field(default_factory=list, max_length=3)
    offer_confirmation: OfferConfirmation | None = None
    verification: VerificationSummary | None = None
    visa: "VisaAssessment | None" = None


class VisaDetails(BaseModel):
    model_config = {"extra": "forbid"}
    holder_name: str | None = Field(default=None, max_length=200)
    passport_number: str | None = Field(default=None, max_length=50)
    visa_number: str | None = Field(default=None, max_length=50)
    nationality: str | None = Field(default=None, max_length=100)
    sponsor: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    visa_type: str | None = Field(default=None, max_length=100)
    issue_date: str | None = Field(default=None, max_length=60)
    expiry_date: str | None = Field(default=None, max_length=60)


class VisaReview(BaseModel):
    model_config = {"extra": "forbid"}
    reviewed: Literal[True]
    details: VisaDetails
    offer_details: VisaDetails | None = None


class VisaPreview(BaseModel):
    country: Literal["QA", "KW"]
    detected_country: str | None
    details: VisaDetails
    offer_details: VisaDetails | None
    warnings: list[str]


class VisaComparison(BaseModel):
    field: str
    visa_value: str | None
    offer_value: str | None
    status: Literal["MATCHED", "MISMATCH", "UNVERIFIED"]
    detail: str


class VisaGuidance(BaseModel):
    source_name: str
    source_url: str
    steps: list[str]


class VisaAssessment(BaseModel):
    details: VisaDetails
    extracted_details: VisaDetails
    offer_details: VisaDetails | None = None
    extracted_offer_details: VisaDetails | None = None
    offer_file_name: str | None = None
    detected_country: str | None = None
    corrections: list[str] = Field(default_factory=list)
    comparisons: list[VisaComparison] = Field(default_factory=list)
    official_status: Literal["NOT_CHECKED"] = "NOT_CHECKED"
    guidance: VisaGuidance


AnalysisReport.model_rebuild()
