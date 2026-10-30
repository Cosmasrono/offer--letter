"""Compare public website evidence with the letter. Website consistency never authenticates an offer."""

import json
import os
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit

from .entities import EMAIL_RE, PHONE_RE, domain_of, extract_entities
from .models import Entities, Finding, SourceCheck, SourceComparison
from .public_web import WebUnavailable, fetch_public, public_url
from .rules import FREE_EMAIL_DOMAINS

LEGAL_WORDS = {"ltd", "limited", "llc", "inc", "incorporated", "plc", "corp", "corporation", "gmbh"}
DIRECTORY_DOMAINS = {"facebook.com", "linkedin.com", "instagram.com", "x.com", "twitter.com", "youtube.com", "tiktok.com", "wikipedia.org",
                     "wikidata.org", "crunchbase.com", "bloomberg.com", "zoominfo.com", "dnb.com", "opencorporates.com", "glassdoor.com",
                     "indeed.com", "brightermonday.co.ke", "naukrigulf.com", "bayt.com", "gulftalent.com"}
# Words too common in company names to identify a brand inside a domain.
GENERIC_WORDS = {"the", "and", "group", "company", "companies", "international", "global", "services", "service", "holding", "holdings",
                 "recruitment", "agency", "agencies", "consultants", "consultancy", "manpower", "employment", "jobs", "careers", "career",
                 "solutions", "enterprises", "trading", "general", "official", "hotel", "hotels", "middle", "east", "africa", "kenya"}


def _name(value: str) -> str:
    return " ".join(word for word in re.findall(r"\w+", value.casefold().replace("&", " and ")) if word not in LEGAL_WORDS)


def _brand_words(company: str) -> list[str]:
    return [word for word in _name(company).split() if len(word) >= 4 and word not in GENERIC_WORDS]


def _carries_brand(host: str, brands: list[str]) -> bool:
    label = host.casefold().replace("-", "")
    return any(brand in label for brand in brands)


def _same_site(left: str, right: str) -> bool:
    return left == right or left.endswith("." + right) or right.endswith("." + left)


class SiteHTML(HTMLParser):
    def __init__(self, url: str, content: str):
        super().__init__(convert_charrefs=True)
        self.url, self.words, self.links, self.contacts, self.names = url, [], [], [], []
        self.hidden = 0
        self.json_parts = None
        self.feed(content)
        self.text = " ".join(" ".join(self.words).split())[:100_000]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "template", "svg"}:
            self.hidden += 1
            if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
                self.json_parts = []
        if self.hidden:
            return
        if tag == "a":
            href = attrs.get("href", "")
            if href.startswith(("mailto:", "tel:")):
                self.contacts.append(href.split(":", 1)[1].split("?", 1)[0])
            elif href:
                self.links.append(urljoin(self.url, href))

    def handle_data(self, value):
        if self.json_parts is not None:
            self.json_parts.append(value)
        elif not self.hidden:
            self.words.append(value)

    def handle_endtag(self, tag):
        if tag == "script" and self.json_parts is not None:
            try:
                self._organization(json.loads("".join(self.json_parts)))
            except (ValueError, RecursionError):
                pass
            self.json_parts = None
        if tag in {"script", "style", "noscript", "template", "svg"}:
            self.hidden = max(0, self.hidden - 1)

    def _organization(self, value, depth=0):
        if depth > 8:
            return
        if isinstance(value, list):
            for item in value[:30]:
                self._organization(item, depth + 1)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if isinstance(types, list) and any(item in {"Organization", "Corporation", "LocalBusiness", "EmploymentAgency"} for item in types if isinstance(item, str)):
                for key in ("legalName", "name"):
                    if isinstance(value.get(key), str):
                        self.names.append(value[key][:200])
            self._organization(value.get("@graph"), depth + 1)


def _comparison(field, letter, observed, status, detail):
    return SourceComparison(field=field, letter_value=letter or "Not stated", source_value=observed or "Not found in checked pages",
                            status=status, detail=detail)


