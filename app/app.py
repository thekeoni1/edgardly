import os
import subprocess
import sys
import webbrowser
import threading
import datetime
import json
import edgar_api
import xbrl_extractor as xbrl
import peer_comparison as pc
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, stream_with_context

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


# ---------------------------------------------------------------------------
# XBRL export: line-item classification and Excel format constants
# ---------------------------------------------------------------------------

_DOLLAR_LINE_ITEMS = frozenset({
    "Revenue", "Cost of Revenue", "Gross Profit", "Operating Income", "Net Income",
    "Total Assets", "Total Liabilities", "Total Equity", "Cash and Equivalents", "Total Debt",
})
_EPS_LINE_ITEMS = frozenset({"EPS Basic", "EPS Diluted"})
_SHARE_LINE_ITEMS = frozenset({"Shares Outstanding (Basic)", "Shares Outstanding (Diluted)"})

# Accounting-style format: positives with trailing space (aligns with closing paren on negatives),
# negatives in parentheses, zero as dash.
_XLSX_FMT_DOLLAR = '#,##0_);(#,##0);"-"'
_XLSX_FMT_EPS    = '#,##0.00_);(#,##0.00);"-"'
_XLSX_FMT_SHARES = '#,##0_);(#,##0);"-"'

# Rows that receive a border in Excel exports (financial modeling convention)
_SINGLE_BORDER_ROW_ITEMS = frozenset({"Gross Profit", "Operating Income"})
_DOUBLE_BORDER_ROW_ITEMS = frozenset({"Net Income"})

# ---------------------------------------------------------------------------
# Shared Excel sanity-check helper
# ---------------------------------------------------------------------------

def _write_xlsx_sanity_checks(ws, start_row, row_map, data_col_idxs, dollar_label, BF):
    """Append formula-driven sanity-check rows to a worksheet.

    row_map:       {line_item_name: excel_row_number}  -- built while writing data rows
    data_col_idxs: ordered list of 1-based column indices that hold financial data

    Each check cell contains a live Excel formula so that editing any cell in the
    sheet immediately recalculates the result.  Conditional-formatting rules colour
    the result green (within 5% tolerance), red (fails), or grey (any input is N/A
    or non-numeric).

    Balance-Sheet:  Total Assets − Total Liabilities − Total Equity  (should be 0)
    Gross-Profit:   Revenue − Cost of Revenue − Gross Profit          (should be 0)

    Returns the row number immediately after the last written row.
    """
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.utils import get_column_letter

    TOLERANCE = 0.05
    CHECKS = [
        # (label, [(line_item, sign), ...], reference_item_for_tolerance)
        ("BS Check: Assets − Liabilities − Equity",
         [("Total Assets", 1), ("Total Liabilities", -1), ("Total Equity", -1)],
         "Total Assets"),
        ("GP Check: Revenue − COGS − Gross Profit",
         [("Revenue", 1), ("Cost of Revenue", -1), ("Gross Profit", -1)],
         "Revenue"),
    ]

    label_font   = Font(name=BF, size=11, italic=True)
    missing_font = Font(name=BF, color="AAAAAA", italic=True, size=11)

    _green_fill = PatternFill("solid", fgColor="D4EDDA")
    _green_font = Font(color="155724", name=BF, size=11)
    _red_fill   = PatternFill("solid", fgColor="F8D7DA")
    _red_font   = Font(color="721C24", name=BF, size=11)
    _grey_fill  = PatternFill("solid", fgColor="F5F5F5")
    _grey_font  = Font(color="AAAAAA", name=BF, size=11, italic=True)

    hdr = ws.cell(start_row, 1, "Sanity Checks")
    hdr.font = Font(name=BF, bold=True, size=11, color="003366")

    cur = start_row + 1
    for check_name, items_signs, ref_item in CHECKS:
        ws.cell(cur, 1, check_name).font = label_font

        # Resolve row numbers; if any required item is absent from the sheet
        # entirely, fall back to a static label.
        item_rows = {li: row_map.get(li) for li, _ in items_signs}
        ref_row   = row_map.get(ref_item)

        if any(r is None for r in item_rows.values()):
            for col_idx in data_col_idxs:
                c = ws.cell(cur, col_idx)
                c.value     = "Item not exported"
                c.font      = missing_font
                c.alignment = Alignment(horizontal="right")
        else:
            for col_idx in data_col_idxs:
                col = get_column_letter(col_idx)
                c   = ws.cell(cur, col_idx)

                # ISNUMBER guards prevent #VALUE! when a cell contains "N/A"/"Not reported"
                guards = ",".join(
                    f"ISNUMBER({col}{item_rows[li]})" for li, _ in items_signs
                )

                # Build arithmetic expression  e.g.  B7-B8-B9
                expr = "".join(
                    (f"{col}{item_rows[li]}" if i == 0
                     else f"+{col}{item_rows[li]}" if sign > 0
                     else f"-{col}{item_rows[li]}")
                    for i, (li, sign) in enumerate(items_signs)
                )

                c.value         = f'=IF(AND({guards}),{expr},"N/A")'
                c.number_format = _XLSX_FMT_DOLLAR
                c.alignment     = Alignment(horizontal="right")

            # Conditional formatting applied to the whole check row
            if data_col_idxs and ref_row is not None:
                first = get_column_letter(data_col_idxs[0])
                last  = get_column_letter(data_col_idxs[-1])
                rng   = f"{first}{cur}:{last}{cur}"
                # Anchor cell for CF formulas (top-left of range; column shifts automatically)
                a   = f"{first}{cur}"         # check result
                ref = f"{first}{ref_row}"     # reference component (e.g. Total Assets)

                ws.conditional_formatting.add(rng, FormulaRule(
                    formula=[f"AND(ISNUMBER({a}),ABS({a})<={TOLERANCE}*ABS({ref}))"],
                    fill=_green_fill, font=_green_font,
                ))
                ws.conditional_formatting.add(rng, FormulaRule(
                    formula=[f"AND(ISNUMBER({a}),ABS({a})>{TOLERANCE}*ABS({ref}))"],
                    fill=_red_fill, font=_red_font,
                ))
                ws.conditional_formatting.add(rng, FormulaRule(
                    formula=[f"NOT(ISNUMBER({a}))"],
                    fill=_grey_fill, font=_grey_font,
                ))

        cur += 1

    ws.cell(cur, 1,
            f"Sanity checks ({dollar_label}):  "
            "green ✓ = within 5% tolerance   "
            "red ✗ = check fails   "
            "grey = data unavailable for this period"
    ).font = Font(name=BF, color="666666", italic=True, size=10)
    return cur + 1


