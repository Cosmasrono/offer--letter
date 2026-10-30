import io
import json
import os
import socket
import time
import unittest
from email.message import Message
from unittest.mock import patch

from app.analyzer import analyze_letter
from app.entities import domain_of, extract_entities
from app.models import AIVerdict, Entities
from app.public_web import WebPage, WebUnavailable, fetch_public, public_url
from app.websites import SiteHTML, _compare_site, _lookalike_domains, website_checks


class PublicFetchTests(unittest.TestCase):
    def response(self, body=b"<html>Public page</html>", status=200, location=None, content_type="text/html"):
        response = io.BytesIO(body)
        response.read1 = response.read
        response.status, response.fp = status, None
        response.headers = Message()
        response.headers["Content-Type"] = content_type
        if location:
            response.headers["Location"] = location
        response.getheader = lambda key, default=None: response.headers.get(key, default)
        return response

    def dns(self, address="93.184.216.34"):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    def test_rejects_unsafe_urls_before_any_request(self):
        for url in ["http://acme.com", "file:///etc/passwd", "https://localhost", "https://127.0.0.1",
                    "https://[::1]", "https://acme.com:8443", "https://user:password@acme.com",
                    "https://metadata.internal", "https://a.local", "https://0x7f000001"]:
            with self.subTest(url=url), self.assertRaises(WebUnavailable):
                public_url(url)

    def test_private_or_mixed_dns_is_blocked_before_connecting(self):
        for addresses in [self.dns("127.0.0.1"), self.dns("169.254.169.254"), self.dns() + self.dns("10.0.0.1"),
                          self.dns("::ffff:127.0.0.1"), self.dns("64:ff9b::7f00:1")]:
            with self.subTest(addresses=addresses), patch("app.public_web.socket.getaddrinfo", return_value=addresses), patch("app.public_web._PinnedHTTPS") as connection:
                with self.assertRaises(WebUnavailable):
                    fetch_public("https://acme.com")
                connection.assert_not_called()

    def test_public_address_is_pinned_and_reading_is_bounded(self):
        with patch("app.public_web.socket.getaddrinfo", return_value=self.dns()) as dns, patch("app.public_web._PinnedHTTPS") as connection:
            connection.return_value.getresponse.return_value = self.response()
            page = fetch_public("https://acme.com/#private-fragment")
            self.assertIn("Public page", page.text)
            self.assertEqual(connection.call_args.args[:2], ("acme.com", "93.184.216.34"))
            self.assertEqual(dns.call_count, 1)
            connection.return_value.getresponse.return_value = self.response(b"a" * 20)
            with self.assertRaises(WebUnavailable):
                fetch_public("https://acme.com", max_bytes=10)

    def test_redirect_to_private_dns_and_https_downgrade_are_blocked(self):
        with patch("app.public_web.socket.getaddrinfo", side_effect=[self.dns(), self.dns("10.0.0.1")]), patch("app.public_web._PinnedHTTPS") as connection:
            connection.return_value.getresponse.return_value = self.response(status=302, location="https://internal.acme.com/")
            with self.assertRaises(WebUnavailable):
                fetch_public("https://acme.com")
            self.assertEqual(connection.call_count, 1)
        with patch("app.public_web.socket.getaddrinfo", return_value=self.dns()), patch("app.public_web._PinnedHTTPS") as connection:
            connection.return_value.getresponse.return_value = self.response(status=302, location="http://acme.com/")
            with self.assertRaises(WebUnavailable):
                fetch_public("https://acme.com")

    def test_credentialed_source_does_not_follow_external_redirect(self):
        with patch("app.public_web.socket.getaddrinfo", return_value=self.dns()), patch("app.public_web._PinnedHTTPS") as connection:
            connection.return_value.getresponse.return_value = self.response(status=302, location="https://other.com/")
            with self.assertRaises(WebUnavailable):
                fetch_public("https://api.search.brave.com/query", allowed_hosts={"api.search.brave.com"}, headers={"X-Subscription-Token": "test-key"})
            self.assertEqual(connection.call_count, 1)

    def test_deadline_and_unsupported_format_are_unavailable(self):
        with self.assertRaises(WebUnavailable):
            fetch_public("https://acme.com", deadline=time.monotonic() - 1)
        with patch("app.public_web.socket.getaddrinfo", return_value=self.dns()), patch("app.public_web._PinnedHTTPS") as connection:
            connection.return_value.getresponse.return_value = self.response(content_type="application/pdf")
            with self.assertRaises(WebUnavailable):
                fetch_public("https://acme.com")

    def test_dns_timeout_is_bounded_before_any_connection(self):
        with patch("app.public_web._DNS_POOL.submit") as submit, patch("app.public_web._PinnedHTTPS") as connection:
            submit.return_value.result.side_effect = TimeoutError()
            with self.assertRaises(WebUnavailable):
                fetch_public("https://acme.com")
            submit.return_value.cancel.assert_called_once()
            connection.assert_not_called()

    def test_structured_queries_require_fixed_source_and_cannot_redirect(self):
        with self.assertRaises(WebUnavailable):
            fetch_public("https://acme.com", json_body={"search": "name"})
        with patch("app.public_web.socket.getaddrinfo", return_value=self.dns()), patch("app.public_web._PinnedHTTPS") as connection:
            connection.return_value.getresponse.return_value = self.response(status=302, location="https://acme.com/other")
            with self.assertRaises(WebUnavailable):
                fetch_public("https://acme.com", allowed_hosts={"acme.com"}, json_body={"search": "name"})
            self.assertEqual(connection.call_count, 1)


class WebsiteComparisonTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ENABLE_WEBSITE_CHECK": "true", "BRAVE_SEARCH_API_KEY": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.entities = Entities(company_name="Acme Logistics Ltd", company_registration_number="12345678",
                                 emails=["hr@acmelogistics.com"], phones=["+44 20 7946 0123"], domains=["acmelogistics.com"])

    def page(self, html, url="https://acmelogistics.com/"):
        return WebPage(url, html, "text/html")

    def test_name_contacts_and_number_match_without_reducing_risk(self):
        html = "<h1>Acme Logistics Limited</h1><p>Company number: 12345678</p><a href='mailto:hr@acmelogistics.com'>Email</a><a href='tel:+442079460123'>Call</a>"
        with patch("app.websites.fetch_public", return_value=self.page(html)):
            checks, findings, not_run = website_checks(self.entities, "GB")
        site = next(check for check in checks if check.check == "website")
        self.assertEqual(site.status, "MATCHED")
        self.assertEqual(findings, [])
        self.assertTrue(any("not configured" in value for value in not_run))
        fields = {item.field: item.status for item in site.comparisons}
        self.assertEqual(fields["Company registration number"], "MATCHED")
        self.assertEqual(fields["Contact email"], "MATCHED")
        self.assertEqual(fields["Phone number"], "MATCHED")
        self.assertEqual(fields["Job, salary and offer terms"], "UNVERIFIED")

    def test_actual_company_number_conflict_is_flagged(self):
        page = SiteHTML("https://acmelogistics.com/", "Acme Logistics Ltd. Company number: 87654321")
        check, findings = _compare_site(self.entities, [page], page.url)
        self.assertEqual(check.status, "MISMATCH")
        self.assertTrue(any(f.id.startswith("website_registration_mismatch") for f in findings))

    def test_lookalike_contact_domain_is_flagged_against_published_contacts(self):
        self.entities.emails = ["hr@acme-logistics-jobs.com"]
        page = SiteHTML("https://acmelogistics.com/", "Acme Logistics Ltd. Email hr@acmelogistics.com")
        check, findings = _compare_site(self.entities, [page], page.url)
        self.assertEqual(check.status, "MISMATCH")
        self.assertTrue(any(f.id.startswith("website_contact_domain_mismatch") for f in findings))

    def test_agency_contact_is_not_compared_as_an_employer_email(self):
        self.entities.agency_name = "Bridge Recruitment Ltd"
        self.entities.emails = ["recruiter@bridgerecruitment.com"]
        page = SiteHTML("https://acmelogistics.com/", "Acme Logistics Ltd. Email hr@acmelogistics.com")
        _, findings = _compare_site(self.entities, [page], page.url)
        self.assertEqual(findings, [])

    def test_explicit_different_organization_is_flagged_but_missing_text_is_not(self):
        html = '<script type="application/ld+json">{"@type":"Organization","legalName":"Unrelated Trading Ltd"}</script><p>Unrelated trading</p>'
        check, findings = _compare_site(self.entities, [SiteHTML("https://other.com/", html)], "https://other.com/")
        self.assertEqual(check.status, "MISMATCH")
        self.assertTrue(findings)
        check, findings = _compare_site(self.entities, [SiteHTML("https://other.com/", "Enable JavaScript to continue")], "https://other.com/")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(findings, [])

    def test_absent_email_does_not_count_as_contradiction_and_scripts_do_not_create_matches(self):
        html = "<h1>Acme Logistics Ltd</h1><script>hr@acmelogistics.com</script><p>contact@acmelogistics.com</p>"
        check, findings = _compare_site(self.entities, [SiteHTML("https://acmelogistics.com/", html)], "https://acmelogistics.com/")
        self.assertEqual(check.status, "UNVERIFIED")
        self.assertEqual(findings, [])
        email = next(item for item in check.comparisons if item.field == "Contact email")
        self.assertEqual(email.status, "UNVERIFIED")

    def test_follows_bounded_same_host_contact_pages_without_sending_letter_or_url_tokens(self):
        self.entities.urls = ["https://acmelogistics.com/private-offer?passport=PRIVATE"]
        html = "Acme Logistics Ltd<a href='/contact'>Contact</a><a href='/about'>About</a><a href='https://other.com/contact'>Other</a><a href='/contact?secret=PRIVATE'>Secret</a>"
        with patch("app.websites.fetch_public", side_effect=[self.page(html), self.page("hr@acmelogistics.com", "https://acmelogistics.com/contact"), self.page("About", "https://acmelogistics.com/about")]) as fetch:
            checks, _, _ = website_checks(self.entities, "GB")
        self.assertEqual(fetch.call_count, 3)
        self.assertNotIn("PRIVATE", str(fetch.call_args_list))
        self.assertEqual(len(checks[1].checked_pages), 3)

    def test_failed_website_does_not_increase_risk_or_expose_unsafe_links(self):
        self.entities.domains = ["127.0.0.1"]
        with patch("app.websites.fetch_public", side_effect=WebUnavailable("private error")):
            checks, findings, not_run = website_checks(self.entities, "GB")
        self.assertEqual(findings, [])
        self.assertEqual(checks[-1].status, "UNAVAILABLE")
        self.assertEqual(checks[-1].source_url, "")
        self.assertNotIn("private error", str(checks))
        self.assertTrue(not_run)

    def test_company_name_search_reads_candidate_and_never_calls_it_official(self):
        search = {"web": {"results": [{"title": "Acme Logistics Limited | Home", "url": "https://acmelogistics.com/"}]}}
        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test-key"}), patch("app.websites.fetch_public", side_effect=[WebPage("https://api.search.brave.com/", json.dumps(search), "application/json"), self.page("Acme Logistics Ltd hr@acmelogistics.com")]) as fetch:
            self.entities.domains = []
            checks, _, _ = website_checks(self.entities, "GB")
        self.assertEqual(checks[0].status, "UNVERIFIED")
        self.assertIn("do not establish", checks[0].detail)
        self.assertNotIn("test-key", str(checks))
        self.assertEqual(fetch.call_args_list[0].kwargs["allowed_hosts"], {"api.search.brave.com"})
        self.assertNotIn("X-Subscription-Token", fetch.call_args_list[1].kwargs.get("headers", {}))

    def test_labelled_names_bare_domains_and_separate_agency_email_are_extracted(self):
        entities = extract_entities("Employer: Acme\nWebsite: acme.com\nRecruitment agency: Bridge Recruitment Ltd\nAgency email: agent@bridge.com\nhr@acme.com")
        self.assertEqual(entities.company_name, "Acme")
        self.assertIn("acme.com", entities.domains)
        self.assertEqual(entities.agency_emails, ["agent@bridge.com"])
        self.assertEqual(domain_of("https://real-company.com@other.com/x"), "other.com")

    def test_identity_conflict_cannot_be_erased_by_ai_or_trust_points(self):
        verdict = AIVerdict(risk_level="LOW", confidence=95, summary="Looks fine", red_flags=[], trust_signals=[], company_name="Invented Ltd", job_title=None, country=None)
        text = b"Employer: Acme Logistics Ltd\nCompany number: 12345678\nWebsite: acmelogistics.com\nhr@acmelogistics.com\nStart date 1 January 2027. Working hours 40 per week."
        with patch.dict(os.environ, {"ENABLE_DOMAIN_LOOKUP": "false", "ENABLE_NEA_LIVE_LOOKUP": "false", "COMPANIES_HOUSE_API_KEY": ""}), patch("app.websites.fetch_public", return_value=self.page("Acme Logistics Ltd. Company number: 87654321")), patch("app.ai.analyze", return_value=(verdict, None)):
            report = analyze_letter(text, "letter.txt", "GB")
        self.assertGreaterEqual(report.score, 30)
        self.assertIn("details differ", report.summary)
        self.assertNotIn("Looks fine", report.summary)
        self.assertEqual(report.company_name, "Acme Logistics Ltd")


