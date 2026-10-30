"""Bounded, labelled-field checks. Neither a document match nor a user correction authenticates a visa."""

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

from .extract import extract
from .forensics import pdf_findings
from .models import AnalysisReport, Entities, Finding, VisaAssessment, VisaComparison, VisaDetails, VisaGuidance, VisaPreview, VisaReview
from .verification import verification_summary

GUIDANCE = {
    "QA": VisaGuidance(source_name="Qatar Ministry of Interior — Visa Inquiry & Printing",
        source_url="https://portal.moi.gov.qa/wps/portal/MOIInternet/services/inquiries/visaservices/enquiryandprinting",
        steps=["Open the official MOI page and choose visa number or passport number.",
               "Enter the number and nationality directly on the government page, then complete its verification code.",
               "Compare the returned holder, sponsor, visa type and validity details with your documents. If the record is unavailable or differs, ask the issuing authority for clarification.",
               "Opening this link does not verify your visa in this app. Do not enter passport details on a lookalike website."]),
    "KW": VisaGuidance(source_name="Kuwait Ministry of Interior — Residency visa services",
        source_url="https://www.moi.gov.kw/main/eservices/residence",
        steps=["Open the official MOI residency services page and choose the visa-status service for your document type.",
               "For a work or entry permit, use the corresponding residency service; the tourist-visa service is not proof of work permission.",
               "Enter the requested visa/application and holder details only on the official service. Login or additional verification may be required.",
               "Compare the result with your document. If no suitable public lookup is available, ask MOI or the issuing sponsor for confirmation. This app does not retrieve or certify the government result."]),
}
COUNTRY_NAMES = {"QA": "Qatar", "KW": "Kuwait"}
LABELS = {
    "holder_name": r"(?:visa holder(?:'s)? name|holder name|applicant name|employee name|full name|latin name|name in english|name)",
    "passport_number": r"passport\s*(?:number|no\.?|#)",
    "visa_number": r"(?:e[ -]?visa|visa|entry permit|work permit)\s*(?:number|no\.?|#)",
    "nationality": r"nationality",
    "sponsor": r"(?:sponsor(?:'s)?(?: name)?|employer(?: name)?|company name)",
    "job_title": r"(?:job title|occupation|profession|position)",
    "visa_type": r"(?:visa type|type of visa|permit type|entry type)",
    # An unqualified expiry can belong to a passport. Only explicit visa/permit labels are used.
    "issue_date": r"(?:(?:visa|entry permit|work permit) (?:issue date|date of issue|issued on))",
    "expiry_date": r"(?:(?:visa|entry permit|work permit) (?:expiry date|expiration date|valid until)|valid until|last date of entry|enter before)",
}


def labelled_details(text: str, offer: bool = False) -> VisaDetails:
    values = {}
    for field, label in LABELS.items():
        matches = re.findall(rf"^[ \t]*{label}(?:[ \t]*[:：][ \t]*|[ \t]*\r?\n[ \t]*|[ \t]{{2,}})([^\n\r]+)", text, re.I | re.M)
        cleaned = [re.sub(r"\s+", " ", value).strip() for value in matches]
        # Conflicting repeated fields need manual review; never silently choose the convenient one.
        unique = list(dict.fromkeys(cleaned))
        if len(unique) == 1 and len(unique[0]) <= (50 if field.endswith("number") else 60 if field.endswith("date") else 100 if field in {"nationality", "visa_type"} else 200):
            values[field] = unique[0]
    if offer:
        values.pop("visa_number", None)
        values.pop("visa_type", None)
        values.pop("issue_date", None)
        values.pop("expiry_date", None)
        if not values.get("holder_name"):
            salutation = re.search(r"^Dear\s+(?:Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+)?([^,\n]{3,100})[,]?\s*$", text, re.I | re.M)
            if salutation and salutation.group(1).strip().lower() not in {"applicant", "candidate", "sir", "madam", "sir/madam"}:
                values["holder_name"] = salutation.group(1).strip()
    return VisaDetails(**values)