def _detect_dollar_scale(rows, columns):
    """Return (factor, label) for dollar scaling based on most recent Revenue.

    Falls back to Total Assets if Revenue has no data in the displayed column range
    (this can happen when a company switched XBRL revenue tags mid-history and the
    older tag only covers pre-filter years).
    """
    def _scale_from_value(val):
        val = abs(val)
        if val > 1_000_000_000:
            return 1_000_000, "$mm"
        if val > 10_000_000:
            return 1_000, "$000s"
        return 1, "$"

    for candidate in ("Revenue", "Total Assets"):
        for row in rows:
            if row["line_item"] == candidate:
                for col in reversed(columns):
                    cell = row["cells"].get(col["key"])
                    if cell and cell.get("value") is not None:
                        return _scale_from_value(cell["value"])
    return 1, "$"


def _detect_share_scale(rows, columns):
    """Return (factor, label) for share-count scaling based on most recent share count."""
    for name in ("Shares Outstanding (Diluted)", "Shares Outstanding (Basic)"):
        for row in rows:
            if row["line_item"] == name:
                for col in reversed(columns):
                    cell = row["cells"].get(col["key"])
                    if cell and cell.get("value") is not None:
                        if abs(cell["value"]) > 1_000_000_000:
                            return 1_000_000, "mm"
                        return 1_000, "000s"
    return 1_000, "000s"


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


def _build_chart_data(entity, columns, rows, dollar_factor, dollar_label):
    """
    Convert _build_xbrl_result output into chart-ready series.

    Revenue and Net Income are scaled by dollar_factor and always included
    when present, marked flagged=True when the underlying cell is flagged.

    Gross Margin % and Net Margin % are computed only when BOTH inputs are
    present and NEITHER is flagged (flagged inputs make derived ratios
    unreliable; those periods appear as null/gap in the chart).

    Each point:  {"period_label": str, "period_end": str, "value": float|None,
                  "flagged": bool}
    """
    row_by_li = {r["line_item"]: r for r in rows}

    def _cell(li, end):
        row = row_by_li.get(li)
        if not row:
            return None, False
        cell = row["cells"].get(end)
        if not cell:
            return None, False
        val = cell.get("value")
        flagged = bool(cell.get("flags"))
        return val, flagged

    series = {k: [] for k in ("revenue", "net_income", "gross_margin_pct", "net_margin_pct")}

    for col in columns:
        end   = col["key"]
        label = col["label"]

        rev_val,  rev_flagged  = _cell("Revenue",      end)
        ni_val,   ni_flagged   = _cell("Net Income",   end)
        gp_val,   gp_flagged   = _cell("Gross Profit", end)

        safe_factor = dollar_factor if dollar_factor else 1

        def _scale(v):
            if v is None:
                return None
            return round(v / safe_factor, 2) if safe_factor != 1 else round(float(v), 2)

        series["revenue"].append({
            "period_label": label, "period_end": end,
            "value": _scale(rev_val), "flagged": rev_flagged,
        })
        series["net_income"].append({
            "period_label": label, "period_end": end,
            "value": _scale(ni_val), "flagged": ni_flagged,
        })

        # Gross Margin %: only when both present and neither flagged
        if (rev_val is not None and rev_val != 0
                and gp_val is not None
                and not rev_flagged and not gp_flagged):
            gm_pct = round(100.0 * gp_val / rev_val, 2)
        else:
            gm_pct = None

        series["gross_margin_pct"].append({
            "period_label": label, "period_end": end,
            "value": gm_pct, "flagged": False,
        })

        # Net Margin %: only when both present and neither flagged
        if (rev_val is not None and rev_val != 0
                and ni_val is not None
                and not rev_flagged and not ni_flagged):
            nm_pct = round(100.0 * ni_val / rev_val, 2)
        else:
            nm_pct = None

        series["net_margin_pct"].append({
            "period_label": label, "period_end": end,
            "value": nm_pct, "flagged": False,
        })

    return {
        "entity": entity,
        "dollar_scale": {"factor": dollar_factor, "label": dollar_label},
        "series": series,
    }


