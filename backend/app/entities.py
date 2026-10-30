"""Pull emails, phones, links, amounts and fee mentions out of letter text."""

import re
from urllib.parse import urlsplit

from .models import Entities

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\"')]+", re.I)
PHONE_RE = re.compile(r"(?:\+|00)\d[\d\s().-]{7,}\d|\b0\d{2,3}[\s-]?\d{3}[\s-]?\d{3,4}\b")
CURRENCY = r"(?:USD|US\$|\$|KES|KSH|Ksh|AED|SAR|QAR|OMR|KWD|BHD|CAD|C\$|GBP|£|EUR|€|AUD|A\$|INR|₹|NGN|₦|PLN|zł)"
MONEY_RE = re.compile(rf"{CURRENCY}\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?{CURRENCY}", re.I)
# Where the money is meant to go. Scammers reuse these across letters, so they are remembered as scam indicators.
_NO = r"\s*(?:no\.?|number|#)?\s*[:\-]?\s*"
PAYBILL_RE = re.compile(
    rf"\bpay\s?bill{_NO}(\d{{5,7}})(?:[^.\n]{{0,40}}?\b(?:account|acc|a/c)(?:\s*name)?{_NO}([A-Z0-9][A-Z0-9-]{{2,19}}))?", re.I
)
TILL_RE = re.compile(rf"\btill{_NO}(\d{{5,8}})\b", re.I)
BANK_ACCOUNT_RE = re.compile(r"\b(?:a/c|acc(?:ount)?\.?)\s*(?:no\.?|number|#)\s*[:\-]?\s*(\d[\d -]{6,22}\d)", re.I)
IBAN_RE = re.compile(r"\bIBAN\s*[:\-]?\s*([A-Z]{2}\d{2}(?:\s?[A-Z0-9]){10,30})", re.I)
CRYPTO_WALLET_RE = re.compile(
    r"\b(?:bc1[a-z0-9]{25,59}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|T[1-9A-HJ-NP-Za-km-z]{33}|0x[a-fA-F0-9]{40})\b"
)
# A fee is a cost word ("fee", "deposit"...) up to three words after what it is for: "visa processing fee",
# "medical and document attestation fees", "COS registration fee".
FEE_FOR = (
    r"visa|processing|application|registration|medical|insurance|ticket|work permit|permit|documentation|"
    r"document|clearance|training|placement|agency|recruitment|embassy|interview|courier|attestation|lmia|cos|"
    r"sponsorship|bond|onboarding|uniform"
)
FEE_RE = re.compile(
    rf"\b(?:{FEE_FOR})\b(?:[\s,&/-]+(?:and\s+|or\s+)?[\w-]+){{0,3}}?\s+(?:fees?|charges?|costs?|deposit|levy)\b"
    r"|\brefundable\b.{0,40}?\b(?:fee|deposit|amount)\b|\bsecurity deposit\b",
    re.I,
)
PAY_RE = re.compile(r"\b(?:pay|paid|payment|send|transfer|deposit|remit)\b", re.I)
# The candidate is told to pay.
DEMAND_RE = re.compile(
    r"\b(?:you|candidates?|applicants?)\b.{0,40}?\b(?:must|are required to|is required to|should|need to|have to)\b.{0,30}?"
    r"\b(?:pay|send|transfer|deposit)\b|\b(?:required to|kindly|please) (?:pay|send|transfer|make (?:the |a )?payment)\b"
    r"|\bmust pay\b|\bpay (?:through|via|by|to)\b",
    re.I,
)
# The employer pays, or the letter promises the candidate pays nothing.
EMPLOYER_PAYS_RE = re.compile(
    r"\b(?:paid (?:for )?by|has been paid|borne by|covered by|at no cost to you|free of charge|"
    r"employer'?s responsibility|responsibility of the (?:company|employer)|arranged and paid|"
    r"not be (?:asked|required) to pay|will not (?:charge|be recovered|ask)|never ask|not recover)\b"
    r"|\b(?:company|employer|we|sponsor|ltd|llc|inc|gmbh|pty)\b.{0,80}?\b(?:will|shall) (?:pay|cover|bear)\b",
    re.I,
)
# "No fees charged", "we never charge candidates".
NO_FEE_RE = re.compile(
    r"\bno (?:\w+ )?(?:fees?|charges?|costs?|payments?)\b|\bnever (?:charge|ask)|\bwithout (?:any )?(?:fees?|charges?|payment)\b",
    re.I,
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])|\n\s*\n")
COMPANY_SUFFIX_RE = re.compile(
    r"\b([A-Z][\w&.,'-]*(?:[ \t]+[A-Z][\w&.,'-]*){0,5}[ \t]+"
    r"(?:Ltd|Limited|LLC|L\.L\.C|Inc|Incorporated|Corp|Corporation|PLC|GmbH|Group|Company|Co\.|FZE|FZ-LLC|WLL|W\.L\.L|Pty|S\.A\.|SA))\b\.?"
)
JOB_RE = re.compile(r"(?:position|post|role|job title|designation)\s*(?:of|as|:)?\s*[\"“]?([A-Z][A-Za-z /&-]{2,50})", re.I)
AGENCY_WORD_RE = re.compile(
    r"\b(?:recruit(?:ment|ers?|ing)|agenc(?:y|ies)|manpower|placements?|staffing|employment (?:services|bureau)|"
    r"consultan(?:ts?|cy))\b",
    re.I,
)
# Without a real name left over, "Recruitment Office" is a department, not an agency.
GENERIC_WORDS = {
    "recruitment", "recruiting", "recruiter", "recruiters", "agency", "agencies", "manpower", "placement",
    "placements", "staffing", "employment", "services", "bureau", "consultant", "consultants", "consultancy",
    "office", "department", "team", "officer", "unit", "section", "desk", "manager", "hr", "human", "resources",
    "the", "our", "your", "and", "of", "for", "international", "overseas", "ltd", "limited",
}
# "Recruitment Manager, Al Waha Medical Group" is someone's job title in a signature.
JOB_ROLE_RE = re.compile(
    r"\b(?:recruit\w*|talent|hr)\s+(?:manager|officer|coordinator|specialist|lead|team|department|office|process|director|executive)\b",
    re.I,
)
AGENCY_LABEL_RE = re.compile(
    r"\b(?:recruitment |employment |placement )?agency(?: name)?\s*:\s*([A-Z][^\n,;:]{2,60})"
    r"|\bthrough (?:our )?(?:(?:licensed|accredited|kenyan|local) )*(?:recruitment |placement |employment )?"
    r"(?:agency|partner),?\s+([A-Z][\w&'.-]*(?:[ \t]+[A-Z][\w&'.-]*){0,6})"
)
# "NEA licence no. NEA/PEA/2025/0412" or just "NEA/PEA/2025/0412".
NEA_LICENCE_RE = re.compile(
    r"\bNEA\s*(?:licen[cs]e|accreditation|registration|reg\.?|certificate)?\s*(?:no\.?|number|#)?\s*[:\-]?\s*"
    r"(?=[A-Z0-9/.-]*\d)([A-Z0-9][A-Z0-9/.-]{3,}[A-Z0-9])|\b(NEA/[A-Z0-9/.-]*\d)",
    re.I,
)
# Any licence number - only used when it appears right after the agency's name.
LICENCE_RE = re.compile(
    r"\b(?:licen[cs]e|accreditation)\s*(?:no\.?|number|#)?\s*[:\-]?\s*(?=[A-Z0-9/.-]*\d)([A-Z0-9][A-Z0-9/.-]{3,}[A-Z0-9])",
    re.I,
)


