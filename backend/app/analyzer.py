"""Runs every check on a letter and combines the results into one risk report."""

import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from . import ai
from .agencies import agency_check
from .checks import domain_age_findings
from .entities import domain_of, extract_entities
from .employers import employer_check
from .extract import extract
from .fingerprint import fingerprint
from .forensics import pdf_findings
from .models import AnalysisReport, Finding, Kind, SourceCheck
from .rules import COUNTRIES, HOME_COUNTRY_LINKS, detect_country, run_general_rules
from .websites import website_checks
from .verification import verification_summary
from .sponsorship import sponsor_name, sponsorship_checks, sponsorship_route
from .uk_sponsors import sponsor_registry_check

HIGH_THRESHOLD = 60
MEDIUM_THRESHOLD = 30
AI_POINTS = {"HIGH": 15, "MEDIUM": 5, "LOW": -10}

BASE_ADVICE = [
    "Never pay any money to get a job, visa, work permit, medical or ticket - genuine employers pay these.",
    "Find the company's official website yourself (not from the letter or message) and contact their HR to confirm the offer.",
    "Check that any recruitment agency is licensed by your government's labour authority.",
    "Don't send your passport, ID or bank details until you've confirmed the employer is real.",
]


def _level(score: int) -> str:
    if score >= HIGH_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def _rule_summary(level: str, findings: list[Finding], has_text: bool, noun: str) -> str:
    if not has_text:
        return (f"We could not read any text from this file, so the {noun} has NOT been checked. "
                "Upload a clearer photo or the original PDF.")
    serious = [f.title.lower() for f in findings if f.severity in ("critical", "high")]
    if level == "HIGH":
        return f"This {noun} shows strong signs of a job scam" + (f": {', '.join(serious[:3])}." if serious else ".")
    if level == "MEDIUM":
        return f"Some details in this {noun} are suspicious. Verify the employer directly before you go any further."
    return "No major scam signs were found, but always confirm the offer with the company's official HR before acting."


