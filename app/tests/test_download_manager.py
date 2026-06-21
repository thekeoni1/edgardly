"""
Stage 4 — download manager and PDF conversion backfill tests.

Covers gaps left by test_step11.py:
  - _safe_dirname special-character sanitization
  - _rate_limited_get 429 retry
  - _find_native_pdf_url absolute-href passthrough
  - download_filing directory and filename construction
  - download_filing html cache-hit (file already exists → no re-download)
  - download_filing pdf mode when source URL is already a .pdf
  - download_filing pdf mode cache-hit (pdf already on disk → no re-download)
  - download_filing both mode with Playwright failure → pdf_fallback=True
  - download_filing both mode when source URL is already a .pdf
  - download_filing raises FilingNotFoundError when no URL available
  - download_filings_batch one failure does not abort remaining items
  - download_filings_batch error result shape
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock, call

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import edgar_api
from edgar_api import FilingNotFoundError

CIK = "320193"
ACCESSION = "0000320193-23-000106"
FAKE_HTM_URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl20230930.htm"
FAKE_PDF_URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl20230930.pdf"


def _base_kwargs(tmp_path, fmt='html', url=FAKE_HTM_URL):
    return dict(
        cik=CIK,
        accession_number=ACCESSION,
        company_name="Apple Inc",
        filing_date="2023-11-03",
        fiscal_year_end="2023-09-30",
        form_type="10-K",
        downloads_dir=str(tmp_path),
        url=url,
        fmt=fmt,
    )


# ---------------------------------------------------------------------------
# _safe_dirname
# ---------------------------------------------------------------------------

class TestSafeDirname:
    def test_plain_name_unchanged(self):
        assert edgar_api._safe_dirname("Apple Inc") == "Apple Inc"

    def test_backslash_replaced(self):
        assert '\\' not in edgar_api._safe_dirname("A\\B")

    def test_forward_slash_replaced(self):
        assert '/' not in edgar_api._safe_dirname("A/B")

    def test_colon_replaced(self):
        assert ':' not in edgar_api._safe_dirname("A:B")

    def test_asterisk_replaced(self):
        assert '*' not in edgar_api._safe_dirname("A*B")

    def test_question_mark_replaced(self):
        assert '?' not in edgar_api._safe_dirname("A?B")

    def test_double_quote_replaced(self):
        assert '"' not in edgar_api._safe_dirname('A"B')

    def test_angle_brackets_replaced(self):
        result = edgar_api._safe_dirname("A<B>C")
        assert '<' not in result and '>' not in result

    def test_pipe_replaced(self):
        assert '|' not in edgar_api._safe_dirname("A|B")

    def test_leading_trailing_spaces_stripped(self):
        assert edgar_api._safe_dirname("  Apple  ") == "Apple"


# ---------------------------------------------------------------------------
# _rate_limited_get
# ---------------------------------------------------------------------------

class TestRateLimitedGet:
    def test_429_triggers_retry(self):
        """On a 429 response the function sleeps and retries once."""
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.raise_for_status.side_effect = None  # don't raise on the 429

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.raise_for_status.return_value = None

        with patch('requests.get', side_effect=[resp_429, resp_200]) as mock_get, \
             patch('time.sleep') as mock_sleep:
            result = edgar_api._rate_limited_get("https://example.com/test")

        assert mock_get.call_count == 2, "Expected exactly two GET calls (initial + retry)"
        # sleep is called at least twice: the rate-limit sleep + the 429 back-off
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        assert any(s >= 5 for s in sleep_args), f"Expected a >=5s back-off sleep; got {sleep_args}"
        assert result is resp_200

    def test_non_429_error_raised(self):
        """Non-429 HTTP errors propagate via raise_for_status."""
        resp = MagicMock()
        resp.status_code = 404
        resp.raise_for_status.side_effect = Exception("404 Not Found")
        with patch('requests.get', return_value=resp), \
             patch('time.sleep'):
            with pytest.raises(Exception, match="404 Not Found"):
                edgar_api._rate_limited_get("https://example.com/missing")


# ---------------------------------------------------------------------------
# _find_native_pdf_url
# ---------------------------------------------------------------------------

class TestFindNativePdfUrl:
    def test_relative_href_gets_sec_prefix(self):
        html = '<a href="/Archives/edgar/data/320193/0001/aapl.pdf">PDF</a>'
        m = MagicMock(); m.text = html
        with patch('edgar_api._rate_limited_get', return_value=m):
            result = edgar_api._find_native_pdf_url(CIK, ACCESSION)
        assert result.startswith("https://www.sec.gov")
        assert result.endswith(".pdf")

    def test_absolute_href_returned_as_is(self):
        """An href that already starts with https:// must not be double-prefixed."""
        html = f'<a href="{FAKE_PDF_URL}">PDF</a>'
        m = MagicMock(); m.text = html
        with patch('edgar_api._rate_limited_get', return_value=m):
            result = edgar_api._find_native_pdf_url(CIK, ACCESSION)
        assert result == FAKE_PDF_URL

    def test_case_insensitive_pdf_match(self):
        html = '<a href="/Archives/edgar/data/320193/0001/aapl.PDF">PDF</a>'
        m = MagicMock(); m.text = html
        with patch('edgar_api._rate_limited_get', return_value=m):
            result = edgar_api._find_native_pdf_url(CIK, ACCESSION)
        assert result is not None and result.endswith(".PDF")


