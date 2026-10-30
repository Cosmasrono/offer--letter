import io
import json
import os
import unittest
from unittest.mock import patch

from app import ai
from app.memory_assessment import assess_memory
from app.models import AIVerdict, AnalysisReport, Entities, MemoryMatch
from app.pdf_report import _html


def report():
    return AnalysisReport(file_name="fixture.txt", kind="letter", risk_level="HIGH", score=60, country="AE",
        country_name="UAE", company_name="Example Ltd", job_title="Tester", summary="Matches a reviewed scam pattern.",
        findings=[], advice=[], verify_links=[], entities=Entities(), text_excerpt="Current letter only", extraction_method="plain-text",
        ai_used=False, warnings=[], checks_not_run=[], fingerprint=None,
        memory_matches=[MemoryMatch(status="CONFIRMED_SCAM", matching_details=["PHONE:254700000000"],
                                   template_similarity=.95, case_count=1, contact_and_template=True)])


def verdict(level="HIGH"):
    return AIVerdict(risk_level=level, confidence=80, summary="This letter reuses details from a reviewed scam.",
                     red_flags=[], trust_signals=[], company_name=None, job_title=None, country=None)


class MemoryAssessmentTests(unittest.TestCase):
    def test_retrieved_evidence_is_in_the_actual_ai_prompt(self):
        answer = {"choices": [{"finish_reason": "stop", "message": {"content": verdict().model_dump_json()}}]}
        with patch.dict(os.environ, {"AI_PROVIDERS": "agentrouter", "AGENTROUTER_API_KEY": "test-key", "AGENTROUTER_BASE_URL": "https://example.test/v1"}), \
             patch.object(ai, "urlopen", return_value=io.BytesIO(json.dumps(answer).encode())) as request:
            result = assess_memory(report())
        self.assertTrue(result["ai_used"])
        content = json.loads(request.call_args.args[0].data)["messages"][1]["content"]
        self.assertIn("retrieved_case_evidence", content)
        self.assertIn("CONFIRMED_SCAM", content)
        self.assertIn("unconfirmed", content)
        self.assertIn("Current letter only", content)
        self.assertEqual(request.call_args.kwargs["timeout"], 12)

    def test_ai_cannot_lower_a_database_based_warning(self):
        current = report()
        with patch.object(ai, "analyze", return_value=(verdict("LOW"), None)):
            result = assess_memory(current)
        self.assertEqual(result["summary"], current.summary)
        self.assertFalse(result["ai_used"])
        self.assertEqual(current.score, 60)
        self.assertIn("retained", result["warning"])

    def test_unavailable_ai_keeps_memory_and_no_match_needs_no_extra_ai_call(self):
        current = report()
        with patch.object(ai, "analyze", return_value=(None, "Provider unavailable")):
            result = assess_memory(current)
        self.assertEqual(result["summary"], current.summary)
        self.assertEqual(current.memory_matches[0].status, "CONFIRMED_SCAM")
        current.memory_matches = []
        with patch.object(ai, "analyze") as request:
            self.assertFalse(assess_memory(current)["ai_used"])
            request.assert_not_called()

    def test_pdf_distinguishes_reviewed_status_from_the_original_scan(self):
        current = report()
        current.scam_status = "CONFIRMED_SCAM"
        current.review_note = "Employer independently confirmed no such offer was issued."
        content = _html(current, "case-id", "today", None)
        self.assertIn("Confirmed scam - reviewed", content)
        self.assertIn("Original scan assessment", content)
        self.assertIn("Matches to earlier scam cases", content)
        self.assertIn(current.review_note, content)


if __name__ == "__main__":
    unittest.main()
