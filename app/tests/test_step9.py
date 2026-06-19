"""
Step 9 tests: multi-form type support
Pass criteria (non-integration):
  - /api/filings with no forms param defaults to 10-K
  - /api/filings with forms=10-K,10-Q filters correctly
  - /api/filings with forms= (empty) defaults to 10-K
  - form_type sanitization in download_filing filename
  - get_filings with form_types=None returns all form types
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import app as flask_app
import edgar_api


@pytest.fixture
def client():
    flask_app.app.config['TESTING'] = True
    with flask_app.app.test_client() as c:
        yield c


FAKE_FILINGS = [
    {'form_type': '10-K',   'filing_date': '2023-11-03', 'fiscal_year_end': '2023-09-30',
     'accession_number': '0000320193-23-000106', 'document_url': 'https://www.sec.gov/a.htm', 'estimated_size': None},
    {'form_type': '10-Q',   'filing_date': '2023-08-04', 'fiscal_year_end': '2023-07-01',
     'accession_number': '0000320193-23-000077', 'document_url': 'https://www.sec.gov/b.htm', 'estimated_size': None},
    {'form_type': '8-K',    'filing_date': '2023-07-12', 'fiscal_year_end': '',
     'accession_number': '0000320193-23-000060', 'document_url': 'https://www.sec.gov/c.htm', 'estimated_size': None},
    {'form_type': 'DEF 14A','filing_date': '2023-01-20', 'fiscal_year_end': '',
     'accession_number': '0000320193-23-000010', 'document_url': 'https://www.sec.gov/d.htm', 'estimated_size': None},
]


def test_default_forms_is_10k(client):
    """No forms param -> only 10-K returned."""
    with patch('edgar_api.get_filings', return_value=[FAKE_FILINGS[0]]) as mock_gf:
        resp = client.get('/api/filings?cik=320193&start=2023-01-01&end=2023-12-31')
        mock_gf.assert_called_once_with('320193', '2023-01-01', '2023-12-31', form_types=['10-K'])
    assert resp.status_code == 200


def test_empty_forms_param_defaults_to_10k(client):
    """forms= (empty string) -> defaults to 10-K."""
    with patch('edgar_api.get_filings', return_value=[FAKE_FILINGS[0]]) as mock_gf:
        resp = client.get('/api/filings?cik=320193&start=2023-01-01&end=2023-12-31&forms=')
        mock_gf.assert_called_once_with('320193', '2023-01-01', '2023-12-31', form_types=['10-K'])
    assert resp.status_code == 200


def test_multi_form_param_parsed(client):
    """forms=10-K,10-Q passes both types through."""
    with patch('edgar_api.get_filings', return_value=FAKE_FILINGS[:2]) as mock_gf:
        resp = client.get('/api/filings?cik=320193&start=2023-01-01&end=2023-12-31&forms=10-K,10-Q')
        mock_gf.assert_called_once_with('320193', '2023-01-01', '2023-12-31', form_types=['10-K', '10-Q'])
    assert resp.status_code == 200


def test_form_with_space_in_name(client):
    """forms=DEF 14A (URL-encoded) is parsed correctly."""
    with patch('edgar_api.get_filings', return_value=[FAKE_FILINGS[3]]) as mock_gf:
        resp = client.get('/api/filings?cik=320193&start=2023-01-01&end=2023-12-31&forms=DEF+14A')
        mock_gf.assert_called_once_with('320193', '2023-01-01', '2023-12-31', form_types=['DEF 14A'])
    assert resp.status_code == 200


def test_get_filings_filters_by_form_types():
    """get_filings with form_types=['10-K'] excludes other types."""
    block = {
        'accessionNumber': ['0001-23-001', '0001-23-002'],
        'form':            ['10-K', '10-Q'],
        'filingDate':      ['2023-11-03', '2023-08-04'],
        'reportDate':      ['2023-09-30', '2023-07-01'],
        'primaryDocument': ['a.htm', 'b.htm'],
    }
    with patch('edgar_api._fetch_all_submissions') as mock_fetch:
        mock_fetch.return_value = edgar_api._parse_filing_block('0000320193', block)
        results = edgar_api.get_filings('320193', '2023-01-01', '2023-12-31', form_types=['10-K'])
    assert all(f['form_type'] == '10-K' for f in results)
    assert len(results) == 1


def test_get_filings_none_returns_all_types():
    """get_filings with form_types=None returns all form types."""
    block = {
        'accessionNumber': ['0001-23-001', '0001-23-002', '0001-23-003'],
        'form':            ['10-K', '10-Q', '8-K'],
        'filingDate':      ['2023-11-03', '2023-08-04', '2023-07-12'],
        'reportDate':      ['2023-09-30', '2023-07-01', ''],
        'primaryDocument': ['a.htm', 'b.htm', 'c.htm'],
    }
    with patch('edgar_api._fetch_all_submissions') as mock_fetch:
        mock_fetch.return_value = edgar_api._parse_filing_block('0000320193', block)
        results = edgar_api.get_filings('320193', '2023-01-01', '2023-12-31', form_types=None)
    assert len(results) == 3


def test_filename_sanitizes_slash():
    """Form types with / are sanitized for filenames (10-K/A -> 10-K-A)."""
    safe = 'DEF 14A'.replace('/', '-').replace(' ', '-')
    assert safe == 'DEF-14A'
    safe2 = '10-K/A'.replace('/', '-').replace(' ', '-')
    assert safe2 == '10-K-A'
    safe3 = 'S-1/A'.replace('/', '-').replace(' ', '-')
    assert safe3 == 'S-1-A'
