"""
Step 3 tests: EDGAR filing search
Pass criteria:
  - Apple (CIK 320193) has >= 9 10-K filings between 2015 and 2024
  - Each filing has required fields
  - Only requested form types are returned
  - Date range filtering works (no filings outside the range)
"""
import sys
import os
import pytest
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

APPLE_CIK = "320193"
REQUIRED_FIELDS = {"form_type", "filing_date", "accession_number", "document_url", "fiscal_year_end"}


@pytest.fixture(scope="module")
def edgar_api():
    import edgar_api
    return edgar_api


@pytest.mark.integration
def test_apple_10k_count(edgar_api):
    filings = edgar_api.get_filings(APPLE_CIK, "2015-01-01", "2024-12-31", form_types=["10-K"])
    assert len(filings) >= 9, f"Expected >= 9 Apple 10-Ks, got {len(filings)}"


@pytest.mark.integration
def test_required_fields(edgar_api):
    filings = edgar_api.get_filings(APPLE_CIK, "2020-01-01", "2024-12-31", form_types=["10-K"])
    assert filings, "No filings returned"
    for f in filings:
        missing = REQUIRED_FIELDS - set(f.keys())
        assert not missing, f"Filing missing fields: {missing}"


@pytest.mark.integration
def test_only_requested_form_types(edgar_api):
    filings = edgar_api.get_filings(APPLE_CIK, "2000-01-01", "2024-12-31", form_types=["10-K"])
    for f in filings:
        assert f["form_type"] == "10-K", f"Got unexpected form type: {f['form_type']}"


@pytest.mark.integration
def test_date_range_respected(edgar_api):
    filings = edgar_api.get_filings(APPLE_CIK, "2020-01-01", "2022-12-31", form_types=["10-K"])
    for f in filings:
        filing_date = datetime.strptime(f["filing_date"], "%Y-%m-%d")
        assert datetime(2020, 1, 1) <= filing_date <= datetime(2022, 12, 31), \
            f"Filing date {f['filing_date']} outside requested range"


@pytest.mark.integration
def test_accession_number_format(edgar_api):
    filings = edgar_api.get_filings(APPLE_CIK, "2023-01-01", "2024-12-31", form_types=["10-K"])
    for f in filings:
        acc = f["accession_number"]
        assert len(acc) > 0, "Empty accession number"
        assert "-" in acc, f"Accession number format unexpected: {acc}"
