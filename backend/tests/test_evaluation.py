import json
import tempfile
import unittest
from pathlib import Path

from tools.evaluate_real import load_cases, metrics


class EvaluationTests(unittest.TestCase):
    def test_metrics_expose_misses_false_alarms_and_borderline_cases(self):
        rows = [dict(id=str(i), expected=label, dataset="real", status="checked", risk_level=level, duration_ms=10)
                for i, (label, level) in enumerate([("SCAM", "LOW"), ("SCAM", "HIGH"), ("GENUINE", "HIGH"), ("GENUINE", "LOW"), ("SCAM", "MEDIUM")])]
        results = metrics(rows)
        self.assertEqual(results["missed_scams_scored_low"], 1)
        self.assertEqual(results["genuine_scored_high"], 1)
        self.assertEqual(results["borderline_cases"], 1)
        self.assertEqual(results["high_risk_precision"], .5)
        self.assertFalse(results["real_sample_target_met"])

    def test_synthetic_documents_and_unreadable_real_files_do_not_satisfy_target(self):
        rows = [dict(id=str(i), expected="SCAM" if i % 2 else "GENUINE", dataset="synthetic", status="checked", risk_level="HIGH", duration_ms=10) for i in range(100)]
        rows.append(dict(id="unreadable", expected="SCAM", dataset="real", status="unreadable", duration_ms=20))
        result = metrics(rows)
        self.assertEqual(result["real_documents_checked"], 0)
        self.assertEqual(result["unreadable"], 1)
        self.assertFalse(result["real_sample_target_met"])

    def test_manifest_rejects_path_escape_and_duplicate_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("Sample")
            manifest = root / "manifest.jsonl"
            row = dict(id="a", path="a.txt", label="SCAM", dataset="real", label_source="Confirmed case")
            manifest.write_text(json.dumps(row) + "\n" + json.dumps({**row, "id": "b"}))
            with self.assertRaisesRegex(ValueError, "Duplicate document"):
                load_cases(manifest, root)
            manifest.write_text(json.dumps({**row, "path": "../outside.txt"}))
            with self.assertRaisesRegex(ValueError, "inside data-root"):
                load_cases(manifest, root)


if __name__ == "__main__":
    unittest.main()
