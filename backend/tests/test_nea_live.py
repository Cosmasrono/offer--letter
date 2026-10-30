import unittest
import json
import csv
import io
from unittest.mock import patch

from app import nea_live
from app.public_web import WebPage, WebUnavailable

HTML = "<table><tr><th>Agency Name</th><th>NEA Reg No</th><th>Certificate Expiry</th><th>Status</th><th>E-mail Address</th><th>Website</th></tr><tr><td>Example Recruitment Ltd</td><td>RA/2026/01/1</td><td>01-01-2099</td><td>Valid</td><td>info@exampleagency.com</td><td>https://exampleagency.com</td></tr></table>"


class LiveDatasetTests(unittest.TestCase):
    def setUp(self):
        cache = patch.dict(nea_live._cache, {"until": 0, "content": None, "retrieved_at": None})
        cache.start()
        self.addCleanup(cache.stop)

    def test_official_table_is_parsed_with_contacts_and_cached(self):
        with patch.object(nea_live, "fetch_public", return_value=WebPage(nea_live.SOURCE_URL, HTML, "text/html")) as fetch:
            content, timestamp = nea_live.live_dataset()
            again, again_at = nea_live.live_dataset()
        self.assertIn(b"info@exampleagency.com", content)
        self.assertEqual((content, timestamp), (again, again_at))
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args.kwargs["allowed_hosts"], {"www.neaims.go.ke", "neaims.go.ke"})

    def test_maintenance_page_is_not_accepted_as_an_empty_register(self):
        with patch.object(nea_live, "fetch_public", return_value=WebPage(nea_live.SOURCE_URL, "<html>Maintenance</html>", "text/html")) as fetch:
            for _ in range(2):
                with self.assertRaises(WebUnavailable):
                    nea_live.live_dataset()
        self.assertEqual(fetch.call_count, 2)

    def test_current_api_is_used_and_business_number_is_not_made_into_a_licence(self):
        payload = {"success": True, "data": [{"instName": "Example Recruitment Ltd", "instCode": None, "instRegNo": "PVT-EXAMPLE",
                    "instStatus": "LICENSE_PAID", "instExpiryDate": "2099-01-01", "instEmail": "info@exampleagency.com", "instLicenseType": "INTERNATIONAL LICENSE"}], "count": 1}
        page = WebPage(nea_live.API_URL, json.dumps(payload), "application/json")
        with patch.object(nea_live, "fetch_public", return_value=page) as fetch:
            content, _ = nea_live.live_dataset()
        self.assertEqual(fetch.call_count, 1)
        records = csv.DictReader(io.StringIO(content.decode()))
        record = next(records)
        self.assertEqual(record["licence_number"], "")
        self.assertEqual(record["business_registration_number"], "PVT-EXAMPLE")
        self.assertEqual(record["status"], "LICENSE_PAID")
        self.assertEqual(record["record_source_url"], nea_live.API_URL)
        self.assertEqual(fetch.call_args.kwargs["allowed_hosts"], {"api.neaims.go.ke"})

    def test_invalid_or_empty_api_records_are_not_a_verified_register(self):
        for payload in [{"success": False, "data": []}, {"success": True, "data": []},
                        {"success": True, "data": [{"instName": "Example", "instExpiryDate": "not-a-date"}]},
                        {"success": True, "data": [{"instName": "Example", "instStatus": True}]}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                nea_live.api_records(payload)


if __name__ == "__main__":
    unittest.main()