def _unique(items: list[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def join_lines(text: str) -> str:
    """Join the line breaks inside paragraphs (PDFs wrap lines mid-sentence)."""
    return re.sub(r"[ \t]*\n(?![ \t]*\n)[ \t]*", " ", text)


def split_sentences(text: str, kind: str = "letter") -> list[str]:
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(join_lines(text)) if s.strip()]
    if kind == "message":
        # Ads put each point on its own line without full stops, but a pasted SMS may wrap mid-sentence,
        # so check both the single lines and the joined sentences.
        lines = [s.strip() for line in text.splitlines() for s in SENTENCE_SPLIT_RE.split(line) if s.strip()]
        return list(dict.fromkeys(lines + sentences))
    return sentences


def fee_demands(sentences: list[str], kind: str = "letter") -> list[str]:
    """Sentences that ask the candidate to pay a fee, ignoring ones saying the employer pays."""
    found = []
    for s in sentences:
        # Skip a joined sentence that contains a single line already counted (see split_sentences).
        if not FEE_RE.search(s) or any(f in s for f in found):
            continue
        demand = DEMAND_RE.search(s)
        if kind == "message":
            # A fee listed in an ad is charged to the applicant even without "you must pay":
            # "Registration fee 3,500 only."
            if (EMPLOYER_PAYS_RE.search(s) or NO_FEE_RE.search(s)) and not demand:
                continue
        else:
            if not (demand or PAY_RE.search(s)):
                continue
            if EMPLOYER_PAYS_RE.search(s) and not demand:
                continue
        found.append(s)
    return found


def payment_accounts(text: str) -> list[str]:
    """Normalised payment destinations, e.g. "paybill 247247 account 778812", "till 5678123", "bank account 0123456789"."""
    joined = join_lines(text)
    found, paybill_spans = [], []
    for m in PAYBILL_RE.finditer(joined):
        paybill_spans.append(m.span())
        found.append(f"paybill {m.group(1)}" + (f" account {m.group(2).lower()}" if m.group(2) else ""))
    found += [f"till {m.group(1)}" for m in TILL_RE.finditer(joined)]
    for m in BANK_ACCOUNT_RE.finditer(joined):
        # A paybill's own account number is already part of that paybill entry.
        if not any(start <= m.start() < end for start, end in paybill_spans):
            found.append(f"bank account {re.sub(r'[ -]', '', m.group(1))}")
    found += [f"iban {re.sub(r'\s', '', m.group(1)).upper()}" for m in IBAN_RE.finditer(joined)]
    found += [f"crypto wallet {m.group(0)}" for m in CRYPTO_WALLET_RE.finditer(joined)]
    return _unique(found)


def domain_of(value: str) -> str:
    value = value.strip().rstrip(".,;")
    if "@" in value and "://" not in value:
        value = value.rsplit("@", 1)[1]
    try:
        host = urlsplit(value if "://" in value else "https://" + value).hostname or ""
        return host.encode("idna").decode("ascii").lower().removeprefix("www.").strip(".")
    except (ValueError, UnicodeError):
        return ""


def is_agency_name(name: str) -> bool:
    if not AGENCY_WORD_RE.search(name) or JOB_ROLE_RE.search(name):
        return False
    return any(t not in GENERIC_WORDS for t in re.findall(r"[a-z]{2,}", name.lower()))


def _agency_name(text: str, company_names: list[str]) -> str | None:
    if labelled := re.search(r"^\s*(?:recruitment |employment |placement )?agency(?: name)?\s*:\s*([^\n;]{2,100})", text, re.I | re.M):
        name = labelled.group(1).strip(" .\t")
        if any(word not in GENERIC_WORDS for word in re.findall(r"[a-z]{2,}", name.lower())):
            return name
    # A registered name that is an agency: "Savannah Bridge Recruitment Agency Ltd" - also when a PDF wraps it
    # onto two lines.
    joined = join_lines(text)
    wrapped_names = [m.group(1) for m in COMPANY_SUFFIX_RE.finditer(joined)]
    if name := next((c for c in company_names + wrapped_names if is_agency_name(c)), None):
        return name
    # "Recruitment agency: X", "through our licensed partner X".
    for m in AGENCY_LABEL_RE.finditer(joined):
        name = (m.group(1) or m.group(2)).strip(" .")
        if m.group(2) or is_agency_name(name):
            return name
    # A letterhead line: "EUROLINK PLACEMENT AGENCY".
    for line in text.splitlines():
        line = line.strip(" \t-|•")
        if (
            3 <= len(line) <= 70 and len(line.split()) <= 8 and line[0].isupper()
            and not re.search(r"[:@]|https?:|^(?:dear|to|re|subject)\b", line, re.I)
            and is_agency_name(line)
        ):
            return line
    return None


def _agency_licence(text: str, agency: str | None) -> str | None:
    if m := NEA_LICENCE_RE.search(text):
        return (m.group(1) or m.group(2)).upper()
    if agency and (at := text.find(agency)) >= 0:
        if m := LICENCE_RE.search(text, at, at + len(agency) + 200):
            return m.group(1).upper()
    return None


def extract_entities(text: str, kind: str = "letter") -> Entities:
    emails = _unique(EMAIL_RE.findall(text))
    urls = _unique([url.rstrip(".,;") for url in URL_RE.findall(text)] + re.findall(
        r"\b(?:website|web\s*site|company domain)\s*:\s*((?:[a-z0-9-]+\.)+[a-z]{2,63}(?:/[^\s<>]*)?)", text, re.I))
    phones = _unique([p for p in PHONE_RE.findall(text) if len(re.sub(r"\D", "", p)) >= 9])
    money = _unique(MONEY_RE.findall(text))
    fees = _unique(fee_demands(split_sentences(text, kind), kind))[:8]
    domains = _unique([domain_of(u) for u in urls] + [domain_of(e) for e in emails])

    company_names = _unique([m.group(1) for m in COMPANY_SUFFIX_RE.finditer(text)])
    # The employer, not the recruitment agency that may also be named in the letter.
    company = next((c for c in company_names if not is_agency_name(c)), company_names[0] if company_names else None)
    if labelled := re.search(r"^(?:employer|company(?: name)?|legal employer)\s*:\s*([^\n;]{2,100})", text, re.I | re.M):
        company = labelled.group(1).strip(" .\t")
    agency = _agency_name(text, company_names)
    job = None
    if m := JOB_RE.search(text):
        job = re.split(r"\s+(?:at|in|with|for|based|of)\s+|[,.;\n]", m.group(1).strip())[0].strip()

    return Entities(
        emails=emails,
        phones=phones,
        urls=urls,
        domains=domains,
        money=money,
        fee_mentions=fees,
        payment_accounts=payment_accounts(text),
        company_name=company,
        job_title=job,
        agency_name=agency,
        agency_licence=_agency_licence(text, agency),
        agency_emails=_unique(email for line in text.splitlines() if re.match(r"\s*(?:agency|recruiter)(?: contact)?\s*(?:e-?mail)?\s*:", line, re.I) for email in EMAIL_RE.findall(line)),
        company_registration_number=(
            re.sub(r"\s+", "", registration.group(1)).upper()
            if (registration := re.search(
                r"\b(?:company\s+(?:(?:registration|reg\.?)\s*)?(?:number|no\.?)|"
                r"companies\s+house\s+(?:number|no\.?))\s*[:#]?\s*([A-Z]{2}\s?\d{6}|\d{1,8})\b",
                text, re.I,
            )) else None
        ),
    )
