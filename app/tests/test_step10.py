"""
Step 10 tests: CSV / Excel metadata export
Pass criteria (non-integration):
  - Route validates required params and format
  - CSV export creates readable file with correct columns and data
  - Excel export creates valid .xlsx with bold header, frozen pane, correct sheet name
  - Amendment flag is correct for /A form types
  - Empty result set creates file with header only (CSV) / 1 row (xlsx)
  - Route returns filename and download_url on success
"""
import csv
import os
import sys

import pytest
from unittest.mock import patch

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
    {
        'form_type': '10-K', 'filing_date': '2023-11-03', 'fiscal_year_end': '2023-09-30',
        'accession_number': '0000320193-23-000106', 'document_url': 'https://www.sec.gov/a.htm',
        'estimated_size': None,
    },
    {
        'form_type': '10-Q', 'filing_date': '2023-08-04', 'fiscal_year_end': '2023-07-01',
        'accession_number': '0000320193-23-000077', 'document_url': 'https://www.sec.gov/b.htm',
        'estimated_size': None,
    },
    {
        'form_type': '10-K/A', 'filing_date': '2023-09-10', 'fiscal_year_end': '2023-09-30',
        'accession_number': '0000320193-23-000090', 'document_url': 'https://www.sec.gov/c.htm',
        'estimated_size': None,
    },
]

FAKE_META = {
    'sic': '3571',
    'sic_description': 'Electronic Computers',
    'category': 'Large accelerated filer',
}


# ---------------------------------------------------------------------------
# Route validation
# ---------------------------------------------------------------------------

def test_export_no_body(client):
    resp = client.post('/api/export')
    assert resp.status_code == 400


def test_export_missing_cik(client):
    resp = client.post('/api/export', json={'start': '2023-01-01', 'end': '2023-12-31'})
    assert resp.status_code == 400


