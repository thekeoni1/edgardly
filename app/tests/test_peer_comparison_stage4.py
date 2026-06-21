"""Stage 4 tests for peer comparison Excel export (_peer_write_xlsx).

All tests are unit tests -- no EDGAR API calls.  A synthetic comparison_result
is constructed that includes: two companies, two line items (one dollar, one EPS),
two periods, one flagged cell, one N/A (missing) cell, and one genuine-zero cell.

Run:
    python -m pytest tests/test_peer_comparison_stage4.py -v
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import _peer_write_xlsx

openpyxl = pytest.importorskip("openpyxl")


# ---------------------------------------------------------------------------
# Shared fixture: a minimal but complete comparison_result
# ---------------------------------------------------------------------------

APPLE_CIK  = "320193"
MSFT_CIK   = "789019"

def _make_comparison_result():
    """
    Two companies, two line items, two periods.
    Apple Revenue FY0: present, flagged.
    Apple Revenue FY-1: present, no flags.
    Apple EPS Diluted FY0: present, no flags.
    Apple EPS Diluted FY-1: N/A (value=None).
    Microsoft Revenue FY0: present, no flags.
    Microsoft Revenue FY-1: present, no flags.
    Microsoft EPS Diluted FY0: N/A (value=None).
    Microsoft EPS Diluted FY-1: present, no flags.
    """
    return {
        "companies": [
            {
                "name": "Apple Inc.",
                "cik": APPLE_CIK,
                "line_items": {
                    "Revenue": {
                        "tag_used": "RevenueFromContractWithCustomerExcludingAssessedTax",
                        "periods": [
                            {
                                "relative_period": "FY0",
                                "period_end": "2025-09-27",
                                "period_start": "2024-09-29",
                                "value": 391_035_000_000,
                                "source_tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
                                "flags": [
                                    {"flag_type": "revenue_decline", "message": "Revenue declined vs prior year"},
                                ],
                            },
                            {
                                "relative_period": "FY-1",
                                "period_end": "2024-09-28",
                                "period_start": "2023-09-25",
                                "value": 383_285_000_000,
                                "source_tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
                                "flags": [],
                            },
                        ],
                    },
                    "EPS Diluted": {
                        "tag_used": "EarningsPerShareDiluted",
                        "periods": [
                            {
                                "relative_period": "FY0",
                                "period_end": "2025-09-27",
                                "period_start": "2024-09-29",
                                "value": 6.42,
                                "source_tag": "EarningsPerShareDiluted",
                                "flags": [],
                            },
                            {
                                "relative_period": "FY-1",
                                "period_end": "2024-09-28",
                                "period_start": None,
                                "value": None,  # missing
                                "source_tag": None,
                                "flags": [],
                            },
                        ],
                    },
                },
            },
            {
                "name": "Microsoft Corp.",
                "cik": MSFT_CIK,
                "line_items": {
                    "Revenue": {
                        "tag_used": "RevenueFromContractWithCustomerExcludingAssessedTax",
                        "periods": [
                            {
                                "relative_period": "FY0",
                                "period_end": "2025-06-30",
                                "period_start": "2024-07-01",
                                "value": 279_012_000_000,
                                "source_tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
                                "flags": [],
                            },
                            {
                                "relative_period": "FY-1",
                                "period_end": "2024-06-30",
                                "period_start": "2023-07-01",
                                "value": 245_122_000_000,
                                "source_tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
                                "flags": [],
                            },
                        ],
                    },
                    "EPS Diluted": {
                        "tag_used": "EarningsPerShareDiluted",
                        "periods": [
                            {
                                "relative_period": "FY0",
                                "period_end": "2025-06-30",
                                "period_start": None,
                                "value": None,  # missing
                                "source_tag": None,
                                "flags": [],
                            },
                            {
                                "relative_period": "FY-1",
                                "period_end": "2024-06-30",
                                "period_start": "2023-07-01",
                                "value": 11.45,
                                "source_tag": "EarningsPerShareDiluted",
                                "flags": [],
                            },
                        ],
                    },
                },
            },
        ],
        "line_items": ["Revenue", "EPS Diluted"],
        "n_periods": 2,
        "scale": {
            "dollar_factor": 1_000_000,
            "dollar_label":  "$mm",
            "share_factor":  1_000,
            "share_label":   "000s",
        },
    }


# ---------------------------------------------------------------------------
# Test 1 -- workbook structure, flagged cells, N/A cells
# ---------------------------------------------------------------------------

def test_excel_structure_flags_and_na():
    """
    Verify the exported workbook has exactly two sheets ('Comparison' and
    'Source Tags'), that flagged cells carry yellow fill and red left border,
    and that missing values are 'N/A' strings (not zero, blank, or None).
    """
    result = _make_comparison_result()

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        fpath = f.name

    try:
        _peer_write_xlsx(fpath, result)
        wb = openpyxl.load_workbook(fpath)

        # -- Sheet names --
        assert "Comparison" in wb.sheetnames, (
            f"Expected 'Comparison' sheet; got sheets: {wb.sheetnames}"
        )
        assert "Source Tags" in wb.sheetnames, (
            f"Expected 'Source Tags' sheet; got sheets: {wb.sheetnames}"
        )

        ws = wb["Comparison"]

        # -- Freeze panes at row 4 --
        assert ws.freeze_panes == "B4", (
            f"freeze_panes should be 'B4' (freeze first 3 header rows + label column); "
            f"got '{ws.freeze_panes}'"
        )

        # -- Header row 2: company name in first data column --
        # Col layout: col1=Line Item, col2=Apple FY0, col3=Apple FY-1,
        #             col4=MSFT FY0, col5=MSFT FY-1
        apple_header = ws.cell(2, 2).value
        msft_header  = ws.cell(2, 4).value
        assert apple_header == "Apple Inc.", (
            f"Row 2, col 2 should be 'Apple Inc.'; got '{apple_header}'"
        )
        assert msft_header == "Microsoft Corp.", (
            f"Row 2, col 4 should be 'Microsoft Corp.'; got '{msft_header}'"
        )

        # -- Period labels in row 3 --
        fy0_apple = ws.cell(3, 2).value
        fy1_apple = ws.cell(3, 3).value
        assert fy0_apple == "FY0",  f"Row 3, col 2 should be 'FY0'; got '{fy0_apple}'"
        assert fy1_apple == "FY-1", f"Row 3, col 3 should be 'FY-1'; got '{fy1_apple}'"

        # -- Row 4: Revenue row --
        # Apple Revenue FY0 (col 2) should be flagged: yellow fill + red left border
        apple_rev_fy0 = ws.cell(4, 2)
        print(f"\nApple Revenue FY0 cell: value={apple_rev_fy0.value}, "
              f"fill={apple_rev_fy0.fill.fgColor.rgb}, "
              f"border_left={apple_rev_fy0.border.left.color.rgb}")

        fill_color = apple_rev_fy0.fill.fgColor.rgb
        assert "FFF3CD" in fill_color.upper() or fill_color.upper() == "FFFFF3CD", (
            f"Flagged cell should have yellow fill (#FFF3CD); got fgColor.rgb='{fill_color}'"
        )

        border_color = apple_rev_fy0.border.left.color.rgb
        assert "DC3545" in border_color.upper() or border_color.upper() == "FFDC3545", (
            f"Flagged cell should have red left border (#DC3545); got '{border_color}'"
        )

        border_style = apple_rev_fy0.border.left.style
        assert border_style == "medium", (
            f"Flagged cell left border style should be 'medium'; got '{border_style}'"
        )

        # Apple Revenue FY-1 (col 3) should NOT be flagged
        apple_rev_fy1 = ws.cell(4, 3)
        fy1_fill = apple_rev_fy1.fill.fgColor.rgb
        assert "FFF3CD" not in fy1_fill.upper(), (
            f"Unflagged cell should not have yellow fill; got '{fy1_fill}'"
        )

        # Apple Revenue FY0 value should be ~391_035 (divided by 1_000_000)
        assert apple_rev_fy0.value is not None, "Apple Revenue FY0 cell should have a numeric value"
        assert isinstance(apple_rev_fy0.value, (int, float)), (
            f"Apple Revenue FY0 should be numeric; got {type(apple_rev_fy0.value).__name__}"
        )
        assert abs(apple_rev_fy0.value - 391_035) < 1, (
            f"Apple Revenue FY0 in $mm should be ~391035; got {apple_rev_fy0.value}"
        )

        # -- Row 5: EPS Diluted row --
        # Apple EPS FY-1 (col 3) is missing → must be "N/A" string
        apple_eps_fy1 = ws.cell(5, 3)
        print(f"Apple EPS FY-1 cell: value={apple_eps_fy1.value!r}")
        assert apple_eps_fy1.value == "N/A", (
            f"Missing cell should be 'N/A' string; got {apple_eps_fy1.value!r}"
        )

        # MSFT EPS FY0 (col 4) is missing → must be "N/A" string
        msft_eps_fy0 = ws.cell(5, 4)
        print(f"MSFT EPS FY0 cell: value={msft_eps_fy0.value!r}")
        assert msft_eps_fy0.value == "N/A", (
            f"Missing cell should be 'N/A' string; got {msft_eps_fy0.value!r}"
        )

        # MSFT EPS FY-1 (col 5) has value 11.45 → must be numeric
        msft_eps_fy1 = ws.cell(5, 5)
        print(f"MSFT EPS FY-1 cell: value={msft_eps_fy1.value!r}")
        assert isinstance(msft_eps_fy1.value, (int, float)), (
            f"MSFT EPS FY-1 should be numeric; got {type(msft_eps_fy1.value).__name__}"
        )
        assert abs(msft_eps_fy1.value - 11.45) < 0.01, (
            f"MSFT EPS FY-1 should be ~11.45; got {msft_eps_fy1.value}"
        )

    finally:
        os.unlink(fpath)

    print("\ntest_excel_structure_flags_and_na PASSED")


# ---------------------------------------------------------------------------
# Test 2 -- Source Tags sheet completeness
# ---------------------------------------------------------------------------

def test_source_tags_sheet_completeness():
    """
    The 'Source Tags' sheet must list one row per (company × line item) pair,
    with the correct company name, line item name, and XBRL tag.  For line
    items with no tag found, the tag cell must say '— not found' (not blank).
    """
    result = _make_comparison_result()

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        fpath = f.name

    try:
        _peer_write_xlsx(fpath, result)
        wb  = openpyxl.load_workbook(fpath)
        ws2 = wb["Source Tags"]

        # Build expected rows: (company_name, line_item, tag_or_placeholder)
        expected = []
        for company in result["companies"]:
            for li in result["line_items"]:
                info     = company["line_items"].get(li) or {}
                tag_used = info.get("tag_used")
                expected.append((
                    company["name"],
                    li,
                    tag_used if tag_used else "— not found",
                ))

        # Collect actual rows (skip header row 1)
        actual = []
        for row in ws2.iter_rows(min_row=2, values_only=True):
            company_cell, li_cell, tag_cell = row[0], row[1], row[2]
            if company_cell is None and li_cell is None:
                break
            actual.append((company_cell, li_cell, tag_cell))

        print(f"\nExpected {len(expected)} source-tag rows:")
        for r in expected:
            print(f"  {r}")
        print(f"\nActual {len(actual)} source-tag rows:")
        for r in actual:
            print(f"  {r}")

        assert len(actual) == len(expected), (
            f"Expected {len(expected)} rows in Source Tags sheet; got {len(actual)}"
        )

        for i, (exp, act) in enumerate(zip(expected, actual)):
            exp_company, exp_li, exp_tag = exp
            act_company, act_li, act_tag = act

            assert act_company == exp_company, (
                f"Row {i+2}: expected company '{exp_company}'; got '{act_company}'"
            )
            assert act_li == exp_li, (
                f"Row {i+2}: expected line item '{exp_li}'; got '{act_li}'"
            )
            assert act_tag == exp_tag, (
                f"Row {i+2}: expected tag '{exp_tag}'; got '{act_tag}'"
            )

        # Confirm columns exist: Company (A), Line Item (B), XBRL Tag Used (C)
        header_a = ws2.cell(1, 1).value
        header_b = ws2.cell(1, 2).value
        header_c = ws2.cell(1, 3).value
        assert header_a == "Company",       f"Col A header should be 'Company'; got '{header_a}'"
        assert header_b == "Line Item",     f"Col B header should be 'Line Item'; got '{header_b}'"
        assert header_c == "XBRL Tag Used", f"Col C header should be 'XBRL Tag Used'; got '{header_c}'"

    finally:
        os.unlink(fpath)

    print("\ntest_source_tags_sheet_completeness PASSED")


# ---------------------------------------------------------------------------
# Test 3 -- N/A vs. genuine-zero distinction
# ---------------------------------------------------------------------------

def test_na_vs_genuine_zero_are_distinct():
    """
    A cell where the XBRL tag was not found (value=None) must be the string
    'N/A'.  A cell where the tag WAS found and the filed value is genuinely
    zero (value=0) must be a numeric 0 with the dash number-format applied --
    NOT the string 'N/A' and NOT a blank cell.

    The Excel number format '#,##0_);(#,##0);"-"' renders numeric 0 as the
    dash character "-", making the two cases visually distinct in the
    spreadsheet: 'N/A' (grey italic, tag never filed) vs '-' (tag filed,
    value is zero).

    Layout used here:
        Row 4, col 2: value = None  → string "N/A"
        Row 4, col 3: value = 0     → numeric 0 with dash format
    """
    from app import _XLSX_FMT_DOLLAR

    result = {
        "companies": [
            {
                "name": "Test Corp",
                "cik": "000001",
                "line_items": {
                    "Revenue": {
                        "tag_used": None,    # tag not in EDGAR for this company
                        "periods": [
                            {
                                "relative_period": "FY0",
                                "period_end": "2025-12-31",
                                "period_start": "2025-01-01",
                                "value": None,  # ← N/A: tag not found
                                "source_tag": None,
                                "flags": [],
                            },
                            {
                                "relative_period": "FY-1",
                                "period_end": "2024-12-31",
                                "period_start": "2024-01-01",
                                "value": 0,     # ← genuine zero: tag found, filed $0
                                "source_tag": "Revenues",
                                "flags": [],
                            },
                        ],
                    },
                },
            },
        ],
        "line_items": ["Revenue"],
        "n_periods": 2,
        "scale": {
            "dollar_factor": 1_000_000,
            "dollar_label":  "$mm",
            "share_factor":  1_000,
            "share_label":   "000s",
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        fpath = f.name

    try:
        _peer_write_xlsx(fpath, result)
        wb = openpyxl.load_workbook(fpath)
        ws = wb["Comparison"]

        # Row 4 col 2 → FY0: value=None → "N/A" string
        na_cell = ws.cell(4, 2)
        print(f"\nN/A cell  (row4,col2): value={na_cell.value!r}  number_format={na_cell.number_format!r}")
        assert na_cell.value == "N/A", (
            f"Missing-tag cell must be 'N/A' string; got {na_cell.value!r}"
        )
        assert na_cell.number_format in ("General", "@", ""), (
            f"N/A cell should not have a numeric format; got {na_cell.number_format!r}"
        )

        # Row 4 col 3 → FY-1: value=0 → numeric 0 with dash format
        zero_cell = ws.cell(4, 3)
        print(f"Zero cell (row4,col3): value={zero_cell.value!r}  number_format={zero_cell.number_format!r}")
        assert zero_cell.value == 0, (
            f"Genuine-zero cell must be numeric 0; got {zero_cell.value!r} "
            f"(type {type(zero_cell.value).__name__})"
        )
        assert isinstance(zero_cell.value, (int, float)), (
            f"Genuine-zero cell value must be int or float, not {type(zero_cell.value).__name__}"
        )
        assert zero_cell.number_format == _XLSX_FMT_DOLLAR, (
            f"Genuine-zero Revenue cell must use the dash number format "
            f"'{_XLSX_FMT_DOLLAR}'; got '{zero_cell.number_format}'"
        )

        # Belt-and-suspenders: the two cells must not be the same type
        assert type(na_cell.value) is not type(zero_cell.value), (
            "N/A cell (str) and zero cell (int/float) should have different Python types"
        )

    finally:
        os.unlink(fpath)

    print("\ntest_na_vs_genuine_zero_are_distinct PASSED")


# ---------------------------------------------------------------------------
# Test 4 -- sanity-check rows in both export functions
# ---------------------------------------------------------------------------

def test_sanity_checks_peer_export():
    """
    Sanity-check rows contain live Excel formulas (not static values) so that
    editing any cell in the sheet immediately recalculates the result.

    Checks:
    - 'Sanity Checks' section header is present at the expected row.
    - BS and GP check cells are Excel formula strings starting with '=IF(AND(ISNUMBER'.
    - Each formula references the correct Excel row numbers for its components.
    - Conditional formatting rules are attached to the check rows.
    """

    # Build a result where:
    #   FY0: Assets=1000, Liabilities=600, Equity=400  → diff=0  (green)
    #   FY-1: Assets=1000, Liabilities=600, Equity=100 → diff=300 (30% off → red)
    #   FY-2: Assets=1000, Liabilities=None, Equity=400 → N/A (missing component)
    result = {
        "companies": [
            {
                "name": "Balanced Corp",
                "cik": "000001",
                "line_items": {
                    "Revenue": {
                        "tag_used": "Revenues",
                        "periods": [
                            {"relative_period": "FY0",  "period_end": "2025-12-31",
                             "period_start": "2025-01-01", "value": 500_000_000,
                             "source_tag": "Revenues", "flags": []},
                            {"relative_period": "FY-1", "period_end": "2024-12-31",
                             "period_start": "2024-01-01", "value": 400_000_000,
                             "source_tag": "Revenues", "flags": []},
                            {"relative_period": "FY-2", "period_end": "2023-12-31",
                             "period_start": "2023-01-01", "value": 300_000_000,
                             "source_tag": "Revenues", "flags": []},
                        ],
                    },
                    "Cost of Revenue": {
                        "tag_used": "CostOfRevenue",
                        "periods": [
                            {"relative_period": "FY0",  "period_end": "2025-12-31",
                             "period_start": "2025-01-01", "value": 200_000_000,
                             "source_tag": "CostOfRevenue", "flags": []},
                            {"relative_period": "FY-1", "period_end": "2024-12-31",
                             "period_start": "2024-01-01", "value": 160_000_000,
                             "source_tag": "CostOfRevenue", "flags": []},
                            {"relative_period": "FY-2", "period_end": "2023-12-31",
                             "period_start": "2023-01-01", "value": 120_000_000,
                             "source_tag": "CostOfRevenue", "flags": []},
                        ],
                    },
                    "Gross Profit": {
                        "tag_used": "GrossProfit",
                        "periods": [
                            {"relative_period": "FY0",  "period_end": "2025-12-31",
                             "period_start": "2025-01-01", "value": 300_000_000,
                             "source_tag": "GrossProfit", "flags": []},
                            {"relative_period": "FY-1", "period_end": "2024-12-31",
                             "period_start": "2024-01-01", "value": 240_000_000,
                             "source_tag": "GrossProfit", "flags": []},
                            {"relative_period": "FY-2", "period_end": "2023-12-31",
                             "period_start": "2023-01-01", "value": 180_000_000,
                             "source_tag": "GrossProfit", "flags": []},
                        ],
                    },
                    "Total Assets": {
                        "tag_used": "Assets",
                        "periods": [
                            {"relative_period": "FY0",  "period_end": "2025-12-31",
                             "period_start": None, "value": 1_000_000_000,
                             "source_tag": "Assets", "flags": []},
                            {"relative_period": "FY-1", "period_end": "2024-12-31",
                             "period_start": None, "value": 1_000_000_000,
                             "source_tag": "Assets", "flags": []},
                            {"relative_period": "FY-2", "period_end": "2023-12-31",
                             "period_start": None, "value": 1_000_000_000,
                             "source_tag": "Assets", "flags": []},
                        ],
                    },
                    "Total Liabilities": {
                        "tag_used": "Liabilities",
                        "periods": [
                            {"relative_period": "FY0",  "period_end": "2025-12-31",
                             "period_start": None, "value": 600_000_000,
                             "source_tag": "Liabilities", "flags": []},
                            {"relative_period": "FY-1", "period_end": "2024-12-31",
                             "period_start": None, "value": 600_000_000,
                             "source_tag": "Liabilities", "flags": []},
                            # FY-2: None to trigger N/A
                            {"relative_period": "FY-2", "period_end": "2023-12-31",
                             "period_start": None, "value": None,
                             "source_tag": None, "flags": []},
                        ],
                    },
                    "Total Equity": {
                        "tag_used": "StockholdersEquity",
                        "periods": [
                            {"relative_period": "FY0",  "period_end": "2025-12-31",
                             "period_start": None, "value": 400_000_000,  # 1000-600-400=0 ✓
                             "source_tag": "StockholdersEquity", "flags": []},
                            {"relative_period": "FY-1", "period_end": "2024-12-31",
                             "period_start": None, "value": 100_000_000,  # 1000-600-100=300 ✗
                             "source_tag": "StockholdersEquity", "flags": []},
                            {"relative_period": "FY-2", "period_end": "2023-12-31",
                             "period_start": None, "value": 400_000_000,
                             "source_tag": "StockholdersEquity", "flags": []},
                        ],
                    },
                },
            },
        ],
        "line_items": ["Revenue", "Cost of Revenue", "Gross Profit",
                       "Total Assets", "Total Liabilities", "Total Equity"],
        "n_periods": 3,
        "scale": {
            "dollar_factor": 1_000_000,
            "dollar_label":  "$mm",
            "share_factor":  1_000,
            "share_label":   "000s",
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        fpath = f.name

    line_items = ["Revenue", "Cost of Revenue", "Gross Profit",
                  "Total Assets", "Total Liabilities", "Total Equity"]

    try:
        _peer_write_xlsx(fpath, result)
        wb = openpyxl.load_workbook(fpath)
        ws = wb["Comparison"]

        # Row layout: rows 4..9 are the 6 line items; row 10 blank; row 11 blank separator;
        # row 12 sanity header; row 13 BS check; row 14 GP check.
        n_li           = len(line_items)      # 6
        sanity_hdr_row = 4 + n_li + 2         # = 12
        bs_row         = sanity_hdr_row + 1   # = 13
        gp_row         = sanity_hdr_row + 2   # = 14

        # Expected row numbers for each line item (data starts at row 4)
        li_row = {li: 4 + i for i, li in enumerate(line_items)}

        # --- Section header ---
        hdr_val = ws.cell(sanity_hdr_row, 1).value
        print(f"\nSanity header (row {sanity_hdr_row}): {hdr_val!r}")
        assert hdr_val == "Sanity Checks", (
            f"Expected 'Sanity Checks' at row {sanity_hdr_row}; got {hdr_val!r}"
        )

        # --- BS check row ---
        bs_label = ws.cell(bs_row, 1).value
        assert "Assets" in str(bs_label), (
            f"BS check label should mention 'Assets'; got {bs_label!r}"
        )

        # All three period cells (cols 2, 3, 4) must be Excel formulas
        for col_idx, period in [(2, "FY0"), (3, "FY-1"), (4, "FY-2")]:
            cell = ws.cell(bs_row, col_idx)
            print(f"  BS {period} (col {col_idx}): {cell.value!r}")
            assert isinstance(cell.value, str) and cell.value.startswith("="), (
                f"BS check {period} must be an Excel formula; got {cell.value!r}"
            )
            assert "ISNUMBER" in cell.value, (
                f"Formula must use ISNUMBER guard; got {cell.value!r}"
            )

        # The formula for FY0 (col B) must reference the correct row numbers
        bs_formula_fy0 = ws.cell(bs_row, 2).value
        for li in ("Total Assets", "Total Liabilities", "Total Equity"):
            expected_row = li_row[li]
            assert f"B{expected_row}" in bs_formula_fy0, (
                f"BS formula should reference B{expected_row} ({li}); "
                f"got {bs_formula_fy0!r}"
            )

        # --- GP check row ---
        gp_label = ws.cell(gp_row, 1).value
        assert "Revenue" in str(gp_label) or "GP" in str(gp_label) or "Gross" in str(gp_label), (
            f"GP check label should mention Revenue/GP/Gross; got {gp_label!r}"
        )

        gp_formula_fy0 = ws.cell(gp_row, 2).value
        print(f"  GP FY0 (col 2): {gp_formula_fy0!r}")
        assert isinstance(gp_formula_fy0, str) and gp_formula_fy0.startswith("="), (
            f"GP check FY0 must be an Excel formula; got {gp_formula_fy0!r}"
        )
        for li in ("Revenue", "Cost of Revenue", "Gross Profit"):
            expected_row = li_row[li]
            assert f"B{expected_row}" in gp_formula_fy0, (
                f"GP formula should reference B{expected_row} ({li}); "
                f"got {gp_formula_fy0!r}"
            )

        # --- Conditional formatting ---
        # At least 6 rules should be present (3 per check row: green/red/grey)
        cf_rule_count = sum(
            len(rules)
            for rules in ws.conditional_formatting._cf_rules.values()
        )
        print(f"  Conditional formatting rule count: {cf_rule_count}")
        assert cf_rule_count >= 6, (
            f"Expected >= 6 conditional formatting rules (3 per check row); "
            f"got {cf_rule_count}"
        )

    finally:
        os.unlink(fpath)

    print("\ntest_sanity_checks_peer_export PASSED")
