import io
import os
import unittest
from email.message import EmailMessage
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient

from app.email_document import read_email
from app.extract import extract
from app.main import app
from app.sponsorship import sponsorship_checks
from app.rules.general import run_general_rules
from app.models import Entities


def email(sender="hr@example.com", reply=None):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "candidate@example.net"
    message["Subject"] = "Employment offer"
    if reply:
        message["Reply-To"] = reply
    message.set_content("Employer: Example Employer Ltd\nPosition: Support Worker\nStart date 1 January 2027. Salary GBP 35000 per year.")
    return message


class OriginalEmailTests(unittest.TestCase):
    def test_normal_email_does_not_authenticate_an_offer_or_read_recipient_as_recruiter(self):
        result = read_email(email().as_bytes())
        self.assertEqual(result.evidence.status, "UNVERIFIED")
        self.assertEqual(result.findings, [])
        self.assertEqual(result.sender_addresses, ["hr@example.com"])
        self.assertNotIn("candidate@example.net", result.text)

    def test_reply_to_and_disguised_sender_are_flagged(self):
        result = read_email(email('"hr@realcompany.com" <recruiter@other.com>', "reply@another.com").as_bytes())
        self.assertEqual(result.evidence.status, "MISMATCH")
        self.assertEqual({finding.id for finding in result.findings}, {"email_reply_domain_mismatch", "email_disguised_sender"})

    def test_forged_pass_headers_and_matching_signing_domains_never_add_trust(self):
        message = email()
        message["Authentication-Results"] = "mail.example.com; spf=pass; dkim=pass; dmarc=pass"
        message["DKIM-Signature"] = "v=1; a=rsa-sha256; d=example.com; s=selector; b=not-a-signature"
        result = read_email(message.as_bytes())
        self.assertEqual(result.evidence.status, "UNVERIFIED")
        self.assertTrue(all(comparison.status == "UNVERIFIED" for comparison in result.evidence.comparisons))
        self.assertFalse(any(finding.points < 0 for finding in result.findings))

    def test_html_is_read_without_executing_scripts_or_fetching_images(self):
        message = EmailMessage()
        message["From"] = "hr@example.com"
        message.set_content("<p>Employer: Example Employer Ltd</p><script>hidden@example.org</script><a href='https://example.com/jobs'>Jobs</a><img src='http://127.0.0.1/private'>", subtype="html")
        result = read_email(message.as_bytes())
        self.assertIn("Example Employer", result.text)
        self.assertIn("https://example.com/jobs", result.text)
        self.assertNotIn("hidden@example.org", result.text)
        self.assertNotIn("127.0.0.1", result.text)

    def test_pdf_attachment_text_is_included_and_its_actual_bytes_are_used_for_forensics(self):
        document = pymupdf.open()
        document.new_page().insert_text((30, 30), "Example Employer Ltd. This is an employment offer for a Support Worker. Salary GBP 35000.")
        data = document.tobytes()
        message = email()
        message.add_attachment(data, maintype="application", subtype="pdf", filename="offer.pdf")
        result = extract(message.as_bytes(), "recruiter.eml")
        self.assertEqual(result.method, "original-email")
        self.assertEqual(result.pdf_data, data)
        self.assertIn("employment offer", result.text)
        self.assertEqual(result.source_checks[0].check, "email")

    def test_an_unreadable_attachment_does_not_silently_get_checked(self):
        message = email()
        message.add_attachment(b"not a PDF", maintype="application", subtype="pdf", filename="offer.pdf")
        result = extract(message.as_bytes(), "recruiter.eml")
        self.assertTrue(any("attachment could not be read" in line for line in result.checks_not_run))

    def test_invalid_image_never_goes_to_an_ai_provider(self):
        with patch("app.extract._ocr_images") as ocr:
            with self.assertRaises(ValueError):
                extract(b"<html>not an image</html>", "offer.png")
            ocr.assert_not_called()

    def test_api_flags_unsupported_and_corrupt_files_without_a_risk_verdict(self):
        with patch.dict(os.environ, {"BACKEND_API_KEY": ""}), TestClient(app) as client:
            for name, data in [("offer.exe", b"program"), ("offer.pdf", b"broken"), ("offer.eml", b"plain text"), ("offer.jpg", b"broken")]:
                result = client.post("/analyze", files={"file": (name, data)})
                self.assertEqual(result.status_code, 422)
                self.assertEqual(result.json()["detail"]["code"], "DOCUMENT_NOT_CHECKED")
                self.assertNotIn("risk_level", result.json())


class SponsorshipTests(unittest.TestCase):
    def test_identity_card_fields_are_not_mistaken_for_financial_card_requests(self):
        findings = run_general_rules("UK ID card number:\nNational ID card number:\nIdentity card number:", Entities(), "GB")
        self.assertNotIn("sensitive_info", [finding.id for finding in findings])
        findings = run_general_rules("Please send your bank account and debit card number.", Entities(), "GB")
        self.assertIn("sensitive_info", [finding.id for finding in findings])
    def test_past_use_by_date_is_flagged_without_claiming_historical_fraud(self):
        checks, findings, _ = sponsorship_checks("Certificate of Sponsorship Details\nExpiry date (use by): 15 October 2023\nWork end date: 16 September 2028")
        self.assertEqual(checks[0].status, "MISMATCH")
        self.assertEqual(findings[0].id, "cos_expired")
        self.assertIn("earlier application", findings[0].detail)

    def test_future_date_does_not_authenticate_and_missing_expiry_does_not_use_passport_date(self):
        for text in ["Certificate of Sponsorship\nExpiry date (use by): 15 October 2099", "Certificate of Sponsorship\nExpiry date (use by): unreadable\nPassport expiry: 15 October 2000"]:
            checks, findings, _ = sponsorship_checks(text)
            self.assertEqual(checks[0].status, "UNVERIFIED")
            self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
