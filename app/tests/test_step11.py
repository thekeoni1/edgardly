"""
Step 11 tests: PDF download format selection
Pass criteria:
  - /api/download with format='html' -> calls download_filing(fmt='html')
  - /api/download with format='pdf' -> calls download_filing(fmt='pdf')
  - /api/download with format='both' -> calls download_filing(fmt='both')
  - /api/download with invalid format -> 400
  - /api/download response includes pdf_fallback field
  - /api/download-batch requires dict body with 'filings' key
  - /api/download-batch passes format to download_filings_batch
  - edgar_api._find_native_pdf_url parses PDF href from index HTML
  - edgar_api._find_native_pdf_url returns None when no PDF in index
  - edgar_api.download_filing(fmt='html') returns dict with .htm path
  - edgar_api.download_filing(fmt='pdf') uses native PDF when found
  - edgar_api.download_filing(fmt='pdf') falls back to HTML on conversion failure
  - edgar_api.download_filing(fmt='both') returns both paths
"""
import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

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


# -- Route format validation --------------------------------------------------

def test_download_invalid_format(client):
    payload = dict(VALID_PAYLOAD, format="docx")
    fake = {'primary': '/tmp/x.htm', 'paths': ['/tmp/x.htm'], 'pdf_fallback': False}
    with patch("edgar_api.download_filing", return_value=fake):
        r = client.post("/api/download",
                        data=json.dumps(payload),
                        content_type="application/json")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_download_html_format_passes_fmt(client, tmp_path):
    fake_path = str(tmp_path / "10-K_2023-11-03.htm")
    fake = {'primary': fake_path, 'paths': [fake_path], 'pdf_fallback': False}
    captured = {}
    def capture(**kwargs):
        captured.update(kwargs)
        return fake
    with patch("edgar_api.download_filing", side_effect=capture):
        client.post("/api/download",
                    data=json.dumps(dict(VALID_PAYLOAD, format="html")),
                    content_type="application/json")
    assert captured.get("fmt") == "html"


def test_download_pdf_format_passes_fmt(client, tmp_path):
    fake_path = str(tmp_path / "10-K_2023-11-03.pdf")
    fake = {'primary': fake_path, 'paths': [fake_path], 'pdf_fallback': False}
    captured = {}
    def capture(**kwargs):
        captured.update(kwargs)
        return fake
    with patch("edgar_api.download_filing", side_effect=capture):
        client.post("/api/download",
                    data=json.dumps(dict(VALID_PAYLOAD, format="pdf")),
                    content_type="application/json")
    assert captured.get("fmt") == "pdf"


def test_download_both_format_passes_fmt(client, tmp_path):
    fake_path = str(tmp_path / "10-K_2023-11-03.pdf")
    fake = {'primary': fake_path, 'paths': [fake_path], 'pdf_fallback': False}
    captured = {}
    def capture(**kwargs):
        captured.update(kwargs)
        return fake
    with patch("edgar_api.download_filing", side_effect=capture):
        client.post("/api/download",
                    data=json.dumps(dict(VALID_PAYLOAD, format="both")),
                    content_type="application/json")
    assert captured.get("fmt") == "both"