def _build_peer_chart_data(comparison_result):
    """
    Convert a fetch_peer_comparison result into per-company chart-ready series.

    Accepts the same comparison_result dict the SSE stream emits (with an
    embedded 'scale' key).  Does not re-fetch EDGAR.

    Periods are aligned by relative label (FY0, FY-1, …) so companies with
    different fiscal-year calendars are still comparable on the same x-axis.
    Periods are returned in chronological order (oldest first).

    Each point: {"period_label": str, "period_end": str, "value": float|None,
                 "flagged": bool}

    Margin rules mirror _build_chart_data:
      - null when either input is missing or zero
      - null when either input is flagged (flagged inputs → unreliable ratios)
    """
    companies  = comparison_result["companies"]
    n_periods  = comparison_result.get("n_periods", 3)
    scale      = comparison_result.get("scale") or pc.select_peer_scale(comparison_result)
    dollar_factor = scale["dollar_factor"]
    dollar_label  = scale["dollar_label"]

    # Chronological order: FY-(n-1), …, FY-1, FY0
    sorted_rels = ["FY-{}".format(i) for i in range(n_periods - 1, 0, -1)] + ["FY0"]

    safe_factor = dollar_factor if dollar_factor else 1

    def _scale(v):
        if v is None:
            return None
        return round(v / safe_factor, 2) if safe_factor != 1 else round(float(v), 2)

    company_series = []
    for company in companies:
        li = company["line_items"]

        def _lookup(line_item_name):
            info = li.get(line_item_name) or {}
            return {p["relative_period"]: p for p in info.get("periods", [])}

        rev_by_rel = _lookup("Revenue")
        ni_by_rel  = _lookup("Net Income")
        gp_by_rel  = _lookup("Gross Profit")

        revenue_pts        = []
        net_income_pts     = []
        gross_margin_pts   = []
        net_margin_pts     = []

        for rel in sorted_rels:
            rev_p = rev_by_rel.get(rel)
            ni_p  = ni_by_rel.get(rel)
            gp_p  = gp_by_rel.get(rel)

            period_end = (rev_p or ni_p or gp_p or {}).get("period_end", "")

            rev_val     = rev_p["value"] if rev_p else None
            rev_flagged = bool(rev_p and rev_p.get("flags"))
            ni_val      = ni_p["value"]  if ni_p  else None
            ni_flagged  = bool(ni_p  and ni_p.get("flags"))
            gp_val      = gp_p["value"]  if gp_p  else None
            gp_flagged  = bool(gp_p  and gp_p.get("flags"))

            revenue_pts.append({
                "period_label": rel, "period_end": period_end,
                "value": _scale(rev_val), "flagged": rev_flagged,
            })
            net_income_pts.append({
                "period_label": rel, "period_end": period_end,
                "value": _scale(ni_val), "flagged": ni_flagged,
            })

            if (rev_val is not None and rev_val != 0
                    and gp_val is not None
                    and not rev_flagged and not gp_flagged):
                gm_pct = round(100.0 * gp_val / rev_val, 2)
            else:
                gm_pct = None

            if (rev_val is not None and rev_val != 0
                    and ni_val is not None
                    and not rev_flagged and not ni_flagged):
                nm_pct = round(100.0 * ni_val / rev_val, 2)
            else:
                nm_pct = None

            gross_margin_pts.append({
                "period_label": rel, "period_end": period_end,
                "value": gm_pct, "flagged": False,
            })
            net_margin_pts.append({
                "period_label": rel, "period_end": period_end,
                "value": nm_pct, "flagged": False,
            })

        company_series.append({
            "name": company["name"],
            "cik":  company["cik"],
            "series": {
                "revenue":          revenue_pts,
                "net_income":       net_income_pts,
                "gross_margin_pct": gross_margin_pts,
                "net_margin_pct":   net_margin_pts,
            },
        })

    return {
        "periods":      sorted_rels,
        "dollar_scale": {"factor": dollar_factor, "label": dollar_label},
        "companies":    company_series,
    }


def _xbrl_write_csv(filepath, entity, columns, rows, period_type):
    import csv
    dollar_factor, dollar_label = _detect_dollar_scale(rows, columns)
    share_factor, share_label = _detect_share_scale(rows, columns)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["# {} -- XBRL Financial Data ({})".format(entity, period_type)])
        writer.writerow(["Line Item", "Source Tag"] + [c["label"] for c in columns] + ["Flags"])
        for row in rows:
            line_item = row["line_item"]
            if line_item in _DOLLAR_LINE_ITEMS:
                factor, suffix = dollar_factor, " ({})".format(dollar_label)
            elif line_item in _SHARE_LINE_ITEMS:
                factor, suffix = share_factor, " ({})".format(share_label)
            else:
                factor, suffix = 1, ""
            label = line_item + suffix
            cells_out = []
            all_row_flags = []
            for col in columns:
                cell = row["cells"].get(col["key"])
                if cell is None:
                    cells_out.append("Not reported")
                else:
                    val = cell.get("value")
                    if val is None:
                        cells_out.append("")
                    elif line_item in _EPS_LINE_ITEMS:
                        cells_out.append("{:.2f}".format(val))
                    else:
                        scaled = val / factor if factor != 1 else val
                        cells_out.append("{:,.0f}".format(scaled))
                    all_row_flags.extend(f["msg"] for f in cell.get("flags", []))
            flags_str = "; ".join(sorted(set(all_row_flags))) if all_row_flags else ""
            writer.writerow([label, row["tag_used"] or ""] + cells_out + [flags_str])


