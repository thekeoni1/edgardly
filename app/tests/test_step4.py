"""
Step 4 tests: Flask UI routes
Pass criteria:
  - GET /api/search?q=AAPL returns JSON list with Apple CIK 320193
  - GET /api/filings?cik=320193&start=2020-01-01&end=2024-12-31 returns JSON list
  - Filings response contains required fields
  - GET /api/filings without required params returns 400
  - Homepage HTML contains the company search input and search button
"""
import sys
import os
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

APPLE_CIK = "320193"
REQUIRED_FIELDS = {"form_type", "filing_date", "accession_number", "document_url", "fiscal_year_end"}


@pytest.fixture(scope="module")
def client():
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def test_homepage_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200


def test_homepage_has_search_input(client):
    r = client.get("/")
    html = r.data.decode()
    assert "company-input" in html, "Company search input missing from homepage"
    assert "search-btn" in html, "Search button missing from homepage"


def test_search_empty_query(client):
    r = client.get("/api/search?q=")
    assert r.status_code == 200
    assert r.get_json() == []


@pytest.mark.integration
def test_search_returns_apple(client):
    r = client.get("/api/search?q=AAPL")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list), "Expected a list"
    ciks = [str(item["cik"]) for item in data]
    assert APPLE_CIK in ciks, f"Apple CIK {APPLE_CIK} not in search results: {ciks}"


@pytest.mark.integration
def test_search_result_fields(client):
    r = client.get("/api/search?q=microsoft")
    assert r.status_code == 200
    data = r.get_json()
    assert data, "No results for 'microsoft'"
    for item in data:
        assert "cik" in item
        assert "ticker" in item
        assert "company_name" in item


def test_filings_missing_params_returns_400(client):
    r = client.get("/api/filings?cik=320193")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_filings_missing_cik_returns_400(client):
    r = client.get("/api/filings?start=2020-01-01&end=2024-12-31")
    assert r.status_code == 400


@pytest.mark.integration
def test_filings_returns_list(client):
    r = client.get(f"/api/filings?cik={APPLE_CIK}&start=2020-01-01&end=2024-12-31")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list), "Expected a list of filings"
    assert len(data) > 0, "Expected at least one filing"


@pytest.mark.integration
def test_filings_required_fields(client):
    r = client.get(f"/api/filings?cik={APPLE_CIK}&start=2022-01-01&end=2024-12-31")
    assert r.status_code == 200
    data = r.get_json()
    assert data, "No filings returned"
    for f in data:
        missing = REQUIRED_FIELDS - set(f.keys())
        assert not missing, f"Filing missing fields: {missing}"


@pytest.mark.integration
def test_filings_amendments_excluded_by_default(client):
    r = client.get(f"/api/filings?cik={APPLE_CIK}&start=2000-01-01&end=2024-12-31")
    assert r.status_code == 200
    data = r.get_json()
    for f in data:
        assert f["form_type"] == "10-K", f"Got amendment when not requested: {f['form_type']}"
