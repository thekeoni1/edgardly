import os
import subprocess
import sys
import webbrowser
import threading
import datetime
import edgar_api
import xbrl_extractor as xbrl
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)


def _xbrl_period_days(dp):
    """Return period duration in days; 999999 for balance-sheet instants (start=None)."""
    start = dp.get("start")
    end = dp.get("end")
    if not start or not end:
        return 999999
    try:
        return (datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)).days
    except Exception:
        return 0


def _xbrl_format_value(value, unit):
    if value is None:
        return None
    if unit == "USD":
        a = abs(value)
        if a >= 1e9:
            return "${:.2f}B".format(value / 1e9)
        if a >= 1e6:
            return "${:.1f}M".format(value / 1e6)
        return "${:,.0f}".format(value)
    if unit in ("USD/shares",):
        return "${:.2f}".format(value)
    if unit == "shares":
        a = abs(value)
        if a >= 1e9:
            return "{:.2f}B".format(value / 1e9)
        if a >= 1e6:
            return "{:.1f}M".format(value / 1e6)
        return "{:,.0f}".format(value)
    return "{:g}".format(value)


def _build_xbrl_result(cik, start_year, end_year, period_type):
    facts = xbrl.fetch_company_facts(cik)
    entity = facts.get("entityName", str(cik))
    raw = xbrl.extract_all_line_items(facts)
    deduped = xbrl.deduplicate_all_line_items(raw)
    all_flags = xbrl.validate_financials(deduped)
    target_fps = {"FY"} if period_type == "annual" else {"Q1", "Q2", "Q3", "Q4"}
    # Filter out partial-year or multi-quarter YTD contexts that EDGAR sometimes
    # mislabels with the wrong fp tag in 10-K/10-Q comparative tables.
    def _valid_period(dp):
        days = _xbrl_period_days(dp)
        if days == 999999:
            return True  # balance-sheet instant — always valid
        if period_type == "annual":
            return days >= 300
        else:
            return 60 <= days <= 130  # single calendar quarter

    all_ends = set()
    end_fp = {}
    for line_item, info in deduped.items():
        for dp in info["data"]:
            fp = dp.get("fiscal_period")
            if fp not in target_fps:
                continue
            if not _valid_period(dp):
                continue
            end = dp.get("end")
            if not end:
                continue
            year = int(end[:4])
            if start_year <= year <= end_year:
                all_ends.add(end)
                if end not in end_fp:
                    end_fp[end] = fp
    sorted_ends = sorted(all_ends)
    columns = []
    for end in sorted_ends:
        fp = end_fp.get(end, "")
        yr = int(end[:4])
        label = "FY{}".format(yr) if period_type == "annual" else "{} {}".format(fp, yr)
        columns.append({"key": end, "label": label, "fp": fp, "fy": yr})
    rows = []
    for line_item in xbrl.TAG_MAP:
        info = deduped[line_item]
        tag_used = info.get("tag_used")
        item_flags = all_flags.get(line_item, [])
        cells = {}
        cell_days = {}
        for dp in info["data"]:
            fp = dp.get("fiscal_period")
            if fp not in target_fps:
                continue
            if not _valid_period(dp):
                continue
            end = dp.get("end")
            if not end or end not in all_ends:
                continue
            days = _xbrl_period_days(dp)
            if end in cells and cell_days[end] >= days:
                continue  # prefer the longest period for this end date
            period_flags = [
                {"type": f["flag_type"], "msg": f["message"]}
                for f in item_flags if f.get("period_end") == end
            ]
            cells[end] = {
                "value": dp["value"],
                "formatted": _xbrl_format_value(dp["value"], dp.get("unit", "")),
                "unit": dp.get("unit"),
                "start": dp.get("start"),
                "end": end,
                "fp": fp,
                "tag": dp.get("tag"),
                "filed": dp.get("filed"),
                "flags": period_flags,
            }
            cell_days[end] = days
        rows.append({"line_item": line_item, "tag_used": tag_used, "cells": cells})
    return entity, columns, rows


