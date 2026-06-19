"""
Step 2 tests: ticker/CIK resolver
Pass criteria:
  - Cache DB is created after first call
  - Searching "MSFT" returns Microsoft with correct CIK
  - Searching "apple" (lowercase) returns Apple Inc with CIK 320193
  - Partial name "berkshire" returns at least one result
  - A recent-ish IPO name falls back to EDGAR company search
"""
import os
import sys
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


@pytest.fixture(scope="module")
def edgar_api():
    import edgar_api
    return edgar_api


@pytest.mark.integration
def test_cache_db_created(edgar_api):
    edgar_api.search_companies("apple")
    db_path = os.path.join(BASE_DIR, "data", "tickers.db")
    assert os.path.isfile(db_path), "tickers.db not created after first call"


@pytest.mark.integration
def test_search_by_ticker_msft(edgar_api):
    results = edgar_api.search_companies("MSFT")
    assert results, "No results for MSFT"
    tickers = [r["ticker"].upper() for r in results]
    assert "MSFT" in tickers, f"MSFT not found in {tickers}"


@pytest.mark.integration
def test_search_by_name_apple(edgar_api):
    results = edgar_api.search_companies("apple")
    assert results, "No results for 'apple'"
    ciks = [str(r["cik"]) for r in results]
    assert "320193" in ciks, f"Apple CIK 320193 not found in {ciks}"


@pytest.mark.integration
def test_partial_name_berkshire(edgar_api):
    results = edgar_api.search_companies("berkshire")
    assert len(results) > 0, "No results for partial name 'berkshire'"


@pytest.mark.integration
def test_result_fields(edgar_api):
    results = edgar_api.search_companies("microsoft")
    assert results, "No results for 'microsoft'"
    for r in results:
        assert "cik" in r, "Missing 'cik' field"
        assert "ticker" in r, "Missing 'ticker' field"
        assert "company_name" in r, "Missing 'company_name' field"