def detected_country(text: str) -> str | None:
    found = [code for code, name in COUNTRY_NAMES.items() if re.search(rf"^\s*(?:state of |issuing country\s*:\s*|country of issue\s*:\s*)?{name}\s*$", text, re.I | re.M)]
    return found[0] if len(found) == 1 else None


def parse_date(value: str | None) -> date | None:
    """Do not guess between day/month and month/day when both are possible."""
    if not value:
        return None
    value = value.strip()
    iso = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", value)
    local = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", value)
    try:
        if iso:
            return date(*map(int, iso.groups()))
        if local:
            first, second, year = map(int, local.groups())
            if first <= 12 and second <= 12 and first != second:
                return None
            return date(year, second, first) if first > 12 or first == second else date(year, first, second)
        for pattern in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(value, pattern).date()
            except ValueError:
                pass
    except ValueError:
        return None
    return None


def _normal(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()))


def invalid_calendar_date(value: str | None) -> bool:
    if not value or parse_date(value):
        return False
    if re.fullmatch(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", value.strip()):
        return True
    local = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.]\d{4}", value.strip())
    if local:
        first, second = map(int, local.groups())
        return first == 0 or second == 0 or first > 12 or second > 12
    return False


def compare_details(visa: VisaDetails, offer: VisaDetails | None) -> list[VisaComparison]:
    comparisons = []
    for field, label in [("holder_name", "Holder name"), ("passport_number", "Passport number"), ("sponsor", "Employer / sponsor"), ("job_title", "Job title")]:
        left, right = getattr(visa, field), getattr(offer, field) if offer else None
        status, detail = "UNVERIFIED", "This field was not available in both documents. Missing information is not evidence of fraud."
        if left and right:
            a, b = _normal(left), _normal(right)
            if field == "passport_number":
                a, b = re.sub(r"[^a-z0-9]", "", a), re.sub(r"[^a-z0-9]", "", b)
            if a and b and (a == b or field == "holder_name" and sorted(a.split()) == sorted(b.split())):
                status, detail = "MATCHED", "The reviewed document values match. This does not establish identity or authenticity."
            elif not a or not b or field == "holder_name" and (set(a.split()) <= set(b.split()) or set(b.split()) <= set(a.split())):
                detail = "The values may be abbreviated or transliterated differently. Confirm the full details independently."
            else:
                status = "MISMATCH"
                detail = "The document values differ. Confirm against the original documents and issuing authority."
                if field == "sponsor":
                    detail += " A sponsor may be an intermediary; ask for evidence explaining its relationship to the offered employer."
        comparisons.append(VisaComparison(field=label, visa_value=left, offer_value=right, status=status, detail=detail))
    return comparisons


def _read(data: bytes, filename: str, country: str, offer_data: bytes | None = None, offer_filename: str | None = None):
    if country not in GUIDANCE:
        raise ValueError("Visa checks support Qatar and Kuwait only.")
    if not filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt")):
        raise ValueError("Choose a PDF, image or text copy of a visa.")
    document = extract(data, filename)
    text = document.text
    details = labelled_details(text)
    recognised = bool(re.search(r"\b(?:visa|entry permit|work permit)\b", text, re.I) and details.visa_number and re.search(r"\d", details.visa_number) and (details.holder_name or details.passport_number))
    if not text.strip() or not recognised:
        if document.pdf is not None:
            document.pdf.close()
        raise ValueError("Not checked — no supported visa fields could be read. Choose a clearer document with labelled visa and holder details.")
    offer = None
    warnings = list(document.warnings)
    if offer_data is not None:
        if not offer_filename or not offer_filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".eml")):
            if document.pdf is not None:
                document.pdf.close()
            raise ValueError("Unsupported offer comparison file.")
        try:
            letter = extract(offer_data, offer_filename)
            try:
                if not letter.text.strip():
                    raise ValueError("Not checked — the attached offer could not be read. Upload a clearer offer or remove it.")
                offer = labelled_details(letter.text, offer=True)
                warnings += letter.warnings
            finally:
                if letter.pdf is not None:
                    letter.pdf.close()
        except Exception:
            if document.pdf is not None:
                document.pdf.close()
            raise
    return document, details, offer, warnings


