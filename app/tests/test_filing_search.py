"""
Stage 3 — filing search backfill tests.

Covers get_filings, _parse_filing_block, _fetch_all_submissions, and
get_company_meta.  All tests are unit-level (no network) unless marked
integration.

Already covered by test_step9.py (excluded here to avoid duplication):
  - form_types=['10-K'] filtering
  - form_types=None returns all types
  - Flask route parameter parsing
"""
import sys
import os
import time
import pytest
from unittest.mock import patch, MagicMock, call

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import edgar_api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_block(accessions, forms, dates, periods=None, primary_docs=None):
    n = len(accessions)
    return {
        'accessionNumber': accessions,
        'form':            forms,
        'filingDate':      dates,
        'reportDate':      periods or [''] * n,
        'primaryDocument': primary_docs or [''] * n,
    }


def _make_submissions_resp(recent_block, files=None, sic='7370',
                           sic_desc='Services-Prepackaged Software',
                           category='Large accelerated filer'):
    m = MagicMock()
    m.json.return_value = {
        'sic': sic,
        'sicDescription': sic_desc,
        'category': category,
        'filings': {
            'recent': recent_block,
            'files': files or [],
        },
    }
    return m


# ---------------------------------------------------------------------------
# _parse_filing_block
# ---------------------------------------------------------------------------

class TestParseFilingBlock:
    CIK = '0000320193'

    def test_basic_fields_populated(self):
        block = _make_block(
            ['0000320193-23-000106'],
            ['10-K'],
            ['2023-11-03'],
            ['2023-09-30'],
            ['aapl-20230930.htm'],
        )
        results = edgar_api._parse_filing_block(self.CIK, block)
        assert len(results) == 1
        r = results[0]
        assert r['form_type'] == '10-K'
        assert r['filing_date'] == '2023-11-03'
        assert r['fiscal_year_end'] == '2023-09-30'
        assert r['accession_number'] == '0000320193-23-000106'
        assert r['estimated_size'] is None

    def test_doc_url_uses_primary_document(self):
        block = _make_block(
            ['0000320193-23-000106'],
            ['10-K'],
            ['2023-11-03'],
            primary_docs=['aapl-20230930.htm'],
        )
        results = edgar_api._parse_filing_block(self.CIK, block)
        url = results[0]['document_url']
        assert '000032019323000106' in url, "accession dashes should be stripped in URL path"
        assert 'aapl-20230930.htm' in url

    def test_doc_url_falls_back_to_index_when_no_primary(self):
        block = _make_block(
            ['0000320193-23-000106'],
            ['10-K'],
            ['2023-11-03'],
            primary_docs=[''],
        )
        results = edgar_api._parse_filing_block(self.CIK, block)
        url = results[0]['document_url']
        assert '-index.htm' in url

    def test_skips_entry_with_empty_form_type(self):
        block = _make_block(
            ['0000320193-23-000106', '0000320193-23-000107'],
            ['', '10-K'],
            ['2023-11-03', '2023-08-04'],
        )
        results = edgar_api._parse_filing_block(self.CIK, block)
        assert len(results) == 1
        assert results[0]['form_type'] == '10-K'

    def test_handles_short_arrays_gracefully(self):
        """If parallel arrays are shorter than accessionNumber, defaults apply."""
        block = {
            'accessionNumber': ['0000320193-23-000106', '0000320193-23-000107'],
            'form':            ['10-K'],   # only one entry
            'filingDate':      [],
            'reportDate':      [],
            'primaryDocument': [],
        }
        results = edgar_api._parse_filing_block(self.CIK, block)
        # First entry has form '10-K'; second has form '' (missing → skipped)
        assert len(results) == 1
        assert results[0]['filing_date'] == ''

    def test_amendment_form_type_preserved(self):
        block = _make_block(
            ['0000320193-22-000001'],
            ['10-K/A'],
            ['2022-01-15'],
            primary_docs=['aapl-20210930.htm'],
        )
        results = edgar_api._parse_filing_block(self.CIK, block)
        assert results[0]['form_type'] == '10-K/A'

    def test_multiple_entries_all_returned(self):
        block = _make_block(
            ['0000320193-23-000106', '0000320193-23-000077', '0000320193-23-000060'],
            ['10-K', '10-Q', '8-K'],
            ['2023-11-03', '2023-08-04', '2023-07-12'],
        )
        results = edgar_api._parse_filing_block(self.CIK, block)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# get_filings — date range filtering and sort
# ---------------------------------------------------------------------------

