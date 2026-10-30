import os
import unittest
import unicodedata
from unittest.mock import patch

import pymupdf

from app.analyzer import analyze_letter
from app.models import AnalysisReport, Entities, SourceCheck, SourceComparison
from app.pdf_report import render_pdf


class ReportEvidenceTests(unittest.TestCase):
    def test_analysis_returns_unavailable_sources_without_claiming_a_match(self):
        with patch.dict(os.environ, {"COMPANIES_HOUSE_API_KEY": "", "ENABLE_DOMAIN_LOOKUP": "false", "ENABLE_WEBSITE_CHECK": "false", "ENABLE_NEA_LIVE_LOOKUP": "false", "NEA_AGENCIES_CSV": "missing-fixture.csv"}), patch("app.ai.is_enabled", return_value=False):
            report = analyze_letter(b"Example Employer Ltd\nCompany registration number: 12345678\nSalary GBP 35000. Start date 1 January 2027.", "letter.txt", "GB")
        self.assertEqual(len(report.source_checks), 3)
        self.assertEqual({check.status for check in report.source_checks}, {"UNAVAILABLE", "NOT_APPLICABLE"})
        self.assertTrue(any("company-register" in line for line in report.checks_not_run))

    def test_pdf_contains_source_evidence_and_handles_older_reports(self):
        report = AnalysisReport(file_name="fixture.txt", kind="letter", risk_level="LOW", score=0, country="GB",
            country_name="United Kingdom", company_name="Example Employer Ltd", job_title="Tester", summary="Confirm directly.",
            findings=[], advice=[], verify_links=[], entities=Entities(), text_excerpt="Fictional fixture", extraction_method="plain-text",
            ai_used=False, warnings=[], checks_not_run=[], fingerprint=None)
        self.assertEqual(report.source_checks, [])
        report.source_checks = [SourceCheck(check="employer", status="MATCHED", subject="Example Employer Ltd", source_name="Companies House",
            source_url="https://find-and-update.company-information.service.gov.uk/company/12345678", checked_at="2026-10-26T10:00:00Z",
            detail="Record match only; offer not authenticated.", record_id="12345678")]
        content = render_pdf(report, "test-report", "26 October 2026")
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            text = unicodedata.normalize("NFKC", "\n".join(page.get_text() for page in pdf))
        self.assertIn("Company, website and agency evidence", text)
        self.assertIn("Companies House", text)
        self.assertIn("12345678", text)
        self.assertIn("offer not authenticated", text)

    def test_pdf_contains_the_letter_and_website_comparison(self):
        report = AnalysisReport(file_name="fixture.txt", kind="letter", risk_level="MEDIUM", score=30, country=None,
            country_name=None, company_name="Example Employer Ltd", job_title=None, summary="Confirm the identity conflict.",
            findings=[], advice=[], verify_links=[], entities=Entities(), text_excerpt="Fictional fixture", extraction_method="plain-text",
            ai_used=False, warnings=[], checks_not_run=[], fingerprint=None,
            source_checks=[SourceCheck(check="website", status="MISMATCH", subject="Example Employer Ltd", source_name="Public website content",
                source_url="https://example.com/", checked_at="2026-10-27T10:00:00Z", detail="Identity needs checking.", checked_pages=["https://example.com/contact"],
                comparisons=[SourceComparison(field="Company registration number", letter_value="12345678", source_value="87654321", status="MISMATCH", detail="Numbers differ.")])])
        with pymupdf.open(stream=render_pdf(report, "test-report", "27 October 2026"), filetype="pdf") as pdf:
            text = unicodedata.normalize("NFKC", "\n".join(page.get_text() for page in pdf))
        for expected in ["12345678", "87654321", "Numbers differ", "https://example.com/contact"]:
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
