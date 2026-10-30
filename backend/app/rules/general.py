"""Red-flag rules that apply to offer letters from any country."""

import re

from ..entities import domain_of, split_sentences
from ..models import Entities, Finding
from .countries import COUNTRIES

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "ymail.com", "outlook.com", "hotmail.com",
    "live.com", "msn.com", "aol.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "gmx.com",
    "gmx.net", "mail.com", "yandex.com", "yandex.ru", "zoho.com", "rediffmail.com", "inbox.com",
}

PAYMENT_CHANNELS = re.compile(
    r"western union|moneygram|m-?pesa|paybill|till number|bitcoin|usdt|crypto|gift ?card|itunes card|"
    r"wire (?:the )?(?:money|funds)|personal account|send (?:the )?money|airtel money|world ?remit|ria money",
    re.I,
)
URGENCY = re.compile(
    r"within (?:24|48|72) ?(?:hours|hrs)|within [1-7] days|first come,? first served|immediately|urgent(?:ly)?|act now|"
    r"limited (?:slots|positions|time)|last chance|failure to (?:pay|respond|comply)|offer will be (?:cancelled|withdrawn|forfeited)",
    re.I,
)
# Job ads often say "urgently hiring" honestly, so for ads and messages only real pressure counts.
STRONG_URGENCY = re.compile(
    r"within (?:24|48|72) ?(?:hours|hrs)|within [1-7] days|first come,? first served|act now|limited (?:slots|time)|"
    r"last chance|failure to (?:pay|respond|comply)|(?:offer|slot) will be (?:cancelled|withdrawn|forfeited|given)",
    re.I,
)
NO_INTERVIEW = re.compile(
    r"no interview|without (?:an )?interview|selected (?:from|through) (?:our|the) database|randomly selected|"
    r"your (?:cv|resume|profile) was (?:selected|picked)|you have been (?:selected|chosen) (?:by|from)",
    re.I,
)
CHAT_APPS = re.compile(r"whats ?app|telegram|signal app|imo app|viber", re.I)
# Kenyan agencies advertise with WhatsApp numbers every day; these apps are rarer and harder to trace.
ANONYMOUS_CHAT_APPS = re.compile(r"telegram|signal app|imo app|viber", re.I)
PASSPORT = re.compile(r"passport|national id|id card|identity card", re.I)
# "We never ask you to send money" is a reassurance, not a request.
NEGATED = re.compile(r"\b(?:never|not|don't|won't|no one|nobody)\b.{0,40}?\b(?:send|ask|pay|money|charge)|\breport\b", re.I)
GENERIC_GREETING = re.compile(r"dear (?:applicant|candidate|beneficiary|sir/madam|sir or madam|friend|winner|job seeker)", re.I)
SENSITIVE_REQUEST = re.compile(
    r"bank (?:account|details|statement)|credit card|debit card|(?<!id )(?<!identity )\bcard number\b|\bpin\b|bvn|password|"
    r"mobile money (?:pin|statement)|atm card",
    re.I,
)
TOO_GOOD = re.compile(r"free (?:accommodation|housing|food|meals|flight|ticket|visa|transport|medical)", re.I)
CONTRACT_TERMS = re.compile(
    r"start(?:ing)? date|commencement|working hours|hours per week|probation|contract (?:duration|period|term)|"
    r"annual leave|notice period|job description|reporting to|basic salary|gross salary",
    re.I,
)
# An agency's NEA licence doesn't count here: agencies.py checks it against the NEA list instead.
REGISTRATION_NO = re.compile(
    r"(?<!NEA )\b(?:company|registration|reg\.?|trade licen[cs]e|commercial registration|c\.?r\.?|crn|ein|abn|krs|hrb|licen[cs]e)"
    r"\s*(?:no\.?|number|#)?\s*[:\-]?\s*(?=[A-Z0-9/-]*\d)[A-Z0-9][A-Z0-9/-]{4,}\b",
    re.I,
)


def _find(fid, title, detail, severity, category, points) -> Finding:
    return Finding(id=fid, title=title, detail=detail, severity=severity, category=category, points=points)


