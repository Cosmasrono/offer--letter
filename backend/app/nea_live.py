"""Read NEA's current public API, with legacy-table fallback and a short in-memory cache."""

import csv
import io
import json
import re
import threading
import time
from datetime import datetime, timezone

from .nea_dataset import FIELDS, SOURCE_URL, parse_export
from .public_web import WebUnavailable, fetch_public

_cache = {"until": 0, "content": None, "retrieved_at": None}
_lock = threading.Lock()
LIVE_URL = "https://neaims.go.ke/EmploymentAgencyList.aspx"
PUBLIC_REGISTER_URL = "https://neaims.go.ke/home/agencies-info"
API_URL = "https://api.neaims.go.ke/api/v1/agencies/public/list"
LIVE_FIELDS = [*FIELDS, "business_registration_number", "licence_type", "record_source_url"]


def api_records(payload: dict) -> list[dict[str, str]]:
    """Map the current public API without mistaking a PVT business number or LICENSE_PAID for a licence."""
    if not isinstance(payload, dict) or payload.get("success") is not True or not isinstance(payload.get("data"), list):
        raise ValueError("The NEA public list did not contain agency records.")
    records = []
    for row in payload["data"]:
        if not isinstance(row, dict) or not isinstance(row.get("instName"), str) or not row["instName"].strip():
            raise ValueError("An NEA agency record has no legal name.")
        for key in ("instCode", "instRegNo", "instExpiryDate", "instStatus", "instEmail", "instLicenseType"):
            if row.get(key) is not None and not isinstance(row[key], str):
                raise ValueError("An NEA record contained an unexpected field format.")
        expiry = (row.get("instExpiryDate") or "").split("T")[0]
        if expiry:
            datetime.strptime(expiry, "%Y-%m-%d")
        code = row.get("instCode") or ""
        licence = code if re.fullmatch(r"(?:RA|NEA)/[A-Z0-9/.-]+", code, re.I) else ""
        records.append(dict(agency_name=row["instName"].strip(), licence_number=licence, expiry_date=expiry,
                            status=row.get("instStatus") or "Unknown", email=row.get("instEmail") or "", website="",
                            business_registration_number=row.get("instRegNo") or "", licence_type=row.get("instLicenseType") or ""))
    if not records:
        raise ValueError("No agency records were returned by NEA.")
    return records


def live_dataset() -> tuple[bytes, str]:
    with _lock:
        if time.monotonic() < _cache["until"]:
            if _cache["content"] is None:
                raise WebUnavailable("The live NEA register is temporarily unavailable.")
            return _cache["content"], _cache["retrieved_at"]
        try:
            try:
                page = fetch_public(API_URL, max_bytes=4_000_000, content_types=("application/json",),
                                    allowed_hosts={"api.neaims.go.ke"},
                                    json_body={"page": 1, "size": 2000, "search": "", "verifiedOnly": None})
                records = api_records(json.loads(page.text))
            except (WebUnavailable, ValueError, TypeError, RecursionError):
                page = fetch_public(LIVE_URL, max_bytes=4_000_000,
                                    allowed_hosts={"www.neaims.go.ke", "neaims.go.ke"})
                records = parse_export(page.text)
            output = io.StringIO(newline="")
            for record in records:
                record["record_source_url"] = page.url
            writer = csv.DictWriter(output, fieldnames=LIVE_FIELDS)
            writer.writeheader()
            writer.writerows(records)
            content = output.getvalue().encode("utf-8")
            retrieved_at = datetime.now(timezone.utc).isoformat()
            _cache.update(until=time.monotonic() + 1800, content=content, retrieved_at=retrieved_at)
            return content, retrieved_at
        except (WebUnavailable, ValueError, RecursionError) as error:
            _cache.update(until=time.monotonic() + 60, content=None, retrieved_at=None)
            raise WebUnavailable("The live NEA register could not be read or its table format was unavailable.") from error