class TestGetFilingsDateRange:
    def _mock_submissions(self, filings_list):
        with patch('edgar_api._fetch_all_submissions', return_value=filings_list):
            yield

    def test_in_range_filings_returned(self):
        block = _make_block(
            ['0000320193-23-000106'],
            ['10-K'],
            ['2023-11-03'],
        )
        filings = edgar_api._parse_filing_block('0000320193', block)
        with patch('edgar_api._fetch_all_submissions', return_value=filings):
            results = edgar_api.get_filings('320193', '2023-01-01', '2023-12-31')
        assert len(results) == 1

    def test_out_of_range_filings_excluded(self):
        block = _make_block(
            ['0000320193-23-000106', '0000320193-22-000001'],
            ['10-K', '10-K'],
            ['2023-11-03', '2021-10-29'],  # 2021 filing is outside 2022-2023
        )
        filings = edgar_api._parse_filing_block('0000320193', block)
        with patch('edgar_api._fetch_all_submissions', return_value=filings):
            results = edgar_api.get_filings('320193', '2022-01-01', '2023-12-31')
        assert len(results) == 1
        assert results[0]['filing_date'] == '2023-11-03'

    def test_boundary_dates_inclusive(self):
        """start_date and end_date are inclusive bounds."""
        block = _make_block(
            ['0001-23-001', '0001-23-002', '0001-23-003'],
            ['10-K', '10-K', '10-K'],
            ['2022-01-01', '2022-06-15', '2022-12-31'],  # all boundary or in-range
        )
        filings = edgar_api._parse_filing_block('0000000001', block)
        with patch('edgar_api._fetch_all_submissions', return_value=filings):
            results = edgar_api.get_filings('1', '2022-01-01', '2022-12-31')
        assert len(results) == 3

    def test_date_just_outside_range_excluded(self):
        block = _make_block(
            ['0001-23-001', '0001-23-002'],
            ['10-K', '10-K'],
            ['2021-12-31', '2023-01-01'],  # one day outside on each side
        )
        filings = edgar_api._parse_filing_block('0000000001', block)
        with patch('edgar_api._fetch_all_submissions', return_value=filings):
            results = edgar_api.get_filings('1', '2022-01-01', '2022-12-31')
        assert results == []

    def test_results_sorted_newest_first(self):
        block = _make_block(
            ['0001-23-001', '0001-23-002', '0001-23-003'],
            ['10-K', '10-K', '10-K'],
            ['2021-11-01', '2023-11-03', '2022-10-28'],
        )
        filings = edgar_api._parse_filing_block('0000000001', block)
        with patch('edgar_api._fetch_all_submissions', return_value=filings):
            results = edgar_api.get_filings('1', '2021-01-01', '2023-12-31')
        dates = [r['filing_date'] for r in results]
        assert dates == sorted(dates, reverse=True), f"Expected newest-first; got {dates}"

    def test_no_filings_in_range_returns_empty_list(self):
        block = _make_block(
            ['0001-20-001'],
            ['10-K'],
            ['2020-11-01'],
        )
        filings = edgar_api._parse_filing_block('0000000001', block)
        with patch('edgar_api._fetch_all_submissions', return_value=filings):
            results = edgar_api.get_filings('1', '2023-01-01', '2023-12-31')
        assert results == []

    def test_cik_zero_padded_before_fetch(self):
        """CIK passed as int or short string is zero-padded to 10 digits."""
        with patch('edgar_api._fetch_all_submissions', return_value=[]) as mock_fetch:
            edgar_api.get_filings(320193, '2023-01-01', '2023-12-31')
        mock_fetch.assert_called_once_with('0000320193')

    def test_amendment_filings_included_when_form_types_allows(self):
        block = _make_block(
            ['0001-23-001', '0001-23-002'],
            ['10-K', '10-K/A'],
            ['2023-11-03', '2023-12-01'],
        )
        filings = edgar_api._parse_filing_block('0000000001', block)
        with patch('edgar_api._fetch_all_submissions', return_value=filings):
            results = edgar_api.get_filings('1', '2023-01-01', '2023-12-31',
                                            form_types=['10-K', '10-K/A'])
        assert len(results) == 2

    def test_amendment_excluded_when_not_in_form_types(self):
        block = _make_block(
            ['0001-23-001', '0001-23-002'],
            ['10-K', '10-K/A'],
            ['2023-11-03', '2023-12-01'],
        )
        filings = edgar_api._parse_filing_block('0000000001', block)
        with patch('edgar_api._fetch_all_submissions', return_value=filings):
            results = edgar_api.get_filings('1', '2023-01-01', '2023-12-31',
                                            form_types=['10-K'])
        assert len(results) == 1
        assert results[0]['form_type'] == '10-K'

    def test_skips_entry_with_missing_filing_date(self):
        block = _make_block(
            ['0001-23-001', '0001-23-002'],
            ['10-K', '10-K'],
            ['2023-11-03', ''],  # second has no date
        )
        filings = edgar_api._parse_filing_block('0000000001', block)
        with patch('edgar_api._fetch_all_submissions', return_value=filings):
            results = edgar_api.get_filings('1', '2023-01-01', '2023-12-31')
        assert len(results) == 1