def analyze_letter(
    data: bytes, filename: str, country_override: str | None = None, kind: Kind = "letter"
) -> AnalysisReport:
    """`kind` is "letter" for an offer letter, or "message" for a job ad, SMS or chat message (text or screenshot)."""
    noun = "message" if kind == "message" else "letter"
    extraction = extract(data, filename)
    text = extraction.text
    warnings = list(extraction.warnings)
    not_run: list[str] = list(extraction.checks_not_run)

    entities = extract_entities(text, kind)
    sponsorship_evidence, sponsorship_findings, sponsorship_not_run = sponsorship_checks(text)
    if sponsorship_evidence:
        entities.company_name = sponsor_name(text, entities.company_name)
    entities.emails = list(dict.fromkeys(extraction.sender_emails + entities.emails))
    entities.domains = list(dict.fromkeys(entities.domains + [domain_of(email) for email in extraction.sender_emails]))
    country = (country_override or "").upper() or ("GB" if sponsorship_evidence else detect_country(text, entities.phones))
    if country and country not in COUNTRIES:
        country = None

    findings = run_general_rules(text, entities, country, kind) if text.strip() else []
    findings += extraction.findings
    if extraction.pdf is not None:
        findings += pdf_findings(extraction.pdf, extraction.pdf_data or data)
    elif kind == "letter":  # a pasted ad or chat message has no document to inspect
        not_run.append("File forensics: only PDF files can be checked for editing (not photos or text).")
    domain_findings, domain_not_run = domain_age_findings(entities.domains)
    findings += domain_findings
    not_run += domain_not_run
    agency_evidence, agency_found, agency_not_run = agency_check(entities, text)
    findings += agency_found
    not_run += agency_not_run
    employer_evidence, employer_findings = employer_check(entities, country)
    findings += employer_findings
    if employer_evidence.status in {"UNVERIFIED", "UNAVAILABLE", "NOT_FOUND"}:
        not_run.append("Employer company-register lookup: " + employer_evidence.detail)
    website_evidence, website_findings, website_not_run = website_checks(entities, country, agency_evidence)
    findings += website_findings
    not_run += website_not_run
    if sponsorship_evidence:
        # A government CoS printout is not an HR letter and need not publish an HR email or full contract.
        findings = [finding for finding in findings if finding.id not in {"no_email", "missing_terms", "generic_greeting"}]
        registry, registry_findings, registry_not_run = sponsor_registry_check(entities.company_name, sponsorship_route(text))
        sponsorship_evidence.append(registry)
        findings += registry_findings
        not_run += registry_not_run
        if re.search(r"care workers?|home carers?|support worker|\b61[34]5\b", text, re.I):
            sponsorship_evidence.append(SourceCheck(check="care_provider", status="UNVERIFIED", subject=entities.company_name or "Care provider",
                source_name="Care Quality Commission (England)", source_url="https://www.cqc.org.uk/search/all?" + urlencode({"query": entities.company_name or ""}),
                checked_at=datetime.now(timezone.utc).isoformat(), detail="Current CQC provider registration has not been automatically established. A company or sponsor-register match does not establish care-provider permission. Check the official provider record, its legal name, locations and any archive date. CQC covers England."))
            not_run.append("England care-provider registration: no independently matched CQC provider record was retrieved; check the official source.")
    findings += sponsorship_findings
    not_run += sponsorship_not_run
    source_checks = [employer_evidence, agency_evidence, *website_evidence, *extraction.source_checks, *sponsorship_evidence]

    if not text.strip():
        warnings.append("No text could be read from this file, so the content checks could not run.")
        not_run.insert(0, "Content checks (fees, contacts, pressure wording): no text could be read from the file.")

    verdict, ai_warning = ai.analyze(text, entities, findings, COUNTRIES[country].name if country else None, kind,
                                    source_checks=source_checks) if text.strip() else (None, None)
    if ai_warning:
        warnings.append(ai_warning)
    if verdict is None and text.strip():
        not_run.append("AI second opinion: " + (f"not available for this {noun}." if ai.is_enabled() else "not set up on this server."))
    if verdict:
        flags = "; ".join(verdict.red_flags[:4]) or "no specific red flags"
        findings.append(Finding(
            id="ai_verdict", title=f"AI assessment: {verdict.risk_level.lower()} risk",
            detail=f"{verdict.summary} Key points: {flags}.", severity={"HIGH": "high", "MEDIUM": "medium", "LOW": "info"}[verdict.risk_level],
            category="ai", points=AI_POINTS[verdict.risk_level],
        ))
        if not country and verdict.country:
            name = verdict.country.lower()
            country = next((c.code for c in COUNTRIES.values() if c.name.lower() == name or name in c.keywords), None)

    score = max(0, min(100, sum(f.points for f in findings)))
    if any(f.severity == "critical" for f in findings):
        score = max(score, HIGH_THRESHOLD)
    identity_mismatch = any(check.status == "MISMATCH" for check in source_checks)
    if identity_mismatch:
        score = max(score, MEDIUM_THRESHOLD)
    sponsorship_expired = any(finding.id == "cos_expired" for finding in findings)
    sponsor_warning = any(finding.id.startswith("sponsor_registry_") for finding in findings)
    if sponsor_warning:
        score = max(score, MEDIUM_THRESHOLD)
    if sponsorship_expired:
        score = max(score, HIGH_THRESHOLD)
    level = _level(score)

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: (severity_rank[f.severity], -f.points))

    advice = list(BASE_ADVICE)
    verify_links = []
    if country:
        c = COUNTRIES[country]
        advice.insert(1, c.fee_rule)
        verify_links += c.verify_links
    verify_links += HOME_COUNTRY_LINKS

    report = AnalysisReport(
        file_name=filename,
        risk_level=level,
        score=score,
        country=country,
        country_name=COUNTRIES[country].name if country else None,
        company_name=entities.company_name or (verdict.company_name if verdict else None),
        job_title=(verdict.job_title if verdict and verdict.job_title else entities.job_title),
        summary=("High risk for a new visa application: this sponsorship document's use-by date has passed. "
                 + ("The named sponsor's current name or visa-route entry could not be matched reliably. " if sponsor_warning else "")
                 + "Do not pay or rely on it as current sponsorship. The PDF's original historical authenticity remains unverified.") if sponsorship_expired
                else ("Current sponsorship permission needs checking against the Home Office register. The individual CoS and sender remain unverified; review the recorded findings before relying on this document.") if sponsor_warning
                else ("Document or identity details differ from the checked evidence, or a validity requirement was not met. Review the evidence and contact the registered employer or agency independently. "
                 + _rule_summary(level, findings, bool(text.strip()), noun)) if identity_mismatch else verdict.summary if verdict else _rule_summary(level, findings, bool(text.strip()), noun),
        kind=kind,
        findings=findings,
        advice=advice,
        verify_links=verify_links,
        entities=entities,
        text_excerpt=text[:3000],
        extraction_method=extraction.method,
        ai_used=verdict is not None,
        warnings=warnings,
        checks_not_run=not_run,
        fingerprint=fingerprint(text),
        source_checks=source_checks,
    )
    report.verification = verification_summary(report)
    return report