def test_download_response_includes_pdf_fallback(client, tmp_path):
    fake_path = str(tmp_path / "10-K_2023-11-03.htm")
    fake = {'primary': fake_path, 'paths': [fake_path], 'pdf_fallback': True}
    with patch("edgar_api.download_filing", return_value=fake):
        r = client.post("/api/download",
                        data=json.dumps(dict(VALID_PAYLOAD, format="pdf")),
                        content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    assert data["pdf_fallback"] is True


# -- Batch route --------------------------------------------------------------

def test_batch_format_passed_to_api(client, tmp_path):
    fake_path = str(tmp_path / "10-K_2023-11-03.pdf")
    fake = {'primary': fake_path, 'paths': [fake_path], 'pdf_fallback': False}
    captured = {}
    def capture(filings, downloads_dir, fmt='html'):
        captured['fmt'] = fmt
        return [{'accession_number': filings[0]['accession_number'],
                 'status': 'ok', 'path': fake_path, 'pdf_fallback': False}]
    with patch("edgar_api.download_filings_batch", side_effect=capture):
        client.post("/api/download-batch",
                    data=json.dumps({"format": "pdf", "filings": [VALID_PAYLOAD]}),
                    content_type="application/json")
    assert captured.get("fmt") == "pdf"


def test_batch_results_include_pdf_fallback(client, tmp_path):
    fake_path = str(tmp_path / "10-K_2023-11-03.htm")
    def fake_batch(filings, downloads_dir, fmt='html'):
        return [{'accession_number': filings[0]['accession_number'],
                 'status': 'ok', 'path': fake_path, 'pdf_fallback': True}]
    with patch("edgar_api.download_filings_batch", side_effect=fake_batch):
        r = client.post("/api/download-batch",
                        data=json.dumps({"format": "pdf", "filings": [VALID_PAYLOAD]}),
                        content_type="application/json")
    assert r.status_code == 200
    results = r.get_json()["results"]
    assert results[0]["pdf_fallback"] is True


# -- edgar_api unit tests -----------------------------------------------------

def test_find_native_pdf_url_found():
    import edgar_api
    index_html = '<a href="/Archives/edgar/data/320193/000032019323000106/aapl20230930.pdf">PDF</a>'
    mock_resp = MagicMock()
    mock_resp.text = index_html
    with patch("edgar_api._rate_limited_get", return_value=mock_resp):
        result = edgar_api._find_native_pdf_url("320193", APPLE_FY2023_ACCESSION)
    assert result is not None
    assert result.endswith(".pdf")
    assert "sec.gov" in result


def test_find_native_pdf_url_not_found():
    import edgar_api
    index_html = '<a href="/Archives/edgar/data/320193/000032019323000106/aapl20230930.htm">10-K</a>'
    mock_resp = MagicMock()
    mock_resp.text = index_html
    with patch("edgar_api._rate_limited_get", return_value=mock_resp):
        result = edgar_api._find_native_pdf_url("320193", APPLE_FY2023_ACCESSION)
    assert result is None


def test_find_native_pdf_url_network_error():
    import edgar_api
    with patch("edgar_api._rate_limited_get", side_effect=Exception("timeout")):
        result = edgar_api._find_native_pdf_url("320193", APPLE_FY2023_ACCESSION)
    assert result is None


def test_download_filing_html_returns_dict(tmp_path):
    import edgar_api
    fake_url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl20230930.htm"
    with patch("edgar_api._download_url_to_file") as mock_dl:
        result = edgar_api.download_filing(
            cik="320193",
            accession_number=APPLE_FY2023_ACCESSION,
            company_name="Apple Inc",
            filing_date="2023-11-03",
            fiscal_year_end="2023-09-30",
            form_type="10-K",
            downloads_dir=str(tmp_path),
            url=fake_url,
            fmt='html',
        )
    assert isinstance(result, dict)
    assert 'primary' in result
    assert 'paths' in result
    assert 'pdf_fallback' in result
    assert result['primary'].endswith('.htm')
    assert result['pdf_fallback'] is False
    mock_dl.assert_called_once()


def test_download_filing_pdf_uses_native(tmp_path):
    import edgar_api
    fake_url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl20230930.htm"
    native_pdf = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl20230930.pdf"
    with patch("edgar_api._find_native_pdf_url", return_value=native_pdf), \
         patch("edgar_api._download_url_to_file") as mock_dl:
        result = edgar_api.download_filing(
            cik="320193",
            accession_number=APPLE_FY2023_ACCESSION,
            company_name="Apple Inc",
            filing_date="2023-11-03",
            fiscal_year_end="2023-09-30",
            form_type="10-K",
            downloads_dir=str(tmp_path),
            url=fake_url,
            fmt='pdf',
        )
    assert result['primary'].endswith('.pdf')
    assert result['pdf_fallback'] is False
    assert mock_dl.call_args[0][0] == native_pdf


def test_download_filing_pdf_fallback_on_conversion_error(tmp_path):
    import edgar_api
    fake_url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl20230930.htm"
    with patch("edgar_api._find_native_pdf_url", return_value=None), \
         patch("edgar_api._download_url_to_file"), \
         patch("edgar_api._html_to_pdf_playwright", side_effect=Exception("Chromium not found")):
        result = edgar_api.download_filing(
            cik="320193",
            accession_number=APPLE_FY2023_ACCESSION,
            company_name="Apple Inc",
            filing_date="2023-11-03",
            fiscal_year_end="2023-09-30",
            form_type="10-K",
            downloads_dir=str(tmp_path),
            url=fake_url,
            fmt='pdf',
        )
    assert result['pdf_fallback'] is True
    assert result['primary'].endswith('.htm')


def test_download_filing_both_returns_two_paths(tmp_path):
    import edgar_api
    fake_url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl20230930.htm"
    native_pdf = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl20230930.pdf"
    with patch("edgar_api._find_native_pdf_url", return_value=native_pdf), \
         patch("edgar_api._download_url_to_file"):
        result = edgar_api.download_filing(
            cik="320193",
            accession_number=APPLE_FY2023_ACCESSION,
            company_name="Apple Inc",
            filing_date="2023-11-03",
            fiscal_year_end="2023-09-30",
            form_type="10-K",
            downloads_dir=str(tmp_path),
            url=fake_url,
            fmt='both',
        )
    assert len(result['paths']) == 2
    assert any(p.endswith('.htm') for p in result['paths'])
    assert any(p.endswith('.pdf') for p in result['paths'])
    assert result['pdf_fallback'] is False


# -- JS fix unit tests (via Playwright) ---------------------------------------

@pytest.mark.integration
def test_fix_removes_near_blank_hr_page():
    """Hidden <hr> + adjacent empty spacers -> no forced break remains."""
    from playwright.sync_api import sync_playwright
    import edgar_api

    html = """\
<html><body>
  <p>Section A content</p>
  <p style="page-break-after:always">&nbsp;</p>
  <hr>
  <p style="page-break-after:always">&nbsp;</p>
  <h2>Section B</h2>
</body></html>"""

    query_js = """\
(function() {
  var out = [];
  document.querySelectorAll('*').forEach(function(el) {
    var cs = window.getComputedStyle(el);
    var ba = cs.breakAfter  || cs.pageBreakAfter  || '';
    var bb = cs.breakBefore || cs.pageBreakBefore || '';
    if (ba === 'always' || ba === 'page' || bb === 'always' || bb === 'page')
      out.push({tag: el.tagName, ba: ba, bb: bb});
  });
  return out;
}())"""

    import tempfile
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        with tempfile.NamedTemporaryFile(suffix='.html', mode='w', delete=False) as f:
            f.write(html)
            f.flush()
            pg.goto('file:///' + f.name.replace('\\', '/'), wait_until='domcontentloaded')
        pg.evaluate(edgar_api._EDGAR_PAGE_BREAK_FIX_JS)
        breaks = pg.evaluate(query_js)
        browser.close()

    h2_breaks = [b for b in breaks if b['tag'] == 'H2']
    assert len(h2_breaks) == 1
    bb = h2_breaks[0]['bb']
    assert bb in ('always', 'page'), f"H2 break-before expected, got {bb!r}"
    other_breaks = [b for b in breaks if b['tag'] != 'H2']
    assert other_breaks == [], f"Unexpected forced breaks: {other_breaks}"


@pytest.mark.integration
def test_fix_pass2_removes_double_break():
    from playwright.sync_api import sync_playwright
    import edgar_api

    html = """\
<html><body>
  <p>Section A content</p>
  <p style="page-break-after:always">&nbsp;</p>
  <p>&nbsp;</p>
  <hr>
  <p style="page-break-after:always">&nbsp;</p>
  <h2>Section B</h2>
</body></html>"""

    query_js = """\
(function() {
  var out = [];
  document.querySelectorAll('*').forEach(function(el) {
    var cs = window.getComputedStyle(el);
    var ba = cs.breakAfter  || cs.pageBreakAfter  || '';
    var bb = cs.breakBefore || cs.pageBreakBefore || '';
    if (ba === 'always' || ba === 'page' || bb === 'always' || bb === 'page')
      out.push({tag: el.tagName, ba: ba, bb: bb,
                text: (el.textContent||'').replace(/[\\u00a0\\s]+/g,' ').trim().slice(0,40)});
  });
  return out;
}())"""

    import tempfile
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        with tempfile.NamedTemporaryFile(suffix='.html', mode='w', delete=False) as f:
            f.write(html)
            f.flush()
            pg.goto('file:///' + f.name.replace('\\', '/'), wait_until='domcontentloaded')
        pg.evaluate(edgar_api._EDGAR_PAGE_BREAK_FIX_JS)
        breaks = pg.evaluate(query_js)
        browser.close()

    assert len(breaks) == 1, f"Expected 1 forced break, got {len(breaks)}: {breaks}"
    assert breaks[0]['tag'] == 'H2', f"Expected H2, got: {breaks}"
    bb = breaks[0]['bb']
    assert bb in ('always', 'page'), f"H2 break-before expected, got {bb!r}"


@pytest.mark.integration
def test_fix_preserves_section_breaks_without_hr():
    from playwright.sync_api import sync_playwright
    import edgar_api

    html = """\
<html><body>
  <div style="page-break-after:always">
    <p>Part I content that fills a page</p>
  </div>
  <div>
    <h2>Part II</h2>
    <p>Part II content</p>
  </div>
</body></html>"""

    query_js = """\
(function() {
  var out = [];
  document.querySelectorAll('*').forEach(function(el) {
    var cs = window.getComputedStyle(el);
    var ba = cs.breakAfter  || cs.pageBreakAfter  || '';
    var bb = cs.breakBefore || cs.pageBreakBefore || '';
    if (ba === 'always' || ba === 'page' || bb === 'always' || bb === 'page')
      out.push({tag: el.tagName, ba: ba, bb: bb});
  });
  return out;
}())"""

    import tempfile
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        with tempfile.NamedTemporaryFile(suffix='.html', mode='w', delete=False) as f:
            f.write(html)
            f.flush()
            pg.goto('file:///' + f.name.replace('\\', '/'), wait_until='domcontentloaded')
        pg.evaluate(edgar_api._EDGAR_PAGE_BREAK_FIX_JS)
        breaks = pg.evaluate(query_js)
        browser.close()

    assert any(b['ba'] in ('always', 'page') for b in breaks), \
        f"Section break-after should survive: {breaks}"


# -- Integration --------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(90)
def test_download_html_integration(client):
    r = client.post("/api/download",
                    data=json.dumps(dict(VALID_PAYLOAD, format="html")),
                    content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert os.path.isfile(data["path"]), "Downloaded HTML file not found"
    assert data["path"].endswith(".htm")