def _xbrl_write_csv(filepath, entity, columns, rows, period_type):
    import csv
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["# {} -- XBRL Financial Data ({})".format(entity, period_type)])
        writer.writerow(["Line Item", "Source Tag"] + [c["label"] for c in columns] + ["Flags"])
        for row in rows:
            cells_out = []
            all_row_flags = []
            for col in columns:
                cell = row["cells"].get(col["key"])
                if cell is None:
                    cells_out.append("Not reported")
                else:
                    cells_out.append(
                        cell["formatted"] if cell["formatted"] is not None else str(cell["value"])
                    )
                    all_row_flags.extend(f["msg"] for f in cell.get("flags", []))
            flags_str = "; ".join(sorted(set(all_row_flags))) if all_row_flags else ""
            writer.writerow([row["line_item"], row["tag_used"] or ""] + cells_out + [flags_str])


def _xbrl_write_xlsx(filepath, entity, columns, rows, period_type):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError("openpyxl is required: pip install openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Financial Data"
    hdr_fill = PatternFill("solid", fgColor="003366")
    hdr_font = Font(color="FFFFFF", bold=True)
    flag_fill = PatternFill("solid", fgColor="FFF3CD")
    ws.cell(1, 1, "{} -- XBRL Financial Data ({})".format(entity, period_type.title()))
    ws.cell(1, 1).font = Font(bold=True, size=12)
    hrow = 3
    for ci, (text, w) in enumerate([("Line Item", 28), ("Source Tag", 46)], start=1):
        c = ws.cell(hrow, ci, text)
        c.font = hdr_font
        c.fill = hdr_fill
        ws.column_dimensions[get_column_letter(ci)].width = w
    for ci, col in enumerate(columns, start=3):
        c = ws.cell(hrow, ci, col["label"])
        c.font = hdr_font
        c.fill = hdr_fill
        c.alignment = Alignment(horizontal="right")
        ws.column_dimensions[get_column_letter(ci)].width = 12
    flags_col = len(columns) + 3
    c = ws.cell(hrow, flags_col, "Flags")
    c.font = hdr_font
    c.fill = hdr_fill
    ws.column_dimensions[get_column_letter(flags_col)].width = 40
    for ri, row in enumerate(rows, start=hrow + 1):
        ws.cell(ri, 1, row["line_item"])
        c = ws.cell(ri, 2, row["tag_used"] or "")
        c.font = Font(color="888888", size=10)
        all_row_flags = []
        for ci, col in enumerate(columns, start=3):
            cell = row["cells"].get(col["key"])
            c = ws.cell(ri, ci)
            if cell is None:
                c.value = "Not reported"
                c.font = Font(color="AAAAAA", italic=True)
                c.alignment = Alignment(horizontal="right")
            else:
                c.value = cell["value"]
                c.alignment = Alignment(horizontal="right")
                if cell.get("flags"):
                    c.fill = flag_fill
                    all_row_flags.extend(f["msg"] for f in cell["flags"])
        flags_str = "; ".join(sorted(set(all_row_flags))) if all_row_flags else ""
        if flags_str:
            c2 = ws.cell(ri, flags_col, flags_str)
            c2.font = Font(color="856404")
    wb.save(filepath)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    results = edgar_api.search_companies(q)
    return jsonify(results)


@app.route("/api/filings")
def api_filings():
    cik = request.args.get("cik", "").strip()
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()
    forms_param = request.args.get("forms", "").strip()
    form_types = [f.strip() for f in forms_param.split(",") if f.strip()] if forms_param else ["10-K"]
    if not cik or not start or not end:
        return jsonify({"error": "cik, start, and end are required"}), 400
    try:
        filings = edgar_api.get_filings(cik, start, end, form_types=form_types)
        return jsonify(filings)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json(silent=True)
    required = {"cik", "accession_number", "company_name", "filing_date", "fiscal_year_end", "form_type"}
    if not data or not required.issubset(data.keys()):
        missing = required - set(data or {})
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
    document_url = data.get("document_url", "")
    if document_url and not document_url.startswith("https://www.sec.gov/"):
        return jsonify({"error": "Invalid document URL"}), 400
    fmt = data.get("format", "html")
    if fmt not in ("html", "pdf", "both"):
        return jsonify({"error": "format must be 'html', 'pdf', or 'both'"}), 400
    try:
        result = edgar_api.download_filing(
            cik=data["cik"],
            accession_number=data["accession_number"],
            company_name=data["company_name"],
            filing_date=data["filing_date"],
            fiscal_year_end=data["fiscal_year_end"],
            form_type=data["form_type"],
            downloads_dir=DOWNLOADS_DIR,
            url=document_url or None,
            fmt=fmt,
        )
        primary = result['primary']
        return jsonify({
            "status": "ok",
            "path": primary,
            "folder": os.path.dirname(primary),
            "pdf_fallback": result.get('pdf_fallback', False),
        })
    except edgar_api.FilingNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download-batch", methods=["POST"])
def api_download_batch():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Expected a JSON object with 'filings' array"}), 400
    filings_data = body.get('filings', [])
    if not isinstance(filings_data, list) or not filings_data:
        return jsonify({"error": "No filings provided"}), 400
    fmt = body.get('format', 'html')
    if fmt not in ('html', 'pdf', 'both'):
        return jsonify({"error": "format must be 'html', 'pdf', or 'both'"}), 400
    required = {"cik", "accession_number", "company_name", "filing_date", "fiscal_year_end", "form_type"}
    for i, item in enumerate(filings_data):
        missing = required - set(item.keys())
        if missing:
            return jsonify({"error": f"Item {i} missing fields: {', '.join(missing)}"}), 400
        url = item.get("document_url", "")
        if url and not url.startswith("https://www.sec.gov/"):
            return jsonify({"error": f"Item {i} has invalid document URL"}), 400
    results = edgar_api.download_filings_batch(filings_data, DOWNLOADS_DIR, fmt=fmt)
    folder = None
    for r in results:
        if r.get('status') == 'ok' and r.get('path'):
            folder = os.path.dirname(os.path.dirname(r['path']))
            break
    return jsonify({"results": results, "folder": folder})


@app.route("/api/downloads")
def api_downloads():
    return jsonify(edgar_api.list_downloads(DOWNLOADS_DIR))


@app.route("/downloads/<path:filepath>")
def serve_download(filepath):
    return send_from_directory(DOWNLOADS_DIR, filepath)


@app.route("/api/export", methods=["POST"])
def api_export():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400
    for field in ("cik", "start", "end"):
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400
    fmt = data.get("format", "xlsx")
    if fmt not in ("csv", "xlsx"):
        return jsonify({"error": "format must be 'csv' or 'xlsx'"}), 400
    forms_param = data.get("forms", "")
    form_types = [f.strip() for f in forms_param.split(",") if f.strip()] if forms_param else ["10-K"]
    try:
        filepath = edgar_api.export_filings(
            cik=data["cik"],
            start_date=data["start"],
            end_date=data["end"],
            form_types=form_types,
            fmt=fmt,
            company_name=data.get("company_name", ""),
            ticker=data.get("ticker", ""),
            exports_dir=EXPORTS_DIR,
        )
        filename = os.path.basename(filepath)
        rel_path = os.path.relpath(filepath, EXPORTS_DIR).replace('\\', '/')
        return jsonify({
            "status": "ok",
            "path": filepath,
            "filename": filename,
            "folder": os.path.dirname(filepath),
            "download_url": "/exports/" + rel_path,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/open-folder", methods=["POST"])
def api_open_folder():
    data = request.get_json(silent=True) or {}
    folder = data.get("folder", EXPORTS_DIR)
    folder = os.path.normpath(folder)
    allowed = (os.path.normpath(EXPORTS_DIR), os.path.normpath(DOWNLOADS_DIR))
    if not any(folder.startswith(root) for root in allowed):
        folder = EXPORTS_DIR
    try:
        os.startfile(folder)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/exports/<path:filepath>")
def serve_export(filepath):
    return send_from_directory(EXPORTS_DIR, filepath)


@app.route("/api/xbrl/extract", methods=["POST"])
def api_xbrl_extract():
    data = request.get_json(silent=True) or {}
    cik = str(data.get("cik", "")).strip()
    if not cik:
        return jsonify({"error": "cik is required"}), 400
    try:
        start_year = int(data.get("start_year", 2015))
        end_year = int(data.get("end_year", datetime.date.today().year))
    except (ValueError, TypeError):
        return jsonify({"error": "start_year and end_year must be integers"}), 400
    period_type = data.get("period_type", "annual")
    if period_type not in ("annual", "quarterly"):
        return jsonify({"error": "period_type must be 'annual' or 'quarterly'"}), 400
    try:
        entity, columns, rows = _build_xbrl_result(cik, start_year, end_year, period_type)
        return jsonify({"entity": entity, "columns": columns, "rows": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/xbrl/export", methods=["POST"])
def api_xbrl_export():
    data = request.get_json(silent=True) or {}
    cik = str(data.get("cik", "")).strip()
    if not cik:
        return jsonify({"error": "cik is required"}), 400
    try:
        start_year = int(data.get("start_year", 2015))
        end_year = int(data.get("end_year", datetime.date.today().year))
    except (ValueError, TypeError):
        return jsonify({"error": "start_year and end_year must be integers"}), 400
    period_type = data.get("period_type", "annual")
    if period_type not in ("annual", "quarterly"):
        return jsonify({"error": "period_type must be 'annual' or 'quarterly'"}), 400
    fmt = data.get("format", "xlsx")
    if fmt not in ("csv", "xlsx"):
        return jsonify({"error": "format must be 'csv' or 'xlsx'"}), 400
    try:
        entity, columns, rows = _build_xbrl_result(cik, start_year, end_year, period_type)
        safe = "".join(c if c.isalnum() or c in " -_" else "" for c in entity)[:40].strip()
        company_folder = os.path.join(EXPORTS_DIR, safe.replace(" ", "_") or cik)
        os.makedirs(company_folder, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "xbrl_{}_{}_{}.{}".format(period_type, ts, cik, fmt)
        filepath = os.path.join(company_folder, filename)
        if fmt == "csv":
            _xbrl_write_csv(filepath, entity, columns, rows, period_type)
        else:
            _xbrl_write_xlsx(filepath, entity, columns, rows, period_type)
        rel_path = os.path.relpath(filepath, EXPORTS_DIR).replace("\\", "/")
        return jsonify({
            "status": "ok",
            "filename": filename,
            "folder": company_folder,
            "download_url": "/exports/" + rel_path,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _ensure_playwright_chromium():
    """Auto-install Playwright's Chromium browser on first run if not present."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            if os.path.exists(p.chromium.executable_path):
                return
    except ImportError:
        print("WARNING: playwright not installed — PDF downloads unavailable.")
        print("  Run: pip install playwright && playwright install chromium")
        return
    except Exception:
        pass  # Fall through to install attempt

    print("\nFirst-time setup: downloading PDF rendering engine (~150 MB)...")
    print("This is a one-time download. Please wait...\n")
    try:
        proc = subprocess.Popen(
            [sys.executable, '-m', 'playwright', 'install', 'chromium'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in iter(proc.stdout.readline, ''):
            print(line, end='', flush=True)
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"installer exited with code {proc.returncode}")
        print("\nSetup complete — PDF rendering engine ready.\n")
    except Exception as exc:
        print(f"\nWARNING: Auto-install failed: {exc}")
        print("To enable PDF downloads, run manually:")
        print("  playwright install chromium")
        print("HTML downloads will still work.\n")


def open_browser():
    webbrowser.open("http://localhost:5000")


if __name__ == "__main__":
    _ensure_playwright_chromium()
    threading.Timer(1.0, open_browser).start()
    app.run(debug=False, port=5000)
