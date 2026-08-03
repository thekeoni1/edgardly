"""
Stage 2 backfill — Ticker / CIK resolver tests.

Unit tests (no network): cache age arithmetic, _ensure_cache refresh
trigger, get_cache_info, no-match graceful handling, case normalisation,
result-count cap, EDGAR fallback parsing and error resilience.

Integration tests (@pytest.mark.integration): live ticker-to-CIK
resolution, partial name match, historical-name fallback via EDGAR EFTS,
empty-result handling, cache meta persistence.

Run all:          python -m pytest tests/test_ticker_resolver.py -v
Run unit only:    python -m pytest tests/test_ticker_resolver.py -v -m "not integration"
Run integration:  python -m pytest tests/test_ticker_resolver.py -v -m integration
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import edgar_api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_db(tmp_path, rows=None, last_updated=None):
    """
    Write a throwaway tickers DB under tmp_path.
    rows:        [(cik, ticker, company_name), ...]
    last_updated: ISO string, or None to leave meta table empty (→ cache age = inf)
    Returns the str path.
    """
    db_path = str(tmp_path / "tickers.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    edgar_api._init_db(conn)
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO tickers (cik, ticker, company_name) VALUES (?, ?, ?)",
            rows,
        )
    if last_updated is not None:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_updated', ?)",
            [last_updated],
        )
    conn.commit()
    conn.close()
    return db_path


def _fresh_ts():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


# ---------------------------------------------------------------------------
# Unit tests — cache age arithmetic
# ---------------------------------------------------------------------------

class TestCacheAge:
    def test_inf_when_no_meta_row(self, tmp_path):
        """No last_updated row → float('inf'), which triggers refresh."""
        db_path = _make_temp_db(tmp_path)          # no last_updated
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        age = edgar_api._cache_age_hours(conn)
        conn.close()
        assert age == float('inf')

    def test_near_zero_for_just_written_timestamp(self, tmp_path):
        """Timestamp written right now → age well under 0.1 hours."""
        db_path = _make_temp_db(tmp_path, last_updated=_fresh_ts())
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        age = edgar_api._cache_age_hours(conn)
        conn.close()
        assert age < 0.1, f"Expected age < 0.1 hours, got {age}"

    def test_large_for_old_timestamp(self, tmp_path):
        """A year-old timestamp → age > 24 (refresh threshold)."""
        old = datetime(2020, 1, 1).isoformat()
        db_path = _make_temp_db(tmp_path, last_updated=old)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        age = edgar_api._cache_age_hours(conn)
        conn.close()
        assert age > 24 * 365, f"Expected age > 8760 hours, got {age}"


# ---------------------------------------------------------------------------
# Unit tests — _ensure_cache refresh trigger
# ---------------------------------------------------------------------------

class TestEnsureCache:
    def test_calls_refresh_when_cache_stale(self, tmp_path):
        """_ensure_cache calls refresh_ticker_cache when last_updated is old."""
        old = datetime(2020, 1, 1).isoformat()
        db_path = _make_temp_db(tmp_path, last_updated=old)

        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api.refresh_ticker_cache') as mock_refresh,
        ):
            edgar_api._ensure_cache()

        mock_refresh.assert_called_once()

    def test_skips_refresh_when_cache_fresh(self, tmp_path):
        """_ensure_cache does NOT call refresh_ticker_cache when cache is fresh."""
        db_path = _make_temp_db(tmp_path, last_updated=_fresh_ts())

        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api.refresh_ticker_cache') as mock_refresh,
        ):
            edgar_api._ensure_cache()

        mock_refresh.assert_not_called()

    def test_calls_refresh_when_db_missing(self, tmp_path):
        """_ensure_cache calls refresh_ticker_cache when the DB file doesn't exist."""
        missing = str(tmp_path / "no_db.db")

        with (
            patch.object(edgar_api, 'DB_PATH', missing),
            patch('edgar_api.refresh_ticker_cache') as mock_refresh,
        ):
            edgar_api._ensure_cache()

        mock_refresh.assert_called_once()


# ---------------------------------------------------------------------------
# Unit tests — get_cache_info
# ---------------------------------------------------------------------------

