"""Employer records from the official UK Companies House API, with explicit uncertainty."""

import base64
import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Entities, Finding, SourceCheck
from .public_web import tls_context

API = "https://api.company-information.service.gov.uk"
PUBLIC = "https://find-and-update.company-information.service.gov.uk"
TIMEOUT_SECONDS = 8


def _name(value: str) -> str:
    words = re.findall(r"[a-z0-9]+", value.casefold().replace("&", " and "))
    return " ".join({"limited": "ltd"}.get(word, word) for word in words)


def _request(path: str, key: str):
    request = Request(API + path, headers={
        "Authorization": "Basic " + base64.b64encode((key + ":").encode()).decode(),
        "Accept": "application/json", "User-Agent": "OfferLetterChecker/0.1",
    })
    with urlopen(request, timeout=TIMEOUT_SECONDS, context=tls_context()) as response:
        content = response.read(256_001)
        if len(content) > 256_000:
            raise ValueError("Registry response exceeded limit")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Invalid registry response")
        return data


def employer_check(entities: Entities, country: str | None) -> tuple[SourceCheck, list[Finding]]:
    company = entities.company_name or "Employer not identified"
    number = entities.company_registration_number
    if number and re.fullmatch(r"\d{1,8}", number):
        number = number.zfill(8)
    if number and not re.fullmatch(r"(?:\d{8}|[A-Z]{2}\d{6})", number):
        number = None
    link = PUBLIC + (f"/company/{number}" if number else "/search/companies?" + urlencode({"q": company}))
    result = SourceCheck(
        check="employer", status="UNVERIFIED", subject=company,
        source_name="Companies House" if country == "GB" else "Official employer registry",
        source_url=link if country == "GB" else "",
        checked_at=datetime.now(timezone.utc).isoformat(),
        detail="Automatic employer registry lookup is not available for this destination. Use the official verification links.",
    )
    if country != "GB":
        return result, []
    if not entities.company_name:
        result.detail = "No employer name could be extracted to compare against the company register."
        return result, []
    key = os.getenv("COMPANIES_HOUSE_API_KEY", "").strip()
    if not key:
        result.status = "UNAVAILABLE"
        result.detail = "The Companies House connection is not configured. Check the employer through the source link."
        return result, []
    try:
        if not number:
            search = _request("/search/companies?" + urlencode({"q": company, "items_per_page": 5}), key)
            items = search.get("items", [])
            if not isinstance(items, list) or not isinstance(search.get("total_results"), int):
                raise ValueError("Invalid search results")
            matches = [item for item in items if isinstance(item, dict) and _name(str(item.get("title", ""))) == _name(company)]
            if search["total_results"] > 5 or len(matches) != 1:
                result.detail = "The name search did not identify one unambiguous employer. Confirm the company registration number directly."
                return result, []
            number = str(matches[0].get("company_number", ""))
            if not re.fullmatch(r"(?:\d{8}|[A-Z]{2}\d{6})", number):
                raise ValueError("Invalid company number")
        result.source_url = PUBLIC + f"/company/{number}"
        record = _request(f"/company/{number}", key)
        record_name = record.get("company_name")
        status = record.get("company_status")
        if not isinstance(record_name, str) or not record_name or not isinstance(status, str) or record.get("company_number") != number:
            raise ValueError("Incomplete company profile")
    except HTTPError as error:
        if error.code == 404 and number:
            result.status = "NOT_FOUND"
            result.detail = "The stated company number was not found in Companies House. Check the number for transcription errors."
        else:
            result.status = "UNAVAILABLE"
            result.detail = "Companies House could not be checked. Retry later or use the official source link."
        return result, []
    except (URLError, TimeoutError, OSError, ValueError, TypeError, KeyError):
        result.status = "UNAVAILABLE"
        result.detail = "Companies House could not be checked. No conclusion about the employer was drawn from this failure."
        return result, []

    result.record_name, result.record_id, result.record_status = record_name, number, status
    findings = []
    if _name(record_name) != _name(company):
        result.status = "MISMATCH"
        result.detail = f"The stated registration number belongs to {record_name}, which differs from the employer name read from the document. Check both names and the number."
        findings.append(Finding(id="employer_registration_mismatch", title="Employer name differs from the registered company",
                                detail=result.detail, severity="high", category="company", points=20))
    elif status != "active":
        result.status = "MISMATCH"
        result.detail = f"The employer name matches, but Companies House reports the company status as {status}. Confirm whether it can fulfil this offer."
        findings.append(Finding(id="employer_registry_status", title="Employer registry status needs checking",
                                detail=result.detail, severity="high", category="company", points=20))
    else:
        result.status = "MATCHED"
        result.detail = "The employer name matches an active company record. This confirms the register entry, not who sent the letter or whether the job exists."
    return result, findings