def _xbrl_add_chart_sheet(wb, entity, columns, rows, dollar_factor, dollar_label):
    """
    Add a 'Charts' sheet with two native openpyxl LineCharts.

    Chart 1: Revenue and Net Income (scaled, dollar_label on y-axis).
    Chart 2: Gross Margin % and Net Margin % (% on y-axis).

    Missing data → empty cell → Excel renders as a gap (never as zero).
    Per-point flagged styling is not available in openpyxl LineChart; a
    text note is written instead when flagged values are present.
    """
    try:
        from openpyxl.chart import LineChart, Reference
    except ImportError:
        return  # skip silently if openpyxl chart objects not available

    chart_data = _build_chart_data(entity, columns, rows, dollar_factor, dollar_label)
    s      = chart_data["series"]
    n_cols = len(columns)

    ws = wb.create_sheet("Charts")
    ws.sheet_properties.tabColor = "16A34A"

    # ------------------------------------------------------------------
    # Helper data table — column-oriented (each period is a column)
    # Row 1: period labels
    # Rows 2-5: series data; None written as empty cell (Excel gap)
    # ------------------------------------------------------------------
    ws.cell(1, 1, "Period")
    for ci, col in enumerate(columns, start=2):
        ws.cell(1, ci, col["label"])

    series_layout = [
        (2, "Revenue ({})".format(dollar_label),    s["revenue"]),
        (3, "Net Income ({})".format(dollar_label),  s["net_income"]),
        (4, "Gross Margin %",                        s["gross_margin_pct"]),
        (5, "Net Margin %",                          s["net_margin_pct"]),
    ]
    for row_idx, label, pts in series_layout:
        ws.cell(row_idx, 1, label)
        for ci, pt in enumerate(pts, start=2):
            if pt["value"] is not None:
                ws.cell(row_idx, ci, pt["value"])

    # Flag note
    has_flags = any(
        pt["flagged"]
        for key in ("revenue", "net_income")
        for pt in s[key]
    )
    note_row = 6
    if has_flags:
        ws.cell(note_row, 1,
            "Note: one or more plotted values are flagged for review — "
            "see 'Financial Data' sheet (yellow highlighted cells) for details."
        )
        note_row = 7

    # ------------------------------------------------------------------
    # Chart 1: Revenue & Net Income
    # ------------------------------------------------------------------
    c1 = LineChart()
    c1.title        = "{} — Revenue & Net Income".format(entity)
    c1.y_axis.title = dollar_label
    c1.x_axis.title = "Period"
    c1.style        = 10
    c1.width        = 22
    c1.height       = 14

    cats = Reference(ws, min_col=2, max_col=1 + n_cols, min_row=1, max_row=1)
    # Rows 2-3; col 1 = series title via titles_from_data=True
    data1 = Reference(ws, min_col=1, max_col=1 + n_cols, min_row=2, max_row=3)
    c1.add_data(data1, from_rows=True, titles_from_data=True)
    c1.set_categories(cats)

    ws.add_chart(c1, "A{}".format(note_row + 1))

    # ------------------------------------------------------------------
    # Chart 2: Gross Margin % and Net Margin %
    # ------------------------------------------------------------------
    c2 = LineChart()
    c2.title        = "{} — Gross Margin % and Net Margin %".format(entity)
    c2.y_axis.title = "%"
    c2.x_axis.title = "Period"
    c2.style        = 10
    c2.width        = 22
    c2.height       = 14

    data2 = Reference(ws, min_col=1, max_col=1 + n_cols, min_row=4, max_row=5)
    c2.add_data(data2, from_rows=True, titles_from_data=True)
    c2.set_categories(cats)

    ws.add_chart(c2, "A{}".format(note_row + 26))


def _peer_add_chart_sheet(wb, comparison_result):
    """
    Add a 'Charts' sheet with four native openpyxl LineCharts.

    Chart 1: Revenue per company.
    Chart 2: Net Income per company.
    Chart 3: Gross Margin % per company.
    Chart 4: Net Margin % per company.
    X-axis uses relative period labels in chronological order (oldest → newest).
    Missing / derived-unavailable data → empty cell → Excel gap per company.
    """
    try:
        from openpyxl.chart import LineChart, Reference
    except ImportError:
        return

    # Use _build_peer_chart_data so margins are computed consistently
    chart_data    = _build_peer_chart_data(comparison_result)
    companies_cd  = chart_data["companies"]   # [{name, cik, series: {revenue, net_income, …}}]
    sorted_rels   = chart_data["periods"]     # chronological: FY-(n-1) … FY0
    dollar_label  = chart_data["dollar_scale"]["label"]
    n_companies   = len(companies_cd)
    n_periods     = len(sorted_rels)

    ws = wb.create_sheet("Charts")
    ws.sheet_properties.tabColor = "16A34A"

    def _write_block(start_row, metric_label, series_key):
        """Write one metric block; returns the row immediately after."""
        ws.cell(start_row, 1, metric_label)
        for ci, rel in enumerate(sorted_rels, start=2):
            ws.cell(start_row, ci, rel)
        for ri, co in enumerate(companies_cd, start=1):
            ws.cell(start_row + ri, 1, co["name"])
            for ci, pt in enumerate(co["series"][series_key], start=2):
                if pt["value"] is not None:
                    ws.cell(start_row + ri, ci, pt["value"])
        return start_row + n_companies + 1

    metrics = [
        ("Revenue ({})".format(dollar_label),    "revenue",          dollar_label),
        ("Net Income ({})".format(dollar_label),  "net_income",       dollar_label),
        ("Gross Margin %",                        "gross_margin_pct", "%"),
        ("Net Margin %",                          "net_margin_pct",   "%"),
    ]

    starts = []
    cur_row = 1
    for label, key, _ in metrics:
        starts.append(cur_row)
        cur_row = _write_block(cur_row, label, key)
        cur_row += 1   # blank row between blocks

    note_row = cur_row
    ws.cell(note_row, 1,
        "Note: flagged values appear highlighted on the Comparison sheet. "
        "Per-point chart markers are not supported in native Excel LineCharts."
    )
    chart_start = note_row + 2

    names_short = " vs ".join(co["name"] for co in companies_cd[:3])
    if n_companies > 3:
        names_short += " & {} more".format(n_companies - 3)

    for idx, ((label, key, y_label), start) in enumerate(zip(metrics, starts)):
        c = LineChart()
        c.title        = "{} — {}".format(label, names_short)
        c.y_axis.title = y_label
        c.x_axis.title = "Period (oldest → newest)"
        c.style        = 10
        c.width        = 22
        c.height       = 14

        cats = Reference(ws, min_col=2, max_col=1 + n_periods,
                         min_row=start, max_row=start)
        data = Reference(ws, min_col=1, max_col=1 + n_periods,
                         min_row=start + 1, max_row=start + n_companies)
        c.add_data(data, from_rows=True, titles_from_data=True)
        c.set_categories(cats)
        ws.add_chart(c, "A{}".format(chart_start + idx * 26))