def _shorten(s: str, n: int = 160) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _company_tokens(company: str | None) -> list[str]:
    if not company:
        return []
    stop = {"ltd", "limited", "llc", "inc", "corp", "group", "company", "co", "plc", "gmbh", "the", "and", "international", "global", "services"}
    return [t for t in re.findall(r"[a-z]{3,}", company.lower()) if t not in stop]


def run_general_rules(text: str, entities: Entities, country_code: str | None, kind: str = "letter") -> list[Finding]:
    """`kind` is "letter" for offer letters or "message" for job ads, SMS and chat messages. Messages are short
    and informal, so the checks that expect a formal letter (greeting, contract terms, company name, official
    email, writing style) are skipped for them."""
    findings: list[Finding] = []
    lower = text.lower()
    message = kind == "message"
    noun = "message" if message else "letter"

    # 1. Money requested from the candidate - the strongest scam signal.
    if entities.fee_mentions:
        findings.append(_find(
            "fee_request", "Asks you to pay money",
            f"The {noun} mentions fees you must pay: \"{_shorten(entities.fee_mentions[0])}\". "
            "Genuine employers pay visa, permit and recruitment costs themselves.",
            "critical", "content", 40 + 5 * min(len(entities.fee_mentions) - 1, 3),
        ))

    sentences = split_sentences(text, kind)
    channels = list(dict.fromkeys(
        m.group(0) for s in sentences if not NEGATED.search(s) for m in PAYMENT_CHANNELS.finditer(s)
    ))
    if channels:
        findings.append(_find(
            "payment_channel", "Payment through a personal or untraceable channel",
            f"It mentions {', '.join(f'\"{c}\"' for c in channels[:4])}. Real companies never ask for job-related payments by mobile money, "
            "money transfer services, crypto or gift cards.",
            "high", "content", 20,
        ))

    # 2. Contact details.
    free = [e for e in entities.emails if domain_of(e) in FREE_EMAIL_DOMAINS]
    corporate = [e for e in entities.emails if domain_of(e) not in FREE_EMAIL_DOMAINS]
    if free:
        findings.append(_find(
            "free_email", "Uses a free email address",
            f"Contact email {free[0]} is a free personal account. Established companies send offers from their own domain.",
            # Small agencies' ads often use Gmail, so it weighs less in a message than in an offer letter.
            "high" if not (corporate or message) else "medium", "contact", 20 if not (corporate or message) else 10,
        ))
    if corporate and entities.company_name:
        tokens = _company_tokens(entities.company_name)
        if tokens and not any(t in domain_of(corporate[0]).replace("-", "") for t in tokens):
            findings.append(_find(
                "domain_mismatch", "Email domain doesn't match the company name",
                f"The company is \"{entities.company_name}\" but the email domain is {domain_of(corporate[0])}.",
                "medium", "contact", 8,
            ))
    if not entities.emails and not message:
        findings.append(_find(
            "no_email", "No official email address",
            "The letter has no email address you could use to verify it with the company.",
            "low", "contact", 6,
        ))

    if (ANONYMOUS_CHAT_APPS if message else CHAT_APPS).search(text):
        findings.append(_find(
            "chat_app_contact", "Asks you to communicate on WhatsApp/Telegram",
            "Recruiters who move you to chat apps are hard to trace. Real HR teams use official email and phone lines.",
            "medium", "contact", 8,
        ))
    if any(PASSPORT.search(s) and CHAT_APPS.search(s) for s in sentences):
        findings.append(_find(
            "passport_over_chat", "Asks for your passport over WhatsApp/Telegram",
            "Sending passport copies to a chat account lets scammers commit identity fraud. Share documents only "
            "after you've confirmed the employer, and only through official channels.",
            "medium", "contact", 10,
        ))

    # An ad from a Kenyan agency naturally has a Kenyan number, so this only applies to letters.
    if not message and country_code and (country := COUNTRIES.get(country_code)) and country.phone_codes != ["+1"]:
        foreign = [
            p for p in entities.phones
            if p.strip().startswith(("+", "00")) and not any(p.replace(" ", "").startswith(pc) for pc in country.phone_codes)
        ]
        if foreign and len(foreign) == len([p for p in entities.phones if p.strip().startswith(("+", "00"))]):
            findings.append(_find(
                "phone_country_mismatch", "Phone number is not from the job's country",
                f"The job is in {country.name} but the contact number {foreign[0]} is from another country.",
                "medium", "contact", 8,
            ))

    # 3. Pressure and recruitment style.
    if m := (STRONG_URGENCY if message else URGENCY).search(text):
        findings.append(_find(
            "urgency", "Pressures you to act fast",
            f"Phrases like \"{m.group(0)}\" are used to stop you from checking the offer.",
            "medium", "content", 10,
        ))
    if m := NO_INTERVIEW.search(text):
        if "interview" not in lower or "no interview" in lower or "without" in m.group(0).lower():
            findings.append(_find(
                "no_interview", "Hired without a proper interview",
                f"It says \"{m.group(0)}\". Real overseas hiring involves interviews and checks before an offer.",
                "medium", "content", 10,
            ))
    if not message and (m := GENERIC_GREETING.search(text)):
        findings.append(_find(
            "generic_greeting", "Generic greeting",
            f"\"{m.group(0)}\" - a real offer letter is addressed to you by name.",
            "low", "content", 5,
        ))
    if m := SENSITIVE_REQUEST.search(text):
        findings.append(_find(
            "sensitive_info", "Asks for financial details",
            f"It requests \"{m.group(0)}\". Never share bank, card or PIN details with a recruiter.",
            "high", "content", 15,
        ))
    perks = {p.lower() for p in TOO_GOOD.findall(text)}
    if len(perks) >= 3:
        findings.append(_find(
            "too_good", "Too many free perks",
            f"Offers {', '.join(sorted(perks))}. A long list of freebies is a common bait in fake offers.",
            "low", "content", 5,
        ))
    if message:
        return findings + _trust_signals(text, lower, entities, country_code)

    caps_words = re.findall(r"\b[A-Z]{4,}\b", text)
    if text.count("!") >= 4 or len(caps_words) > 25:
        findings.append(_find(
            "unprofessional_style", "Unprofessional writing style",
            "Lots of exclamation marks or SHOUTING in capitals - unusual for HR documents.",
            "low", "content", 4,
        ))
    if not CONTRACT_TERMS.search(text):
        findings.append(_find(
            "missing_terms", "Missing normal contract details",
            "No start date, working hours, probation, leave or contract period. Real offers spell these out.",
            "low", "content", 6,
        ))
    if not entities.company_name:
        findings.append(_find(
            "no_company", "Company could not be identified",
            "No clear registered company name (e.g. ending in Ltd, LLC, Inc, GmbH) was found.",
            "low", "company", 6,
        ))
    return findings + _trust_signals(text, lower, entities, country_code)


def _trust_signals(text: str, lower: str, entities: Entities, country_code: str | None) -> list[Finding]:
    """Trust signals lower the score; breaking the destination country's fee rules raises it."""
    findings: list[Finding] = []
    if REGISTRATION_NO.search(text):
        findings.append(_find(
            "registration_number", "Includes a company registration number",
            "A registration or licence number is present - look it up in the official register to confirm.",
            "info", "company", -5,
        ))
    if country_code and (country := COUNTRIES.get(country_code)):
        terms = [t for t in country.permit_terms if t in lower]
        if terms and not entities.fee_mentions:
            findings.append(_find(
                "permit_terms", f"Mentions the correct {country.name} work-permit process",
                f"Refers to {', '.join(terms[:3])}, which matches how hiring works in {country.name}.",
                "info", "country", -5,
            ))
        if entities.fee_mentions:
            findings.append(_find(
                "country_fee_rule", f"Breaks {country.name} hiring rules",
                country.fee_rule, "high", "country", 10,
            ))

    return findings
