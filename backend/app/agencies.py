"""Compare agencies with the official NEA public API, with a dated imported snapshot as fallback.

Business registration, licence payment, licence approval and sender identity are distinct claims.
"""

import csv
import io
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from .entities import EMAIL_RE, GENERIC_WORDS, domain_of
from .models import Entities, Finding, SourceCheck, SourceComparison
from .nea_dataset import SOURCE_URL, dataset_metadata
from .nea_live import API_URL, PUBLIC_REGISTER_URL, live_dataset
from .public_web import WebUnavailable

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "nea_agencies.csv"
NAME_MATCH_RATIO = 0.9
LEGAL_SUFFIXES = {"the", "ltd", "limited", "co", "company", "plc", "llc", "inc", "kenya"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y")
INACTIVE_RE = re.compile(r"revoked|suspended|cancel+ed|deregistered|expired|inactive|withdrawn", re.I)
KENYA_HINT_RE = re.compile(r"nairobi|mombasa|kisumu|nakuru|eldoret|thika|kenya|\.co\.ke\b|\.ke\b", re.I)
KENYA_PHONE_RE = re.compile(r"^(?:\+|00)?254|^0[17]\d")


@dataclass(frozen=True)
class Agency:
    name: str
    licence: str
    expiry: date | None
    status: str
    key: str  # normalised name used for matching
    email: str = ""
    website: str = ""
    business_registration_number: str = ""
    licence_type: str = ""
    source_url: str = ""


_cache: dict = {"file": None, "agencies": []}


def _norm_name(name: str) -> str:
    return " ".join(t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in LEGAL_SUFFIXES)


def _norm_licence(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _status_label(status: str) -> str:
    return {"LICENSE_PAID": "Licence fee paid (approval unverified)", "LICENSE_EXPIRED": "Licence expired",
            "LICENSE_DEREGISTERED": "Deregistered"}.get(status, status)


def _parse_date(value: str) -> date | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _column(headers: list[str], *words: str) -> str | None:
    return next((h for h in headers if any(w in h.lower() for w in words)), None)


def load_agencies(*, content: bytes | None = None) -> list[Agency]:
    path = Path(os.getenv("NEA_AGENCIES_CSV") or DEFAULT_CSV)
    file = None
    if content is None:
        try:
            file = (str(path), path.stat().st_mtime_ns)
            if _cache["file"] == file:
                return _cache["agencies"]
            content = path.read_bytes()
        except OSError:
            return []

    with io.StringIO(content.decode("utf-8-sig"), newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        name_col = _column(headers, "name", "agency")
        licence_col = _column(headers, "licen", "accredit", "cert", "registration")
        expiry_col = _column(headers, "expir", "valid")
        status_col = _column(headers, "status")
        email_col = _column(headers, "e-mail", "email")
        website_col = _column(headers, "website")
        agencies = [
            Agency(
                name=row[name_col].strip(),
                licence=(row.get(licence_col) or "").strip() if licence_col else "",
                expiry=_parse_date(row.get(expiry_col) or "") if expiry_col else None,
                status=(row.get(status_col) or "").strip() if status_col else "",
                key=_norm_name(row[name_col]),
                email=(row.get(email_col) or "").strip() if email_col else "",
                website=(row.get(website_col) or "").strip() if website_col else "",
                business_registration_number=(row.get("business_registration_number") or "").strip(),
                licence_type=(row.get("licence_type") or "").strip(),
                source_url=(row.get("record_source_url") or "").strip(),
            )
            for row in reader
            if name_col and (row.get(name_col) or "").strip()
        ]
    if file is not None:
        _cache.update(file=file, agencies=agencies)
    return agencies


def agency_check(entities: Entities, text: str) -> tuple[SourceCheck, list[Finding], list[str]]:
    """Use live NEA records when possible, falling back to a dated, intact, recent snapshot."""
    result = SourceCheck(
        check="agency", status="UNVERIFIED", subject=entities.agency_name or entities.agency_licence or "Recruitment agency",
        source_name="NEA public employment-agency register", source_url=SOURCE_URL,
        checked_at=datetime.now(timezone.utc).isoformat(), detail="",
    )
    path = Path(os.getenv("NEA_AGENCIES_CSV") or DEFAULT_CSV)
    try:
        content = path.read_bytes()
        agencies = load_agencies(content=content)
    except (OSError, UnicodeError, csv.Error, ValueError, KeyError, TypeError):
        agencies = []
    metadata = dataset_metadata(path, content=content) if agencies else {}
    live_failed = False
    if (entities.agency_name or entities.agency_licence or entities.company_name) and os.getenv("ENABLE_NEA_LIVE_LOOKUP", "true").lower() == "true":
        try:
            live_content, retrieved_at = live_dataset()
            agencies = load_agencies(content=live_content)
            metadata = {"fresh": True, "retrieved_at": retrieved_at, "source_name": "NEA live employment-agency register"}
            result.source_url = PUBLIC_REGISTER_URL
            result.checked_pages = [agencies[0].source_url or API_URL] if agencies else []
        except WebUnavailable:
            live_failed = True
    if not entities.agency_name and not entities.agency_licence and not agencies:
        result.status = "NOT_APPLICABLE"
        result.detail = "No recruitment agency was identified in this document."
        return result, [], []
    if not agencies:
        result.status = "UNAVAILABLE"
        result.detail = "The live NEA register was unavailable and no usable snapshot was loaded. No agency licence was verified." if live_failed else "The NEA agency list has not been loaded or could not be read. No agency licence was verified."
        return result, [], [result.detail]
    result.source_updated_at = metadata.get("retrieved_at")
    if not metadata.get("fresh"):
        result.detail = "The NEA snapshot is undated, changed since import, or older than 30 days. Refresh it before relying on a licence match."
        return result, [], [result.detail]
    result.source_name = metadata.get("source_name", result.source_name)
    names = [n for n in (entities.agency_name, entities.company_name) if n]
    exact_candidates = [a for a in agencies if any(_norm_name(name) == a.key for name in names)]
    licence_candidates = [a for a in agencies if entities.agency_licence and a.licence and _norm_licence(a.licence) == _norm_licence(entities.agency_licence)]
    if len(exact_candidates) > 1 and len(licence_candidates) != 1:
        result.detail = "Multiple NEA records share the agency name. A unique licence was not identified, so no current licence or adverse status was attributed to this sender. Confirm the legal entity with NEA."
        return result, [], [result.detail]
    match, matched_by, name_used = find_agency(names, entities.agency_licence, agencies)
    if not entities.agency_name and not entities.agency_licence and not match:
        result.status = "NOT_APPLICABLE"
        result.detail = "No recruitment agency was identified in this document."
        return result, [], []
    if not match:
        result.status = "NOT_FOUND"
        result.detail = "No matching agency was found in the NEA records read. The name may be spelled differently, so search the official register and confirm with NEA."
        # Only reached with live or fresh snapshot data: an agency the letter names but NEA does not list is a scam signal.
        findings, _ = agency_findings(entities, text, agencies=agencies)
        return result, findings, []
    result.subject = entities.agency_name or match.name
    result.record_name, result.record_id, result.record_status = match.name, match.licence or match.business_registration_number, _status_label(match.status)
    findings, not_run = agency_findings(entities, text, agencies=agencies)
    claimed = entities.agency_name or name_used
    exact_name = bool(claimed and _norm_name(claimed) == match.key)
    if not exact_name and not (matched_by == "licence" and any(f.id == "agency_licence_other_agency" for f in findings)):
        result.status = "UNVERIFIED"
        result.detail = "A licence or similar agency name was found, but an exact agency-name match was not established. Confirm the legal name and licence with NEA before trusting the sender."
        return result, [], [result.detail]
    registered_emails = sorted(set(email.lower() for email in EMAIL_RE.findall(match.email)))
    agency_emails = entities.agency_emails or (entities.emails if entities.company_name == entities.agency_name or (not entities.agency_name and name_used == entities.company_name) else [])
    email_match = bool(set(email.lower() for email in agency_emails) & set(registered_emails))
    domain_mismatch = bool(agency_emails and registered_emails
                           and not {domain_of(email) for email in agency_emails} & {domain_of(email) for email in registered_emails})
    result.comparisons = [
        SourceComparison(field="Agency legal name", letter_value=claimed or "Not stated", source_value=match.name,
                         status="MATCHED" if exact_name else "MISMATCH", detail="Compare the legal agency name, not just the licence number."),
        SourceComparison(field="Agency licence", letter_value=entities.agency_licence or "Not stated", source_value=match.licence or "Not published by this source",
                         status="MATCHED" if entities.agency_licence and match.licence and _norm_licence(entities.agency_licence) == _norm_licence(match.licence) else "MISMATCH" if entities.agency_licence and match.licence else "UNVERIFIED",
                         detail="A real licence may be copied. A business registration number is not an NEA recruitment licence."),
        SourceComparison(field="Licence status and expiry", letter_value="Claims to recruit", source_value=f"{_status_label(match.status)}; expires {match.expiry or 'unknown'}",
                         status="MISMATCH" if INACTIVE_RE.search(match.status) or (match.expiry and match.expiry < date.today()) else "MATCHED" if match.expiry and match.status.lower() in {"valid", "active"} else "UNVERIFIED",
                         detail="Status and certificate expiry come from the named NEA source."),
        SourceComparison(field="Agency email", letter_value=", ".join(agency_emails) or "Not identified separately from employer contacts",
                         source_value=", ".join(registered_emails) or "Not listed in source",
                         status="MISMATCH" if domain_mismatch else "MATCHED" if email_match else "UNVERIFIED",
                         detail="Contact the agency using the register's address. A different address on the same domain is not automatically fraudulent."),
        SourceComparison(field="Agency website", letter_value=", ".join(entities.domains) or "Not stated", source_value=match.website or "Not listed in source",
                         status="UNVERIFIED", detail="The NEA-listed website is an independent contact lead; it does not authenticate this sender."),
    ]
    if match.business_registration_number:
        result.comparisons.append(SourceComparison(field="Agency business registration", letter_value="Not identified separately",
                                                   source_value=match.business_registration_number, status="UNVERIFIED",
                                                   detail="NEA publishes this business registration number; it is not the recruitment licence number."))
    if match.licence_type:
        result.comparisons.append(SourceComparison(field="Recruitment licence scope", letter_value="Overseas recruitment",
                                                   source_value=match.licence_type, status="UNVERIFIED",
                                                   detail="Confirm that the licence authorizes this destination and type of recruitment."))
    if domain_mismatch:
        findings = [finding for finding in findings if finding.points >= 0]
        findings.append(Finding(id="agency_registry_email_mismatch", title="Agency email domain differs from NEA's contact record",
                                detail=f"The letter identifies agency email {', '.join(agency_emails)}; NEA lists {', '.join(registered_emails)} for {match.name}. This may be impersonation or an outdated contact; ask the registered agency to confirm.",
                                severity="high", category="contact", points=20))
    if (match.licence_type and "local" in match.licence_type.lower()
            and not re.search(r"international|foreign|overseas", match.licence_type, re.I)):
        findings = [finding for finding in findings if finding.points >= 0]
        findings.append(Finding(id="agency_local_only", title="Agency record only lists local recruitment",
                                detail=f"NEA lists {match.licence_type} for {match.name}. Overseas recruitment permission was not established.",
                                severity="high", category="company", points=20))
    mismatches = [finding for finding in findings if finding.points > 0]
    result.status = "MISMATCH" if mismatches else "MATCHED"
    result.detail = " ".join(finding.detail for finding in findings)
    if live_failed:
        result.detail += " Live NEA access was unavailable; this result uses the dated imported snapshot."
        not_run.append("Live NEA lookup unavailable; used the dated imported snapshot instead.")
    if not mismatches and (not match.expiry or match.status.lower() not in {"valid", "active"}):
        result.status = "UNVERIFIED"
        result.detail = f"The agency name was found in NEA's records, but current recruitment permission could not be established. The source reports {_status_label(match.status)} with expiry {match.expiry or 'not provided'}. A paid licence fee or business registration is not itself licence approval. Confirm with NEA."
        return result, [], [result.detail]
    return result, findings, not_run


def _distinctive(name: str) -> str:
    """The part of a name that tells agencies apart: "Savannah Bridge Recruitment Agency Ltd" -> "savannah bridge"."""
    return " ".join(t for t in _norm_name(name).split() if t not in GENERIC_WORDS)


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _name_matches(name: str, agency: Agency) -> bool:
    full = _ratio(_norm_name(name), agency.key)
    # The distinctive part may match closely while generic words differ ("X Recruitment" vs "X Recruitment Agency"),
    # but a shared place name alone ("Rift Valley ...") is not enough.
    return full >= NAME_MATCH_RATIO or (full >= 0.75 and _ratio(_distinctive(name), _distinctive(agency.name)) >= 0.95)


def find_agency(names: list[str], licence: str | None, agencies: list[Agency]) -> tuple[Agency | None, str, str | None]:
    """Return (agency, matched_by, name_used). matched_by is 'licence' or 'name'."""
    if licence:
        wanted = _norm_licence(licence)
        if match := next((a for a in agencies if a.licence and _norm_licence(a.licence) == wanted), None):
            return match, "licence", None
    for name in names:
        if match := next((a for a in agencies if _norm_name(name) == a.key), None):
            return match, "name", name
    for name in names:
        if match := next((a for a in agencies if _name_matches(name, a)), None):
            return match, "name", name
    return None, "", None


def _looks_kenyan(text: str, entities: Entities) -> bool:
    name = entities.agency_name or ""
    at = text.find(name) if name else -1
    nearby = text[max(0, at - 150): at + len(name) + 150] if at >= 0 else ""
    return bool(KENYA_HINT_RE.search(nearby)) or any(KENYA_PHONE_RE.match(re.sub(r"[\s().-]", "", p)) for p in entities.phones)


def agency_findings(entities: Entities, text: str, *, agencies: list[Agency] | None = None) -> tuple[list[Finding], list[str]]:
    """Return (findings, checks_not_run)."""
    no_agency = ["NEA licensed-agency check: no recruitment agency is named."]
    agency_claimed = bool(entities.agency_name or entities.agency_licence)
    if agencies is None:
        agencies = load_agencies()
    if not agencies:
        return [], ["NEA licensed-agency check: the NEA agency list has not been loaded on this server."] if agency_claimed else no_agency

    # The sender may itself be a listed agency whose name has no agency word in it ("Kilima Jobs International Ltd").
    names = [n for n in (entities.agency_name, entities.company_name) if n]
    match, matched_by, name_used = find_agency(names, entities.agency_licence, agencies)
    if match is None and not agency_claimed:
        return [], no_agency
    claimed = entities.agency_name or name_used
    label = f"\"{claimed}\"" if claimed else f"licence number {entities.agency_licence}"

    if match is None:
        if _looks_kenyan(text, entities):
            severity, points, extra = "high", 20, "Kenyan agencies must be accredited by NEA to recruit people for jobs abroad."
        else:
            severity, points, extra = "medium", 10, (
                "If this is a foreign recruiter, ask which NEA-accredited Kenyan agency they work with, and check that one."
            )
        return [Finding(
            id="agency_not_accredited", title="Recruitment agency is not on NEA's accredited list",
            detail=f"{label} was not found among the {len(agencies)} agencies on our copy of the NEA list. {extra} "
            "The name may be spelled differently, so also search it yourself on the NEA register.",
            severity=severity, category="company", points=points,
        )], []

    findings: list[Finding] = []
    listed = f"NEA lists \"{match.name}\"" + (f" with licence {match.licence}" if match.licence else "")
    if INACTIVE_RE.search(match.status):
        findings.append(Finding(
            id="agency_inactive", title=f"Agency's NEA record: {_status_label(match.status).lower()}",
            detail=f"{listed}, marked as \"{_status_label(match.status)}\". Current recruitment permission has not been established; confirm directly with NEA.",
            severity="high", category="company", points=25,
        ))
    elif match.expiry and match.expiry < date.today():
        findings.append(Finding(
            id="agency_expired", title="Agency's NEA accreditation has expired",
            detail=f"{listed}, valid only until {match.expiry:%d %b %Y}.",
            severity="high", category="company", points=20,
        ))
    if matched_by == "name" and entities.agency_licence and match.licence \
            and _norm_licence(entities.agency_licence) != _norm_licence(match.licence):
        findings.append(Finding(
            id="agency_licence_mismatch", title="Licence number doesn't match NEA's record",
            detail=f"The letter gives licence {entities.agency_licence}, but {listed}. "
            "Scammers often borrow a real agency's name.",
            severity="medium", category="company", points=12,
        ))
    if matched_by == "licence" and claimed and _ratio(_distinctive(claimed), _distinctive(match.name)) < 0.6:
        findings.append(Finding(
            id="agency_licence_other_agency", title="Licence number belongs to a different agency",
            detail=f"The letter names {label}, but {listed}. Scammers often copy a real agency's licence number.",
            severity="high", category="company", points=15,
        ))
    if not findings:
        findings.append(Finding(
            id="agency_accredited", title="Recruitment agency is on NEA's accredited list",
            detail=f"{listed}" + (f", valid until {match.expiry:%d %b %Y}" if match.expiry else "") + ". "
            "Scammers sometimes use a real agency's name, so call the agency on the number in NEA's register, "
            "not the one in this letter.",
            severity="info", category="company", points=-10,
        ))
    return findings, []
