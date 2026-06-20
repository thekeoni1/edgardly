"""test_xbrl_export.py -- automated tests for XBRL Excel export formatting.

Tests cover scale detection, label suffixes, value scaling, number formats,
cell types (must be numeric, not strings), flag highlighting, and freeze panes.
No real EDGAR API calls are made here -- all data is constructed.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import (
    _detect_dollar_scale,
    _detect_share_scale,
    _xbrl_write_xlsx,
    _xbrl_write_csv,
    _DOLLAR_LINE_ITEMS,
    _EPS_LINE_ITEMS,
    _SHARE_LINE_ITEMS,
    _XLSX_FMT_DOLLAR,
    _XLSX_FMT_EPS,
    _XLSX_FMT_SHARES,
)

openpyxl = pytest.importorskip("openpyxl")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cell(value, flags=None):
    return {
        "value": value,
        "formatted": str(value) if value is not None else None,
        "unit": "USD",
        "start": "2023-01-01",
        "end": "2023-12-31",
        "fp": "FY",
        "tag": "TestTag",
        "filed": "2024-01-01",
        "flags": flags or [],
    }


def _make_rows(revenue=None, net_income=None, eps=None, shares=None, equity=None):
    """Build a minimal rows list with the given values for key line items."""
    rows = []
    for line_item in [
        "Revenue", "Cost of Revenue", "Gross Profit", "Operating Income", "Net Income",
        "EPS Basic", "EPS Diluted",
        "Shares Outstanding (Basic)", "Shares Outstanding (Diluted)",
        "Total Assets", "Total Liabilities", "Total Equity",
        "Cash and Equivalents", "Total Debt",
    ]:
        val = None
        if line_item == "Revenue":
            val = revenue
        elif line_item == "Net Income":
            val = net_income
        elif line_item in ("EPS Basic", "EPS Diluted"):
            val = eps
        elif line_item in ("Shares Outstanding (Basic)", "Shares Outstanding (Diluted)"):
            val = shares
        elif line_item == "Total Equity":
            val = equity

        cells = {"2023-12-31": _make_cell(val)} if val is not None else {}
        rows.append({
            "line_item": line_item,
            "tag_used": "Us-gaap/TestTag",
            "cells": cells,
        })
    return rows


def _make_columns():
    return [{"key": "2023-12-31", "label": "FY2023", "fp": "FY", "fy": 2023}]


def _write_xlsx(rows, columns=None, tmp_path=None):
    if columns is None:
        columns = _make_columns()
    if tmp_path is None:
        tmp_path = tempfile.mkdtemp()
    filepath = os.path.join(tmp_path, "test_xbrl.xlsx")
    _xbrl_write_xlsx(filepath, "Test Corp", columns, rows, "annual")
    return openpyxl.load_workbook(filepath)


def _get_data_cell(ws, line_item_label, col_idx=3, hrow=3):
    """Find the row for a line item label and return the data cell at col_idx."""
    for row in ws.iter_rows(min_row=hrow + 1):
        if row[0].value == line_item_label:
            return row[col_idx - 1]
    return None


# ---------------------------------------------------------------------------
# 1. Scale detection -- dollar
# ---------------------------------------------------------------------------

def test_detect_dollar_scale_millions():
    rows = _make_rows(revenue=391_035_000_000)
    columns = _make_columns()
    factor, label = _detect_dollar_scale(rows, columns)
    assert factor == 1_000_000
    assert label == "$mm"


def test_detect_dollar_scale_thousands():
    rows = _make_rows(revenue=500_000_000)
    columns = _make_columns()
    factor, label = _detect_dollar_scale(rows, columns)
    assert factor == 1_000
    assert label == "$000s"


def test_detect_dollar_scale_actual():
    rows = _make_rows(revenue=5_000_000)
    columns = _make_columns()
    factor, label = _detect_dollar_scale(rows, columns)
    assert factor == 1
    assert label == "$"


def test_detect_dollar_scale_no_revenue():
    rows = _make_rows()  # no revenue
    columns = _make_columns()
    factor, label = _detect_dollar_scale(rows, columns)
    assert factor == 1
    assert label == "$"


def test_detect_dollar_scale_exactly_1b_is_thousands():
    # Boundary: exactly $1B is NOT > 1B, so should be thousands not millions
    rows = _make_rows(revenue=1_000_000_000)
    columns = _make_columns()
    factor, label = _detect_dollar_scale(rows, columns)
    assert factor == 1_000
    assert label == "$000s"


def test_detect_dollar_scale_just_above_1b_is_millions():
    rows = _make_rows(revenue=1_000_000_001)
    columns = _make_columns()
    factor, label = _detect_dollar_scale(rows, columns)
    assert factor == 1_000_000
    assert label == "$mm"


# ---------------------------------------------------------------------------
# 2. Scale detection -- shares
# ---------------------------------------------------------------------------

def test_detect_share_scale_millions():
    rows = _make_rows(shares=15_550_000_000)
    columns = _make_columns()
    factor, label = _detect_share_scale(rows, columns)
    assert factor == 1_000_000
    assert label == "mm"


def test_detect_share_scale_thousands():
    rows = _make_rows(shares=500_000_000)
    columns = _make_columns()
    factor, label = _detect_share_scale(rows, columns)
    assert factor == 1_000
    assert label == "000s"


def test_detect_share_scale_no_shares():
    rows = _make_rows()
    columns = _make_columns()
    factor, label = _detect_share_scale(rows, columns)
    assert factor == 1_000  # default
    assert label == "000s"


# ---------------------------------------------------------------------------
# 3. Line item label suffixes in xlsx
# ---------------------------------------------------------------------------

def test_xlsx_dollar_label_millions():
    rows = _make_rows(revenue=2_000_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    labels = [row[0].value for row in ws.iter_rows(min_row=4)]
    assert "Revenue ($mm)" in labels
    assert "Net Income ($mm)" in labels
    assert "Total Assets ($mm)" in labels


def test_xlsx_dollar_label_thousands():
    rows = _make_rows(revenue=200_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    labels = [row[0].value for row in ws.iter_rows(min_row=4)]
    assert "Revenue ($000s)" in labels
    assert "Net Income ($000s)" in labels


def test_xlsx_dollar_label_actual():
    rows = _make_rows(revenue=1_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    labels = [row[0].value for row in ws.iter_rows(min_row=4)]
    assert "Revenue ($)" in labels


def test_xlsx_share_label_suffix():
    rows = _make_rows(revenue=2_000_000_000, shares=15_000_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    labels = [row[0].value for row in ws.iter_rows(min_row=4)]
    assert "Shares Outstanding (Diluted) (mm)" in labels
    assert "Shares Outstanding (Basic) (mm)" in labels


def test_xlsx_eps_has_no_scale_suffix():
    rows = _make_rows(revenue=2_000_000_000, eps=3.88)
    wb = _write_xlsx(rows)
    ws = wb.active
    labels = [row[0].value for row in ws.iter_rows(min_row=4)]
    # EPS should NOT have a scale suffix
    assert "EPS Diluted" in labels
    assert "EPS Basic" in labels
    assert not any("EPS Diluted (" in (l or "") for l in labels)


# ---------------------------------------------------------------------------
# 4. Value scaling
# ---------------------------------------------------------------------------

def test_xlsx_revenue_scaled_to_millions():
    rows = _make_rows(revenue=391_035_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Revenue ($mm)")
    assert cell is not None
    assert cell.value == 391_035  # 391,035,000,000 / 1,000,000


def test_xlsx_revenue_scaled_to_thousands():
    rows = _make_rows(revenue=500_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Revenue ($000s)")
    assert cell is not None
    assert cell.value == 500_000  # 500,000,000 / 1,000


def test_xlsx_revenue_unscaled():
    rows = _make_rows(revenue=5_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Revenue ($)")
    assert cell is not None
    assert cell.value == 5_000_000


def test_xlsx_eps_not_scaled():
    rows = _make_rows(revenue=2_000_000_000, eps=6.43)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "EPS Diluted")
    assert cell is not None
    assert abs(cell.value - 6.43) < 0.0001


def test_xlsx_shares_scaled():
    rows = _make_rows(revenue=2_000_000_000, shares=15_550_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Shares Outstanding (Diluted) (mm)")
    assert cell is not None
    assert cell.value == 15_550  # 15,550,000,000 / 1,000,000


def test_xlsx_negative_value_scaled():
    rows = _make_rows(revenue=500_000_000, net_income=-50_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Net Income ($000s)")
    assert cell is not None
    assert cell.value == -50_000  # -50,000,000 / 1,000


# ---------------------------------------------------------------------------
# 5. Cell types must be numeric (not strings)
# ---------------------------------------------------------------------------

def test_xlsx_values_are_numeric_not_strings():
    rows = _make_rows(revenue=391_035_000_000, net_income=97_000_000_000, eps=6.43,
                      shares=15_550_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    for row in ws.iter_rows(min_row=4):
        label = row[0].value
        if not label:
            continue
        for cell in row[2:]:
            if cell.value in (None, "Not reported"):
                continue
            assert isinstance(cell.value, (int, float)), (
                f"Cell at {cell.coordinate} for '{label}' has value {cell.value!r} "
                f"(type {type(cell.value).__name__}), expected int or float"
            )


# ---------------------------------------------------------------------------
# 6. Number format strings are applied
# ---------------------------------------------------------------------------

def test_xlsx_dollar_format_applied():
    rows = _make_rows(revenue=391_035_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Revenue ($mm)")
    assert cell is not None and cell.number_format == _XLSX_FMT_DOLLAR


def test_xlsx_eps_format_applied():
    rows = _make_rows(revenue=2_000_000_000, eps=6.43)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "EPS Diluted")
    assert cell is not None and cell.number_format == _XLSX_FMT_EPS


def test_xlsx_shares_format_applied():
    rows = _make_rows(revenue=2_000_000_000, shares=15_000_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Shares Outstanding (Diluted) (mm)")
    assert cell is not None and cell.number_format == _XLSX_FMT_SHARES


# ---------------------------------------------------------------------------
# 7. Flag highlighting
# ---------------------------------------------------------------------------

def test_xlsx_flagged_cell_has_yellow_fill():
    FLAG_COLOR = "FFF3CD"
    rows = _make_rows(revenue=2_000_000_000, net_income=10_000_000_000)
    # Manually inject a flag on net income
    for row in rows:
        if row["line_item"] == "Net Income":
            row["cells"]["2023-12-31"]["flags"] = [
                {"type": "NET_INCOME_EXCEEDS_REVENUE", "msg": "test flag"}
            ]
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Net Income ($mm)")
    assert cell is not None
    assert cell.fill.fgColor.rgb.endswith(FLAG_COLOR), "Flagged cell should have yellow fill"


def test_xlsx_flagged_cell_still_has_number_format():
    rows = _make_rows(revenue=2_000_000_000, net_income=10_000_000_000)
    for row in rows:
        if row["line_item"] == "Net Income":
            row["cells"]["2023-12-31"]["flags"] = [
                {"type": "NET_INCOME_EXCEEDS_REVENUE", "msg": "test flag"}
            ]
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Net Income ($mm)")
    assert cell is not None
    assert cell.number_format == _XLSX_FMT_DOLLAR, "Flag should not override number format"


def test_xlsx_unflagged_cell_has_no_fill():
    rows = _make_rows(revenue=2_000_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    cell = _get_data_cell(ws, "Revenue ($mm)")
    assert cell is not None
    # No fill means fill type is None or "none"
    assert cell.fill.fill_type in (None, "none")


# ---------------------------------------------------------------------------
# 8. Spreadsheet structure
# ---------------------------------------------------------------------------

def test_xlsx_header_row_is_bold():
    rows = _make_rows(revenue=2_000_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    hrow = 3
    for cell in ws[hrow]:
        if cell.value:
            assert cell.font.bold, f"Header cell {cell.coordinate} should be bold"


def test_xlsx_freeze_panes_set():
    rows = _make_rows(revenue=2_000_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    assert ws.freeze_panes == "A4", "Should freeze rows 1-3 (title + blank + header)"


def test_xlsx_numeric_columns_right_aligned():
    rows = _make_rows(revenue=2_000_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    for row in ws.iter_rows(min_row=4):
        for cell in row[2:]:  # columns C onwards are data
            if isinstance(cell.value, (int, float)):
                assert cell.alignment.horizontal == "right", (
                    f"Cell {cell.coordinate} ({cell.value}) should be right-aligned"
                )


def test_xlsx_column_widths_set_for_all_columns():
    rows = _make_rows(revenue=2_000_000_000)
    columns = _make_columns()
    with tempfile.TemporaryDirectory() as tmp:
        filepath = os.path.join(tmp, "test.xlsx")
        _xbrl_write_xlsx(filepath, "Test Corp", columns, rows, "annual")
        wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    # Columns 1, 2, 3 (A, B, C) + flags column must all have a width set
    for letter in ("A", "B", "C"):
        assert ws.column_dimensions[letter].width > 0, f"Column {letter} has no width set"


def test_xlsx_font_is_calibri():
    rows = _make_rows(revenue=2_000_000_000)
    wb = _write_xlsx(rows)
    ws = wb.active
    # Title cell and header cells should use Calibri
    assert ws.cell(1, 1).font.name == "Calibri"
    assert ws.cell(3, 1).font.name == "Calibri"


# ---------------------------------------------------------------------------
# 9. CSV export scale labels and values
# ---------------------------------------------------------------------------

def test_csv_revenue_label_includes_scale(tmp_path):
    import csv as csv_mod
    rows = _make_rows(revenue=2_000_000_000)
    columns = _make_columns()
    filepath = str(tmp_path / "test.csv")
    _xbrl_write_csv(filepath, "Test Corp", columns, rows, "annual")
    with open(filepath, encoding="utf-8") as f:
        reader = csv_mod.reader(f)
        data = list(reader)
    line_item_labels = [r[0] for r in data]
    assert "Revenue ($mm)" in line_item_labels


def test_csv_revenue_value_is_scaled(tmp_path):
    import csv as csv_mod
    rows = _make_rows(revenue=391_035_000_000)
    columns = _make_columns()
    filepath = str(tmp_path / "test.csv")
    _xbrl_write_csv(filepath, "Test Corp", columns, rows, "annual")
    with open(filepath, encoding="utf-8") as f:
        reader = csv_mod.reader(f)
        data = list(reader)
    for row in data:
        if row[0] == "Revenue ($mm)":
            # Value column is index 2 (0=label, 1=tag, 2=FY2023)
            assert row[2] == "391,035"
            break
    else:
        pytest.fail("Revenue ($mm) row not found in CSV")