class TestGetCacheInfo:
    def test_missing_db_returns_zeros(self, tmp_path):
        """get_cache_info with no DB file → last_updated=None, company_count=0."""
        missing = str(tmp_path / "no_db.db")
        with patch.object(edgar_api, 'DB_PATH', missing):
            info = edgar_api.get_cache_info()
        assert info['last_updated'] is None
        assert info['company_count'] == 0

    def test_populated_db_returns_correct_count(self, tmp_path):
        """get_cache_info reflects exact row count and parses last_updated."""
        rows = [(i, f"T{i:03d}", f"Company {i}") for i in range(1, 6)]
        db_path = _make_temp_db(tmp_path, rows=rows, last_updated=_fresh_ts())

        with patch.object(edgar_api, 'DB_PATH', db_path):
            info = edgar_api.get_cache_info()

        assert info['company_count'] == 5
        assert isinstance(info['last_updated'], datetime)

    def test_db_with_no_meta_returns_none_timestamp(self, tmp_path):
        """DB exists but no last_updated meta row → last_updated=None."""
        rows = [(1, 'AAAA', 'Alpha Corp')]
        db_path = _make_temp_db(tmp_path, rows=rows)   # no last_updated

        with patch.object(edgar_api, 'DB_PATH', db_path):
            info = edgar_api.get_cache_info()

        assert info['last_updated'] is None
        assert info['company_count'] == 1


# ---------------------------------------------------------------------------
# Unit tests — search_companies (isolated, no network)
# ---------------------------------------------------------------------------

class TestSearchCompaniesUnit:
    """All tests in this class patch _ensure_cache and DB_PATH so no network
    calls are made and no real tickers DB is required."""

    def test_no_match_returns_empty_list(self, tmp_path):
        """A query with no local or fallback matches returns [] without crashing."""
        db_path = _make_temp_db(tmp_path, last_updated=_fresh_ts())
        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api._edgar_company_fallback', return_value=[]),
        ):
            results = edgar_api.search_companies("xyzzy_no_such_company_zz9")
        assert results == []

    def test_whitespace_query_does_not_crash(self, tmp_path):
        """Whitespace-only query returns a list (possibly empty) without crashing."""
        db_path = _make_temp_db(tmp_path, last_updated=_fresh_ts())
        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api._edgar_company_fallback', return_value=[]),
        ):
            results = edgar_api.search_companies("   ")
        assert isinstance(results, list)

    def test_exact_ticker_found_case_insensitive(self, tmp_path):
        """Searching 'aapl' (lowercase) finds the 'AAPL' ticker."""
        rows = [(320193, 'AAPL', 'Apple Inc.')]
        db_path = _make_temp_db(tmp_path, rows=rows, last_updated=_fresh_ts())
        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api._edgar_company_fallback', return_value=[]),
        ):
            results = edgar_api.search_companies("aapl")
        ciks = [r['cik'] for r in results]
        assert 320193 in ciks, f"CIK 320193 not in results: {ciks}"

    def test_partial_name_match(self, tmp_path):
        """Company name substring match returns the matching row."""
        rows = [(320193, 'AAPL', 'Apple Inc.'), (789019, 'MSFT', 'Microsoft Corp')]
        db_path = _make_temp_db(tmp_path, rows=rows, last_updated=_fresh_ts())
        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api._edgar_company_fallback', return_value=[]),
        ):
            results = edgar_api.search_companies("micro")
        ciks = [r['cik'] for r in results]
        assert 789019 in ciks, f"Microsoft CIK 789019 not in results: {ciks}"
        assert 320193 not in ciks, "Apple should not match 'micro'"

    def test_result_capped_at_25(self, tmp_path):
        """Even if many rows match, search_companies returns at most 25."""
        rows = [(i, f"T{i:04d}", f"Test Company {i}") for i in range(1, 60)]
        db_path = _make_temp_db(tmp_path, rows=rows, last_updated=_fresh_ts())
        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api._edgar_company_fallback', return_value=[]),
        ):
            results = edgar_api.search_companies("test")
        assert len(results) <= 25, f"Got {len(results)} results; expected <= 25"

    def test_fallback_called_when_no_local_match(self, tmp_path):
        """_edgar_company_fallback is invoked (and its results returned) when the
        local DB has no matches for the query."""
        db_path = _make_temp_db(tmp_path, last_updated=_fresh_ts())
        sentinel = [{'cik': 9999, 'ticker': '', 'company_name': 'Fallback Co'}]
        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api._edgar_company_fallback', return_value=sentinel) as mock_fb,
        ):
            results = edgar_api.search_companies("some_obscure_query")
        mock_fb.assert_called_once_with("some_obscure_query")
        assert results == sentinel

    def test_fallback_not_called_when_local_match_exists(self, tmp_path):
        """_edgar_company_fallback is NOT called when the local DB has results."""
        rows = [(1, 'AAPL', 'Apple Inc.')]
        db_path = _make_temp_db(tmp_path, rows=rows, last_updated=_fresh_ts())
        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api._edgar_company_fallback') as mock_fb,
        ):
            edgar_api.search_companies("apple")
        mock_fb.assert_not_called()

    def test_result_fields_always_present(self, tmp_path):
        """Every result dict has cik, ticker, company_name keys."""
        rows = [(320193, 'AAPL', 'Apple Inc.')]
        db_path = _make_temp_db(tmp_path, rows=rows, last_updated=_fresh_ts())
        with (
            patch.object(edgar_api, 'DB_PATH', db_path),
            patch('edgar_api._edgar_company_fallback', return_value=[]),
        ):
            results = edgar_api.search_companies("apple")
        for r in results:
            assert 'cik' in r
            assert 'ticker' in r
            assert 'company_name' in r


