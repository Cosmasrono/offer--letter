"""Evaluate labelled documents without publishing their contents or mistaking fixtures for real validation."""

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_cases(manifest: Path, data_root: Path) -> list[dict]:
    data_root = data_root.resolve()
    cases, ids, hashes = [], set(), set()
    for number, line in enumerate(manifest.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("Expected an object")
            if not isinstance(row.get("id"), str) or not row["id"].strip() or len(row["id"]) > 100:
                raise ValueError("Provide a short anonymous case id")
            if row["id"] in ids or row.get("label") not in {"GENUINE", "SCAM"}:
                raise ValueError("Duplicate id or invalid label")
            if row.get("dataset") not in {"real", "synthetic"} or not str(row.get("label_source", "")).strip():
                raise ValueError("Declare dataset real/synthetic and how the label was confirmed")
            if row.get("kind", "letter") not in {"letter", "message"}:
                raise ValueError("Invalid document kind")
            path = (data_root / row["path"]).resolve()
            if not path.is_relative_to(data_root) or not path.is_file():
                raise ValueError("Document must exist inside data-root")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in hashes:
                raise ValueError("Duplicate document bytes; duplicates must not inflate sample counts")
            ids.add(row["id"])
            hashes.add(digest)
            cases.append({**row, "resolved_path": path})
        except (ValueError, OSError, KeyError, TypeError) as error:
            raise ValueError(f"Invalid manifest row {number}: {error}") from None
    if not cases:
        raise ValueError("The manifest has no cases")
    return cases


def metrics(results: list[dict], minimum_real: int = 100) -> dict:
    checked = [row for row in results if row["status"] == "checked"]
    matrix = {label: {level: 0 for level in ["LOW", "MEDIUM", "HIGH"]} for label in ["GENUINE", "SCAM"]}
    for row in checked:
        matrix[row["expected"]][row["risk_level"]] += 1
    scams, genuine = sum(matrix["SCAM"].values()), sum(matrix["GENUINE"].values())
    high = matrix["SCAM"]["HIGH"] + matrix["GENUINE"]["HIGH"]
    ratio = lambda n, d: round(n / d, 4) if d else None
    latencies = sorted(row["duration_ms"] for row in results)
    real = [row for row in checked if row["dataset"] == "real"]
    real_classes = Counter(row["expected"] for row in real)
    by_dataset = {kind: {label: {level: 0 for level in ["LOW", "MEDIUM", "HIGH"]} for label in ["GENUINE", "SCAM"]}
                  for kind in ["real", "synthetic"]}
    for row in checked:
        by_dataset[row["dataset"]][row["expected"]][row["risk_level"]] += 1
    return {
        "total": len(results), "checked": len(checked), "errors": sum(row["status"] == "error" for row in results),
        "unreadable": sum(row["status"] == "unreadable" for row in results),
        "confusion_matrix": matrix, "confusion_matrix_by_dataset": by_dataset,
        "missed_scams_scored_low": matrix["SCAM"]["LOW"],
        "genuine_scored_high": matrix["GENUINE"]["HIGH"],
        "borderline_cases": matrix["SCAM"]["MEDIUM"] + matrix["GENUINE"]["MEDIUM"],
        "scam_warning_recall_medium_or_high": ratio(scams - matrix["SCAM"]["LOW"], scams),
        "scam_high_risk_recall": ratio(matrix["SCAM"]["HIGH"], scams),
        "high_risk_precision": ratio(matrix["SCAM"]["HIGH"], high),
        "genuine_false_alarm_rate": ratio(matrix["GENUINE"]["HIGH"], genuine),
        "real_documents_checked": len(real), "minimum_real_target": minimum_real,
        "real_sample_target_met": len(real) >= minimum_real and all(real_classes[label] for label in ["GENUINE", "SCAM"]),
        "latency_ms": {"median": round(statistics.median(latencies), 1) if latencies else None,
                       "p95": latencies[min(len(latencies) - 1, max(0, math.ceil(len(latencies) * .95) - 1))] if latencies else None},
        "within_one_minute": sum(row["duration_ms"] < 60_000 and row["status"] == "checked" for row in results),
        "scope": "Backend analysis only. Excludes the frontend scam database, payment, and network time to the browser.",
        "note": "Labels and real/synthetic declarations are supplied by the dataset owner. A sample-count target is not an accuracy guarantee.",
    }


def evaluate(cases: list[dict], *, online: bool = False) -> list[dict]:
    from app import ai
    from app.analyzer import analyze_letter
    results = []
    with ExitStack() as context:
        if not online:
            context.enter_context(patch.dict(os.environ, {"ENABLE_DOMAIN_LOOKUP": "false", "COMPANIES_HOUSE_API_KEY": "", "ENABLE_WEBSITE_CHECK": "false", "ENABLE_NEA_LIVE_LOOKUP": "false", "ENABLE_UK_SPONSOR_LOOKUP": "false"}))
            context.enter_context(patch.object(ai, "is_enabled", return_value=False))
        for case in cases:
            start = time.perf_counter()
            result = {"id": case["id"], "expected": case["label"], "dataset": case["dataset"]}
            try:
                path = case["resolved_path"]
                report = analyze_letter(path.read_bytes(), path.name, case.get("country"), case.get("kind", "letter"))
                result.update({"status": "checked" if report.text_excerpt.strip() else "unreadable",
                               "risk_level": report.risk_level, "score": report.score,
                               "ai_used": report.ai_used, "extraction_method": report.extraction_method,
                               "checks_not_run_count": len(report.checks_not_run),
                               "registry_outcomes": {check.check: check.status for check in report.source_checks}})
            except Exception as error:
                # Class names aid debugging without copying private document text or provider responses into results.
                result.update({"status": "error", "error_type": type(error).__name__})
            result["duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
            results.append(result)
            print(f"{case['id']}: {result['status']}", flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSONL manifest of labelled files")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Aggregate metrics and anonymous case outcomes")
    parser.add_argument("--minimum-real", type=int, default=100)
    parser.add_argument("--online", action="store_true", help="Use configured AI, domain, and registry services; may incur provider charges")
    args = parser.parse_args()
    if args.minimum_real < 100:
        parser.error("The real-document validation target must be at least 100")
    try:
        cases = load_cases(args.manifest, args.data_root)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    if args.output.resolve() == args.manifest.resolve() or any(args.output.resolve() == case["resolved_path"] for case in cases):
        parser.error("Output must not overwrite the manifest or an input document")
    if args.online:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    results = evaluate(cases, online=args.online)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "mode": "online" if args.online else "offline",
              "metrics": metrics(results, args.minimum_real), "cases": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    print(f"Saved anonymous evaluation outcomes to {args.output}")
    return 1 if report["metrics"]["errors"] or report["metrics"]["missed_scams_scored_low"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