def _discovery(entities: Entities, country: str | None, deadline: float) -> tuple[SourceCheck, list[str]]:
    check = SourceCheck(check="discovery", status="UNVERIFIED", subject=entities.company_name or "Employer not identified",
                        source_name="Independent company-name search", source_url="", checked_at=datetime.now(timezone.utc).isoformat(),
                        detail="Independent website discovery is not configured. Websites supplied in a letter may be impersonations.")
    if not entities.company_name:
        check.detail = "No employer name could be extracted for an independent website search."
        return check, []
    key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not key:
        return check, []
    brands = _brand_words(entities.company_name)
    query = f'"{entities.company_name[:180]}" {country or ""} official website'
    url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": 5})
    try:
        response = fetch_public(url, deadline=min(deadline, time.monotonic() + 6), max_bytes=200_000,
                                content_types=("application/json",), allowed_hosts={"api.search.brave.com"},
                                headers={"X-Subscription-Token": key})
        data = json.loads(response.text)
        results = data.get("web", {}).get("results", [])
        if not isinstance(results, list):
            raise ValueError()
        candidates = []
        for result in results[:5]:
            if not isinstance(result, dict) or not isinstance(result.get("url"), str):
                continue
            try:
                candidate = public_url(result["url"])
            except WebUnavailable:
                continue
            host = domain_of(candidate)
            if any(_same_site(host, directory) for directory in DIRECTORY_DOMAINS):
                continue
            # A search hit is a lead only. Read it before comparing any claims.
            title = str(result.get("title", ""))
            if (" " + _name(entities.company_name) + " ") in (" " + _name(title) + " ") or _carries_brand(host, brands):
                candidates.append("https://" + host + "/")
        # News and directory pages also mention the name; prefer hosts that carry the brand itself.
        candidates = sorted(dict.fromkeys(candidates), key=lambda site: not _carries_brand(domain_of(site), brands))
        check.source_url = "https://search.brave.com/search?" + urlencode({"q": query})
        check.detail = ("Company-name search found candidate websites: " + ", ".join(candidates[:3]) + ". Search results do not establish official ownership."
                        if candidates else "No clear company-name website candidate was found in the search results. This does not prove the employer is fake.")
        check.status = "UNVERIFIED" if candidates else "NOT_FOUND"
        return check, candidates
    except (WebUnavailable, ValueError, TypeError, AttributeError, RecursionError):
        check.status = "UNAVAILABLE"
        check.detail = "Independent company-name search was unavailable. No website ownership was established."
        return check, []


