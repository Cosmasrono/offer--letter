import unittest
import unicodedata
from datetime import date
from unittest.mock import patch

import pymupdf

from app.models import VisaReview
from app.pdf_report import render_pdf
from app.visas import analyze_visa, labelled_details, parse_date, preview_visa


VISA = """State of Qatar
Electronic Visa
Visa Number: 001234567890123
Holder Name: TEST APPLICANT PERSON
Passport Number: A00123456
Nationality: Kenya
Sponsor Name: Example Hospitality LLC
Profession: Cook
Visa Type: Work / Employment
Visa Issue Date: 2026-01-15
Visa Expiry Date: 2030-12-31
"""
OFFER = """Employment offer
Employee Name: TEST APPLICANT PERSON
Passport No.: A00123456
Employer Name: Example Hospitality LLC
Job Title: Cook
Salary: QAR 2000
This is a fictional test document.
"""


class VisaTests(unittest.TestCase):
    def scan(self, visa=VISA, offer=OFFER, country="QA", changes=None):
        preview = preview_visa(visa.encode(), "visa.txt", country, offer.encode() if offer is not None else None, "offer.txt" if offer is not None else None)
        details = preview.details.model_dump()
        details.update(changes or {})
        review = VisaReview(reviewed=True, details=details, offer_details=preview.offer_details)
        return analyze_visa(visa.encode(), "visa.txt", country, review, offer.encode() if offer is not None else None, "offer.txt" if offer is not None else None, today=date(2026, 10, 29))

    def test_matching_documents_remain_officially_unverified_and_preserve_leading_zeros(self):
        report = self.scan()
        self.assertEqual(report.kind, "visa")
        self.assertEqual(report.visa.details.visa_number, "001234567890123")
        self.assertEqual(report.risk_level, "LOW")
        self.assertTrue(all(item.status == "MATCHED" for item in report.visa.comparisons))
        self.assertEqual(report.visa.official_status, "NOT_CHECKED")
        self.assertEqual(report.verification.level, "PARTIAL")
        self.assertIsNone(report.fingerprint)
        self.assertEqual(report.entities.phones, [])

    def test_expired_visa_is_high_risk_for_new_use_without_historical_forgery_claim(self):
        report = self.scan(VISA.replace("2030-12-31", "2026-01-20"))
        self.assertEqual(report.risk_level, "HIGH")
        self.assertTrue(any(item.id == "visa_expired" for item in report.findings))
        self.assertIn("does not prove", report.findings[0].detail)

    def test_sponsor_passport_and_job_differences_are_shown_but_not_proof_of_fraud(self):
        offer = OFFER.replace("A00123456", "A00999999").replace("Example Hospitality LLC", "Other Employer LLC").replace("Job Title: Cook", "Job Title: Driver")
        report = self.scan(offer=offer)
        conflicts = [item for item in report.visa.comparisons if item.status == "MISMATCH"]
        self.assertEqual(len(conflicts), 3)
        self.assertIn("intermediary", next(item.detail for item in conflicts if item.field == "Employer / sponsor"))

    def test_name_reordering_is_supported_and_partial_name_is_unverified(self):
        report = self.scan(offer=OFFER.replace("TEST APPLICANT PERSON", "PERSON TEST APPLICANT"))
        self.assertEqual(report.visa.comparisons[0].status, "MATCHED")
        partial = self.scan(offer=OFFER.replace("TEST APPLICANT PERSON", "TEST APPLICANT"))
        self.assertEqual(partial.visa.comparisons[0].status, "UNVERIFIED")

    def test_missing_offer_fields_and_salary_do_not_raise_risk(self):
        report = self.scan(offer="Dear TEST APPLICANT PERSON,\nWe offer employment. Please contact us for the full terms.")
        self.assertEqual(report.risk_level, "LOW")
        self.assertEqual(report.visa.comparisons[1].status, "UNVERIFIED")
        self.assertFalse(any("salary" in finding.id for finding in report.findings))
        standalone = self.scan(offer=None)
        self.assertTrue(all(item.status == "UNVERIFIED" for item in standalone.visa.comparisons))

    def test_passport_expiry_and_unqualified_expiry_are_not_visa_expiry(self):
        text = VISA.replace("Visa Expiry Date: 2030-12-31", "Passport Expiry Date: 2020-01-01\nExpiry Date: 2020-01-01")
        report = self.scan(text)
        self.assertIsNone(report.visa.details.expiry_date)
        self.assertFalse(any(item.id == "visa_expired" for item in report.findings))

    def test_ambiguous_and_unrecognised_dates_remain_unverified(self):
        for value in ("03/04/2026", "not-a-date"):
            self.assertIsNone(parse_date(value))
            report = self.scan(VISA.replace("2030-12-31", value))
            self.assertEqual(report.risk_level, "LOW")
            self.assertTrue(any("ambiguous or invalid" in item for item in report.checks_not_run))
        self.assertEqual(parse_date("31/12/2030"), date(2030, 12, 31))
        self.assertEqual(parse_date("12/31/2030"), date(2030, 12, 31))

    def test_impossible_numeric_dates_raise_a_calendar_warning_not_a_forgery_verdict(self):
        for value in ("2026-02-30", "31/02/2030", "2026-00-10"):
            report = self.scan(VISA.replace("2030-12-31", value))
            self.assertEqual(report.risk_level, "MEDIUM")
            finding = next(item for item in report.findings if item.id == "visa_invalid_expiry_date")
            self.assertIn("does not prove forgery", finding.detail)

    def test_invalid_date_order_and_future_issue_are_flagged(self):
        report = self.scan(VISA.replace("2026-01-15", "2031-01-15"))
        self.assertTrue({"visa_future_issue", "visa_date_order"} <= {item.id for item in report.findings})

    def test_country_conflict_and_kuwait_guidance(self):
        report = self.scan(VISA.replace("State of Qatar", "State of Kuwait"), country="QA")
        self.assertTrue(any(item.id == "visa_country_mismatch" for item in report.findings))
        kuwait = self.scan(VISA.replace("State of Qatar", "State of Kuwait"), country="KW")
        self.assertTrue(kuwait.visa.guidance.source_url.startswith("https://www.moi.gov.kw/"))
        with self.assertRaises(ValueError):
            self.scan(country="AE")

    def test_tourist_visa_is_not_itself_a_scam_but_cannot_establish_offered_work_permission(self):
        tourist = VISA.replace("Work / Employment", "Tourist Visa")
        self.assertEqual(self.scan(tourist, offer=None).risk_level, "LOW")
        report = self.scan(tourist)
        self.assertTrue(any(item.id == "visa_non_work_route" for item in report.findings))

    def test_corrections_retain_original_fields_and_cannot_hide_clear_source_expiry(self):
        report = self.scan(VISA.replace("2030-12-31", "2020-12-31"), changes={"expiry_date": "2030-12-31"})
        self.assertEqual(report.visa.extracted_details.expiry_date, "2020-12-31")
        self.assertIn("Visa: expiry_date", report.visa.corrections)
        self.assertTrue(any(item.id == "visa_source_expiry" for item in report.findings))

    def test_line_separated_labels_are_read_and_conflicting_repeated_values_are_not_chosen(self):
        details = labelled_details(VISA.replace(": ", "\n"))
        self.assertEqual(details.passport_number, "A00123456")
        self.assertEqual(details.visa_number, "001234567890123")
        repeated = labelled_details(VISA + "Passport Number: A00999999\n")
        self.assertIsNone(repeated.passport_number)

    def test_unreadable_and_non_visa_files_never_get_a_verdict(self):
        for data, name in [(b"", "empty.txt"), (b"An offer mentioning a visa, with no visa record.", "offer.txt"), (b"bad pdf", "bad.pdf"), (VISA.encode(), "unsupported.exe")]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                preview_visa(data, name, "QA")
        with self.assertRaises(ValueError):
            self.scan(offer="")

    def test_visa_does_not_call_offer_rules_ai_verdict_or_external_portals(self):
        with patch("app.ai.analyze", side_effect=AssertionError("No AI verdict")), patch("app.analyzer.run_general_rules", side_effect=AssertionError("No offer rules")), patch("app.websites.website_checks", side_effect=AssertionError("No external portal")):
            self.assertEqual(self.scan().risk_level, "LOW")

    def test_pdf_includes_comparisons_corrections_and_official_status_without_forgery_verdict(self):
        report = self.scan(VISA.replace("2030-12-31", "2020-12-31"), changes={"expiry_date": "2030-12-31"})
        content = render_pdf(report, "test-report", "2026-10-29")
        with pymupdf.open(stream=content, filetype="pdf") as document:
            text = unicodedata.normalize("NFKC", "".join(page.get_text() for page in document))
        self.assertIn("Government visa status: not checked", text)
        self.assertIn("Offer and visa comparison", text)
        self.assertIn("2020-12-31", text)
        self.assertNotIn("Fraud signals found", text)


if __name__ == "__main__":
    unittest.main()