# ---------------------------------------------------------------------------
# _fetch_all_submissions — caching and pagination
# ---------------------------------------------------------------------------

class TestFetchAllSubmissions:
    def setup_method(self):
        # Clear the module-level cache before each test
        edgar_api._submissions_cache.clear()

    def _primary_resp(self, recent_block, files=None, sic='7370'):
        return _make_submissions_resp(recent_block, files=files, sic=sic)

    def test_fetches_from_network_when_cache_empty(self):
        recent = _make_block(['0000320193-23-000106'], ['10-K'], ['2023-11-03'],
                             primary_docs=['a.htm'])
        resp = self._primary_resp(recent)
        with patch('edgar_api._rate_limited_get', return_value=resp) as mock_get:
            edgar_api._fetch_all_submissions('0000320193')
        mock_get.assert_called_once()

    def test_returns_cached_result_within_ttl(self):
        recent = _make_block(['0000320193-23-000106'], ['10-K'], ['2023-11-03'])
        resp = self._primary_resp(recent)
        with patch('edgar_api._rate_limited_get', return_value=resp) as mock_get:
            edgar_api._fetch_all_submissions('0000320193')
            edgar_api._fetch_all_submissions('0000320193')  # second call
        # Only one HTTP call despite two invocations
        assert mock_get.call_count == 1

    def test_refetches_after_ttl_expires(self):
        recent = _make_block(['0000320193-23-000106'], ['10-K'], ['2023-11-03'])
        resp = self._primary_resp(recent)
        with patch('edgar_api._rate_limited_get', return_value=resp) as mock_get:
            edgar_api._fetch_all_submissions('0000320193')
            # Expire the cache entry
            edgar_api._submissions_cache['0000320193'] = (
                time.time() - edgar_api._SUBMISSIONS_CACHE_TTL - 1,
                [], {}
            )
            edgar_api._fetch_all_submissions('0000320193')
        assert mock_get.call_count == 2

    def test_pagination_files_are_fetched(self):
        """When filings.files lists extra pages, each page is fetched."""
        recent = _make_block(['0000320193-23-000106'], ['10-K'], ['2023-11-03'])
        page2_block = _make_block(['0000320193-22-000001'], ['10-K'], ['2022-10-28'])
        page2_resp = MagicMock()
        page2_resp.json.return_value = page2_block

        primary_resp = _make_submissions_resp(
            recent,
            files=[{'name': 'CIK0000320193-submissions-001.json'}],
        )

        def dispatch(url):
            if 'CIK0000320193.json' in url:
                return primary_resp
            return page2_resp

        with patch('edgar_api._rate_limited_get', side_effect=dispatch):
            result = edgar_api._fetch_all_submissions('0000320193')

        accessions = [f['accession_number'] for f in result]
        assert '0000320193-23-000106' in accessions
        assert '0000320193-22-000001' in accessions

    def test_pagination_page_failure_is_skipped(self):
        """A failed page fetch is silently skipped; other filings still returned."""
        recent = _make_block(['0000320193-23-000106'], ['10-K'], ['2023-11-03'])
        primary_resp = _make_submissions_resp(
            recent,
            files=[{'name': 'CIK0000320193-submissions-001.json'}],
        )

        def dispatch(url):
            if 'CIK0000320193.json' in url:
                return primary_resp
            raise Exception("network error")

        with patch('edgar_api._rate_limited_get', side_effect=dispatch):
            result = edgar_api._fetch_all_submissions('0000320193')

        # Primary page results still returned
        assert len(result) == 1

    def test_company_meta_stored_in_cache(self):
        """SIC, SIC description, and category are stored alongside filings."""
        recent = _make_block([], [], [])
        resp = _make_submissions_resp(
            recent,
            sic='7370',
            sic_desc='Services-Prepackaged Software',
            category='Large accelerated filer',
        )
        with patch('edgar_api._rate_limited_get', return_value=resp):
            edgar_api._fetch_all_submissions('0000320193')

        cached = edgar_api._submissions_cache.get('0000320193')
        assert cached is not None
        meta = cached[2]
        assert meta['sic'] == '7370'
        assert meta['sic_description'] == 'Services-Prepackaged Software'
        assert meta['category'] == 'Large accelerated filer'


