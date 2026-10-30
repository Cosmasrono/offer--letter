import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from app import uk_sponsors
from app.analyzer import analyze_letter
from app.models import AIVerdict
from app.public_web import WebPage, WebUnavailable
from app.sponsorship import sponsor_name
from app.sponsorship import sponsorship_checks

HEADER = "Organisation Name,Town/City,County,Type & Rating,Route\n"


def dataset(rows="Example Care Limited,Stockport,,Worker (A rating),Skilled Worker\n"):
    return uk_sponsors.parse_register(HEADER + rows, "https://assets.publishing.service.gov.uk/fixture.csv", date.today())


class SponsorRegisterTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"ENABLE_UK_SPONSOR_LOOKUP": "true"})
        environment.start()
        self.addCleanup(environment.stop)
        cache = patch.dict(uk_sponsors._cache, {"until": 0, "dataset": None, "error": None})
        cache.start()
        self.addCleanup(cache.stop)

    def test_download_discovers_latest_official_dated_csv_and_caches_it(self):
        url = f"https://assets.publishing.service.gov.uk/media/example/Worker_Web_Register_-_{date.today()}.csv"
        html = f'<a href="https://other.com/Worker_Web_Register_-_{date.today()}.csv">Untrusted</a><a href="{url}">Official register</a>'
        pages = [WebPage(uk_sponsors.REGISTER_URL, html, "text/html"), WebPage(url, HEADER + "Example Care Limited,Stockport,,Worker (A rating),Skilled Worker\n", "text/csv")]
        with patch.object(uk_sponsors, "fetch_public", side_effect=pages) as fetch:
            first = uk_sponsors.current_register()
            second = uk_sponsors.current_register()
        self.assertIs(first, second)
        self.assertEqual(first.count, 1)
        self.assertEqual(first.source_url, url)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args.kwargs["allowed_hosts"], {"assets.publishing.service.gov.uk"})

    def test_stale_register_and_bad_csv_are_not_used_to_make_licensing_claims(self):
        url = f"https://assets.publishing.service.gov.uk/media/example/Worker_Web_Register_-_{date.today() - timedelta(days=8)}.csv"
        with patch.object(uk_sponsors, "fetch_public", return_value=WebPage(uk_sponsors.REGISTER_URL, f'<a href="{url}">Old</a>', "text/html")) as fetch:
            with self.assertRaises(WebUnavailable):
                uk_sponsors.current_register()
            self.assertEqual(fetch.call_count, 1)
        for content in ["maintenance", HEADER, HEADER + "Example Care Limited,Stockport\n", HEADER + ",Stockport,,Worker (A rating),Skilled Worker\n"]:
            with self.subTest(content=content), self.assertRaises(WebUnavailable):
                uk_sponsors.parse_register(content, "https://example.com/register.csv", date.today())

    def test_exact_name_and_correct_route_match_without_authenticating_certificate_or_lowering_risk(self):
        with patch.object(uk_sponsors, "current_register", return_value=dataset()):
            evidence, findings, _ = uk_sponsors.sponsor_registry_check("EXAMPLE CARE LTD")
        self.assertEqual(evidence.status, "MATCHED")
        self.assertEqual(findings, [])
        self.assertEqual(evidence.source_updated_at, date.today().isoformat())
        certificate = next(item for item in evidence.comparisons if item.field == "Individual CoS and licence number")
        self.assertEqual(certificate.status, "UNVERIFIED")

    def test_missing_sponsor_is_flagged_as_current_nonmatch_not_historical_forgery(self):
        with patch.object(uk_sponsors, "current_register", return_value=dataset()):
            evidence, findings, _ = uk_sponsors.sponsor_registry_check("Unrelated Employer Ltd")
        self.assertEqual(evidence.status, "NOT_FOUND")
        self.assertEqual(findings[0].id, "sponsor_registry_not_found")
        self.assertIn("historical", evidence.detail)

    def test_lookalike_name_is_not_accepted_as_an_exact_sponsor_match(self):
        with patch.object(uk_sponsors, "current_register", return_value=dataset("Example Centre Limited,London,,Worker (A rating),Skilled Worker\n")):
            evidence, findings, _ = uk_sponsors.sponsor_registry_check("Example Center Limited")
        self.assertEqual(evidence.status, "MISMATCH")
        self.assertEqual(findings[0].id, "sponsor_registry_name_mismatch")

    def test_organisation_listed_for_a_different_route_is_flagged(self):
        with patch.object(uk_sponsors, "current_register", return_value=dataset("Example Care Limited,London,,Temporary Worker (A rating),Charity Worker\n")):
            evidence, findings, _ = uk_sponsors.sponsor_registry_check("Example Care Limited")
        self.assertEqual(evidence.status, "MISMATCH")
        self.assertEqual(findings[0].id, "sponsor_registry_wrong_route")

    def test_unavailable_lookup_and_unreadable_name_do_not_create_fraud_findings(self):
        with patch.object(uk_sponsors, "current_register", side_effect=WebUnavailable("network")):
            evidence, findings, not_run = uk_sponsors.sponsor_registry_check("Example Care Limited")
        self.assertEqual(evidence.status, "UNAVAILABLE")
        self.assertEqual(findings, [])
        self.assertTrue(not_run)
        with patch.object(uk_sponsors, "current_register") as lookup:
            evidence, findings, _ = uk_sponsors.sponsor_registry_check(None)
            self.assertEqual(evidence.status, "UNVERIFIED")
            self.assertEqual(findings, [])
            lookup.assert_not_called()

    def test_sponsor_label_is_read_without_requiring_a_company_suffix_or_using_other_field_labels(self):
        self.assertEqual(sponsor_name("Sponsor name: Example NHS Trust\nCertificate number: private"), "Example NHS Trust")
        self.assertEqual(sponsor_name("Sponsor name:\nCertificate number: private", "Fallback Ltd"), "Fallback Ltd")

    def test_offer_letter_merely_mentioning_cos_is_not_mistaken_for_a_cos_form(self):
        checks, findings, _ = sponsorship_checks("Example Care Ltd\nWe will assign your certificate of sponsorship after the interview. Please contact HR.")
        self.assertEqual(checks, [])
        self.assertEqual(findings, [])

    def test_expired_cos_is_always_high_for_current_use_even_if_ai_says_low(self):
        text = b"Certificate of Sponsorship Details\nSponsor name: Example Care Limited\nTier and Category: Skilled Worker\nExpiry date (use by): 15 October 2023\nJob title: Support Worker\nSalary GBP 35000. Start date 1 January 2023."
        verdict = AIVerdict(risk_level="LOW", confidence=99, summary="Looks genuine", red_flags=[], trust_signals=[], company_name=None, job_title=None, country=None)
        environment = {"ENABLE_DOMAIN_LOOKUP": "false", "ENABLE_WEBSITE_CHECK": "false", "ENABLE_NEA_LIVE_LOOKUP": "false", "COMPANIES_HOUSE_API_KEY": ""}
        with patch.dict(os.environ, environment), patch.object(uk_sponsors, "current_register", return_value=dataset()), patch("app.ai.analyze", return_value=(verdict, None)):
            report = analyze_letter(text, "cos.txt")
        self.assertEqual(report.country, "GB")
        self.assertEqual(report.company_name, "Example Care Limited")
        self.assertEqual(report.risk_level, "HIGH")
        self.assertGreaterEqual(report.score, 60)
        self.assertIn("historical authenticity remains unverified", report.summary)
        self.assertNotIn("Looks genuine", report.summary)
        self.assertTrue(any(check.check == "care_provider" and check.status == "UNVERIFIED" for check in report.source_checks))


if __name__ == "__main__":
    unittest.main()