# ---------------------------------------------------------------------------
# Unit tests — _edgar_company_fallback (isolated, no network)
# ---------------------------------------------------------------------------

def _make_efts_resp(hits):
    """Return a MagicMock shaped like an EFTS search-index response."""
    m = MagicMock()
    m.json.return_value = {'hits': {'hits': hits}}
    return m


def _make_sub_resp(name, tickers=None):
    """Return a MagicMock shaped like a submissions endpoint response."""
    m = MagicMock()
    m.json.return_value = {'name': name, 'tickers': tickers or []}
    return m


def _url_dispatcher(efts_resp, sub_resps_by_cik):
    """
    Return a side_effect function for _rate_limited_get that returns
    efts_resp for the EFTS URL and looks up sub_resps_by_cik[cik_int]
    for submissions calls.
    """
    def _dispatch(url, **kwargs):
        if 'efts.sec.gov' in url:
            return efts_resp
        # Extract the CIK from the submissions URL  CIK0001234567.json
        import re
        m = re.search(r'CIK(\d+)', url)
        if m:
            cik = int(m.group(1))
            if cik in sub_resps_by_cik:
                return sub_resps_by_cik[cik]
        raise ValueError(f"Unexpected URL in test: {url}")
    return _dispatch


class TestEdgarFallback:
    def test_returns_empty_on_efts_network_error(self):
        """Top-level network failure (EFTS call) → [] without raising."""
        with patch('edgar_api._rate_limited_get', side_effect=Exception("timeout")):
            result = edgar_api._edgar_company_fallback("any query")
        assert result == []

    def test_returns_empty_when_hits_is_empty(self):
        """EFTS response with no hits → no submissions calls, returns []."""
        efts = _make_efts_resp([])
        with patch('edgar_api._rate_limited_get', return_value=efts):
            result = edgar_api._edgar_company_fallback("obscure")
        assert result == []

    def test_cik_extracted_and_name_fetched_from_submissions(self):
        """
        CIK is extracted from the accession-number prefix; company name and
        ticker are then fetched from the submissions endpoint.
        (Previously the function read entity_name from EFTS _source, which
        EDGAR's API no longer populates reliably.)
        """
        efts = _make_efts_resp([
            {'_id': '0001326801-22-000018', '_source': {}},  # no entity_name
        ])
        sub = _make_sub_resp('Meta Platforms, Inc.', tickers=['META'])
        dispatch = _url_dispatcher(efts, {1326801: sub})

        with patch('edgar_api._rate_limited_get', side_effect=dispatch):
            results = edgar_api._edgar_company_fallback("facebook")

        assert len(results) == 1
        assert results[0]['cik'] == 1326801
        assert results[0]['company_name'] == 'Meta Platforms, Inc.'
        assert results[0]['ticker'] == 'META'

    def test_deduplicates_ciks_before_submissions_calls(self):
        """
        Multiple hits sharing the same CIK collapse to a single submissions
        call and a single result entry.
        """
        efts = _make_efts_resp([
            {'_id': '0001326801-22-000018', '_source': {}},  # CIK 1326801 × 2
            {'_id': '0001326801-21-000010', '_source': {}},
            {'_id': '0000320193-23-000001', '_source': {}},  # CIK 320193
        ])
        sub_meta  = _make_sub_resp('Meta Platforms, Inc.', ['META'])
        sub_apple = _make_sub_resp('Apple Inc.',           ['AAPL'])
        dispatch = _url_dispatcher(efts, {1326801: sub_meta, 320193: sub_apple})

        call_log = []
        original_dispatch = dispatch

        def tracking_dispatch(url, **kwargs):
            call_log.append(url)
            return original_dispatch(url, **kwargs)

        with patch('edgar_api._rate_limited_get', side_effect=tracking_dispatch):
            results = edgar_api._edgar_company_fallback("test")

        # One EFTS call + two unique-CIK submissions calls (not three)
        sub_calls = [u for u in call_log if 'submissions' in u]
        assert len(sub_calls) == 2, f"Expected 2 submissions calls, got {sub_calls}"
        ciks = [r['cik'] for r in results]
        assert ciks.count(1326801) == 1
        assert len(results) == 2

    def test_submissions_failure_per_cik_skipped_gracefully(self):
        """If the submissions call for one CIK fails, that CIK is skipped
        without affecting the others."""
        efts = _make_efts_resp([
            {'_id': '0001326801-22-000018', '_source': {}},
            {'_id': '0000320193-23-000001', '_source': {}},
        ])
        sub_apple = _make_sub_resp('Apple Inc.', ['AAPL'])

        def dispatch(url, **kwargs):
            if 'efts' in url:
                return efts
            if '0001326801' in url:
                raise Exception("network error for Meta")
            return sub_apple

        with patch('edgar_api._rate_limited_get', side_effect=dispatch):
            results = edgar_api._edgar_company_fallback("test")

        assert len(results) == 1
        assert results[0]['cik'] == 320193

    def test_skips_hits_with_unparseable_id(self):
        """Hits whose accession id can't yield an integer CIK are skipped."""
        efts = _make_efts_resp([
            {'_id': 'INVALID_ID',            '_source': {}},  # skipped
            {'_id': '0000320193-23-000001',  '_source': {}},  # valid
        ])
        sub_apple = _make_sub_resp('Apple Inc.', ['AAPL'])
        dispatch = _url_dispatcher(efts, {320193: sub_apple})

        with patch('edgar_api._rate_limited_get', side_effect=dispatch):
            results = edgar_api._edgar_company_fallback("test")

        assert len(results) == 1
        assert results[0]['cik'] == 320193

    def test_capped_at_10_unique_ciks(self):
        """At most 10 unique CIKs are resolved via submissions calls."""
        hits = [{'_id': f'{str(i).zfill(10)}-22-000001', '_source': {}} for i in range(1, 20)]
        efts = _make_efts_resp(hits)

        sub_responses = {i: _make_sub_resp(f'Company {i}') for i in range(1, 20)}
        dispatch = _url_dispatcher(efts, sub_responses)

        with patch('edgar_api._rate_limited_get', side_effect=dispatch):
            results = edgar_api._edgar_company_fallback("test")

        assert len(results) <= 10, f"Expected <= 10 results, got {len(results)}"

    def test_ticker_empty_string_when_submissions_has_no_tickers(self):
        """ticker field is '' (not None) when the submissions response has no tickers."""
        efts = _make_efts_resp([{'_id': '0000320193-23-000001', '_source': {}}])
        sub = _make_sub_resp('Apple Inc.', tickers=[])
        dispatch = _url_dispatcher(efts, {320193: sub})

        with patch('edgar_api._rate_limited_get', side_effect=dispatch):
            results = edgar_api._edgar_company_fallback("apple")

        assert results[0]['ticker'] == ''

    def test_skips_submissions_with_empty_name(self):
        """A submissions response with no name field is dropped silently."""
        efts = _make_efts_resp([{'_id': '0000320193-23-000001', '_source': {}}])
        sub = MagicMock()
        sub.json.return_value = {'name': ''}    # empty name
        dispatch = _url_dispatcher(efts, {320193: sub})

        with patch('edgar_api._rate_limited_get', side_effect=dispatch):
            results = edgar_api._edgar_company_fallback("apple")

        assert results == []