class LookalikeDomainTests(unittest.TestCase):
    candidates = ["https://theemiratesgroup.com/", "https://emirates.com/", "https://agbi.com/"]

    def check(self, domain, mentioned_on):
        entities = Entities(company_name="The Emirates Group", domains=[domain])
        with patch("app.websites._search_hosts", return_value=mentioned_on) as search:
            result = _lookalike_domains(entities, self.candidates, [domain], time.monotonic() + 5)
        return result, search

    def test_brand_domain_unknown_to_official_sites_is_flagged(self):
        (check, findings, confirmed), _ = self.check("emirates-careers-recruitment.com", [])
        self.assertEqual(check.status, "MISMATCH")
        self.assertEqual([(f.id, f.points) for f in findings], [("lookalike_domain:emirates-careers-recruitment.com", 25)])
        self.assertEqual(confirmed, [])

    def test_careers_site_mentioned_on_official_pages_is_confirmed(self):
        (check, findings, confirmed), _ = self.check("emiratesgroupcareers.com", ["indeed.com", "emirates.com"])
        self.assertEqual(check.status, "MATCHED")
        self.assertEqual(findings, [])
        self.assertEqual(confirmed, ["emiratesgroupcareers.com"])

    def test_official_domain_needs_no_extra_search(self):
        (check, findings, _), search = self.check("emirates.com", [])
        self.assertEqual(check.status, "MATCHED")
        self.assertEqual(findings, [])
        search.assert_not_called()

    def test_failed_confirmation_search_still_flags(self):
        (_, findings, _), _ = self.check("emirates-careers-recruitment.com", None)
        self.assertEqual(len(findings), 1)

    def test_news_site_is_never_treated_as_official(self):
        entities = Entities(company_name="The Emirates Group", domains=["agbi-jobs.com"])
        self.assertEqual(_lookalike_domains(entities, ["https://agbi.com/"], ["agbi-jobs.com"], time.monotonic() + 5), (None, [], []))


if __name__ == "__main__":
    unittest.main()
