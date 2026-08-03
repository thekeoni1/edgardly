"""Tests verifying that validation flags reach the tooltip data (backend) and
the peer comparison Excel Flag Details section.

Run:
    python -m pytest tests/test_flag_tooltip_flow.py -v
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import xbrl_extractor as xbrl
from app import _peer_write_xlsx

openpyxl = pytest.importorskip("openpyxl")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dp(unit, start, end, value, fp="FY", tag="Revenues",
             form="10-K", filed="2025-02-01"):
    return {
        "unit": unit, "start": start, "end": end,
        "value": value, "fiscal_period": fp,
        "tag": tag, "form": form, "filed": filed,
    }


def _make_instant(unit, end, value, fp="FY", tag="Assets",
                  form="10-K", filed="2025-02-01"):
    return {
        "unit": unit, "start": None, "end": end,
        "value": value, "fiscal_period": fp,
        "tag": tag, "form": form, "filed": filed,
    }


def _empty_line_item():
    return {"data": [], "tag_used": None}


# ---------------------------------------------------------------------------
# Test 1 — validate_financials produces flag with non-empty message,
#           and the _build_xbrl_result period_flags construction picks it up.
# ---------------------------------------------------------------------------

def test_yoy_flag_appears_in_period_flags():
    """
    A 10x YoY Revenue jump must produce a LARGE_YOY_CHANGE flag whose
    'message' field is non-empty, and the simulated period_flags list built
    exactly as _build_xbrl_result does it must contain that message under
    the 'msg' key (the key the single-company tooltip reads).
    """
    deduped = {li: _empty_line_item() for li in xbrl.TAG_MAP}
    deduped["Revenue"] = {
        "tag_used": "Revenues",
        "data": [
            _make_dp("USD", "2022-01-01", "2022-12-31", 1_000_000),
            _make_dp("USD", "2023-01-01", "2023-12-31", 10_000_000),  # 900% change → flag
        ],
    }

    all_flags = xbrl.validate_financials(deduped)
    rev_flags = all_flags.get("Revenue", [])

    # At least one flag must be produced
    assert rev_flags, "Expected at least one Revenue flag for a 10x YoY jump"

    # Every flag must have a non-empty message
    for f in rev_flags:
        assert f.get("message"), f"Flag has empty/missing message: {f}"
        assert f.get("period_end"), f"Flag has missing period_end: {f}"

    # Simulate _build_xbrl_result's period_flags construction (line 294-296 of app.py)
    flagged_end = "2023-12-31"
    period_flags = [
        {"type": f["flag_type"], "msg": f["message"]}
        for f in rev_flags if f.get("period_end") == flagged_end
    ]

    assert period_flags, (
        f"period_flags is empty for end={flagged_end!r}. "
        f"Flags present: {[f['period_end'] for f in rev_flags]}"
    )
    assert period_flags[0]["msg"], (
        f"period_flags[0]['msg'] is empty: {period_flags[0]}"
    )
    assert "msg" in period_flags[0], (
        f"'msg' key missing from period_flags dict: {period_flags[0].keys()}"
    )

    print("\nSingle-company period_flags:", repr(period_flags))
    print("  -> tooltip would show:", repr(period_flags[0]["msg"]))


# ---------------------------------------------------------------------------
# Test 2 — peer_comparison period_flags use 'message' key (not 'msg')
# ---------------------------------------------------------------------------

def test_peer_period_flags_use_message_key():
    """
    peer_comparison.py stores flags as {"flag_type": ..., "message": ...}.
    The JS tooltip reads f.message || f.msg.  Verify the key name is 'message'
    and the value is non-empty.
    """
    deduped = {li: _empty_line_item() for li in xbrl.TAG_MAP}
    deduped["Revenue"] = {
        "tag_used": "Revenues",
        "data": [
            _make_dp("USD", "2022-01-01", "2022-12-31", 1_000_000),
            _make_dp("USD", "2023-01-01", "2023-12-31", 10_000_000),
        ],
    }

    all_flags = xbrl.validate_financials(deduped)
    rev_flags = all_flags.get("Revenue", [])
    assert rev_flags, "No Revenue flags produced"

    # Simulate peer_comparison.py's period_flags construction (lines 215-217)
    flagged_end = "2023-12-31"
    period_flags = [
        {"flag_type": f["flag_type"], "message": f["message"]}
        for f in rev_flags if f.get("period_end") == flagged_end
    ]

    assert period_flags, "period_flags empty for peer comparison"
    assert "message" in period_flags[0], (
        f"'message' key missing: {period_flags[0].keys()}"
    )
    assert period_flags[0]["message"], "Flag message is empty"

    print("\nPeer period_flags:", repr(period_flags))
    print("  -> tooltip would show:", repr(period_flags[0]["message"]))


# ---------------------------------------------------------------------------
# Test 3 — balance sheet equation flag reaches Total Assets cell
# ---------------------------------------------------------------------------

def test_bs_mismatch_flag_reaches_total_assets_cell():
    """
    A balance sheet that doesn't balance (Assets != Liabilities + Equity)
    must produce a flag attached to 'Total Assets' with the correct period_end,
    and the period_flags for the Total Assets cell at that end date must be
    non-empty with a non-empty 'msg'.
    """
    end_date = "2024-12-31"

    deduped = {li: _empty_line_item() for li in xbrl.TAG_MAP}
    deduped["Total Assets"]      = {"tag_used": "Assets",      "data": [
        _make_instant("USD", end_date, 100_000_000, tag="Assets"),
    ]}
    deduped["Total Liabilities"] = {"tag_used": "Liabilities", "data": [
        _make_instant("USD", end_date, 50_000_000, tag="Liabilities"),
    ]}
    deduped["Total Equity"]      = {"tag_used": "StockholdersEquity", "data": [
        _make_instant("USD", end_date, 40_000_000, tag="StockholdersEquity"),
        # 40M equity + 50M liab = 90M ≠ 100M assets → 10% gap → flag
    ]}

    all_flags = xbrl.validate_financials(deduped)
    ta_flags = all_flags.get("Total Assets", [])

    assert ta_flags, "Expected a balance sheet mismatch flag"
    assert ta_flags[0]["period_end"] == end_date, (
        f"Flag period_end {ta_flags[0]['period_end']!r} != cell end {end_date!r}"
    )

    # Simulate period_flags for the Total Assets cell at end_date
    period_flags = [
        {"type": f["flag_type"], "msg": f["message"]}
        for f in ta_flags if f.get("period_end") == end_date
    ]
    assert period_flags, "BS mismatch flag not found for end_date"
    assert period_flags[0]["msg"], "BS mismatch flag message is empty"
    assert "Assets" in period_flags[0]["msg"], (
        f"Expected 'Assets' in flag message: {period_flags[0]['msg']!r}"
    )
    print("\nBS mismatch period_flags:", repr(period_flags))


# ---------------------------------------------------------------------------
# Test 4 — peer Excel Flag Details section appears with correct message text
# ---------------------------------------------------------------------------

def _make_peer_result_with_flag(flag_message="Revenue jumped 900% YoY — tagging error?"):
    return {
        "companies": [
            {
                "name": "FlagCo",
                "cik": "111111",
                "line_items": {
                    "Revenue": {
                        "tag_used": "Revenues",
                        "periods": [
                            {
                                "relative_period": "FY0",
                                "period_end": "2024-12-31",
                                "period_start": "2024-01-01",
                                "value": 10_000_000,
                                "source_tag": "Revenues",
                                "flags": [
                                    {"flag_type": "LARGE_YOY_CHANGE",
                                     "message": flag_message},
                                ],
                            },
                            {
                                "relative_period": "FY-1",
                                "period_end": "2023-12-31",
                                "period_start": "2023-01-01",
                                "value": 1_000_000,
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
            "dollar_factor": 1_000,
            "dollar_label": "$000s",
            "share_factor": 1_000,
            "share_label": "000s",
        },
    }


def test_peer_excel_flag_details_section_present():
    """
    When the comparison_result contains a flagged period, _peer_write_xlsx
    must write a 'Flag Details' section with the flag message text.
    """
    FLAG_MSG = "Revenue jumped 900% YoY — possible tagging error or unit mismatch"
    result = _make_peer_result_with_flag(FLAG_MSG)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = f.name
    try:
        _peer_write_xlsx(path, result)
        wb = openpyxl.load_workbook(path)
        ws = wb["Comparison"]

        all_values = [
            str(cell.value)
            for row in ws.iter_rows()
            for cell in row
            if cell.value is not None
        ]

        assert any(v == "Flag Details" for v in all_values), (
            "'Flag Details' header cell not found in Comparison sheet."
        )
        assert any(FLAG_MSG in v for v in all_values), (
            f"Flag message text not found in Comparison sheet.\n"
            f"Looking for: {FLAG_MSG!r}"
        )
        assert any(v == "FlagCo" for v in all_values), (
            "Company name 'FlagCo' not in Flag Details section"
        )
        print("\nFlag Details section verified present.")
    finally:
        os.unlink(path)


def test_peer_excel_no_flag_details_section_when_no_flags():
    """
    When no periods have flags, the Flag Details section must not appear.
    """
    result = {
        "companies": [{
            "name": "CleanCo",
            "cik": "222222",
            "line_items": {
                "Revenue": {
                    "tag_used": "Revenues",
                    "periods": [{
                        "relative_period": "FY0",
                        "period_end": "2024-12-31",
                        "period_start": "2024-01-01",
                        "value": 5_000_000,
                        "source_tag": "Revenues",
                        "flags": [],
                    }],
                },
            },
        }],
        "line_items": ["Revenue"],
        "n_periods": 1,
        "scale": {
            "dollar_factor": 1_000, "dollar_label": "$000s",
            "share_factor": 1_000, "share_label": "000s",
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = f.name
    try:
        _peer_write_xlsx(path, result)
        wb = openpyxl.load_workbook(path)
        ws = wb["Comparison"]
        all_values = [
            str(cell.value)
            for row in ws.iter_rows()
            for cell in row
            if cell.value is not None
        ]
        assert not any(v == "Flag Details" for v in all_values), (
            "Flag Details header cell should not appear when there are no flags"
        )
    finally:
        os.unlink(path)