def _xbrl_write_xlsx(filepath, entity, columns, rows, period_type):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError("openpyxl is required: pip install openpyxl")

    dollar_factor, dollar_label = _detect_dollar_scale(rows, columns)
    share_factor, share_label = _detect_share_scale(rows, columns)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Financial Data"
    ws.sheet_properties.tabColor = "003366"

    BF = "Calibri"
    hdr_fill = PatternFill("solid", fgColor="003366")
    hdr_font = Font(name=BF, color="FFFFFF", bold=True, size=11)
    flag_fill = PatternFill("solid", fgColor="FFF3CD")
    tag_font = Font(name=BF, color="888888", size=10)
    flag_text_font = Font(name=BF, color="856404", size=11)
    base_font = Font(name=BF, size=11)
    missing_font = Font(name=BF, color="AAAAAA", italic=True, size=11)
    extracted_font = Font(name=BF, color="0066CC", size=11)   # blue: direct XBRL values
    calc_font = Font(name=BF, size=11)                          # black: computed/derived values
    flag_data_font = Font(name=BF, color="CC0000", size=11)    # red: flagged data cells
    _border_thin   = Border(bottom=Side(style="thin"))
    _border_double = Border(bottom=Side(style="double"))

    # Row 1: title
    tc = ws.cell(1, 1, "{} -- XBRL Financial Data ({})".format(entity, period_type.title()))
    tc.font = Font(name=BF, bold=True, size=12)

    hrow = 3
    col_widths = {}

    # Header row
    for ci, (text, min_w) in enumerate([("Line Item", 28), ("Source Tag", 15)], start=1):
        c = ws.cell(hrow, ci, text)
        c.font = hdr_font
        c.fill = hdr_fill
        col_widths[ci] = max(min_w, len(text))

    for ci, col in enumerate(columns, start=3):
        c = ws.cell(hrow, ci, col["label"])
        c.font = hdr_font
        c.fill = hdr_fill
        c.alignment = Alignment(horizontal="right")
        col_widths[ci] = len(col["label"])

    flags_col = len(columns) + 3
    c = ws.cell(hrow, flags_col, "Flags")
    c.font = hdr_font
    c.fill = hdr_fill
    col_widths[flags_col] = 12

    # Data rows
    for ri, row in enumerate(rows, start=hrow + 1):
        line_item = row["line_item"]
        is_dollar = line_item in _DOLLAR_LINE_ITEMS
        is_eps = line_item in _EPS_LINE_ITEMS
        is_shares = line_item in _SHARE_LINE_ITEMS

        if is_dollar:
            factor, suffix, num_fmt = dollar_factor, " ({})".format(dollar_label), _XLSX_FMT_DOLLAR
        elif is_shares:
            factor, suffix, num_fmt = share_factor, " ({})".format(share_label), _XLSX_FMT_SHARES
        elif is_eps:
            factor, suffix, num_fmt = 1, "", _XLSX_FMT_EPS
        else:
            factor, suffix, num_fmt = 1, "", _XLSX_FMT_DOLLAR

        is_extracted = is_dollar or is_eps or is_shares
        value_font = extracted_font if is_extracted else calc_font

        label = line_item + suffix
        c = ws.cell(ri, 1, label)
        c.font = base_font
        col_widths[1] = min(42, max(col_widths.get(1, 0), len(label)))

        tag_val = row["tag_used"] or ""
        c = ws.cell(ri, 2, tag_val)
        c.font = tag_font
        col_widths[2] = min(52, max(col_widths.get(2, 0), len(tag_val)))

        all_row_flags = []

        for ci, col in enumerate(columns, start=3):
            cell = row["cells"].get(col["key"])
            c = ws.cell(ri, ci)
            if cell is None:
                c.value = "Not reported"
                c.font = missing_font
                c.alignment = Alignment(horizontal="right")
            else:
                raw_val = cell.get("value")
                if raw_val is not None:
                    scaled = raw_val / factor if factor != 1 else raw_val
                    # Write as int when the scaled value has no fractional part (except EPS)
                    if is_eps:
                        c.value = float(scaled)
                    elif isinstance(scaled, float) and scaled == int(scaled):
                        c.value = int(scaled)
                    else:
                        c.value = float(scaled)
                    c.number_format = num_fmt
                    abs_s = abs(scaled)
                    dstr = "{:,.2f}".format(abs_s) if is_eps else "{:,.0f}".format(abs_s)
                    col_widths[ci] = max(col_widths.get(ci, 0), len(dstr) + 3)
                    if cell.get("flags"):
                        c.fill = flag_fill
                        c.font = flag_data_font
                        all_row_flags.extend(f["msg"] for f in cell["flags"])
                    else:
                        c.font = value_font
                else:
                    c.value = "Not reported"
                    c.font = missing_font
                c.alignment = Alignment(horizontal="right")

        # Bottom border: single under subtotals, double under final total
        if line_item in _SINGLE_BORDER_ROW_ITEMS:
            _rb = _border_thin
        elif line_item in _DOUBLE_BORDER_ROW_ITEMS:
            _rb = _border_double
        else:
            _rb = None
        if _rb:
            for _bc in range(1, flags_col + 1):
                ws.cell(ri, _bc).border = _rb

        flags_str = "; ".join(sorted(set(all_row_flags))) if all_row_flags else ""
        if flags_str:
            c2 = ws.cell(ri, flags_col, flags_str)
            c2.font = flag_text_font
            col_widths[flags_col] = max(col_widths.get(flags_col, 0), min(len(flags_str), 60))

    # Apply auto-fit column widths
    for ci, w in col_widths.items():
        ws.column_dimensions[get_column_letter(ci)].width = w + 2

    # Freeze title + header rows AND left label column so scrolling works in both axes
    ws.freeze_panes = "B4"

    # Sanity-check rows (one blank separator row, then BS and GP reconciliation)
    _row_map = {row["line_item"]: (hrow + 1 + ri) for ri, row in enumerate(rows)}
    _data_col_idxs = list(range(3, 3 + len(columns)))
    _write_xlsx_sanity_checks(
        ws, hrow + len(rows) + 2, _row_map, _data_col_idxs, dollar_label, BF
    )

    _xbrl_add_chart_sheet(wb, entity, columns, rows, dollar_factor, dollar_label)
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