# ---------------------------------------------------------------------------
# get_company_meta
# ---------------------------------------------------------------------------

class TestGetCompanyMeta:
    def setup_method(self):
        edgar_api._submissions_cache.clear()

    def test_returns_meta_from_warm_cache(self):
        edgar_api._submissions_cache['0000320193'] = (
            time.time(),
            [],
            {'sic': '7370', 'sic_description': 'Prepackaged Software', 'category': 'Large accelerated filer'},
        )
        meta = edgar_api.get_company_meta(320193)
        assert meta['sic'] == '7370'

    def test_fetches_if_cache_cold(self):
        recent = _make_block([], [], [])
        resp = _make_submissions_resp(recent, sic='5734', sic_desc='Computer Stores')
        with patch('edgar_api._rate_limited_get', return_value=resp):
            meta = edgar_api.get_company_meta(320193)
        assert meta['sic'] == '5734'

    def test_cik_zero_padded(self):
        """get_company_meta accepts an int CIK and zero-pads it."""
        recent = _make_block([], [], [])
        resp = _make_submissions_resp(recent, sic='7370')
        with patch('edgar_api._rate_limited_get', return_value=resp):
            edgar_api.get_company_meta(1)
        # Cache entry must use the 10-digit form
        assert '0000000001' in edgar_api._submissions_cache


# ---------------------------------------------------------------------------
# Integration tests — live SEC network access required
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFilingSearchIntegration:
    def setup_method(self):
        edgar_api._submissions_cache.clear()

    def test_apple_10k_in_known_year(self):
        """Apple (CIK 320193) filed a 10-K in 2023."""
        results = edgar_api.get_filings('320193', '2023-01-01', '2023-12-31',
                                        form_types=['10-K'])
        assert results, "No 10-K results for Apple in 2023"
        assert all(r['form_type'] == '10-K' for r in results)
        dates = [r['filing_date'] for r in results]
        assert all('2023' in d for d in dates)

    def test_results_sorted_newest_first_live(self):
        """Live results from Apple must still be sorted newest-first."""
        results = edgar_api.get_filings('320193', '2018-01-01', '2023-12-31',
                                        form_types=['10-K'])
        assert len(results) > 1, "Expected multiple 10-Ks across 2018-2023"
        dates = [r['filing_date'] for r in results]
        assert dates == sorted(dates, reverse=True)

    def test_no_filings_before_company_existed(self):
        """Querying a date range predating the company yields []."""
        # Apple was incorporated in 1977 but didn't file with EDGAR until ~1993.
        # Using a date before any electronic filings exist.
        results = edgar_api.get_filings('320193', '1985-01-01', '1987-12-31',
                                        form_types=['10-K'])
        assert results == []

    def test_multi_form_types_include_both(self):
        """Requesting 10-K and 10-Q both return in the result set."""
        results = edgar_api.get_filings('320193', '2023-01-01', '2023-12-31',
                                        form_types=['10-K', '10-Q'])
        form_types_seen = {r['form_type'] for r in results}
        assert '10-K' in form_types_seen, "Expected 10-K in multi-type result"
        assert '10-Q' in form_types_seen, "Expected 10-Q in multi-type result"

    def test_document_url_is_valid_sec_url(self):
        """document_url for each filing is a well-formed SEC URL."""
        results = edgar_api.get_filings('320193', '2023-01-01', '2023-12-31',
                                        form_types=['10-K'])
        assert results, "No results to check"
        for r in results:
            assert r['document_url'].startswith('https://www.sec.gov/Archives/'), (
                f"Unexpected URL: {r['document_url']}"
            )

    def test_company_meta_populated_after_get_filings(self):
        """After get_filings, get_company_meta returns data without a new HTTP call."""
        edgar_api.get_filings('320193', '2023-01-01', '2023-12-31', form_types=['10-K'])
        meta = edgar_api.get_company_meta(320193)
        assert meta.get('sic'), f"Expected non-empty SIC; got: {meta}"
        assert meta.get('category'), f"Expected non-empty category; got: {meta}"
