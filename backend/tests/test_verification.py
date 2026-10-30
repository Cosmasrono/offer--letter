import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app.agencies import agency_check
from app.employers import employer_check
from app.entities import extract_entities
from app.models import Entities
from app.nea_dataset import dataset_metadata, import_export, parse_export
from app.public_web import WebUnavailable


class EmployerTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"COMPANIES_HOUSE_API_KEY": "test-only-key"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.entities = Entities(company_name="Example Employer Ltd", company_registration_number="12345678")

    def response(self, data):
        return io.BytesIO(json.dumps(data).encode())

    def profile(self, **overrides):
        return {"company_number": "12345678", "company_name": "EXAMPLE EMPLOYER LIMITED", "company_status": "active", **overrides}

    def test_exact_profile_match_is_evidence_not_offer_authentication(self):
        with patch("app.employers.urlopen", return_value=self.response(self.profile())) as request:
            check, findings = employer_check(self.entities, "GB")
        self.assertEqual(check.status, "MATCHED")
        self.assertIn("not who sent", check.detail)
        self.assertEqual(findings, [])
        self.assertEqual(request.call_args.args[0].full_url, "https://api.company-information.service.gov.uk/company/12345678")
        self.assertEqual(request.call_args.kwargs["timeout"], 8)

    def test_different_registered_name_is_flagged(self):
        with patch("app.employers.urlopen", return_value=self.response(self.profile(company_name="UNRELATED COMPANY LTD"))):
            check, findings = employer_check(self.entities, "GB")
        self.assertEqual(check.status, "MISMATCH")
        self.assertEqual(findings[0].id, "employer_registration_mismatch")

    def test_inactive_company_is_not_a_positive_match(self):
        with patch("app.employers.urlopen", return_value=self.response(self.profile(company_status="dissolved"))):
            check, findings = employer_check(self.entities, "GB")
        self.assertEqual(check.status, "MISMATCH")
        self.assertEqual(check.record_status, "dissolved")
        self.assertTrue(findings)

    def test_missing_key_and_unsupported_country_do_not_call_a_registry(self):
        with patch("app.employers.urlopen") as request, patch.dict(os.environ, {"COMPANIES_HOUSE_API_KEY": ""}):
            check, findings = employer_check(self.entities, "GB")
            self.assertEqual(check.status, "UNAVAILABLE")
            self.assertEqual(findings, [])
            other, _ = employer_check(self.entities, "AE")
            self.assertEqual(other.status, "UNVERIFIED")
            request.assert_not_called()

    def test_failed_and_invalid_registry_responses_never_mark_verified(self):
        for failure in [URLError("secret error"), TimeoutError(), HTTPError("url", 401, "secret", {}, None)]:
            with self.subTest(failure=type(failure).__name__), patch("app.employers.urlopen", side_effect=failure):
                check, findings = employer_check(self.entities, "GB")
                self.assertEqual(check.status, "UNAVAILABLE")
                self.assertNotIn("secret", check.detail)
                self.assertEqual(findings, [])
        with patch("app.employers.urlopen", return_value=self.response(self.profile(company_number="00000000"))):
            check, _ = employer_check(self.entities, "GB")
            self.assertEqual(check.status, "UNAVAILABLE")

    def test_404_is_not_found_without_assuming_fraud(self):
        with patch("app.employers.urlopen", side_effect=HTTPError("url", 404, "missing", {}, None)):
            check, findings = employer_check(self.entities, "GB")
        self.assertEqual(check.status, "NOT_FOUND")
        self.assertEqual(findings, [])

    def test_ambiguous_name_search_requires_number(self):
        entities = Entities(company_name="Example Employer Ltd")
        with patch("app.employers.urlopen", return_value=self.response({"items": [{"title": "Example Employer Ltd", "company_number": "12345678"}], "total_results": 12})) as request:
            check, findings = employer_check(entities, "GB")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(findings, [])

    def test_unambiguous_name_search_checks_the_full_profile(self):
        entities = Entities(company_name="Example Employer Ltd")
        with patch("app.employers.urlopen", side_effect=[self.response({"items": [{"title": "EXAMPLE EMPLOYER LIMITED", "company_number": "12345678"}], "total_results": 1}), self.response(self.profile())]) as request:
            check, _ = employer_check(entities, "GB")
        self.assertEqual(check.status, "MATCHED")
        self.assertEqual(request.call_count, 2)

    def test_registration_is_extracted_and_does_not_confuse_agency_licence(self):
        text = "Example Employer Ltd\nCompany registration number: SC 123456\nNEA licence no. NEA/PEA/2025/0412"
        self.assertEqual(extract_entities(text).company_registration_number, "SC123456")
        self.assertIsNone(extract_entities("NEA licence no. NEA/PEA/2025/0412").company_registration_number)


class NEADatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.output = self.root / "export.csv", self.root / "nea.csv"
        self.source.write_text("agency_name,licence_number,expiry_date,status\nExample Recruitment Agency Ltd,RA/2026/01/1,2099-01-01,Valid\n", encoding="utf-8")
        self.env = patch.dict(os.environ, {"NEA_AGENCIES_CSV": str(self.output), "ENABLE_NEA_LIVE_LOOKUP": "false"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def import_now(self, days_old=0):
        return import_export(self.source, self.output, retrieved_at=(datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat())

    def test_html_and_csv_headers_produce_the_same_records(self):
        html = "<table><tr><th>No.</th><th>NEA Reg No</th><th>Agency Name</th><th>E-mail Address</th><th>Website</th><th>Service Type</th><th>Certificate Valid From</th><th>Certificate Expiry</th><th>Status</th></tr><tr><td>1</td><td>RA/2026/01/1</td><td>Example Recruitment Agency Ltd</td><td></td><td></td><td>Foreign</td><td>01-01-2026</td><td>01-01-2099</td><td>Valid</td></tr></table>"
        self.assertEqual(parse_export(html), parse_export(self.source.read_text()))

    def test_fresh_snapshot_records_date_and_matches(self):
        metadata = self.import_now()
        self.assertEqual(metadata["records"], 1)
        self.assertTrue(dataset_metadata(self.output)["fresh"])
        check, findings, not_run = agency_check(Entities(agency_name="Example Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "MATCHED")
        self.assertTrue(check.source_updated_at)
        self.assertEqual(check.record_id, "RA/2026/01/1")
        self.assertTrue(findings)
        self.assertFalse(not_run)

    def test_stale_tampered_and_undated_data_never_provide_a_licence_match(self):
        self.import_now(days_old=31)
        check, findings, _ = agency_check(Entities(agency_name="Example Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(findings, [])
        self.import_now()
        self.output.write_text(self.output.read_text() + "\n")
        self.assertEqual(dataset_metadata(self.output), {})
        check, findings, _ = agency_check(Entities(agency_name="Example Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(findings, [])

    def test_kenyan_agency_missing_from_fresh_register_is_flagged(self):
        self.import_now()
        check, findings, _ = agency_check(Entities(agency_name="Unrelated Recruitment Agency Ltd"), "Unrelated Recruitment Agency Ltd, Nairobi")
        self.assertEqual(check.status, "NOT_FOUND")
        self.assertEqual([(f.id, f.points) for f in findings], [("agency_not_accredited", 20)])

    def test_foreign_agency_missing_from_register_scores_lower(self):
        self.import_now()
        check, findings, _ = agency_check(Entities(agency_name="Unrelated Recruitment Agency Ltd"), "Unrelated Recruitment Agency Ltd, Dubai")
        self.assertEqual(check.status, "NOT_FOUND")
        self.assertEqual([(f.id, f.points) for f in findings], [("agency_not_accredited", 10)])

    def test_stale_register_never_flags_a_missing_agency(self):
        self.import_now(days_old=31)
        check, findings, _ = agency_check(Entities(agency_name="Unrelated Recruitment Agency Ltd"), "Unrelated Recruitment Agency Ltd, Nairobi")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(findings, [])

    def test_invalid_export_and_conflicting_duplicates_do_not_overwrite_dataset(self):
        self.import_now()
        before = self.output.read_bytes()
        for invalid in ["<html>Maintenance</html>", self.source.read_text().replace("2099-01-01", "not-a-date"), self.source.read_text() + "Another Agency Ltd,RA/2026/01/1,2099-01-01,Valid\n"]:
            self.source.write_text(invalid)
            with self.assertRaises(ValueError):
                self.import_now()
            self.assertEqual(self.output.read_bytes(), before)

    def test_future_retrieval_date_is_rejected(self):
        with self.assertRaises(ValueError):
            import_export(self.source, self.output, retrieved_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())

    def test_expired_record_and_borrowed_licence_are_not_matches(self):
        self.source.write_text(self.source.read_text().replace("2099-01-01", "2020-01-01"))
        self.import_now()
        check, findings, _ = agency_check(Entities(agency_name="Example Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "MISMATCH")
        self.assertIn("agency_expired", [finding.id for finding in findings])

    def test_live_register_works_without_a_local_snapshot(self):
        content = self.source.read_bytes()
        with patch.dict(os.environ, {"ENABLE_NEA_LIVE_LOOKUP": "true"}), patch("app.agencies.live_dataset", return_value=(content, "2026-10-27T09:00:00+00:00")):
            check, _, not_run = agency_check(Entities(agency_name="Example Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "MATCHED")
        self.assertIn("live", check.source_name)
        self.assertEqual(check.source_updated_at, "2026-10-27T09:00:00+00:00")
        self.assertFalse(not_run)
        self.assertFalse(self.output.exists())

    def test_failed_live_lookup_falls_back_to_fresh_snapshot_with_notice(self):
        self.import_now()
        with patch.dict(os.environ, {"ENABLE_NEA_LIVE_LOOKUP": "true"}), patch("app.agencies.live_dataset", side_effect=WebUnavailable("unavailable")):
            check, _, not_run = agency_check(Entities(agency_name="Example Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "MATCHED")
        self.assertIn("snapshot", check.detail)
        self.assertTrue(any("Live NEA" in item for item in not_run))

    def test_failed_live_lookup_does_not_validate_stale_snapshot(self):
        self.import_now(days_old=31)
        with patch.dict(os.environ, {"ENABLE_NEA_LIVE_LOOKUP": "true"}), patch("app.agencies.live_dataset", side_effect=WebUnavailable("unavailable")):
            check, findings, _ = agency_check(Entities(agency_name="Example Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(findings, [])

    def test_licence_alone_and_similar_names_do_not_validate_an_agency(self):
        self.import_now()
        for entities in [Entities(agency_licence="RA/2026/01/1"), Entities(agency_name="Exampel Recruitment Agency Ltd")]:
            check, findings, _ = agency_check(entities, "Nairobi")
            self.assertNotEqual(check.status, "MATCHED")
            self.assertFalse(any(finding.points < 0 for finding in findings))

    def test_borrowed_licence_and_explicit_agency_email_mismatch_are_flagged(self):
        self.source.write_text("agency_name,licence_number,expiry_date,status,email,website\nExample Recruitment Agency Ltd,RA/2026/01/1,2099-01-01,Valid,info@exampleagency.com,https://exampleagency.com\n")
        self.import_now()
        borrowed, findings, _ = agency_check(Entities(agency_name="Unrelated Recruitment Agency Ltd", agency_licence="RA/2026/01/1"), "Nairobi")
        self.assertEqual(borrowed.status, "MISMATCH")
        self.assertIn("agency_licence_other_agency", [finding.id for finding in findings])
        impersonated, findings, _ = agency_check(Entities(agency_name="Example Recruitment Agency Ltd", agency_emails=["recruiter@other.com"]), "Nairobi")
        self.assertEqual(impersonated.status, "MISMATCH")
        self.assertIn("agency_registry_email_mismatch", [finding.id for finding in findings])
        self.assertFalse(any(finding.points < 0 for finding in findings))
        self.assertTrue(any(item.field == "Agency email" and item.status == "MISMATCH" for item in impersonated.comparisons))
        self.assertTrue(any(item.source_value == "https://exampleagency.com" for item in impersonated.comparisons))

    def test_foreign_employer_email_is_not_mistaken_for_agency_contact(self):
        self.source.write_text("agency_name,licence_number,expiry_date,status,email\nExample Recruitment Agency Ltd,RA/2026/01/1,2099-01-01,Valid,info@exampleagency.com\n")
        self.import_now()
        check, findings, _ = agency_check(Entities(company_name="Foreign Employer Ltd", agency_name="Example Recruitment Agency Ltd", emails=["hr@foreignemployer.com"]), "Nairobi")
        self.assertEqual(check.status, "MATCHED")
        self.assertNotIn("agency_registry_email_mismatch", [finding.id for finding in findings])

    def test_live_paid_status_and_business_number_do_not_verify_a_recruitment_licence(self):
        content = b"agency_name,licence_number,expiry_date,status,business_registration_number,licence_type\nExample Recruitment Agency Ltd,,2099-01-01,LICENSE_PAID,PVT-EXAMPLE,INTERNATIONAL LICENSE\n"
        with patch.dict(os.environ, {"ENABLE_NEA_LIVE_LOOKUP": "true"}), patch("app.agencies.live_dataset", return_value=(content, "2026-10-27T09:00:00Z")):
            check, findings, _ = agency_check(Entities(agency_name="Example Recruitment Agency Ltd", agency_licence="RA/2026/01/1"), "Nairobi")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(check.record_id, "PVT-EXAMPLE")
        self.assertFalse(findings)
        licence = next(item for item in check.comparisons if item.field == "Agency licence")
        self.assertEqual(licence.status, "UNVERIFIED")
        self.assertIn("not itself", check.detail)

    def test_duplicate_legal_names_do_not_attribute_one_records_adverse_status(self):
        self.source.write_text(self.source.read_text() + "Example Recruitment Agency Ltd,RA/2026/01/2,2020-01-01,Expired\n")
        self.import_now()
        check, findings, _ = agency_check(Entities(agency_name="Example Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(findings, [])

    def test_a_similar_name_does_not_inherit_another_agencys_expiry_warning(self):
        self.source.write_text(self.source.read_text().replace("2099-01-01", "2020-01-01"))
        self.import_now()
        check, findings, _ = agency_check(Entities(agency_name="Exampel Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(findings, [])

    def test_local_only_permission_is_flagged_for_overseas_recruitment(self):
        content = b"agency_name,licence_number,expiry_date,status,licence_type\nExample Recruitment Agency Ltd,,2099-01-01,LICENSE_PAID,LOCAL LICENSE\n"
        with patch.dict(os.environ, {"ENABLE_NEA_LIVE_LOOKUP": "true"}), patch("app.agencies.live_dataset", return_value=(content, "2026-10-27T09:00:00Z")):
            check, findings, _ = agency_check(Entities(agency_name="Example Recruitment Agency Ltd"), "Nairobi")
        self.assertEqual(check.status, "MISMATCH")
        self.assertIn("agency_local_only", [finding.id for finding in findings])

    def test_an_unlabelled_sender_can_be_identified_as_a_registered_agency(self):
        content = b"agency_name,licence_number,expiry_date,status\nBridge Jobs International Ltd,RA/2026/01/1,2020-01-01,Expired\n"
        with patch.dict(os.environ, {"ENABLE_NEA_LIVE_LOOKUP": "true"}), patch("app.agencies.live_dataset", return_value=(content, "2026-10-27T09:00:00Z")):
            check, findings, _ = agency_check(Entities(company_name="Bridge Jobs International Ltd"), "Offer from Bridge Jobs International Ltd")
        self.assertEqual(check.status, "MISMATCH")
        self.assertEqual(check.subject, "Bridge Jobs International Ltd")
        self.assertIn("agency_inactive", [finding.id for finding in findings])


if __name__ == "__main__":
    unittest.main()
