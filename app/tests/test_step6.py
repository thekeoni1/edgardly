"""
Step 6 tests: download Flask route
Pass criteria:
  - POST /api/download with missing fields returns 400
  - POST /api/download with no body returns 400
  - POST /api/download (mocked) returns {status: ok, path: ...}
  - POST /api/download with FilingNotFoundError returns 404
  - Integration: real download creates file on disk
"""
import sys
import os
import json
import pytest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

APPLE_CIK = "320193"
APPLE_FY2023_ACCESSION = "0000320193-23-000106"

VALID_PAYLOAD = {
    "cik": APPLE_CIK,
    "accession_number": APPLE_FY2023_ACCESSION,
    "company_name": "Apple Inc",
    "filing_date": "2023-11-03",
    "fiscal_year_end": "2023-09-30",
    "form_type": "10-K",
}


@pytest.fixture(scope="module")
def client():
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def test_download_no_body(client):
    r = client.post("/api/download", content_type="application/json")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_download_missing_fields(client):
    r = client.post(
        "/api/download",
        data=json.dumps({"cik": APPLE_CIK}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_download_mocked_success(client, tmp_path):
    fake_path = str(tmp_path / "10-K_2023-11-03.htm")
    fake_result = {"primary": fake_path, "paths": [fake_path], "pdf_fallback": False}
    with patch("edgar_api.download_filing", return_value=fake_result):
        r = client.post(
            "/api/download",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("status") == "ok"
    assert "path" in data


def test_download_mocked_filing_not_found(client):
    import edgar_api
    with patch("edgar_api.download_filing",
               side_effect=edgar_api.FilingNotFoundError("not found")):
        r = client.post(
            "/api/download",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
        )
    assert r.status_code == 404
    assert "error" in r.get_json()


@pytest.mark.integration
@pytest.mark.timeout(90)
def test_download_integration(client):
    r = client.post(
        "/api/download",
        data=json.dumps(VALID_PAYLOAD),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("status") == "ok"
    path = data.get("path", "")
    assert path, "No path returned"
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    assert os.path.isfile(path), f"Downloaded file not found on disk: {path}"