# ---------------------------------------------------------------------------
# download_filing — directory and filename construction
# ---------------------------------------------------------------------------

class TestDownloadFilingStructure:
    def test_creates_company_year_subdirectory(self, tmp_path):
        with patch('edgar_api._download_url_to_file'):
            edgar_api.download_filing(**_base_kwargs(tmp_path))
        expected = tmp_path / "Apple Inc" / "2023"
        assert expected.is_dir(), f"Expected directory {expected}"

    def test_filename_includes_form_type_and_date(self, tmp_path):
        with patch('edgar_api._download_url_to_file'):
            result = edgar_api.download_filing(**_base_kwargs(tmp_path))
        fname = os.path.basename(result['primary'])
        assert '10-K' in fname
        assert '2023-11-03' in fname

    def test_amendment_form_type_slash_sanitized_in_filename(self, tmp_path):
        kwargs = _base_kwargs(tmp_path)
        kwargs['form_type'] = '10-K/A'
        with patch('edgar_api._download_url_to_file'):
            result = edgar_api.download_filing(**kwargs)
        fname = os.path.basename(result['primary'])
        assert '/' not in fname, f"Slash should be sanitized in filename: {fname}"
        assert '10-K-A' in fname

    def test_fiscal_year_drives_subdir_year(self, tmp_path):
        kwargs = _base_kwargs(tmp_path)
        kwargs['fiscal_year_end'] = '2022-09-24'
        with patch('edgar_api._download_url_to_file'):
            edgar_api.download_filing(**kwargs)
        assert (tmp_path / "Apple Inc" / "2022").is_dir()


# ---------------------------------------------------------------------------
# download_filing — html mode
# ---------------------------------------------------------------------------

class TestDownloadFilingHtml:
    def test_skips_download_when_file_already_exists(self, tmp_path):
        # Pre-create the destination file so os.path.exists returns True
        dest = tmp_path / "Apple Inc" / "2023" / "10-K_2023-11-03.htm"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"<html/>")

        with patch('edgar_api._download_url_to_file') as mock_dl:
            edgar_api.download_filing(**_base_kwargs(tmp_path))
        mock_dl.assert_not_called()

    def test_html_result_has_correct_keys(self, tmp_path):
        with patch('edgar_api._download_url_to_file'):
            result = edgar_api.download_filing(**_base_kwargs(tmp_path))
        assert set(result.keys()) >= {'primary', 'paths', 'pdf_fallback'}
        assert result['pdf_fallback'] is False


# ---------------------------------------------------------------------------
# download_filing — pdf mode
# ---------------------------------------------------------------------------

