"""Runs every test letter through the checker and compares the result with the expected answer.

Run from backend/:
    .venv/Scripts/python samples/make_samples.py     # once, to create the files
    .venv/Scripts/python samples/evaluate.py         # add -v to list each letter's findings

PASS     REAL letter scored LOW, or FAKE letter scored HIGH (job ads and messages from messages.py too)
BORDER   letter scored MEDIUM (the user is told to verify - acceptable, but worth improving)
FAIL     REAL letter scored HIGH (false alarm) or FAKE letter scored LOW (missed scam)

Domain lookups are switched off because the test companies are fictional and their domains don't exist.
Agencies are checked against samples/nea_agencies_sample.csv, a fictional NEA list.
The AI check runs only if ANTHROPIC_API_KEY is set (each AI-checked letter costs a small API fee).
"""

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

os.environ["ENABLE_DOMAIN_LOOKUP"] = "false"
os.environ["ENABLE_WEBSITE_CHECK"] = "false"
os.environ["ENABLE_NEA_LIVE_LOOKUP"] = "false"
os.environ["ENABLE_UK_SPONSOR_LOOKUP"] = "false"
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "samples"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env", override=False)
os.environ["ENABLE_DOMAIN_LOOKUP"] = "false"
# The test letters' agencies are fictional, so check them against a fictional NEA list.
# Import it fresh each run: undated or stale lists are ignored, which would skip every agency check.
from app.nea_dataset import import_export  # noqa: E402

NEA_SAMPLE = Path(tempfile.mkdtemp()) / "nea_agencies.csv"
import_export(BACKEND / "samples" / "nea_agencies_sample.csv", NEA_SAMPLE, retrieved_at=datetime.now(timezone.utc).isoformat())
os.environ["NEA_AGENCIES_CSV"] = str(NEA_SAMPLE)

from app.analyzer import analyze_letter  # noqa: E402
from app import ai  # noqa: E402
from letters import LETTERS  # noqa: E402
from messages import MESSAGES  # noqa: E402

GENERATED = BACKEND / "samples" / "generated"
GOOD = {"REAL": "LOW", "FAKE": "HIGH"}
BAD = {"REAL": "HIGH", "FAKE": "LOW"}


def verdict(expected: str, level: str) -> str:
    if level == GOOD[expected]:
        return "PASS"
    if level == BAD[expected]:
        return "FAIL"
    return "BORDER"


def main() -> int:
    verbose = "-v" in sys.argv
    if not GENERATED.exists():
        print("Run samples/make_samples.py first.")
        return 1

    # (label, file contents, file name, kind, expected, note)
    cases = [(l.file, (GENERATED / l.file).read_bytes(), l.file, "letter", l.expected, l.note) for l in LETTERS]
    for photo in sorted(GENERATED.glob("*_photo.*")):
        source = photo.name.split("_photo")[0] + ".pdf"
        expected = next(l.expected for l in LETTERS if l.file == source)
        cases.append((photo.name, photo.read_bytes(), photo.name, "letter", expected, f"photo of {source}"))
    # Job ads and chat/SMS messages are pasted as text and checked with the gentler message rules.
    cases += [(f"[msg] {m.name}", m.text.encode(), "message.txt", "message", m.expected, m.note) for m in MESSAGES]

    counts = {"PASS": 0, "BORDER": 0, "FAIL": 0, "SKIPPED": 0}
    print(f"AI analysis: {'ON' if ai.is_enabled() else 'OFF (rules only)'}\n")
    print(f"{'result':7} {'expected':8} {'got':6} {'score':>5}  file")
    print("-" * 78)
    for file, data, file_name, kind, expected, note in cases:
        report = analyze_letter(data, file_name, kind=kind)
        if report.extraction_method.endswith("none"):
            counts["SKIPPED"] += 1
            print(f"{'SKIP':7} {expected:8} {'-':6} {'-':>5}  {file}  (no OCR available for images)")
            continue
        result = verdict(expected, report.risk_level)
        counts[result] += 1
        print(f"{result:7} {expected:8} {report.risk_level:6} {report.score:5}  {file}")
        if verbose or result != "PASS":
            print(f"{'':30}{note}")
            for f in report.findings:
                print(f"{'':30}{f.points:+4}  {f.title}")

    checked = counts["PASS"] + counts["BORDER"] + counts["FAIL"]
    print("-" * 78)
    print(
        f"{counts['PASS']}/{checked} correct, {counts['BORDER']} borderline, {counts['FAIL']} wrong"
        + (f", {counts['SKIPPED']} skipped" if counts["SKIPPED"] else "")
    )
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
