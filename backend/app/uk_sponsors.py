"""Current UK sponsor-register comparisons, with dated evidence and no private CoS-number lookups."""

import csv
import io
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .models import Finding, SourceCheck, SourceComparison
from .public_web import WebUnavailable, fetch_public, public_url

REGISTER_URL = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
_cache = {"until": 0, "dataset": None, "error": None}
_lock = threading.Lock()


def name_key(value: str) -> str:
    return " ".join("ltd" if word == "limited" else word for word in re.findall(r"[a-z0-9]+", value.casefold().replace("&", " and ")))


class RegisterLinks(HTMLParser):
    def __init__(self, content: str):
        super().__init__()
        self.urls = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "") or ""
        try:
            url = public_url(urljoin(REGISTER_URL, href))
        except WebUnavailable:
            return
        parts = urlsplit(url)
        if parts.hostname == "assets.publishing.service.gov.uk" and parts.path.lower().endswith(".csv") and re.search(r"worker.*register", parts.path, re.I):
            self.urls.append(url)


@dataclass
class SponsorDataset:
    rows: dict[str, list[dict[str, str]]]
    source_url: str
    published: date
    retrieved_at: str
    count: int


def parse_register(content: str, source_url: str, published: date) -> SponsorDataset:
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    fields = {"Organisation Name", "Town/City", "County", "Type & Rating", "Route"}
    if not fields <= set(reader.fieldnames or []):
        raise WebUnavailable("The official sponsor register format was not recognized.")
    rows, count = {}, 0
    for row in reader:
        if None in row or any(row.get(field) is None for field in fields) or not row["Organisation Name"].strip() or not row["Route"].strip():
            raise WebUnavailable("The sponsor register contains incomplete rows.")
        clean = {field: row[field].strip() for field in fields}
        key = name_key(clean["Organisation Name"])
        if not key:
            raise WebUnavailable("The sponsor register contains an unreadable organisation name.")
        rows.setdefault(key, []).append(clean)
        count += 1
    if not count:
        raise WebUnavailable("The sponsor register contained no records.")
    return SponsorDataset(rows, source_url, published, datetime.now(timezone.utc).isoformat(), count)


def current_register() -> SponsorDataset:
    with _lock:
        if time.monotonic() < _cache["until"]:
            dataset = _cache["dataset"]
            if dataset is None:
                raise WebUnavailable(_cache["error"] or "The sponsor register is temporarily unavailable.")
            if 0 <= (date.today() - dataset.published).days <= 7:
                return dataset
            raise WebUnavailable("The cached sponsor register is too old for a current comparison.")
        try:
            deadline = time.monotonic() + 35
            publication = fetch_public(REGISTER_URL, deadline=deadline, max_bytes=2_000_000, allowed_hosts={"www.gov.uk", "gov.uk"})
            choices = []
            for url in RegisterLinks(publication.text).urls:
                stamp = re.search(r"(\d{4}-\d{2}-\d{2})\.csv$", urlsplit(url).path)
                if stamp:
                    choices.append((date.fromisoformat(stamp.group(1)), url))
            if not choices:
                raise WebUnavailable("No dated official sponsor-register download was found.")
            published, source_url = max(choices)
            if not 0 <= (date.today() - published).days <= 7:
                raise WebUnavailable("The available sponsor register is undated, future-dated or too old for a current comparison.")
            response = fetch_public(source_url, deadline=deadline, max_bytes=25_000_000,
                                    content_types=("text/csv", "application/csv", "application/octet-stream"), allowed_hosts={"assets.publishing.service.gov.uk"})
            dataset = parse_register(response.text, response.url, published)
            _cache.update(until=time.monotonic() + 6 * 3600, dataset=dataset, error=None)
            return dataset
        except (WebUnavailable, ValueError, csv.Error, RecursionError) as error:
            _cache.update(until=time.monotonic() + 60, dataset=None, error="The current official sponsor register could not be read.")
            raise WebUnavailable("The current official sponsor register could not be read. No licensing conclusion was drawn from this failure.") from error