class TestDownloadFilingPdf:
    def test_direct_pdf_url_downloaded_without_conversion(self, tmp_path):
        """When the source URL itself is a .pdf, no conversion or native lookup needed."""
        with patch('edgar_api._download_url_to_file') as mock_dl, \
             patch('edgar_api._find_native_pdf_url') as mock_native, \
             patch('edgar_api._html_to_pdf_playwright') as mock_convert:
            result = edgar_api.download_filing(**_base_kwargs(tmp_path, fmt='pdf', url=FAKE_PDF_URL))
        assert result['primary'].endswith('.pdf')
        assert result['pdf_fallback'] is False
        mock_native.assert_not_called()
        mock_convert.assert_not_called()
        mock_dl.assert_called_once()

    def test_pdf_cache_hit_skips_download(self, tmp_path):
        """If the .pdf already exists on disk, no download or conversion is triggered."""
        kwargs = _base_kwargs(tmp_path, fmt='pdf')
        with patch('edgar_api._find_native_pdf_url', return_value=None), \
             patch('edgar_api._download_url_to_file'), \
             patch('edgar_api._html_to_pdf_playwright'):
            # Warm the cache
            edgar_api.download_filing(**kwargs)

        # Make the pdf exist on disk
        dest = tmp_path / "Apple Inc" / "2023" / "10-K_2023-11-03.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF-1.4 fake")

        with patch('edgar_api._find_native_pdf_url') as mock_native, \
             patch('edgar_api._download_url_to_file') as mock_dl, \
             patch('edgar_api._html_to_pdf_playwright') as mock_convert:
            result = edgar_api.download_filing(**kwargs)

        mock_native.assert_not_called()
        mock_dl.assert_not_called()
        mock_convert.assert_not_called()
        assert result['primary'].endswith('.pdf')

    def test_playwright_conversion_called_when_no_native(self, tmp_path):
        """When no native PDF exists, Playwright conversion is attempted."""
        with patch('edgar_api._find_native_pdf_url', return_value=None), \
             patch('edgar_api._download_url_to_file'), \
             patch('edgar_api._html_to_pdf_playwright') as mock_convert:
            edgar_api.download_filing(**_base_kwargs(tmp_path, fmt='pdf'))
        mock_convert.assert_called_once()


# ---------------------------------------------------------------------------
# download_filing — both mode
# ---------------------------------------------------------------------------

class TestDownloadFilingBoth:
    def test_both_mode_playwright_failure_returns_htm_with_fallback(self, tmp_path):
        """When Playwright raises in 'both' mode, primary is .htm and pdf_fallback=True."""
        with patch('edgar_api._find_native_pdf_url', return_value=None), \
             patch('edgar_api._download_url_to_file'), \
             patch('edgar_api._html_to_pdf_playwright', side_effect=Exception("no chromium")):
            result = edgar_api.download_filing(**_base_kwargs(tmp_path, fmt='both'))
        assert result['pdf_fallback'] is True
        assert result['primary'].endswith('.htm')
        assert len(result['paths']) == 1

    def test_both_mode_direct_pdf_url_skips_conversion(self, tmp_path):
        """Source URL is already a .pdf — download it directly, no conversion."""
        with patch('edgar_api._download_url_to_file') as mock_dl, \
             patch('edgar_api._find_native_pdf_url') as mock_native, \
             patch('edgar_api._html_to_pdf_playwright') as mock_convert:
            result = edgar_api.download_filing(**_base_kwargs(tmp_path, fmt='both', url=FAKE_PDF_URL))
        assert result['primary'].endswith('.pdf')
        assert result['pdf_fallback'] is False
        mock_native.assert_not_called()
        mock_convert.assert_not_called()

    def test_both_mode_pdf_already_on_disk_skips_native_lookup(self, tmp_path):
        """If the .pdf already exists, both mode skips the native PDF lookup."""
        dest = tmp_path / "Apple Inc" / "2023" / "10-K_2023-11-03.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF-1.4 fake")

        with patch('edgar_api._download_url_to_file'), \
             patch('edgar_api._find_native_pdf_url') as mock_native, \
             patch('edgar_api._html_to_pdf_playwright') as mock_convert:
            result = edgar_api.download_filing(**_base_kwargs(tmp_path, fmt='both'))

        mock_native.assert_not_called()
        mock_convert.assert_not_called()
        assert result['pdf_fallback'] is False


