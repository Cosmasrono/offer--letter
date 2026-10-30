"""Import and inspect dated NEA registry snapshots. No requests happen during individual scans."""

import csv
import hashlib
import io
import json
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SOURCE_URL = "https://www.neaims.go.ke/EmploymentAgencyList.aspx"
FIELDS = ["agency_name", "licence_number", "expiry_date", "status", "email", "website"]


class RegistryHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row, self.cell = None, None


def parse_export(content: str) -> list[dict[str, str]]:
    """Accept the official HTML table or a CSV exported from it."""
    if "<table" in content.lower():
        parser = RegistryHTML()
        parser.feed(content)
        rows = parser.rows
    else:
        rows = list(csv.reader(io.StringIO(content)))
    header_at = next((i for i, row in enumerate(rows)
                      if any("agency" in c.lower() and "name" in c.lower() for c in row)
                      and any("reg" in c.lower() or "licen" in c.lower() for c in row)), None)
    if header_at is None:
        raise ValueError("No NEA agency table was found; the existing dataset has not been replaced.")
    headers = [c.lower().replace("_", " ") for c in rows[header_at]]
    def index(*labels):
        return next((i for i, c in enumerate(headers) if any(label in c for label in labels)), None)
    columns = {
        "agency_name": index("agency name"), "licence_number": index("reg no", "licence", "license"),
        "expiry_date": index("expiry", "expiration"), "status": index("status"),
        "email": index("e-mail", "email"), "website": index("website"),
    }
    if any(columns[field] is None for field in ["agency_name", "licence_number", "expiry_date", "status"]):
        raise ValueError("Required NEA columns are missing; the existing dataset has not been replaced.")
    records, seen = [], {}
    for row in rows[header_at + 1:]:
        if len(row) != len(headers):
            continue
        record = {name: row[i].strip() if i is not None else "" for name, i in columns.items()}
        if not record["agency_name"] or not record["licence_number"]:
            continue
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                record["expiry_date"] = datetime.strptime(record["expiry_date"], fmt).date().isoformat()
                break
            except ValueError:
                pass
        else:
            raise ValueError("An agency expiry date could not be parsed; the existing dataset has not been replaced.")
        if record["status"].lower() not in {"valid", "active", "expired", "revoked", "suspended", "cancelled", "canceled", "inactive", "deregistered", "withdrawn"}:
            raise ValueError("An agency status could not be parsed; the existing dataset has not been replaced.")
        key = record["licence_number"].upper()
        if key in seen and seen[key] != record:
            raise ValueError("Conflicting duplicate agency licences were found; review the export before importing.")
        if key not in seen:
            records.append(record)
            seen[key] = record
    if not records:
        raise ValueError("The export contained no agency records; the existing dataset has not been replaced.")
    return records


def import_export(source: Path, destination: Path, *, retrieved_at: str) -> dict:
    timestamp = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
        raise ValueError("The retrieval date must include a timezone and cannot be in the future.")
    records = parse_export(source.read_text(encoding="utf-8-sig"))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(records)
    content = buffer.getvalue().encode("utf-8")
    metadata = {
        "source_name": "NEA public employment-agency register", "source_url": SOURCE_URL,
        "retrieved_at": timestamp.isoformat(), "imported_at": datetime.now(timezone.utc).isoformat(),
        "records": len(records), "sha256": hashlib.sha256(content).hexdigest(),
        "coverage": "Export snapshot; absence is not proof of unlicensed activity.",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    meta = destination.with_suffix(".metadata.json")
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".csv.tmp", delete=False) as temporary:
        temporary.write(content)
        data_tmp = Path(temporary.name)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".json.tmp", delete=False) as temporary:
        temporary.write((json.dumps(metadata, indent=2) + "\n").encode())
        meta_tmp = Path(temporary.name)
    try:
        data_tmp.replace(destination)
        meta_tmp.replace(meta)
    finally:
        data_tmp.unlink(missing_ok=True)
        meta_tmp.unlink(missing_ok=True)
    return metadata


def dataset_metadata(path: Path, *, content: bytes | None = None) -> dict:
    try:
        metadata = json.loads(path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
        timestamp = datetime.fromisoformat(metadata["retrieved_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return {}
        if metadata.get("sha256") != hashlib.sha256(path.read_bytes() if content is None else content).hexdigest():
            return {}
        age = (datetime.now(timezone.utc) - timestamp).total_seconds() / 86400
        return {**metadata, "fresh": 0 <= age <= 30}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}
