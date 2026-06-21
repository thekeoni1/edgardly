import csv as _csv_module
import os
import re
import shutil
import tempfile
import time
import sqlite3
import requests
from datetime import datetime, timezone
from urllib.parse import quote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "tickers.db")

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

HEADERS = {
    "User-Agent": "Edgardly/1.0 (research tool; contact@example.com)",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}


def _rate_limited_get(url, **kwargs):
    """GET with 0.1s rate-limit delay and one 429 back-off retry."""
    time.sleep(0.1)
    resp = requests.get(url, headers=HEADERS, timeout=30, **kwargs)
    if resp.status_code == 429:
        time.sleep(5)
        resp = requests.get(url, headers=HEADERS, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


def _get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            cik INTEGER PRIMARY KEY,
            ticker TEXT NOT NULL,
            company_name TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON tickers(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON tickers(company_name)")
    conn.commit()


def _cache_age_hours(conn):
    row = conn.execute("SELECT value FROM meta WHERE key = 'last_updated'").fetchone()
    if not row:
        return float('inf')
    last_updated = datetime.fromisoformat(row['value'])
    return (datetime.now(timezone.utc).replace(tzinfo=None) - last_updated).total_seconds() / 3600


def refresh_ticker_cache():
    """Download company_tickers.json from SEC and rebuild the SQLite cache."""
    resp = _rate_limited_get(TICKERS_URL)
    data = resp.json()

    conn = _get_db()
    _init_db(conn)
    conn.execute("DELETE FROM tickers")

    rows = [
        (int(entry['cik_str']), entry['ticker'].upper(), entry['title'])
        for entry in data.values()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO tickers (cik, ticker, company_name) VALUES (?, ?, ?)",
        rows,
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_updated', ?)",
        [datetime.now(timezone.utc).replace(tzinfo=None).isoformat()],
    )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM tickers").fetchone()[0]
    conn.close()
    return count


def _ensure_cache():
    """Create or refresh the ticker cache if missing or older than 24 hours."""
    if not os.path.exists(DB_PATH):
        refresh_ticker_cache()
        return
    conn = _get_db()
    _init_db(conn)
    age = _cache_age_hours(conn)
    conn.close()
    if age >= 24:
        refresh_ticker_cache()


def _edgar_company_fallback(query):
    """
    Fallback: search EDGAR's full-text search (EFTS) for companies not in the
    local ticker cache — handles recent IPOs, foreign filers, and companies
    whose names have changed since the local cache was built.

    The EFTS search-index endpoint returns document-level hits whose _source
    no longer reliably includes entity_name.  Instead we:
      1. Extract CIKs from the leading segment of each accession-number hit id.
      2. Deduplicate by CIK before making any further requests (many hits share
         the same filer CIK, so deduplication keeps rate-limit exposure low).
      3. Fetch each unique CIK's current name and ticker from the submissions
         endpoint (≤10 calls; each respects the existing 0.1 s rate-limit delay).
    """
    url = (
        "https://efts.sec.gov/LATEST/search-index"
        "?q=%22{}%22&forms=10-K".format(quote(query))
    )
    try:
        resp = _rate_limited_get(url)
        data = resp.json()
        hits = data.get('hits', {}).get('hits', [])

        # Pass 1 — extract unique CIKs from accession-number prefixes.
        # Accession format: XXXXXXXXXX-YY-ZZZZZZ[:document.htm]
        # The first 10-digit segment is the filer's CIK.
        seen = set()
        unique_ciks = []
        for hit in hits:
            hit_id = hit.get('_id', '')
            try:
                cik = int(hit_id.split('-')[0])
            except (ValueError, IndexError):
                continue
            if cik and cik not in seen:
                seen.add(cik)
                unique_ciks.append(cik)

        # Pass 2 — fetch company name + ticker from submissions endpoint.
        # Cap at 10 unique CIKs to bound the number of extra HTTP calls.
        results = []
        for cik in unique_ciks[:10]:
            try:
                sub_url = "https://data.sec.gov/submissions/CIK{}.json".format(
                    str(cik).zfill(10)
                )
                sub_resp = _rate_limited_get(sub_url)
                sub_data = sub_resp.json()
                name = sub_data.get('name') or ''
                if not name:
                    continue
                tickers = sub_data.get('tickers') or []
                ticker = tickers[0] if tickers else ''
                results.append({'cik': cik, 'ticker': ticker, 'company_name': name})
            except Exception:
                continue

        return results
    except Exception:
        return []


def search_companies(query):
    """
    Search for companies by ticker or partial company name.
    Returns list of dicts: [{cik, ticker, company_name}, ...]
    Falls back to EDGAR's company search for names not in the local cache.
    """
    _ensure_cache()
    q_upper = query.strip().upper()

    conn = _get_db()
    seen = set()
    results = []

    # 1. Exact ticker match
    for row in conn.execute(
        "SELECT cik, ticker, company_name FROM tickers WHERE ticker = ? LIMIT 5",
        (q_upper,),
    ).fetchall():
        seen.add(row['cik'])
        results.append(dict(row))

    # 2. Ticker prefix match (for short queries that look like tickers)
    if not results and len(q_upper) <= 5:
        for row in conn.execute(
            "SELECT cik, ticker, company_name FROM tickers WHERE ticker LIKE ? LIMIT 10",
            (q_upper + '%',),
        ).fetchall():
            if row['cik'] not in seen:
                seen.add(row['cik'])
                results.append(dict(row))

    # 3. Company name partial match (case-insensitive)
    for row in conn.execute(
        "SELECT cik, ticker, company_name FROM tickers "
        "WHERE UPPER(company_name) LIKE ? LIMIT 20",
        ('%' + q_upper + '%',),
    ).fetchall():
        if row['cik'] not in seen:
            seen.add(row['cik'])
            results.append(dict(row))

    conn.close()

    # 4. EDGAR full-text search fallback when nothing found locally
    if not results:
        results = _edgar_company_fallback(query.strip())

    return results[:25]


def get_cache_info():
    """Return {'last_updated': datetime|None, 'company_count': int}."""
    if not os.path.exists(DB_PATH):
        return {'last_updated': None, 'company_count': 0}
    conn = _get_db()
    _init_db(conn)
    row = conn.execute("SELECT value FROM meta WHERE key = 'last_updated'").fetchone()
    last_updated = datetime.fromisoformat(row['value']) if row else None
    count = conn.execute("SELECT COUNT(*) FROM tickers").fetchone()[0]
    conn.close()
    return {'last_updated': last_updated, 'company_count': count}


# ---------------------------------------------------------------------------
# Step 5 — download manager
# ---------------------------------------------------------------------------

class FilingNotFoundError(Exception):
    pass


def list_downloads(downloads_dir):
    """
    Scan downloads_dir. Handles both structures:
      - downloads/{company}/{year}/{filename}  (new)
      - downloads/{company}/{filename}         (flat/legacy, year inferred from filename)
    Returns {company: {year: [{filename, path, size, modified}]}}.
    Files are sorted newest-downloaded first within each year group.
    """
    result = {}
    if not os.path.isdir(downloads_dir):
        return result

    for company in sorted(os.listdir(downloads_dir)):
        company_path = os.path.join(downloads_dir, company)
        if not os.path.isdir(company_path):
            continue

        years: dict = {}
        for entry in os.listdir(company_path):
            entry_path = os.path.join(company_path, entry)
            if os.path.isdir(entry_path):
                year = entry
                for fname in sorted(os.listdir(entry_path)):
                    fpath = os.path.join(entry_path, fname)
                    if os.path.isfile(fpath):
                        years.setdefault(year, []).append({
                            'filename': fname,
                            'path': '/'.join([company, year, fname]),
                            'size': os.path.getsize(fpath),
                            'modified': os.path.getmtime(fpath),
                        })
            elif os.path.isfile(entry_path):
                year = _year_from_filename(entry)
                years.setdefault(year, []).append({
                    'filename': entry,
                    'path': '/'.join([company, entry]),
                    'size': os.path.getsize(entry_path),
                    'modified': os.path.getmtime(entry_path),
                })

        if years:
            for yr in years:
                years[yr].sort(key=lambda f: f['modified'], reverse=True)
            result[company] = years

    return result


def _year_from_filename(fname):
    """Extract YYYY from filenames like 10-K_2023-11-03.htm."""
    m = re.search(r'_(\d{4})-\d{2}-\d{2}', fname)
    return m.group(1) if m else '—'


def resolve_primary_document(cik, accession_number):
    """Return the SEC URL for the primary .htm/.html/.pdf document of a filing."""
    cik_str = str(int(cik)).zfill(10)
    try:
        filings = _fetch_all_submissions(cik_str)
    except Exception as exc:
        raise FilingNotFoundError(f"Cannot fetch submissions for CIK {cik}: {exc}") from exc
    for f in filings:
        if f['accession_number'] == accession_number:
            return f['document_url'] or None
    raise FilingNotFoundError(
        f"Accession {accession_number} not found in submissions for CIK {cik}"
    )


def download_filings_batch(filings, downloads_dir, fmt='html'):
    """
    Download a list of filings sequentially, optionally converting to PDF.
    fmt: 'html' | 'pdf' | 'both'
    Returns list of {accession_number, status, path, pdf_fallback}.
    One failure does not stop the rest.
    """
    results = []
    _pw = _browser = _page = None

    if fmt in ('pdf', 'both'):
        try:
            from playwright.sync_api import sync_playwright
            _pw = sync_playwright().start()
            _browser = _pw.chromium.launch(headless=True)
            _page = _browser.new_page()
        except Exception:
            pass  # PDF conversion will fall back per-file

    try:
        for f in filings:
            try:
                result = download_filing(
                    cik=f['cik'],
                    accession_number=f['accession_number'],
                    company_name=f['company_name'],
                    filing_date=f['filing_date'],
                    fiscal_year_end=f['fiscal_year_end'],
                    form_type=f['form_type'],
                    downloads_dir=downloads_dir,
                    url=f.get('document_url') or None,
                    fmt=fmt,
                    page=_page,
                )
                results.append({
                    'accession_number': f['accession_number'],
                    'status': 'ok',
                    'path': result['primary'],
                    'pdf_fallback': result.get('pdf_fallback', False),
                })
            except Exception as exc:
                results.append({
                    'accession_number': f['accession_number'],
                    'status': 'error',
                    'error': str(exc),
                })
    finally:
        if _page:
            try: _page.close()
            except Exception: pass
        if _browser:
            try: _browser.close()
            except Exception: pass
        if _pw:
            try: _pw.stop()
            except Exception: pass

    return results


def _safe_dirname(name):
    return ''.join(c if c not in r'\/:*?"<>|' else '_' for c in name).strip()


def _download_url_to_file(url, path):
    """Stream-download *url* to *path*, overwriting if it exists."""
    resp = _rate_limited_get(url, stream=True)
    with open(path, 'wb') as fh:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                fh.write(chunk)


def _find_native_pdf_url(cik, accession_number):
    """
    Fetch the filing index page and return the URL of the first .pdf href,
    or None if no PDF is linked.
    """
    cik_int = int(cik)
    acc_no_dashes = accession_number.replace('-', '')
    index_url = (
        "https://www.sec.gov/Archives/edgar/data"
        "/{}/{}/{}-index.htm".format(cik_int, acc_no_dashes, accession_number)
    )
    try:
        resp = _rate_limited_get(index_url)
        hrefs = re.findall(r'href="([^"]*\.pdf)"', resp.text, re.IGNORECASE)
        if hrefs:
            href = hrefs[0]
            if href.startswith('http'):
                return href
            return "https://www.sec.gov" + href
    except Exception:
        pass
    return None


# Fix EDGAR's [break-spacer][<hr>][break-spacer] pattern that creates near-blank
# pages, while keeping all other section breaks (Part I, II, ...) intact.
_EDGAR_PAGE_BREAK_FIX_JS = """\
(function () {
    function isEmpty(el) {
        if (!el) return false;
        return el.textContent.replace(/[\\u00a0\\u200b\\s]/g, '').length === 0;
    }

    function collapseEl(el) {
        el.style.lineHeight = '0';
        el.style.fontSize   = '0';
        el.style.height     = '0';
        el.style.minHeight  = '0';
        el.style.maxHeight  = '0';
        el.style.overflow   = 'hidden';
        el.style.margin     = '0';
        el.style.padding    = '0';
        el.style.border     = 'none';
    }

    // -- Pass 1: fix per-<hr> breaks --
    document.querySelectorAll('hr').forEach(function (hr) {
        var prev             = hr.previousElementSibling;
        var prevAlreadyBreaks = false;

        if (prev && isEmpty(prev)) {
            prev.style.pageBreakAfter = 'auto';
            prev.style.breakAfter     = 'auto';
            collapseEl(prev);
        } else if (prev) {
            var pcs = window.getComputedStyle(prev);
            var pba = pcs.breakAfter || pcs.pageBreakAfter || '';
            prevAlreadyBreaks = (pba === 'always' || pba === 'page');
        }

        hr.style.display = 'none';

        var el        = hr.nextElementSibling;
        var needBreak = false;

        while (el && isEmpty(el)) {
            var cs = window.getComputedStyle(el);
            var ba = cs.breakAfter  || cs.pageBreakAfter  || '';
            var bb = cs.breakBefore || cs.pageBreakBefore || '';
            if (ba === 'always' || ba === 'page' || bb === 'always' || bb === 'page') {
                needBreak = true;
            }
            el.style.pageBreakAfter  = 'auto';
            el.style.breakAfter      = 'auto';
            el.style.pageBreakBefore = 'auto';
            el.style.breakBefore     = 'auto';
            collapseEl(el);
            el = el.nextElementSibling;
        }

        if (el && needBreak && !prevAlreadyBreaks) {
            el.style.pageBreakBefore = 'always';
            el.style.breakBefore     = 'always';
        }
    });

    // -- Pass 2: remove double-breaks left by Pass 1 --
    var allEls = Array.from(document.querySelectorAll('*'));

    var elPos = new Map();
    allEls.forEach(function (el, i) { elPos.set(el, i); });

    var breakEls = allEls.filter(function (el) {
        var cs = window.getComputedStyle(el);
        var ba = cs.breakAfter  || cs.pageBreakAfter  || '';
        var bb = cs.breakBefore || cs.pageBreakBefore || '';
        return ba === 'always' || ba === 'page' || bb === 'always' || bb === 'page';
    });

    for (var i = 0; i < breakEls.length - 1; i++) {
        var aEl = breakEls[i];
        var bEl = breakEls[i + 1];

        var acs = window.getComputedStyle(aEl);
        var bcs = window.getComputedStyle(bEl);
        var aba = acs.breakAfter  || acs.pageBreakAfter  || '';
        var bbb = bcs.breakBefore || bcs.pageBreakBefore || '';

        if (!((aba === 'always' || aba === 'page') &&
              (bbb === 'always' || bbb === 'page'))) continue;

        if (aEl.contains(bEl) || bEl.contains(aEl)) continue;

        var posA = elPos.get(aEl);
        var posB = elPos.get(bEl);

        if (posB - posA > 14) continue;

        var onlyEmpty = true;
        for (var j = posA + 1; j < posB; j++) {
            var mid = allEls[j];
            if (aEl.contains(mid)) continue;
            if (bEl.contains(mid)) break;

            var mcs = window.getComputedStyle(mid);
            if (mcs.display === 'none') continue;

            var t = mid.textContent.replace(/[\\u00a0\\u200b\\s]/g, '');
            var h = mid.getBoundingClientRect().height;
            if (t.length > 0 || h > 1) { onlyEmpty = false; break; }
        }

        if (onlyEmpty) {
            aEl.style.pageBreakAfter = 'auto';
            aEl.style.breakAfter     = 'auto';
        }
    }
}());
"""


def _html_to_pdf_playwright(html_path, pdf_path, page=None):
    """Convert a local HTML file to PDF using Playwright Chromium."""
    from playwright.sync_api import sync_playwright

    file_url = 'file:///' + html_path.replace('\\', '/')
    pdf_opts = dict(
        path=pdf_path,
        format='Letter',
        margin={'top': '0.75in', 'right': '0.75in', 'bottom': '0.75in', 'left': '0.75in'},
        print_background=True,
    )

    def _run(pg):
        pg.goto(file_url, wait_until='domcontentloaded', timeout=30000)
        pg.evaluate(_EDGAR_PAGE_BREAK_FIX_JS)
        pg.pdf(**pdf_opts)

    if page is not None:
        _run(page)
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pg = browser.new_page()
            _run(pg)
            browser.close()


def download_filing(cik, accession_number, company_name, filing_date,
                    fiscal_year_end, form_type, downloads_dir, url=None,
                    fmt='html', page=None):
    """
    Download the primary document to downloads_dir/{company}/{year}/.
    fmt: 'html' (original), 'pdf' (convert/find native), 'both' (html + pdf).
    page: open Playwright page for reuse across batch downloads.
    Returns: {'primary': str, 'paths': [str, ...], 'pdf_fallback': bool}
    """
    if not url:
        url = resolve_primary_document(cik, accession_number)
    if not url:
        raise FilingNotFoundError(f"No document URL for {accession_number}")

    safe_year = str(fiscal_year_end).split('-')[0]
    dest_dir = os.path.join(downloads_dir, _safe_dirname(company_name), safe_year)
    os.makedirs(dest_dir, exist_ok=True)

    safe_form = form_type.replace('/', '-').replace(' ', '-')
    src_ext = url.split('/')[-1].rsplit('.', 1)[-1].lower() if '.' in url.split('/')[-1] else 'htm'
    htm_path = os.path.join(dest_dir, f"{safe_form}_{filing_date}.htm")
    pdf_path = os.path.join(dest_dir, f"{safe_form}_{filing_date}.pdf")

    if fmt == 'html':
        if not os.path.exists(htm_path):
            _download_url_to_file(url, htm_path)
        return {'primary': htm_path, 'paths': [htm_path], 'pdf_fallback': False}

    if fmt == 'pdf':
        if os.path.exists(pdf_path):
            return {'primary': pdf_path, 'paths': [pdf_path], 'pdf_fallback': False}

        if src_ext == 'pdf':
            _download_url_to_file(url, pdf_path)
            return {'primary': pdf_path, 'paths': [pdf_path], 'pdf_fallback': False}

        native = _find_native_pdf_url(cik, accession_number)
        if native:
            _download_url_to_file(native, pdf_path)
            return {'primary': pdf_path, 'paths': [pdf_path], 'pdf_fallback': False}

        fd, tmp = tempfile.mkstemp(suffix='.htm')
        os.close(fd)
        try:
            _download_url_to_file(url, tmp)
            _html_to_pdf_playwright(tmp, pdf_path, page)
            return {'primary': pdf_path, 'paths': [pdf_path], 'pdf_fallback': False}
        except Exception:
            if not os.path.exists(htm_path):
                shutil.copy2(tmp, htm_path)
            return {'primary': htm_path, 'paths': [htm_path], 'pdf_fallback': True}
        finally:
            if os.path.exists(tmp):
                try: os.unlink(tmp)
                except Exception: pass

    # Both mode: HTML + PDF
    if src_ext == 'pdf':
        if not os.path.exists(pdf_path):
            _download_url_to_file(url, pdf_path)
        return {'primary': pdf_path, 'paths': [pdf_path], 'pdf_fallback': False}

    if not os.path.exists(htm_path):
        _download_url_to_file(url, htm_path)

    if os.path.exists(pdf_path):
        return {'primary': pdf_path, 'paths': [htm_path, pdf_path], 'pdf_fallback': False}

    native = _find_native_pdf_url(cik, accession_number)
    if native:
        _download_url_to_file(native, pdf_path)
        return {'primary': pdf_path, 'paths': [htm_path, pdf_path], 'pdf_fallback': False}

    try:
        _html_to_pdf_playwright(htm_path, pdf_path, page)
        return {'primary': pdf_path, 'paths': [htm_path, pdf_path], 'pdf_fallback': False}
    except Exception:
        return {'primary': htm_path, 'paths': [htm_path], 'pdf_fallback': True}


# ---------------------------------------------------------------------------
# Step 3 — EDGAR filing search
# ---------------------------------------------------------------------------

def get_filings(cik, start_date, end_date, form_types=None):
    """
    Return filings for *cik* within the date range.

    Args:
        cik: str or int
        start_date: "YYYY-MM-DD"
        end_date:   "YYYY-MM-DD"
        form_types: list of form type strings, e.g. ['10-K', '10-Q', '8-K'].
                    None means return all form types.

    Returns:
        list of dicts, newest first:
        {form_type, filing_date, fiscal_year_end, accession_number,
         document_url, estimated_size}
    """
    cik_str = str(int(cik)).zfill(10)
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    allowed = set(form_types) if form_types else None

    all_filings = _fetch_all_submissions(cik_str)

    results = []
    for filing in all_filings:
        if allowed and filing['form_type'] not in allowed:
            continue
        if not filing['filing_date']:
            continue
        filing_date = datetime.strptime(filing['filing_date'], "%Y-%m-%d")
        if start <= filing_date <= end:
            results.append(filing)

    results.sort(key=lambda x: x['filing_date'], reverse=True)
    return results


# Per-session cache: cik_str -> (fetched_at_timestamp, filings_list, company_meta)
_submissions_cache: dict = {}
_SUBMISSIONS_CACHE_TTL = 300  # seconds


def _fetch_all_submissions(cik_str):
    """
    Fetch the primary submissions JSON for a CIK, then follow any pagination
    files listed in filings.files.  Returns a flat list of filing dicts.
    Results are cached for 5 minutes so repeated lookups within a session are instant.
    Also caches company-level metadata (SIC, category) for use by export.
    """
    now = time.time()
    cached = _submissions_cache.get(cik_str)
    if cached and now - cached[0] < _SUBMISSIONS_CACHE_TTL:
        return cached[1]

    url = "https://data.sec.gov/submissions/CIK{}.json".format(cik_str)
    resp = _rate_limited_get(url)
    data = resp.json()

    company_meta = {
        'sic': str(data.get('sic', '') or ''),
        'sic_description': data.get('sicDescription', '') or '',
        'category': data.get('category', '') or '',
    }

    filings = []

    recent = data.get('filings', {}).get('recent', {})
    if recent:
        filings.extend(_parse_filing_block(cik_str, recent))

    for file_info in data.get('filings', {}).get('files', []):
        name = file_info.get('name', '')
        if not name:
            continue
        page_url = "https://data.sec.gov/submissions/{}".format(name)
        try:
            page_resp = _rate_limited_get(page_url)
            filings.extend(_parse_filing_block(cik_str, page_resp.json()))
        except Exception:
            continue

    _submissions_cache[cik_str] = (now, filings, company_meta)
    return filings


def get_company_meta(cik):
    """
    Return company-level metadata dict: {sic, sic_description, category}.
    Uses the submissions cache populated by get_filings; no extra HTTP call
    if the cache is warm.
    """
    cik_str = str(int(cik)).zfill(10)
    now = time.time()
    cached = _submissions_cache.get(cik_str)
    if cached and now - cached[0] < _SUBMISSIONS_CACHE_TTL and len(cached) > 2:
        return cached[2]
    _fetch_all_submissions(cik_str)
    cached = _submissions_cache.get(cik_str)
    return cached[2] if cached and len(cached) > 2 else {}


# ---------------------------------------------------------------------------
# Step 10 — metadata export (CSV / Excel)
# ---------------------------------------------------------------------------

_EXPORT_COLUMNS = [
    'Company Name', 'Ticker', 'CIK', 'Form Type', 'Filing Date',
    'Fiscal Year End', 'Accession Number', 'SIC Code', 'SIC Description',
    'Filer Category', 'Document URL', 'Amendment',
]


def export_filings(cik, start_date, end_date, form_types, fmt,
                   company_name, ticker, exports_dir):
    """
    Generate a CSV or Excel file of filing metadata for the given search params.
    fmt: 'csv' | 'xlsx'
    Returns the absolute path to the created file.
    """
    filings = get_filings(cik, start_date, end_date, form_types=form_types)
    meta = get_company_meta(cik)

    rows = []
    for f in filings:
        rows.append({
            'Company Name': company_name,
            'Ticker': ticker,
            'CIK': str(int(cik)),
            'Form Type': f['form_type'],
            'Filing Date': f['filing_date'],
            'Fiscal Year End': f['fiscal_year_end'] or '',
            'Accession Number': f['accession_number'],
            'SIC Code': meta.get('sic', ''),
            'SIC Description': meta.get('sic_description', ''),
            'Filer Category': meta.get('category', ''),
            'Document URL': f['document_url'],
            'Amendment': 'Yes' if f['form_type'].endswith('/A') else 'No',
        })

    safe_company_dir = _safe_dirname(company_name)
    safe_company_fn = safe_company_dir.replace(' ', '_')
    dest_dir = os.path.join(exports_dir, safe_company_dir)
    os.makedirs(dest_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d_%H%M%S')

    if fmt == 'csv':
        filename = f"{safe_company_fn}_export_{ts}.csv"
        filepath = os.path.join(dest_dir, filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as fh:
            writer = _csv_module.DictWriter(fh, fieldnames=_EXPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    else:
        import openpyxl
        from openpyxl.styles import Font

        filename = f"{safe_company_fn}_export_{ts}.xlsx"
        filepath = os.path.join(dest_dir, filename)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'EDGAR Search Results'

        ws.append(_EXPORT_COLUMNS)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.freeze_panes = 'A2'

        for row in rows:
            ws.append([row[col] for col in _EXPORT_COLUMNS])

        for col in ws.columns:
            max_len = max((len(str(cell.value or '')) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 80)

        wb.save(filepath)

    return filepath


def _parse_filing_block(cik_str, block):
    """
    Convert a filing block (parallel arrays from the submissions API) into a
    list of filing dicts. Returns all form types; filtering happens in get_filings.
    """
    accessions = block.get('accessionNumber', [])
    forms = block.get('form', [])
    dates = block.get('filingDate', [])
    periods = block.get('reportDate', [])
    primary_docs = block.get('primaryDocument', [])

    cik_int = int(cik_str)
    results = []

    for i, acc in enumerate(accessions):
        form_type = forms[i] if i < len(forms) else ''
        if not form_type:
            continue

        filing_date = dates[i] if i < len(dates) else ''
        fiscal_year_end = periods[i] if i < len(periods) else ''
        primary_doc = primary_docs[i] if i < len(primary_docs) else ''

        acc_no_dashes = acc.replace('-', '')

        if primary_doc:
            doc_url = (
                "https://www.sec.gov/Archives/edgar/data"
                "/{}/{}/{}".format(cik_int, acc_no_dashes, primary_doc)
            )
        else:
            doc_url = (
                "https://www.sec.gov/Archives/edgar/data"
                "/{}/{}/{}-index.htm".format(cik_int, acc_no_dashes, acc)
            )

        results.append({
            'form_type': form_type,
            'filing_date': filing_date,
            'fiscal_year_end': fiscal_year_end,
            'accession_number': acc,
            'document_url': doc_url,
            'estimated_size': None,
        })

    return results