def test_export_invalid_format(client):
    resp = client.post('/api/export', json={
        'cik': '320193', 'start': '2023-01-01', 'end': '2023-12-31', 'format': 'xml',
    })
    assert resp.status_code == 400
    assert 'format' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def test_csv_created_with_correct_columns(tmp_path):
    with patch('edgar_api.get_filings', return_value=FAKE_FILINGS[:2]), \
         patch('edgar_api.get_company_meta', return_value=FAKE_META):
        filepath = edgar_api.export_filings(
            cik='320193', start_date='2023-01-01', end_date='2023-12-31',
            form_types=['10-K', '10-Q'], fmt='csv',
            company_name='Apple Inc', ticker='AAPL',
            exports_dir=str(tmp_path),
        )

    assert os.path.exists(filepath)
    assert filepath.endswith('.csv')

    with open(filepath, encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    assert len(rows) == 2
    assert set(edgar_api._EXPORT_COLUMNS).issubset(set(rows[0].keys()))
    assert rows[0]['Company Name'] == 'Apple Inc'
    assert rows[0]['Ticker'] == 'AAPL'
    assert rows[0]['CIK'] == '320193'
    assert rows[0]['Form Type'] == '10-K'
    assert rows[0]['SIC Code'] == '3571'
    assert rows[0]['SIC Description'] == 'Electronic Computers'
    assert rows[0]['Filer Category'] == 'Large accelerated filer'
    assert rows[0]['Document URL'] == 'https://www.sec.gov/a.htm'


def test_csv_empty_results_header_only(tmp_path):
    with patch('edgar_api.get_filings', return_value=[]), \
         patch('edgar_api.get_company_meta', return_value=FAKE_META):
        filepath = edgar_api.export_filings(
            cik='320193', start_date='2023-01-01', end_date='2023-12-31',
            form_types=['10-K'], fmt='csv',
            company_name='Apple Inc', ticker='AAPL',
            exports_dir=str(tmp_path),
        )

    with open(filepath, encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    assert rows == []


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def test_xlsx_created_with_correct_structure(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')

    with patch('edgar_api.get_filings', return_value=FAKE_FILINGS), \
         patch('edgar_api.get_company_meta', return_value=FAKE_META):
        filepath = edgar_api.export_filings(
            cik='320193', start_date='2023-01-01', end_date='2023-12-31',
            form_types=['10-K', '10-Q', '10-K/A'], fmt='xlsx',
            company_name='Apple Inc', ticker='AAPL',
            exports_dir=str(tmp_path),
        )

    assert os.path.exists(filepath)
    assert filepath.endswith('.xlsx')

    wb = openpyxl.load_workbook(filepath)
    assert 'EDGAR Search Results' in wb.sheetnames
    ws = wb['EDGAR Search Results']

    headers = [cell.value for cell in ws[1]]
    assert headers == edgar_api._EXPORT_COLUMNS

    # Header row is bold
    assert ws['A1'].font.bold is True

    # Frozen header row
    assert ws.freeze_panes == 'A2'

    # 1 header + 3 data rows
    assert ws.max_row == 4


def test_xlsx_column_widths_set(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')

    with patch('edgar_api.get_filings', return_value=FAKE_FILINGS[:1]), \
         patch('edgar_api.get_company_meta', return_value=FAKE_META):
        filepath = edgar_api.export_filings(
            cik='320193', start_date='2023-01-01', end_date='2023-12-31',
            form_types=['10-K'], fmt='xlsx',
            company_name='Apple Inc', ticker='AAPL',
            exports_dir=str(tmp_path),
        )

    wb = openpyxl.load_workbook(filepath)
    ws = wb['EDGAR Search Results']
    # Every column should have a width set (auto-fit was applied)
    for col in ws.columns:
        letter = col[0].column_letter
        assert ws.column_dimensions[letter].width > 0


# ---------------------------------------------------------------------------
# Amendment flag
# ---------------------------------------------------------------------------

def test_amendment_flag_correct(tmp_path):
    with patch('edgar_api.get_filings', return_value=FAKE_FILINGS), \
         patch('edgar_api.get_company_meta', return_value=FAKE_META):
        filepath = edgar_api.export_filings(
            cik='320193', start_date='2023-01-01', end_date='2023-12-31',
            form_types=['10-K', '10-Q', '10-K/A'], fmt='csv',
            company_name='Apple Inc', ticker='AAPL',
            exports_dir=str(tmp_path),
        )

    with open(filepath, encoding='utf-8') as fh:
        by_type = {r['Form Type']: r['Amendment'] for r in csv.DictReader(fh)}

    assert by_type['10-K'] == 'No'
    assert by_type['10-Q'] == 'No'
    assert by_type['10-K/A'] == 'Yes'


# ---------------------------------------------------------------------------
# Route integration (mocked edgar_api)
# ---------------------------------------------------------------------------

def test_export_route_returns_filename(client, tmp_path):
    fake_path = str(tmp_path / 'edgar_export_2024-01-01_120000.xlsx')
    (tmp_path / 'edgar_export_2024-01-01_120000.xlsx').touch()

    with patch('edgar_api.export_filings', return_value=fake_path):
        resp = client.post('/api/export', json={
            'cik': '320193', 'start': '2023-01-01', 'end': '2023-12-31',
            'format': 'xlsx', 'company_name': 'Apple Inc', 'ticker': 'AAPL',
        })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['filename'] == 'edgar_export_2024-01-01_120000.xlsx'
    assert data['download_url'].startswith('/exports/')


def test_export_default_format_is_xlsx(client, tmp_path):
    fake_path = str(tmp_path / 'edgar_export_2024-01-01_120001.xlsx')
    (tmp_path / 'edgar_export_2024-01-01_120001.xlsx').touch()

    with patch('edgar_api.export_filings', return_value=fake_path) as mock_ef:
        client.post('/api/export', json={
            'cik': '320193', 'start': '2023-01-01', 'end': '2023-12-31',
        })
        _, kwargs = mock_ef.call_args
        assert kwargs.get('fmt') == 'xlsx'
