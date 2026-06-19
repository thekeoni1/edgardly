"""
Step 5 tests: download manager
Pass criteria:
  - Resolving a filing index returns a primary document URL
  - Downloading a single small filing produces a file on disk
  - File is saved under downloads/{company_name}/{fiscal_year}/
  - Filename follows the 10-K_{filing_date}.htm convention
  - A failed download (bad accession) is logged but does not crash the batch
"""
import sys
import os
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

APPLE_CIK = "320193"
# A known Apple 10-K accession number (FY2023, filed 2023-11-03)
APPLE_FY2023_ACCESSION = "0000320193-23-000106"


@pytest.fixture(scope="module")
def edgar_api():
    import edgar_api
    return edgar_api


@pytest.mark.integration
def test_resolve_primary_document(edgar_api):
    url = edgar_api.resolve_primary_document(APPLE_CIK, APPLE_FY2023_ACCESSION)
    assert url, "resolve_primary_document returned empty"
    assert url.startswith("https://www.sec.gov/"), f"Unexpected URL: {url}"
    assert url.endswith((".htm", ".html", ".pdf")), f"Unexpected file type: {url}"


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_download_creates_file(edgar_api):
    downloads_dir = os.path.join(BASE_DIR, "downloads")
    edgar_api.download_filing(
        cik=APPLE_CIK,
        accession_number=APPLE_FY2023_ACCESSION,
        company_name="Apple Inc",
        filing_date="2023-11-03",
        fiscal_year_end="2023",
        form_type="10-K",
        downloads_dir=downloads_dir,
    )
    company_dir = os.path.join(downloads_dir, "Apple Inc", "2023")
    assert os.path.isdir(company_dir), f"Company directory not created: {company_dir}"
    files = os.listdir(company_dir)
    assert any("10-K" in f and "2023-11-03" in f for f in files), \
        f"Expected file not found in {company_dir}: {files}"


@pytest.mark.integration
def test_bad_accession_does_not_crash(edgar_api):
    """A bad accession number should raise a specific exception or return an error dict, not crash."""
    try:
        result = edgar_api.resolve_primary_document(APPLE_CIK, "0000000000-00-000000")
        # If it returns None or empty string, that is acceptable
        assert result is None or result == ""
    except edgar_api.FilingNotFoundError:
        pass  # A typed exception is also acceptable
    except Exception as e:
        pytest.fail(f"Unexpected exception type on bad accession: {type(e).__name__}: {e}")
