"""Recognize UK CoS validity fields without claiming access to UKVI's private certificate records."""

import re
from datetime import date, datetime, timezone

from .models import Finding, SourceCheck, SourceComparison

SOURCE = "https://www.gov.uk/uk-visa-sponsorship-employers/certificates-of-sponsorship"


def sponsor_name(text: str, fallback: str | None = None) -> str | None:
    match = re.search(r"^\s*sponsor name[ \t]*:[ \t]*([^\r\n]*)", text, re.I | re.M)
    if match:
        value = match.group(1).strip(" .\t")
        if 2 <= len(value) <= 160 and not re.search(r"certificate|status|licen[cs]e|number|^assigned$", value, re.I):
            return value
    return fallback


def sponsorship_route(text: str) -> str | None:
    for pattern, route in [(r"skilled worker|health and care worker|tier 2\s*\(general\)", "Skilled Worker"),
                           (r"creative worker", "Creative Worker"), (r"seasonal worker", "Seasonal Worker"),
                           (r"charity worker", "Charity Worker"), (r"religious worker", "Religious Worker")]:
        if re.search(pattern, text, re.I):
            return route
    return None


def sponsorship_checks(text: str) -> tuple[list[SourceCheck], list[Finding], list[str]]:
    title = re.search(r"^\s*certificate\s+of\s+sponsorship(?:\s+details)?\s*$", text, re.I | re.M)
    fields = [bool(re.search(pattern, text, re.I)) for pattern in
              [r"sponsor licen[cs]e number\s*:", r"certificate number\s*:", r"sponsor name\s*:", r"expiry date\s*\(\s*use\s*by\s*\)\s*:"]]
    if not ((title and any(fields)) or sum(fields) >= 2):
        return [], [], []
    evidence = SourceCheck(check="sponsorship", status="UNVERIFIED", subject="UK Certificate of Sponsorship",
                           source_name="GOV.UK CoS guidance and supplied document", source_url=SOURCE,
                           checked_at=datetime.now(timezone.utc).isoformat(),
                           detail="Recognized as a UK sponsorship document. The individual CoS number and its private UKVI record have not been authenticated.")
    match = re.search(r"(?:expiry date\s*\(\s*use\s*by\s*\)|use[- ]by(?: date)?)\s*:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})", text, re.I)
    expiry = None
    if match:
        for pattern in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
            try:
                expiry = datetime.strptime(match.group(1), pattern).date()
                break
            except ValueError:
                pass
    findings, not_run = [], ["Individual UKVI sponsorship record: cannot be authenticated from a PDF or public company register. Confirm through the sponsor and UKVI."]
    expired = bool(expiry and expiry < date.today())
    evidence.comparisons.append(SourceComparison(field="Certificate use-by date", letter_value=expiry.isoformat() if expiry else "Could not read the use-by date reliably",
                                                 source_value="Today's date: " + date.today().isoformat(), status="MISMATCH" if expired else "UNVERIFIED",
                                                 detail="The use-by date has passed. This document cannot be used for a new visa application today. A historical certificate already used for an earlier application may still be genuine." if expired
                                                 else "A future date or an unreadable date does not authenticate the certificate."))
    if expired:
        evidence.status = "MISMATCH"
        evidence.detail += " The stated use-by date has passed; do not treat this as a current, usable CoS."
        findings.append(Finding(id="cos_expired", title="Sponsorship certificate's use-by date has passed",
                                detail=f"This document says use by {expiry:%d %B %Y}. It cannot support a new visa application today. This does not establish whether it was genuine or used in an earlier application.",
                                severity="high", category="document", points=35))
    if expiry is None:
        not_run.append("CoS use-by date: the expiry field could not be read reliably. Check the original record with the sponsor.")
    return [evidence], findings, not_run