def _compare_site(entities: Entities, pages: list[SiteHTML], origin: str, confirmed_domains: list[str] = ()) -> tuple[SourceCheck, list[Finding]]:
    host = domain_of(origin)
    text = " ".join(page.text for page in pages)
    contacts = text + " " + " ".join(contact for page in pages for contact in page.contacts)
    normalized = " " + _name(text) + " "
    company_match = bool(entities.company_name and " " + _name(entities.company_name) + " " in normalized)
    agency_match = bool(entities.agency_name and " " + _name(entities.agency_name) + " " in normalized)
    names = list(dict.fromkeys(name for page in pages for name in page.names))
    company_match |= bool(entities.company_name and any(_name(name) == _name(entities.company_name) for name in names))
    agency_match |= bool(entities.agency_name and any(_name(name) == _name(entities.agency_name) for name in names))
    role = "Recruitment agency" if agency_match and not company_match else "Employer"
    subject = entities.agency_name if role == "Recruitment agency" else entities.company_name
    name_match = agency_match if role == "Recruitment agency" else company_match
    comparisons = [_comparison(role + " name", subject, ", ".join(names) or (subject if name_match else ""),
                               "MATCHED" if name_match else "UNVERIFIED", "Name appears on the website; ownership is not independently established."
                               if name_match else "The expected name was not identified in the pages read. Missing text alone is not a contradiction.")]
    published_emails = sorted({email.lower() for email in EMAIL_RE.findall(contacts)})[:20]
    published_phones = sorted(set(PHONE_RE.findall(contacts)))[:20]
    letter_emails = entities.agency_emails if role == "Recruitment agency" and entities.agency_emails else entities.emails
    matching_emails = sorted(set(email.lower() for email in letter_emails) & set(published_emails))
    comparisons.append(_comparison("Contact email", ", ".join(letter_emails), ", ".join(published_emails),
                                   "MATCHED" if matching_emails else "UNVERIFIED", "Published email matches: " + ", ".join(matching_emails)
                                   if matching_emails else "An unpublished email is not automatically fake. Confirm the sender using a published contact."))
    digits = lambda phone: re.sub(r"\D", "", phone).removeprefix("00")
    phone_match = bool({digits(p) for p in entities.phones} & {digits(p) for p in published_phones})
    comparisons.append(_comparison("Phone number", ", ".join(entities.phones), ", ".join(published_phones),
                                   "MATCHED" if phone_match else "UNVERIFIED", "Phone appears on a checked page." if phone_match
                                   else "No exact phone match was established. Websites may list only some company numbers."))
    findings = []
    # Only compare contacts whose role is clear. An agency may legitimately use its own domain.
    role_emails = (entities.agency_emails or (entities.emails if entities.company_name == entities.agency_name else [])) if role == "Recruitment agency" else (entities.emails if not entities.agency_name else [])
    # Domains the company's own pages were found to mention count as published.
    published_domains = {domain_of(email) for email in published_emails if domain_of(email) not in FREE_EMAIL_DOMAINS} | set(confirmed_domains)
    different_domains = bool(name_match and role_emails and published_domains
                             and not any(_same_site(domain_of(email), public_domain) for email in role_emails for public_domain in published_domains))
    if different_domains:
        comparisons.append(_comparison(role + " email domain", ", ".join(sorted({domain_of(email) for email in role_emails})),
                                       ", ".join(sorted(published_domains)), "MISMATCH",
                                       "The letter's contact domains differ from the website's published contact domains. An alternate hiring provider is possible; confirm it through a published contact."))
        findings.append(Finding(id=f"website_contact_domain_mismatch:{host}", title="Letter email domain differs from published website contacts",
                                detail=f"The website naming {subject} publishes {', '.join(published_emails)}; the letter uses {', '.join(role_emails)}. Confirm this alternate contact directly before sending money or documents.",
                                severity="medium", category="contact", points=20))
    if subject and names and not company_match and not agency_match and len(_name(subject)) >= 5:
        comparisons[0] = _comparison(role + " name", subject, ", ".join(names), "MISMATCH",
                                      "The website explicitly identifies a different organization. Brand names, group companies or an unrelated domain may explain the difference; confirm directly.")
        findings.append(Finding(id=f"website_identity_mismatch:{host}", title="Website identifies a different organization",
                                detail=f"The letter names {subject}; {host} identifies {', '.join(names)}. This domain has not been established as belonging to the named employer or agency.",
                                severity="medium", category="company", points=15))
    number = entities.company_registration_number if role == "Employer" else None
    page_numbers = {value for page in pages if (value := extract_entities(page.text).company_registration_number)}
    if number:
        mismatch = bool(company_match and page_numbers and number not in page_numbers)
        comparisons.append(_comparison("Company registration number", number, ", ".join(sorted(page_numbers)),
                                       "MISMATCH" if mismatch else "MATCHED" if number in page_numbers else "UNVERIFIED",
                                       "The company numbers differ; check whether subsidiaries or a copied identity explain the difference." if mismatch
                                       else "Compared the company number where publicly stated."))
        if mismatch:
            findings.append(Finding(id=f"website_registration_mismatch:{host}", title="Website and letter give different company numbers",
                                    detail=f"The letter gives {number}; pages at {host} name the employer but give {', '.join(sorted(page_numbers))}. Confirm the legal entity directly.",
                                    severity="high", category="company", points=25))
    comparisons.append(_comparison("Job, salary and offer terms", entities.job_title, "",
                                   "UNVERIFIED", "Public website pages cannot authenticate a private offer, salary or vacancy. Ask HR to confirm the reference and terms."))
    check = SourceCheck(check="website", status="MISMATCH" if findings else "MATCHED" if name_match and matching_emails else "UNVERIFIED",
                        subject=f"{subject or 'Unidentified company'} — {host}", source_name="Public website content", source_url=pages[0].url,
                        checked_at=datetime.now(timezone.utc).isoformat(), checked_pages=[page.url for page in pages], comparisons=comparisons,
                        detail="Compared the name, contact details and any company number in the pages read. A website may copy a real employer's information; consistency does not authenticate the sender or offer.")
    return check, findings