@app.route("/api/xbrl/chart-data", methods=["POST"])
def api_xbrl_chart_data():
    """Return chart-ready series for Revenue, Net Income, Gross Margin %,
    and Net Margin % using the same extraction logic as /api/xbrl/extract."""
    data = request.get_json(silent=True) or {}
    cik = str(data.get("cik", "")).strip()
    if not cik:
        return jsonify({"error": "cik is required"}), 400
    try:
        start_year = int(data.get("start_year", 2015))
        end_year   = int(data.get("end_year", datetime.date.today().year))
    except (ValueError, TypeError):
        return jsonify({"error": "start_year and end_year must be integers"}), 400
    period_type = data.get("period_type", "annual")
    if period_type not in ("annual", "quarterly"):
        return jsonify({"error": "period_type must be 'annual' or 'quarterly'"}), 400
    try:
        entity, columns, rows = _build_xbrl_result(cik, start_year, end_year, period_type)
        dollar_factor, dollar_label = _detect_dollar_scale(rows, columns)
        return jsonify(_build_chart_data(entity, columns, rows, dollar_factor, dollar_label))
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
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H%M")
        filename = "{}_XBRL_{}_{}_{}{}".format(
            safe.replace(" ", "_") or cik,
            period_type.title(),
            date_str,
            time_str,
            "." + fmt,
        )
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


# ---------------------------------------------------------------------------
# Peer comparison -- Stage 3 (stream) and Stage 4 (export)
# ---------------------------------------------------------------------------

