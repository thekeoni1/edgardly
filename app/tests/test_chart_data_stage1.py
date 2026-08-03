"""Stage 1 tests for /api/xbrl/chart-data endpoint and _build_chart_data helper.

Tests 1-3 are the required stage gates:
  Test 1 -- Apple across 5 years (integration, real EDGAR data)
  Test 2 -- Missing line-item data returns null, not zero (unit)
  Test 3 -- Flagged value included with flagged=True; derived margins null (unit)

Additional unit tests exercise edge cases without network calls.

Run unit tests only:
    python -m pytest tests/test_chart_data_stage1.py -v

Run all including integration:
    python -m pytest tests/test_chart_data_stage1.py -v -m integration -s
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app as flask_app, _build_chart_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _make_cell(value, flags=None):
    """Minimal cell dict matching _build_xbrl_result output."""
    return {
        "value": value,
        "formatted": str(value),
        "unit": "USD",
        "start": "2024-01-01",
        "end": "2024-12-31",
        "fp": "FY",
        "tag": "Revenues",
        "filed": "2025-02-01",
        "flags": flags or [],
    }


def _make_rows(cells_by_li):
    """
    Build the minimal rows list that _build_chart_data expects.

    cells_by_li: {"Revenue": {end_date: value_or_None}, ...}
    Pass a dict with end_date -> value for each line item; None means
    the cell is absent (not reported), not just None-valued.
    """
    COLS = {
        "Revenue":      "Revenues",
        "Net Income":   "NetIncomeLoss",
        "Gross Profit": "GrossProfit",
    }
    rows = []
    for li, tag in COLS.items():
        cells = {}
        for end, val in cells_by_li.get(li, {}).items():
            if val is not None:
                cells[end] = _make_cell(val)
            # None means absent — do not add to cells dict
        rows.append({"line_item": li, "tag_used": tag, "cells": cells})
    return rows


def _make_rows_with_flags(cells_and_flags_by_li):
    """Like _make_rows but accepts (value, flags_list) tuples."""
    COLS = {
        "Revenue":      "Revenues",
        "Net Income":   "NetIncomeLoss",
        "Gross Profit": "GrossProfit",
    }
    rows = []
    for li, tag in COLS.items():
        cells = {}
        for end, entry in cells_and_flags_by_li.get(li, {}).items():
            val, flags = entry
            if val is not None:
                cells[end] = _make_cell(val, flags)
        rows.append({"line_item": li, "tag_used": tag, "cells": cells})
    return rows


_COLUMNS = [
    {"key": "2024-12-31", "label": "FY2024", "fp": "FY", "fy": 2024},
    {"key": "2023-12-31", "label": "FY2023", "fp": "FY", "fy": 2023},
]


# ===========================================================================
# Test 1 — Apple across 5 years (integration, real EDGAR data)
# ===========================================================================

@pytest.mark.integration
def test_apple_chart_data_all_series_correct(client):
    """
    Stage gate 1 of 3.

    Apple CIK 320193 across 5 years must return:
      - All 4 series populated (revenue, net_income, gross_margin_pct, net_margin_pct)
      - Dollar scale = $mm (factor=1_000_000)
      - Period labels of the form FYxxxx
      - Revenue values in the Apple range (~$275K–$400K in $mm)
      - Gross margin in the Apple range (~40–50%)
      - Net margin in the Apple range (~20–30%)
      - Every point has a non-null period_end date
    """
    resp = client.post("/api/xbrl/chart-data", json={
        "cik": "320193",
        "start_year": 2020,
        "end_year": 2025,
        "period_type": "annual",
    })
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"
    d = resp.get_json()

    print("\nentity:", d.get("entity"))
    print("dollar_scale:", d.get("dollar_scale"))

    # Entity and scale
    assert "apple" in d["entity"].lower(), f"Expected Apple entity, got {d['entity']!r}"
    assert d["dollar_scale"]["factor"] == 1_000_000, (
        f"Expected $mm (factor=1_000_000), got {d['dollar_scale']}"
    )
    assert d["dollar_scale"]["label"] == "$mm"

    series = d["series"]
    assert set(series.keys()) == {"revenue", "net_income", "gross_margin_pct", "net_margin_pct"}

    # At least 5 periods returned
    for key in series:
        assert len(series[key]) >= 5, f"Expected >=5 periods for {key}, got {len(series[key])}"

    # Every point has period_end and period_label
    for key in series:
        for pt in series[key]:
            assert pt["period_end"] is not None, f"Null period_end in {key}: {pt}"
            assert pt["period_label"].startswith("FY"), (
                f"Expected FYxxxx label in {key}: {pt['period_label']!r}"
            )

    # Revenue values should be in Apple range ($mm)
    rev_values = [pt["value"] for pt in series["revenue"] if pt["value"] is not None]
    assert rev_values, "No non-null Revenue values"
    most_recent_rev = rev_values[-1]
    print(f"Most recent Revenue ($mm): {most_recent_rev:,.0f}")
    assert 200_000 < most_recent_rev < 500_000, (
        f"Apple Revenue out of expected range: {most_recent_rev}"
    )

    # Net Income should be positive and smaller than Revenue
    ni_values = [pt["value"] for pt in series["net_income"] if pt["value"] is not None]
    assert ni_values, "No non-null Net Income values"
    recent_ni = ni_values[-1]
    print(f"Most recent Net Income ($mm): {recent_ni:,.0f}")
    assert 0 < recent_ni < most_recent_rev, (
        f"Net Income {recent_ni} should be positive and < Revenue {most_recent_rev}"
    )

    # Gross margin % in Apple range (~40-50%)
    gm_values = [pt["value"] for pt in series["gross_margin_pct"] if pt["value"] is not None]
    assert gm_values, "No non-null Gross Margin % values"
    recent_gm = gm_values[-1]
    print(f"Most recent Gross Margin %%: {recent_gm:.2f}%%")
    assert 35.0 < recent_gm < 60.0, (
        f"Apple Gross Margin % out of expected range: {recent_gm}"
    )

    # Net margin % in Apple range (~20-30%)
    nm_values = [pt["value"] for pt in series["net_margin_pct"] if pt["value"] is not None]
    assert nm_values, "No non-null Net Margin % values"
    recent_nm = nm_values[-1]
    print(f"Most recent Net Margin %%: {recent_nm:.2f}%%")
    assert 15.0 < recent_nm < 40.0, (
        f"Apple Net Margin % out of expected range: {recent_nm}"
    )

    # No flagged=None values (flagged must always be a bool)
    for key in ("revenue", "net_income"):
        for pt in series[key]:
            assert isinstance(pt["flagged"], bool), (
                f"flagged must be bool, got {type(pt['flagged'])} in {key}: {pt}"
            )

    # Print sample periods for manual verification
    print("\nRevenue series (last 3 points):")
    for pt in series["revenue"][-3:]:
        flag_str = " [FLAGGED]" if pt["flagged"] else ""
        print(f"  {pt['period_label']} ({pt['period_end']}): "
              f"{pt['value']:,.0f} $mm{flag_str}")
    print("Gross Margin % series (last 3 points):")
    for pt in series["gross_margin_pct"][-3:]:
        val_str = f"{pt['value']:.2f}%" if pt["value"] is not None else "null"
        print(f"  {pt['period_label']} ({pt['period_end']}): {val_str}")


# ===========================================================================
# Test 2 — Missing data returns null (not zero) — unit test
# ===========================================================================

def test_missing_revenue_period_returns_null_not_zero():
    """
    Stage gate 2 of 3.

    When Revenue is absent for a period, the chart point must have
    value=None (JSON null), not 0.  Gross Margin % and Net Margin % for
    that period must also be None (not computable from missing Revenue).
    """
    columns = list(_COLUMNS)   # FY2024 and FY2023

    # Revenue present for FY2024 only; missing for FY2023
    rows = _make_rows({
        "Revenue":      {"2024-12-31": 100_000_000},   # present
        # 2023-12-31 absent → not in cells dict
        "Net Income":   {"2024-12-31": 20_000_000, "2023-12-31": 15_000_000},
        "Gross Profit": {"2024-12-31": 45_000_000, "2023-12-31": 40_000_000},
    })

    result = _build_chart_data("TestCo", columns, rows, 1_000_000, "$mm")
    rev = result["series"]["revenue"]
    gm  = result["series"]["gross_margin_pct"]
    nm  = result["series"]["net_margin_pct"]

    # FY2024: Revenue present
    assert rev[0]["period_label"] == "FY2024"
    assert rev[0]["value"] == 100.0, f"Expected 100.0, got {rev[0]['value']}"
    assert rev[0]["flagged"] is False

    # FY2023: Revenue missing → null
    assert rev[1]["period_label"] == "FY2023"
    assert rev[1]["value"] is None, (
        f"Missing Revenue must be null, not {rev[1]['value']!r}"
    )
    assert rev[1]["flagged"] is False

    # FY2024: Gross Margin present (100M revenue, 45M GP → 45%)
    assert gm[0]["value"] == pytest.approx(45.0, abs=0.01), (
        f"Expected GP%=45.0, got {gm[0]['value']}"
    )

    # FY2023: Revenue missing → Gross Margin null
    assert gm[1]["value"] is None, (
        f"Gross Margin must be null when Revenue is missing, got {gm[1]['value']!r}"
    )

    # FY2023: Revenue missing → Net Margin null
    assert nm[1]["value"] is None, (
        f"Net Margin must be null when Revenue is missing, got {nm[1]['value']!r}"
    )

    print("\nRevenue series:", rev)
    print("Gross Margin series:", gm)


def test_missing_gross_profit_period_leaves_net_income_intact():
    """
    When Gross Profit is absent but Revenue and Net Income are present,
    gross_margin_pct must be null for that period while net_margin_pct is
    still computed correctly.
    """
    columns = [{"key": "2024-12-31", "label": "FY2024", "fp": "FY", "fy": 2024}]
    rows = _make_rows({
        "Revenue":      {"2024-12-31": 100_000_000},
        "Net Income":   {"2024-12-31": 25_000_000},
        # Gross Profit absent
    })
    result = _build_chart_data("TestCo", columns, rows, 1, "$")
    assert result["series"]["gross_margin_pct"][0]["value"] is None
    assert result["series"]["net_margin_pct"][0]["value"] == pytest.approx(25.0, abs=0.01)


# ===========================================================================
# Test 3 — Flagged value included with flagged=True; derived margins null
# ===========================================================================

def test_flagged_revenue_included_with_flag_marker_and_margins_null():
    """
    Stage gate 3 of 3.

    A flagged Revenue value must:
      - Still appear in the revenue series (value is NOT suppressed)
      - Have flagged=True
    And because Revenue is flagged, Gross Margin % and Net Margin % for
    that period must be null (derived from unreliable input).
    """
    FLAG = [{"type": "NEGATIVE_REVENUE", "msg": "Revenue is negative (-50000000)"}]
    columns = [{"key": "2024-12-31", "label": "FY2024", "fp": "FY", "fy": 2024}]
    rows = _make_rows_with_flags({
        "Revenue":      {"2024-12-31": (-50_000_000, FLAG)},
        "Net Income":   {"2024-12-31": (-60_000_000, [])},
        "Gross Profit": {"2024-12-31": (-20_000_000, [])},
    })

    result = _build_chart_data("TestCo", columns, rows, 1_000_000, "$mm")

    rev_pt = result["series"]["revenue"][0]
    assert rev_pt["value"] == pytest.approx(-50.0, abs=0.01), (
        f"Flagged value must be included, got {rev_pt['value']}"
    )
    assert rev_pt["flagged"] is True, "Expected flagged=True for flagged Revenue"

    gm_pt = result["series"]["gross_margin_pct"][0]
    assert gm_pt["value"] is None, (
        f"Gross Margin must be null when Revenue is flagged, got {gm_pt['value']!r}"
    )

    nm_pt = result["series"]["net_margin_pct"][0]
    assert nm_pt["value"] is None, (
        f"Net Margin must be null when Revenue is flagged, got {nm_pt['value']!r}"
    )

    print("\nFlagged Revenue point:", rev_pt)
    print("Gross Margin (should be null):", gm_pt)
    print("Net Margin (should be null):", nm_pt)


def test_flagged_gross_profit_leaves_revenue_unflagged_and_net_margin_intact():
    """
    Gross Profit flagged → gross_margin_pct null for that period.
    Revenue unflagged → revenue series unflagged.
    Net Income unflagged, Revenue unflagged → net_margin_pct still computable.
    """
    GP_FLAG = [{"type": "ZERO_AMONG_NONZERO", "msg": "Gross Profit is zero"}]
    columns = [{"key": "2024-12-31", "label": "FY2024", "fp": "FY", "fy": 2024}]
    rows = _make_rows_with_flags({
        "Revenue":      {"2024-12-31": (100_000_000, [])},
        "Net Income":   {"2024-12-31": (20_000_000,  [])},
        "Gross Profit": {"2024-12-31": (0,            GP_FLAG)},
    })

    result = _build_chart_data("TestCo", columns, rows, 1_000_000, "$mm")

    assert result["series"]["revenue"][0]["flagged"] is False
    assert result["series"]["gross_margin_pct"][0]["value"] is None
    assert result["series"]["net_margin_pct"][0]["value"] == pytest.approx(20.0, abs=0.01)


# ===========================================================================
# Additional unit tests — scale, zero revenue, response keys
# ===========================================================================

def test_chart_data_scaling_correct():
    """Revenue of $391B with $mm scale should yield ~391_000 in chart."""
    columns = [{"key": "2024-12-31", "label": "FY2024", "fp": "FY", "fy": 2024}]
    rows = _make_rows({
        "Revenue":      {"2024-12-31": 391_035_000_000},
        "Net Income":   {"2024-12-31":  93_736_000_000},
        "Gross Profit": {"2024-12-31": 180_683_000_000},
    })
    result = _build_chart_data("Apple Inc.", columns, rows, 1_000_000, "$mm")

    rev = result["series"]["revenue"][0]["value"]
    assert rev == pytest.approx(391_035.0, abs=1.0), f"Expected ~391035, got {rev}"

    gm = result["series"]["gross_margin_pct"][0]["value"]
    assert gm == pytest.approx(46.2, abs=0.5), f"Expected ~46.2%, got {gm}"


def test_zero_revenue_yields_null_margins():
    """Revenue=0 → division by zero; both margins must be null, not Inf."""
    columns = [{"key": "2024-12-31", "label": "FY2024", "fp": "FY", "fy": 2024}]
    rows = _make_rows({
        "Revenue":      {"2024-12-31": 0},
        "Net Income":   {"2024-12-31": 5_000_000},
        "Gross Profit": {"2024-12-31": 2_000_000},
    })
    result = _build_chart_data("TestCo", columns, rows, 1, "$")
    assert result["series"]["gross_margin_pct"][0]["value"] is None
    assert result["series"]["net_margin_pct"][0]["value"] is None


def test_chart_data_response_structure():
    """Response must have entity, dollar_scale, and series with all 4 keys."""
    columns = [{"key": "2024-12-31", "label": "FY2024", "fp": "FY", "fy": 2024}]
    rows = _make_rows({"Revenue": {"2024-12-31": 100_000_000}})
    result = _build_chart_data("Acme", columns, rows, 1_000, "$000s")

    assert result["entity"] == "Acme"
    assert result["dollar_scale"] == {"factor": 1_000, "label": "$000s"}
    assert set(result["series"].keys()) == {
        "revenue", "net_income", "gross_margin_pct", "net_margin_pct"
    }
    for key in result["series"]:
        pts = result["series"][key]
        assert len(pts) == 1
        assert "period_label" in pts[0]
        assert "period_end"   in pts[0]
        assert "value"        in pts[0]
        assert "flagged"      in pts[0]


def test_api_chart_data_returns_400_without_cik(client):
    resp = client.post("/api/xbrl/chart-data", json={})
    assert resp.status_code == 400
    assert "cik" in resp.get_json().get("error", "")


def test_api_chart_data_returns_400_for_invalid_period_type(client):
    resp = client.post("/api/xbrl/chart-data", json={
        "cik": "320193", "period_type": "monthly"
    })
    assert resp.status_code == 400
    assert "period_type" in resp.get_json().get("error", "")