# ---------------------------------------------------------------------------
# download_filing — FilingNotFoundError
# ---------------------------------------------------------------------------

class TestDownloadFilingNotFound:
    def test_raises_when_no_url_and_resolve_fails(self, tmp_path):
        """No url kwarg + resolve_primary_document returning None → FilingNotFoundError."""
        kwargs = _base_kwargs(tmp_path)
        kwargs.pop('url')  # no url provided
        with patch('edgar_api.resolve_primary_document', return_value=None):
            with pytest.raises(FilingNotFoundError):
                edgar_api.download_filing(**kwargs)


# ---------------------------------------------------------------------------
# download_filings_batch
# ---------------------------------------------------------------------------

class TestDownloadFilingsBatch:
    def _filing(self, acc):
        return {
            'cik': CIK,
            'accession_number': acc,
            'company_name': 'Apple Inc',
            'filing_date': '2023-11-03',
            'fiscal_year_end': '2023-09-30',
            'form_type': '10-K',
            'document_url': FAKE_HTM_URL,
        }

    def test_one_failure_does_not_abort_remaining(self, tmp_path):
        """An exception on filing N must not prevent filing N+1 from being processed."""
        filings = [self._filing('0000320193-23-000001'),
                   self._filing('0000320193-23-000002'),
                   self._filing('0000320193-23-000003')]

        call_count = 0
        def fake_download(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs['accession_number'] == '0000320193-23-000002':
                raise Exception("download error")
            return {'primary': '/fake/path.htm', 'paths': ['/fake/path.htm'], 'pdf_fallback': False}

        with patch('edgar_api.download_filing', side_effect=fake_download):
            results = edgar_api.download_filings_batch(filings, str(tmp_path))

        assert call_count == 3, "All 3 filings must be attempted"
        assert len(results) == 3

    def test_failed_item_has_error_status_and_key(self, tmp_path):
        """A failed filing produces {'status': 'error', 'error': str}."""
        filings = [self._filing(ACCESSION)]

        with patch('edgar_api.download_filing', side_effect=Exception("boom")):
            results = edgar_api.download_filings_batch(filings, str(tmp_path))

        assert results[0]['status'] == 'error'
        assert 'error' in results[0]
        assert results[0]['accession_number'] == ACCESSION

    def test_successful_item_has_ok_status(self, tmp_path):
        """A successful filing produces {'status': 'ok', 'path': ..., 'pdf_fallback': ...}."""
        filings = [self._filing(ACCESSION)]
        fake = {'primary': '/fake/path.htm', 'paths': ['/fake/path.htm'], 'pdf_fallback': False}

        with patch('edgar_api.download_filing', return_value=fake):
            results = edgar_api.download_filings_batch(filings, str(tmp_path))

        assert results[0]['status'] == 'ok'
        assert results[0]['path'] == '/fake/path.htm'
        assert results[0]['pdf_fallback'] is False
        assert results[0]['accession_number'] == ACCESSION

    def test_fmt_passed_to_download_filing(self, tmp_path):
        """The fmt parameter is forwarded to each download_filing call."""
        filings = [self._filing(ACCESSION)]
        fake = {'primary': '/fake/path.pdf', 'paths': ['/fake/path.pdf'], 'pdf_fallback': False}
        captured = {}

        def capture(**kwargs):
            captured['fmt'] = kwargs.get('fmt')
            return fake

        with patch('edgar_api.download_filing', side_effect=capture):
            edgar_api.download_filings_batch(filings, str(tmp_path), fmt='pdf')

        assert captured['fmt'] == 'pdf'