def _peer_write_xlsx(filepath, comparison_result):
    """Write a peer comparison result to an Excel workbook with two sheets:
      'Comparison' -- the scaled table, flagged cells highlighted, N/A for missing.
      'Source Tags' -- which XBRL tag was used for each company / line item.
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError("openpyxl is required: pip install openpyxl")

    companies  = comparison_result["companies"]
    line_items = comparison_result["line_items"]
    n_periods  = comparison_result["n_periods"]
    scale      = comparison_result.get("scale", pc.select_peer_scale(comparison_result))

    dollar_factor = scale["dollar_factor"]
    dollar_label  = scale["dollar_label"]
    share_factor  = scale["share_factor"]
    share_label   = scale["share_label"]

    # ---- constants ----
    BF         = "Calibri"
    HDR_FILL   = PatternFill("solid", fgColor="003366")
    GRP_FILL   = PatternFill("solid", fgColor="1A5276")   # slightly lighter for company rows
    HDR_FONT   = Font(name=BF, color="FFFFFF", bold=True, size=11)
    GRP_FONT   = Font(name=BF, color="FFFFFF", bold=True, size=11)
    BASE_FONT  = Font(name=BF, size=11)
    MISS_FONT  = Font(name=BF, color="AAAAAA", italic=True, size=11)
    TAG_FONT   = Font(name=BF, color="888888", size=10)
    FLAG_FILL  = PatternFill("solid", fgColor="FFF3CD")
    FLAG_FONT  = Font(name=BF, color="856404", size=11)   # kept for flag-details text
    FLAG_DATA_FONT = Font(name=BF, color="CC0000", size=11)  # red font on flagged data cells
    EXTRACTED_FONT = Font(name=BF, color="0066CC", size=11)  # blue: XBRL-sourced values
    FLAG_BORDER = Border(
        left=Side(style="medium", color="DC3545"),
    )
    _border_thin   = Border(bottom=Side(style="thin"))
    _border_double = Border(bottom=Side(style="double"))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Comparison"
    ws.sheet_properties.tabColor = "003366"

    # ---- Row 1: title ----
    company_names = " vs ".join(c["name"] for c in companies)
    title = "Peer Comparison: {}  |  Scale: {} / {}".format(
        company_names, dollar_label, share_label + " shares"
    )
    tc = ws.cell(1, 1, title)
    tc.font = Font(name=BF, bold=True, size=12)

    # ---- Column layout ----
    # Col 1: Line Item label
    # Then for each company: n_periods columns
    first_val_col = 2   # first data column

    def _col(company_idx, period_idx):
        return first_val_col + company_idx * n_periods + period_idx

    # ---- Row 2: company group headers ----
    c = ws.cell(2, 1, "Line Item")
    c.font = HDR_FONT
    c.fill = HDR_FILL
    c.alignment = Alignment(vertical="center")

    for ci, company in enumerate(companies):
        col_start = _col(ci, 0)
        col_end   = _col(ci, n_periods - 1)
        ws.cell(2, col_start, company["name"]).fill = GRP_FILL
        ws.cell(2, col_start).font  = GRP_FONT
        ws.cell(2, col_start).alignment = Alignment(horizontal="center", vertical="center")
        if n_periods > 1:
            ws.merge_cells(
                start_row=2, start_column=col_start,
                end_row=2,   end_column=col_end,
            )

    # ---- Row 3: period label headers ----
    ws.cell(3, 1)  # empty corner
    ws.cell(3, 1).fill = HDR_FILL

    for ci, company in enumerate(companies):
        company_data = company["line_items"].get(line_items[0]) if line_items else None
        for pi in range(n_periods):
            col = _col(ci, pi)
            rel_label = "FY0" if pi == 0 else "FY-{}".format(pi)
            c = ws.cell(3, col, rel_label)
            c.font = HDR_FONT
            c.fill = HDR_FILL
            c.alignment = Alignment(horizontal="right")

    ws.freeze_panes = "B4"

    col_widths = {1: 28}

    # ---- Row 4+: data ----
    for ri, li in enumerate(line_items, start=4):
        is_dollar = li in pc.DOLLAR_LINE_ITEMS
        is_eps    = li in pc.EPS_LINE_ITEMS
        is_shares = li in pc.SHARE_LINE_ITEMS

        if is_dollar:
            factor, suffix, num_fmt = dollar_factor, " ({})".format(dollar_label), _XLSX_FMT_DOLLAR
        elif is_shares:
            factor, suffix, num_fmt = share_factor, " ({})".format(share_label), _XLSX_FMT_SHARES
        elif is_eps:
            factor, suffix, num_fmt = 1, "", _XLSX_FMT_EPS
        else:
            factor, suffix, num_fmt = 1, "", _XLSX_FMT_DOLLAR

        label = li + suffix
        lc = ws.cell(ri, 1, label)
        lc.font = BASE_FONT
        col_widths[1] = min(42, max(col_widths.get(1, 0), len(label)))

        total_data_cols = first_val_col + len(companies) * n_periods - 1

        for ci, company in enumerate(companies):
            item_info = company["line_items"].get(li) or {}
            periods   = item_info.get("periods", [])

            for pi in range(n_periods):
                col = _col(ci, pi)
                c   = ws.cell(ri, col)
                period = periods[pi] if pi < len(periods) else None
                value  = period["value"] if period else None

                if value is None:
                    c.value = "N/A"
                    c.font  = MISS_FONT
                    c.alignment = Alignment(horizontal="right")
                else:
                    scaled = value / factor if factor != 1 else value
                    if is_eps:
                        c.value = float(scaled)
                    elif isinstance(scaled, float) and scaled == int(scaled):
                        c.value = int(scaled)
                    else:
                        c.value = float(scaled)
                    c.number_format = num_fmt
                    c.alignment = Alignment(horizontal="right")
                    abs_s = abs(scaled)
                    dstr = "{:,.2f}".format(abs_s) if is_eps else "{:,.0f}".format(abs_s)
                    col_widths[col] = max(col_widths.get(col, len(rel_label) + 2), len(dstr) + 3)

                    if period and period.get("flags"):
                        c.fill   = FLAG_FILL
                        c.border = FLAG_BORDER
                        c.font   = FLAG_DATA_FONT
                        c.number_format = num_fmt
                    else:
                        c.font = EXTRACTED_FONT

        # Bottom border: single under subtotals, double under Net Income
        if li in _SINGLE_BORDER_ROW_ITEMS:
            _rb = _border_thin
        elif li in _DOUBLE_BORDER_ROW_ITEMS:
            _rb = _border_double
        else:
            _rb = None
        if _rb:
            for _bc in range(1, total_data_cols + 1):
                ws.cell(ri, _bc).border = _rb

    # Auto-fit
    for col_idx, w in col_widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = w + 2

    # Ensure every value column has at least a minimum width
    total_cols = first_val_col + len(companies) * n_periods - 1
    for col_idx in range(first_val_col, total_cols + 1):
        if col_idx not in col_widths:
            ws.column_dimensions[get_column_letter(col_idx)].width = 10

    # Sanity-check rows (one blank separator row, then BS and GP reconciliation)
    _row_map = {li: (4 + idx) for idx, li in enumerate(line_items)}
    _data_col_idxs = [_col(ci, pi)
                      for ci in range(len(companies))
                      for pi in range(n_periods)]
    next_row = _write_xlsx_sanity_checks(
        ws, 4 + len(line_items) + 2, _row_map, _data_col_idxs, dollar_label, BF
    )

    # Validation-flag legend (after sanity checks)
    ws.cell(next_row, 1,
            "Yellow cells with red left border have validation flags. "
            "Explanations listed below (if any). See Source Tags sheet for XBRL tag details."
    ).font = Font(name=BF, color="666666", italic=True, size=10)

    # ---- Flag Details section ----
    flag_entries = []
    for company in companies:
        for li in line_items:
            item_info = company["line_items"].get(li) or {}
            for period in item_info.get("periods", []):
                for f in period.get("flags", []):
                    msg = f.get("message") or f.get("msg") or ""
                    if msg:
                        flag_entries.append({
                            "company": company["name"],
                            "period":  period.get("relative_period", ""),
                            "li":      li,
                            "msg":     msg,
                        })

    if flag_entries:
        fd_start = next_row + 2
        sh = ws.cell(fd_start, 1, "Flag Details")
        sh.font = Font(name=BF, bold=True, size=11, color="856404")
        fd_hdr = fd_start + 1
        for col, lbl in enumerate(["Company", "Period", "Line Item", "Flag Message"], start=1):
            hc = ws.cell(fd_hdr, col, lbl)
            hc.font = HDR_FONT
            hc.fill = HDR_FILL
        fd_row = fd_hdr + 1
        max_msg_len = 0
        for fe in flag_entries:
            ws.cell(fd_row, 1, fe["company"]).font = BASE_FONT
            ws.cell(fd_row, 2, fe["period"]).font  = BASE_FONT
            ws.cell(fd_row, 3, fe["li"]).font      = BASE_FONT
            mc = ws.cell(fd_row, 4, fe["msg"])
            mc.font = Font(name=BF, color="856404", size=11)
            max_msg_len = max(max_msg_len, len(fe["msg"]))
            fd_row += 1
        ws.column_dimensions["D"].width = min(80, max_msg_len + 4)

    # ---- Sheet 2: Source Tags ----
    ws2 = wb.create_sheet("Source Tags")
    ws2.sheet_properties.tabColor = "888888"
    ws2.cell(1, 1, "Company").font  = HDR_FONT
    ws2.cell(1, 1).fill             = HDR_FILL
    ws2.cell(1, 2, "Line Item").font = HDR_FONT
    ws2.cell(1, 2).fill              = HDR_FILL
    ws2.cell(1, 3, "XBRL Tag Used").font = HDR_FONT
    ws2.cell(1, 3).fill                   = HDR_FILL

    tag_row = 2
    for company in companies:
        for li in line_items:
            item_info = company["line_items"].get(li) or {}
            tag_used  = item_info.get("tag_used")
            ws2.cell(tag_row, 1, company["name"]).font = BASE_FONT
            ws2.cell(tag_row, 2, li).font              = BASE_FONT
            ws2.cell(tag_row, 3, tag_used or "— not found").font = (
                BASE_FONT if tag_used else MISS_FONT
            )
            tag_row += 1

    ws2.column_dimensions["A"].width = 30
    ws2.column_dimensions["B"].width = 28
    ws2.column_dimensions["C"].width = 60

    _peer_add_chart_sheet(wb, comparison_result)
    wb.save(filepath)


@app.route("/api/xbrl/peer-comparison/stream")
def api_peer_comparison_stream():
    """SSE endpoint: fetches one company at a time, yielding progress events,
    then a final 'result' event containing the full comparison data + scale.

    Query params:
        cik (repeated)           -- CIKs to include
        n_periods                -- fiscal years per company (default 3)
        line_items (repeated)    -- which line items (default: all TAG_MAP keys)
    """
    ciks = request.args.getlist("cik")
    if not ciks:
        def _err():
            yield 'data: ' + json.dumps({"type": "error", "message": "cik parameter required"}) + '\n\n'
        return Response(stream_with_context(_err()), mimetype="text/event-stream")

    try:
        n_periods = max(1, min(10, int(request.args.get("n_periods", "3"))))
    except (ValueError, TypeError):
        n_periods = 3

    req_items = request.args.getlist("line_items")
    line_items = req_items if req_items else list(xbrl.TAG_MAP.keys())

    def generate():
        companies = []
        total = len(ciks)
        for i, cik in enumerate(ciks):
            yield 'data: ' + json.dumps({
                "type": "progress", "current": i, "total": total, "cik": cik,
            }) + '\n\n'
            try:
                company_data = pc.fetch_peer_data(str(cik), line_items, n_periods)
                companies.append(company_data)
            except Exception as exc:
                yield 'data: ' + json.dumps({
                    "type": "company_error", "cik": cik, "message": str(exc),
                }) + '\n\n'

        result = {"companies": companies, "line_items": line_items, "n_periods": n_periods}
        result["scale"] = pc.select_peer_scale(result)
        yield 'data: ' + json.dumps({"type": "result", "data": result}) + '\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/xbrl/peer-comparison/chart-data", methods=["POST"])
def api_peer_chart_data():
    """Transform an already-fetched comparison_result into chart-ready series.

    Accepts the same comparison_result JSON the SSE stream emits so the
    frontend can call this immediately after the stream completes without
    triggering additional EDGAR requests.
    """
    data = request.get_json(silent=True) or {}
    comparison_result = data.get("comparison_result")
    if not comparison_result or not comparison_result.get("companies"):
        return jsonify({"error": "comparison_result with companies is required"}), 400
    try:
        return jsonify(_build_peer_chart_data(comparison_result))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/xbrl/peer-comparison/export", methods=["POST"])
def api_peer_comparison_export():
    """Write a peer comparison result to an Excel file and return a download URL."""
    data = request.get_json(silent=True) or {}
    comparison_result = data.get("comparison_result")
    if not comparison_result or not comparison_result.get("companies"):
        return jsonify({"error": "comparison_result with companies is required"}), 400

    try:
        company_names = [c.get("name", "Unknown") for c in comparison_result["companies"]]
        safe_names = "_vs_".join(
            "".join(ch if ch.isalnum() or ch in " -_" else "" for ch in n)[:20].strip().replace(" ", "_")
            for n in company_names
        )
        if not safe_names:
            safe_names = "Peer_Comparison"
        folder = os.path.join(EXPORTS_DIR, "Peer_Comparisons")
        os.makedirs(folder, exist_ok=True)
        now      = datetime.datetime.now()
        filename = "Peer_{}_{}_{}.xlsx".format(
            safe_names, now.strftime("%Y-%m-%d"), now.strftime("%H%M")
        )
        filepath = os.path.join(folder, filename)
        _peer_write_xlsx(filepath, comparison_result)
        rel_path = os.path.relpath(filepath, EXPORTS_DIR).replace("\\", "/")
        return jsonify({
            "status": "ok",
            "filename": filename,
            "folder": folder,
            "download_url": "/exports/" + rel_path,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


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