def preview_visa(data: bytes, filename: str, country: str, offer_data: bytes | None = None, offer_filename: str | None = None) -> VisaPreview:
    document, details, offer, warnings = _read(data, filename, country, offer_data, offer_filename)
    try:
        return VisaPreview(country=country, detected_country=detected_country(document.text), details=details, offer_details=offer,
            warnings=warnings + ["Review every extracted value against the original. An unlabelled expiry date is not assumed to be the visa expiry. Use YYYY-MM-DD for dates you can confirm."])
    finally:
        if document.pdf is not None:
            document.pdf.close()


def analyze_visa(data: bytes, filename: str, country: str, review: VisaReview, offer_data: bytes | None = None, offer_filename: str | None = None, today: date | None = None) -> AnalysisReport:
    document, original, original_offer, warnings = _read(data, filename, country, offer_data, offer_filename)
    try:
        if bool(offer_data is not None) != bool(review.offer_details is not None):
            raise ValueError("Reviewed offer fields must correspond to the attached offer.")
        details = VisaDetails(**{key: value.strip() or None if value is not None else None for key, value in review.details.model_dump().items()})
        offer = review.offer_details
        corrections = [f"Visa: {field}" for field in VisaDetails.model_fields if getattr(details, field) != getattr(original, field)]
        if offer and original_offer:
            corrections += [f"Offer: {field}" for field in VisaDetails.model_fields if getattr(offer, field) != getattr(original_offer, field)]
        findings, not_run = [], ["Government visa validity and authenticity were not checked. Complete the official lookup yourself.",
            "Visa-number issuance formats and security features have not been authenticated. A readable number is not proof of issuance.",
            "This module compares labelled offer fields; it does not run a full employer, agency or offer-letter investigation."]
        # Qatar and Kuwait both use UTC+3; do not let the host's timezone decide the validity day.
        now = today or datetime.now(timezone(timedelta(hours=3))).date()
        issue, expiry = parse_date(details.issue_date), parse_date(details.expiry_date)
        def flag(key, title, detail, points=30):
            findings.append(Finding(id=key, title=title, detail=detail, severity="high" if points >= 60 else "medium", category="document", points=points))
        if expiry and expiry < now:
            flag("visa_expired", "The visa / entry validity date has passed", "Do not rely on this document for a new entry. A past validity date does not prove the historical document was forged or that existing residence permission has expired.", 60)
        if issue and expiry and expiry < issue:
            flag("visa_date_order", "Expiry is before the issue date", "Recheck the printed dates and any extraction corrections. Ask the issuing authority to explain the inconsistency.")
        if issue and issue > now:
            flag("visa_future_issue", "The issue date is in the future", "Check the date and whether this is a proposed or issued document. The date alone does not prove fraud.")
        for field in ("issue_date", "expiry_date"):
            if invalid_calendar_date(getattr(details, field)):
                flag("visa_invalid_" + field, "The stated " + field.replace("_", " ") + " is not a calendar date",
                     "This numeric date cannot occur on a calendar. Recheck the original document and any OCR correction; a date error alone does not prove forgery.")
            if not parse_date(getattr(details, field)):
                not_run.append(f"Visa {field.replace('_', ' ')}: missing, ambiguous or invalid; no date conclusion was made for this field.")
        # Preserve clear source-date conflicts even when a reviewed value replaces them.
        original_expiry = parse_date(original.expiry_date)
        if original_expiry and original_expiry < now and details.expiry_date != original.expiry_date:
            flag("visa_source_expiry", "The extracted source expiry needs resolving", "The original extracted visa expiry is in the past, while the reviewed value differs. Confirm the printed date and official record; a user correction does not resolve this conflict.")
        actual_country = detected_country(document.text)
        if actual_country and actual_country != country:
            flag("visa_country_mismatch", "The document country differs from your selection", f"The document identifies {COUNTRY_NAMES[actual_country]}, while you selected {COUNTRY_NAMES[country]}. Recheck the issuing country.")
        if not actual_country:
            not_run.append("Issuing country could not be independently read from an explicit country heading.")
        if details.visa_type and re.search(r"\b(?:tourist|tourism|visit|business)\b", details.visa_type, re.I):
            if offer is not None:
                flag("visa_non_work_route", "The stated route does not establish permission for the offered job", "The visa type mentions a visit, tourist or business route. Obtain confirmation of the required work authorisation before taking the offered job; route wording alone does not authenticate or establish work permission.", 60)
            else:
                not_run.append("The stated visit/tourist/business route does not establish work permission. No employment offer was attached.")
        if not details.visa_type:
            not_run.append("Visa type and permission to work: not identified.")
        for field in ("visa_number", "passport_number"):
            value = getattr(details, field)
            if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /-]{1,49}", value):
                not_run.append(f"{field.replace('_', ' ').title()}: missing or not interpretable; verify on the official portal. No country-specific number length is assumed.")
        comparisons = compare_details(details, offer)
        if offer is None:
            not_run.append("Offer-to-visa comparison: no offer letter attached.")
        else:
            for comparison in comparisons:
                if comparison.status == "MISMATCH":
                    flag("visa_offer_" + comparison.field.lower().split()[0], comparison.field + " differs between the documents", comparison.detail)
        if document.pdf is not None:
            for hint in pdf_findings(document.pdf, data):
                findings.append(hint.model_copy(update={"id": "visa_" + hint.id, "points": 0, "severity": "info", "detail": hint.detail + " This editing observation alone does not establish visa fraud."}))
        else:
            not_run.append("PDF editing observations: not available for image or text uploads.")
        score = min(100, sum(f.points for f in findings))
        level = "HIGH" if score >= 60 else "MEDIUM" if score >= 30 else "LOW"
        summary = "Validity or document differences need resolving before you pay or travel." if findings and score else "No major red flags were found in the supported document checks. Official visa status and authenticity remain unverified."
        if corrections:
            warnings.append("Reviewed values include user corrections. Original extracted values are retained in this report; neither set is government-confirmed.")
        assessment = VisaAssessment(details=details, extracted_details=original, offer_details=offer, extracted_offer_details=original_offer,
            offer_file_name=offer_filename, detected_country=actual_country, corrections=corrections, comparisons=comparisons, guidance=GUIDANCE[country])
        report = AnalysisReport(file_name=filename, kind="visa", risk_level=level, score=score, country=country, country_name=COUNTRY_NAMES[country],
            company_name=details.sponsor, job_title=details.job_title, summary=summary, findings=sorted(findings, key=lambda f: -f.points),
            advice=["Complete the official government lookup before paying or travelling.", "Confirm the holder and passport details against the original passport without sharing it unnecessarily.",
                    "Ask the employer to explain any sponsor or job-title difference using independently sourced contact details.",
                    "Use the offer-letter checker separately for employer, agency and recruitment-scam checks."],
            verify_links=[{"label": GUIDANCE[country].source_name, "url": GUIDANCE[country].source_url}], entities=Entities(company_name=details.sponsor, job_title=details.job_title),
            text_excerpt=document.text[:3000], extraction_method=document.method, ai_used=False, warnings=warnings, checks_not_run=not_run, fingerprint=None, visa=assessment)
        report.verification = verification_summary(report)
        return report
    finally:
        if document.pdf is not None:
            document.pdf.close()
