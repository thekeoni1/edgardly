"""
Step 7 tests: batch download route
Pass criteria:
  - POST /api/download-batch with non-list body returns 400
  - POST /api/download-batch with empty list returns 400
  - POST /api/download-batch with a missing field returns 400
  - POST /api/download-batch (mocked) returns per-item {status, path}
  - One failed item does not prevent others from succeeding
  - Integration: batch of two Apple filings downloads both files to disk
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
APPLE_FY2022_ACCESSION = "0000320193-22-000108"

FILING_FY2023 = {
    "cik": APPLE_CIK,
    "accession_number": APPLE_FY2023_ACCESSION,
    "company_name": "Apple Inc",
    "filing_date": "2023-11-03",
    "fiscal_year_end": "2023-09-30",
    "form_type": "10-K",
}
FILING_FY2022 = {
    "cik": APPLE_CIK,
    "accession_number": APPLE_FY2022_ACCESSION,
    "company_name": "Apple Inc",
    "filing_date": "2022-10-28",
    "fiscal_year_end": "2022-09-24",
    "form_type": "10-K",
}


@pytest.fixture(scope="module")
def client():
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def test_batch_non_list_body(client):
    r = client.post("/api/download-batch",
                    data=json.dumps({"cik": APPLE_CIK}),
                    content_type="application/json")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_batch_empty_list(client):
    r = client.post("/api/download-batch",
                    data=json.dumps([]),
                    content_type="application/json")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_batch_missing_field(client):
    bad = dict(FILING_FY2023)
    del bad["company_name"]
    r = client.post("/api/download-batch",
                    data=json.dumps([bad]),
                    content_type="application/json")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_batch_mocked_success(client, tmp_path):
    fake_path = str(tmp_path / "10-K_2023-11-03.htm")
    fake_result = [{"accession_number": APPLE_FY2023_ACCESSION, "status": "ok", "path": fake_path, "pdf_fallback": False}]
    with patch("edgar_api.download_filings_batch", return_value=fake_result):
        r = client.post("/api/download-batch",
                        data=json.dumps({"filings": [FILING_FY2023]}),
                        content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    results = data["results"]
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["status"] == "ok"
    assert "path" in results[0]


def test_batch_partial_failure(client, tmp_path):
    fake_path = str(tmp_path / "10-K_2023-11-03.htm")
    import edgar_api

    fake_results = [
        {"accession_number": APPLE_FY2023_ACCESSION, "status": "ok", "path": fake_path, "pdf_fallback": False},
        {"accession_number": APPLE_FY2022_ACCESSION, "status": "error", "error": "not found", "pdf_fallback": False},
    ]
    with patch("edgar_api.download_filings_batch", return_value=fake_results):
        r = client.post("/api/download-batch",
                        data=json.dumps({"filings": [FILING_FY2023, FILING_FY2022]}),
                        content_type="application/json")
    assert r.status_code == 200
    results = r.get_json()["results"]
    assert len(results) == 2
    statuses = {res["accession_number"]: res["status"] for res in results}
    assert statuses[APPLE_FY2023_ACCESSION] == "ok"
    assert statuses[APPLE_FY2022_ACCESSION] == "error"


@pytest.mark.integration
@pytest.mark.timeout(180)
def test_batch_integration_two_filings(client):
    r = client.post("/api/download-batch",
                    data=json.dumps([FILING_FY2023, FILING_FY2022]),
                    content_type="application/json")
    assert r.status_code == 200
    results = r.get_json()
    assert isinstance(results, list)
    assert len(results) == 2
    for res in results:
        assert res["status"] == "ok", f"Filing {res['accession_number']} failed: {res.get('error')}"
        path = res["path"]
        if not os.path.isabs(path):
            path = os.path.join(BASE_DIR, path)
        assert os.path.isfile(path), f"File not found on disk: {path}"