def sponsor_registry_check(company: str | None, required_route: str | None = "Skilled Worker") -> tuple[SourceCheck, list[Finding], list[str]]:
    result = SourceCheck(check="sponsor_registry", status="UNVERIFIED", subject=company or "Sponsor not identified",
                         source_name="Home Office register of licensed Worker and Temporary Worker sponsors", source_url=REGISTER_URL,
                         checked_at=datetime.now(timezone.utc).isoformat(), detail="")
    if not company or not name_key(company):
        result.detail = "The sponsor's legal name could not be read reliably. Confirm the original record with the sponsor."
        return result, [], [result.detail]
    if os.getenv("ENABLE_UK_SPONSOR_LOOKUP", "true").lower() != "true":
        result.status = "UNAVAILABLE"
        result.detail = "The current UK sponsor-register lookup is switched off on this server."
        return result, [], [result.detail]
    try:
        dataset = current_register()
    except WebUnavailable:
        result.status = "UNAVAILABLE"
        result.detail = "The current UK sponsor register could not be checked. No conclusion about licensing was drawn from this failure."
        return result, [], [result.detail]
    result.source_updated_at = dataset.published.isoformat()
    result.checked_pages = [REGISTER_URL, dataset.source_url]
    key = name_key(company)
    rows = dataset.rows.get(key, [])
    if not rows:
        # A near name is a lead to review, never an exact licence match.
        first = key.split()[0] if key.split() else ""
        similar = [(SequenceMatcher(None, key, candidate).ratio(), records) for candidate, records in dataset.rows.items()
                   if candidate.split()[0] == first and abs(len(candidate) - len(key)) <= 6]
        similar = [records for ratio, records in similar if ratio >= .9]
        if len(similar) == 1:
            candidate = similar[0][0]["Organisation Name"]
            result.status = "MISMATCH"
            result.record_name = candidate
            result.detail = f"The document names {company}, but the current register contains the similar name {candidate}. A spelling difference or trading name must be resolved; it is not an exact sponsor match."
            result.comparisons = [SourceComparison(field="Sponsor legal name", letter_value=company, source_value=candidate, status="MISMATCH", detail="Confirm the exact legal sponsor name. A similar name does not authenticate the sender or certificate.")]
            return result, [Finding(id="sponsor_registry_name_mismatch", title="Sponsor name differs from the current register", detail=result.detail, severity="high", category="company", points=20)], []
        result.status = "NOT_FOUND"
        result.detail = f"No exact entry for {company} was found among {dataset.count} current register rows published {dataset.published.isoformat()}. Current sponsorship permission is not established. Names may differ, and this does not establish historical licence status or prove a past CoS was forged."
        return result, [Finding(id="sponsor_registry_not_found", title="Named sponsor not found in the current Home Office register", detail=result.detail, severity="high", category="company", points=25)], []
    result.record_name = rows[0]["Organisation Name"]
    result.record_status = "; ".join(sorted({f'{row["Route"]} — {row["Type & Rating"]}' for row in rows}))
    if not required_route:
        result.detail = "The organisation appears in the current sponsor register, but the document's visa route could not be read reliably. The individual certificate remains unverified."
        return result, [], [result.detail]
    route_match = any(row["Route"].casefold() == required_route.casefold() for row in rows)
    result.comparisons = [SourceComparison(field="Sponsor legal name", letter_value=company, source_value=result.record_name, status="MATCHED", detail="The current register names this organisation; the sender and individual certificate remain unverified."),
                          SourceComparison(field="Sponsorship route", letter_value=required_route, source_value=", ".join(sorted({row["Route"] for row in rows})), status="MATCHED" if route_match else "MISMATCH", detail="Compared the claimed route with the routes published for this organisation."),
                          SourceComparison(field="Individual CoS and licence number", letter_value="Stated in the document", source_value="Not published in this register", status="UNVERIFIED", detail="The public register cannot authenticate an individual certificate number or match a printed sponsor licence number.")]
    if not route_match:
        result.status = "MISMATCH"
        result.detail = f"The organisation appears in the register, but {required_route} is not among its published routes. Confirm whether the correct sponsor and route were named."
        return result, [Finding(id="sponsor_registry_wrong_route", title="Sponsor is not listed for the claimed visa route", detail=result.detail, severity="high", category="company", points=25)], []
    result.status = "MATCHED"
    result.detail = f"The current register lists {company} for {required_route}. This matches a current public sponsor record, not the sender, individual CoS or job offer."
    return result, [], []