# ---------------------------------------------------------------------------
# Integration tests — live SEC network access required
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestTickerResolverIntegration:
    def test_aapl_resolves_to_correct_cik(self):
        """AAPL ticker must map to Apple CIK 320193."""
        results = edgar_api.search_companies("AAPL")
        assert results, "No results returned for AAPL"
        match = next((r for r in results if r['ticker'].upper() == 'AAPL'), None)
        assert match is not None, f"AAPL not in result tickers: {[r['ticker'] for r in results]}"
        assert str(match['cik']) == '320193', (
            f"AAPL mapped to CIK {match['cik']}, expected 320193"
        )

    def test_partial_lowercase_name_match(self):
        """Lowercase partial name 'berkshire' returns Berkshire Hathaway entries."""
        results = edgar_api.search_companies("berkshire")
        assert results, "No results for 'berkshire'"
        names_lower = [r['company_name'].lower() for r in results]
        assert any('berkshire' in n for n in names_lower), (
            f"No Berkshire entry in: {names_lower}"
        )

    def test_meta_platforms_searchable_by_current_name(self):
        """
        Meta Platforms, Inc. (CIK 1326801 — the former Facebook CIK, kept after
        the rename) is findable by its current name via the local ticker DB.
        """
        results = edgar_api.search_companies("meta platforms")
        assert results, "No results for 'meta platforms'"
        ciks = [r['cik'] for r in results]
        assert 1326801 in ciks, (
            f"Meta Platforms CIK 1326801 not found; results: "
            f"{[(r['ticker'], r['cik'], r['company_name']) for r in results]}"
        )

    def test_historical_name_facebook_via_fallback(self):
        """
        'Facebook' is not in the local ticker DB (renamed to Meta Platforms).
        The EDGAR EFTS fallback extracts CIK 1326801 from old 10-K accession
        numbers and fetches the current company name from the submissions endpoint.

        BEFORE FIX: returned [] because EFTS _source entity_name was None.
        AFTER FIX:  returns Meta Platforms (CIK 1326801) via submissions lookup.
        """
        results = edgar_api.search_companies("facebook")
        assert isinstance(results, list), "Expected a list, never a crash"
        ciks = [r['cik'] for r in results]
        assert 1326801 in ciks, (
            "Facebook/Meta CIK 1326801 not found via fixed fallback. "
            f"Actual results: {results}"
        )
        # Verify the company name comes from the submissions endpoint, not EFTS
        meta = next(r for r in results if r['cik'] == 1326801)
        assert 'meta' in meta['company_name'].lower() or 'facebook' in meta['company_name'].lower(), (
            f"Unexpected company name for CIK 1326801: {meta['company_name']!r}"
        )

    def test_fallback_populates_ticker_from_submissions(self):
        """
        When the fallback resolves a company via EDGAR EFTS + submissions,
        the ticker field is populated from the submissions endpoint (not '').
        Verifies the ticker is now populated correctly after the bug fix.
        """
        results = edgar_api.search_companies("facebook")
        assert results, "No fallback results — see test_historical_name_facebook_via_fallback"
        meta = next((r for r in results if r['cik'] == 1326801), None)
        assert meta is not None, "CIK 1326801 not in results"
        # Meta's ticker is META; confirm it came through from submissions
        assert meta['ticker'] == 'META', (
            f"Expected ticker 'META', got {meta['ticker']!r}"
        )

    def test_nonsense_query_returns_empty_not_crash(self):
        """A clearly nonsense query returns [] without raising."""
        results = edgar_api.search_companies("xyzzy_no_such_company_zz9plural_99")
        assert results == [], f"Expected [], got {results}"

    def test_cache_meta_is_current_after_ensure(self):
        """After _ensure_cache, get_cache_info reflects a populated, recent cache."""
        edgar_api._ensure_cache()
        info = edgar_api.get_cache_info()
        assert info['company_count'] > 0, "Cache has 0 companies after _ensure_cache"
        assert info['last_updated'] is not None, "No last_updated after _ensure_cache"
        age_hours = (datetime.now() - info['last_updated']).total_seconds() / 3600
        assert age_hours < 25, (
            f"Cache is {age_hours:.1f}h old — either stale or clock skew"
        )