def _search_hosts(query: str, deadline: float) -> list[str] | None:
    """Hosts of the top search results, or None when the search could not run."""
    key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not key:
        return None
    url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": 10})
    try:
        response = fetch_public(url, deadline=min(deadline, time.monotonic() + 6), max_bytes=300_000,
                                content_types=("application/json",), allowed_hosts={"api.search.brave.com"},
                                headers={"X-Subscription-Token": key})
        results = json.loads(response.text).get("web", {}).get("results", [])
        return [domain_of(result["url"]) for result in results if isinstance(result, dict) and isinstance(result.get("url"), str)]
    except (WebUnavailable, ValueError, TypeError, AttributeError, RecursionError):
        return None


def _lookalike_domains(entities: Entities, candidates: list[str], supplied: list[str], deadline: float) -> tuple[SourceCheck | None, list[Finding], list[str]]:
    """Flag letter domains that carry the employer's brand but differ from the domain an independent search found.

    Also returns the letter domains confirmed as the company's own."""
    brands = _brand_words(entities.company_name or "")
    # Every brand-carrying host in the results counts as official: companies often run separate careers sites.
    officials = [host for host in (domain_of(site) for site in candidates) if brands and _carries_brand(host, brands)]
    if not officials:
        return None, [], []
    official = ", ".join(officials)
    suspects = [domain for domain in supplied if _carries_brand(domain, brands) and not any(_same_site(domain, host) for host in officials)]
    matched = [domain for domain in supplied if any(_same_site(domain, host) for host in officials)]
    # A real careers site is mentioned on the company's own pages; a look-alike is not.
    unconfirmed = []
    for domain in suspects[:2]:
        hosts = _search_hosts(f'"{domain}"', deadline)
        if hosts and any(_same_site(host, official_host) for host in hosts for official_host in officials):
            matched.append(domain)
        else:
            unconfirmed.append(domain)
    suspects = unconfirmed
    if not suspects and not matched:
        return None, [], []
    check = SourceCheck(check="website", status="MISMATCH" if suspects else "MATCHED", subject=f"{entities.company_name} — domain comparison",
                        source_name="Independent company-name search", source_url=candidates[0], checked_at=datetime.now(timezone.utc).isoformat(),
                        comparisons=[_comparison("Employer domain", ", ".join(suspects or matched), official, "MISMATCH" if suspects else "MATCHED",
                                                 "A domain that uses the company's name but is not its website is a common impersonation trick."
                                                 if suspects else "The letter uses a domain found by an independent search or mentioned on the company's own pages. Scammers can still copy a real domain into a letter.")],
                        detail=(f"An independent search found {official} for {entities.company_name}; the letter uses {', '.join(suspects)}, which those sites were not found to mention."
                                if suspects else f"The letter's domain matches {official} or is mentioned on those sites, found by an independent search."))
    findings = [Finding(id=f"lookalike_domain:{domain}", title="Domain imitates the company's name",
                        detail=f"The letter uses {domain}, but an independent search found {entities.company_name}'s website at {official}, "
                        f"and no page on those sites was found mentioning {domain}. Scammers register domains containing a real company's name. "
                        f"Check {official} yourself for a link to {domain} before replying.",
                        severity="high", category="company", points=25) for domain in suspects]
    return check, findings, matched


