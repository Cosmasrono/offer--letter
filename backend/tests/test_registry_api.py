import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class RegistryAPITests(unittest.TestCase):
    def test_maintenance_requires_a_configured_matching_key(self):
        with TestClient(app) as client:
            with patch.dict(os.environ, {"BACKEND_API_KEY": ""}):
                self.assertEqual(client.get("/verification/nea").status_code, 503)
            with patch.dict(os.environ, {"BACKEND_API_KEY": "local-test-key"}):
                self.assertEqual(client.get("/verification/nea").status_code, 401)
                self.assertEqual(client.post("/verification/nea", headers={"X-Api-Key": "wrong"}).status_code, 401)

    def test_valid_import_updates_status_and_invalid_import_keeps_existing_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"BACKEND_API_KEY": "local-test-key", "NEA_AGENCIES_CSV": str(Path(directory) / "nea.csv")}):
            with TestClient(app) as client:
                headers = {"X-Api-Key": "local-test-key"}
                body = b"agency_name,licence_number,expiry_date,status\nExample Recruitment Agency Ltd,RA/2026/01/1,2099-01-01,Valid\n"
                response = client.post("/verification/nea", headers=headers, files={"file": ("nea.csv", body)}, data={"retrieved_at": "2026-01-01T00:00:00Z"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["records"], 1)
                self.assertEqual(client.get("/verification/nea", headers=headers).json()["records"], 1)
                failed = client.post("/verification/nea", headers=headers, files={"file": ("nea.html", b"<html>maintenance</html>")}, data={"retrieved_at": "2026-01-01T00:00:00Z"})
                self.assertEqual(failed.status_code, 400)
                self.assertEqual(client.get("/verification/nea", headers=headers).json()["records"], 1)


if __name__ == "__main__":
    unittest.main()