def website_checks(entities: Entities, country: str | None, agency_evidence: SourceCheck | None = None) -> tuple[list[SourceCheck], list[Finding], list[str]]:
    checked_at = datetime.now(timezone.utc).isoformat()
    if os.getenv("ENABLE_WEBSITE_CHECK", "true").lower() != "true":
        return [SourceCheck(check="website", status="UNAVAILABLE", subject=entities.company_name or "Employer website", source_name="Public website content",
                            source_url="", checked_at=checked_at, detail="Website content checks are switched off on this server.")], [], ["Website content and independent discovery: switched off on this server."]
    deadline = time.monotonic() + 18
    discovery, candidates = _discovery(entities, country, deadline)
    checks, findings, not_run = [discovery], [], []
    if not candidates:
        not_run.append("Independent employer website discovery: " + discovery.detail)
    supplied = [domain for domain in entities.domains if domain not in FREE_EMAIL_DOMAINS and not any(_same_site(domain, directory) for directory in DIRECTORY_DOMAINS)]
    lookalike_check, lookalike_findings, confirmed_domains = _lookalike_domains(entities, candidates, supplied, deadline)
    if lookalike_check:
        checks.append(lookalike_check)
        findings += lookalike_findings
    registered_sites = []
    if agency_evidence and agency_evidence.record_name:
        for item in agency_evidence.comparisons:
            if item.field == "Agency website" and item.source_value != "Not listed in source":
                host = domain_of(item.source_value)
                try:
                    registered_sites.append(public_url("https://" + host + "/"))
                except WebUnavailable:
                    pass
    origins = list(dict.fromkeys(candidates[:1] + registered_sites + ["https://" + domain + "/" for domain in supplied[:2]]))[:3]
    if not origins:
        checks.append(SourceCheck(check="website", status="UNVERIFIED", subject=entities.company_name or "Employer website", source_name="Public website content",
                                  source_url="", checked_at=checked_at, detail="No company website was supplied or independently discovered. A domain is never guessed from the company name."))
        not_run.append("Website content: no company website was available to read.")
    for origin in origins:
        pages, partial = [], False
        try:
            root = fetch_public(origin, deadline=deadline, max_bytes=2_000_000)  # large corporate home pages exceed the default
            pages.append(SiteHTML(root.url, root.text))
            host = domain_of(root.url)
            links = []
            for link in pages[0].links:
                try:
                    link = public_url(link)
                except WebUnavailable:
                    continue
                parts = urlsplit(link)
                if domain_of(link) == host and not parts.query and re.search(r"(?:^|/)(?:contact(?:-us)?|about(?:-us)?|careers?|jobs)(?:/|\.|$)", parts.path, re.I):
                    links.append(link)
            # Read the home page and at most two same-host identity/contact pages; never follow upload-specific links.
            links = sorted(set(links), key=lambda link: ("contact" not in link.lower(), link))[:2]
            for link in links:
                try:
                    page = fetch_public(link, deadline=deadline, allowed_hosts={urlsplit(root.url).hostname})
                    pages.append(SiteHTML(page.url, page.text))
                except WebUnavailable:
                    partial = True
            evidence, flags = _compare_site(entities, pages, origin, confirmed_domains)
            if not _same_site(domain_of(root.url), domain_of(origin)):
                evidence.detail += f" The requested domain redirected to a different website: {domain_of(root.url)}. Confirm why."
                evidence.status = "MISMATCH" if flags else "UNVERIFIED"
            if partial:
                evidence.detail += " Some linked pages were unavailable; comparisons cover the listed pages only."
                not_run.append(f"Website {domain_of(origin)}: some contact/about pages could not be read.")
            checks.append(evidence)
            findings.extend(flags)
        except (WebUnavailable, RecursionError):
            checks.append(SourceCheck(check="website", status="UNAVAILABLE", subject=domain_of(origin), source_name="Public website content", source_url="",
                                      checked_at=checked_at, detail="The website could not be read securely within the reading limit. No conclusion about the employer was drawn from this failure."))
            not_run.append(f"Website content for {domain_of(origin)}: could not be read.")
    return checks, findings, not_run
