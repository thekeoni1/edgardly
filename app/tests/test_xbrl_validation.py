"""test_xbrl_validation.py -- automated tests for xbrl_extractor validation checks.

Each validation function is tested with:
  - known-bad data that must produce a flag
  - known-good data that must produce no flag

Tests import the private check functions directly so failures are easy to diagnose.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from xbrl_extractor import (
    _check_negative_revenue,
    _check_net_income_vs_revenue,
    _check_balance_sheet_equation,
    _check_zero_among_nonzero,
    _check_eps_reconciliation,
    _check_large_yoy_change,
    _check_missing_critical_data,
    FLAG_NEGATIVE_REVENUE,
    FLAG_NET_INCOME_EXCEEDS_REVENUE,
    FLAG_BALANCE_SHEET_MISMATCH,
    FLAG_ZERO_AMONG_NONZERO,
    FLAG_EPS_RECONCILIATION,
    FLAG_LARGE_YOY_CHANGE,
    FLAG_MISSING_CRITICAL_DATA,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dp(value, end="2023-12-31", start="2023-01-01", fiscal_period="FY", instant=False):
    """Build a minimal data-point dict."""
    dp = {"value": value, "end": end, "fiscal_period": fiscal_period}
    if not instant:
        dp["start"] = start
    return dp


def _instant_dp(value, end="2023-12-31"):
    """Build a minimal instant (balance-sheet) data-point dict."""
    return {"value": value, "end": end}


def _flags_of_type(flags, flag_type):
    return [f for f in flags if f["flag_type"] == flag_type]


# ---------------------------------------------------------------------------
# 1. Negative Revenue
# ---------------------------------------------------------------------------

def test_negative_revenue_flagged():
    pts = [_dp(-1_000_000)]
    flags = _check_negative_revenue(pts)
    assert _flags_of_type(flags, FLAG_NEGATIVE_REVENUE), "Expected NEGATIVE_REVENUE flag"


def test_negative_revenue_not_flagged_for_positive():
    pts = [_dp(5_000_000)]
    flags = _check_negative_revenue(pts)
    assert not flags, "Positive revenue should produce no flag"


def test_negative_revenue_not_flagged_for_zero():
    pts = [_dp(0)]
    flags = _check_negative_revenue(pts)
    assert not flags, "Zero revenue should produce no flag"


def test_negative_revenue_skips_none():
    pts = [_dp(None)]
    flags = _check_negative_revenue(pts)
    assert not flags, "None value should produce no flag"


# ---------------------------------------------------------------------------
# 2. Net Income Exceeds Revenue
# ---------------------------------------------------------------------------

def _ni_rev_pts(ni, rev, end="2023-12-31"):
    ni_pts = [_dp(ni, end=end)]
    rev_pts = [_dp(rev, end=end)]
    return ni_pts, rev_pts


def test_net_income_exceeds_revenue_flagged():
    ni_pts, rev_pts = _ni_rev_pts(ni=500_000_000, rev=100_000_000)
    flags = _check_net_income_vs_revenue(ni_pts, rev_pts)
    assert _flags_of_type(flags, FLAG_NET_INCOME_EXCEEDS_REVENUE), \
        "5x ratio should trigger flag"


def test_net_income_exceeds_revenue_not_flagged_normal():
    ni_pts, rev_pts = _ni_rev_pts(ni=20_000_000, rev=100_000_000)
    flags = _check_net_income_vs_revenue(ni_pts, rev_pts)
    assert not flags, "20% margin should not flag"


def test_net_income_exceeds_revenue_skipped_below_floor():
    # Revenue is only $5M (below the $10M floor) -- should NOT flag even at 5x
    ni_pts, rev_pts = _ni_rev_pts(ni=25_000_000, rev=5_000_000)
    flags = _check_net_income_vs_revenue(ni_pts, rev_pts)
    assert not flags, "Revenue below $10M floor should skip the ratio check"


def test_net_income_exceeds_revenue_skipped_zero_revenue():
    ni_pts, rev_pts = _ni_rev_pts(ni=100_000_000, rev=0)
    flags = _check_net_income_vs_revenue(ni_pts, rev_pts)
    assert not flags, "Zero revenue should skip the ratio check"


def test_net_income_exceeds_revenue_negative_ni_flagged():
    # Large loss can also be suspicious (e.g. |NI| = 5x |Rev|)
    ni_pts, rev_pts = _ni_rev_pts(ni=-500_000_000, rev=100_000_000)
    flags = _check_net_income_vs_revenue(ni_pts, rev_pts)
    assert _flags_of_type(flags, FLAG_NET_INCOME_EXCEEDS_REVENUE), \
        "Large loss vs revenue should flag"


# ---------------------------------------------------------------------------
# 3. Balance Sheet Equation
# ---------------------------------------------------------------------------

def _bs_pts(assets, liabs, equity, end="2023-12-31"):
    return [_instant_dp(assets, end)], [_instant_dp(liabs, end)], [_instant_dp(equity, end)]


def test_balance_sheet_mismatch_flagged():
    # Assets=100, Liabs=50, Equity=10 -> mismatch of 40 (40% of 100)
    a, l, e = _bs_pts(100_000_000, 50_000_000, 10_000_000)
    flags = _check_balance_sheet_equation(a, l, e)
    assert _flags_of_type(flags, FLAG_BALANCE_SHEET_MISMATCH), \
        "40% mismatch should flag"


def test_balance_sheet_equation_passes_exact():
    a, l, e = _bs_pts(100_000_000, 60_000_000, 40_000_000)
    flags = _check_balance_sheet_equation(a, l, e)
    assert not flags, "Exact A=L+E should not flag"


def test_balance_sheet_equation_passes_within_5pct():
    # Assets=100M, L+E=96M -> 4% difference (inside 5% tolerance)
    a, l, e = _bs_pts(100_000_000, 56_000_000, 40_000_000)
    flags = _check_balance_sheet_equation(a, l, e)
    assert not flags, "4% mismatch is within tolerance and should not flag"


def test_balance_sheet_equation_flags_above_5pct():
    # Assets=100M, L+E=93M -> 7% difference (above 5% tolerance)
    a, l, e = _bs_pts(100_000_000, 53_000_000, 40_000_000)
    flags = _check_balance_sheet_equation(a, l, e)
    assert _flags_of_type(flags, FLAG_BALANCE_SHEET_MISMATCH), \
        "7% mismatch should flag"


def test_balance_sheet_no_matching_period():
    # Assets period 2023, Liabilities period 2022 -- no matching instant key
    a = [_instant_dp(100_000_000, "2023-12-31")]
    l = [_instant_dp(60_000_000, "2022-12-31")]
    e = [_instant_dp(40_000_000, "2022-12-31")]
    flags = _check_balance_sheet_equation(a, l, e)
    assert not flags, "Non-matching periods should produce no flag"


# ---------------------------------------------------------------------------
# 4. Zero Among Non-Zero
# ---------------------------------------------------------------------------

def _zero_series(line_item, zero_end="2021-12-31"):
    """Three years of data: two nonzero, one zero."""
    return [
        _dp(100_000_000, end="2022-12-31"),
        _dp(120_000_000, end="2023-12-31"),
        _dp(0, end=zero_end),
    ]


def test_zero_among_nonzero_revenue_flagged():
    pts = _zero_series("Revenue")
    flags = _check_zero_among_nonzero("Revenue", pts)
    assert _flags_of_type(flags, FLAG_ZERO_AMONG_NONZERO), \
        "Zero Revenue among large values should flag"


def test_zero_among_nonzero_net_income_flagged():
    pts = _zero_series("Net Income")
    flags = _check_zero_among_nonzero("Net Income", pts)
    assert _flags_of_type(flags, FLAG_ZERO_AMONG_NONZERO), \
        "Zero Net Income among large values should flag"


def test_zero_among_nonzero_total_assets_flagged():
    pts = _zero_series("Total Assets")
    flags = _check_zero_among_nonzero("Total Assets", pts)
    assert _flags_of_type(flags, FLAG_ZERO_AMONG_NONZERO)


def test_zero_among_nonzero_total_liabilities_flagged():
    pts = _zero_series("Total Liabilities")
    flags = _check_zero_among_nonzero("Total Liabilities", pts)
    assert _flags_of_type(flags, FLAG_ZERO_AMONG_NONZERO)


def test_zero_among_nonzero_cash_not_checked():
    # Cash going to zero is a legitimate business event -- should never flag
    pts = _zero_series("Cash and Equivalents")
    flags = _check_zero_among_nonzero("Cash and Equivalents", pts)
    assert not flags, "Cash is not in the whitelist -- zero should not flag"


def test_zero_among_nonzero_total_debt_not_checked():
    pts = _zero_series("Total Debt")
    flags = _check_zero_among_nonzero("Total Debt", pts)
    assert not flags, "Total Debt is not in the whitelist -- zero should not flag"


def test_zero_among_nonzero_no_flag_when_all_zero():
    # If every period is zero there is nothing suspicious
    pts = [_dp(0, end="2021-12-31"), _dp(0, end="2022-12-31"), _dp(0, end="2023-12-31")]
    flags = _check_zero_among_nonzero("Revenue", pts)
    assert not flags, "All-zero series should not flag"


def test_zero_among_nonzero_no_flag_when_tiny_median():
    # Median below $1000 -- trivially small values, skip
    pts = [_dp(500), _dp(700), _dp(0)]
    flags = _check_zero_among_nonzero("Revenue", pts)
    assert not flags, "Tiny median (below $1000) should not flag"


# ---------------------------------------------------------------------------
# 5. EPS Reconciliation
# ---------------------------------------------------------------------------

def _eps_pts(ni, shares, eps, end="2023-12-31", start="2023-01-01"):
    ni_pts = [_dp(ni, end=end, start=start)]
    sh_pts = [_dp(shares, end=end, start=start)]
    eps_pts = [_dp(eps, end=end, start=start)]
    return ni_pts, sh_pts, eps_pts


def test_eps_reconciliation_flagged():
    # NI=1B, Shares=1B -> computed EPS=1.00 but reported=2.00 (100% off)
    ni_pts, sh_pts, eps_pts = _eps_pts(1_000_000_000, 1_000_000_000, 2.00)
    flags = _check_eps_reconciliation(ni_pts, sh_pts, eps_pts)
    assert _flags_of_type(flags, FLAG_EPS_RECONCILIATION), \
        "100% EPS discrepancy should flag"


def test_eps_reconciliation_passes():
    # NI=100M, Shares=50M -> computed EPS=2.00, reported=2.00
    ni_pts, sh_pts, eps_pts = _eps_pts(100_000_000, 50_000_000, 2.00)
    flags = _check_eps_reconciliation(ni_pts, sh_pts, eps_pts)
    assert not flags, "Matching EPS should not flag"


def test_eps_reconciliation_passes_within_5pct():
    # computed=2.00, reported=2.05 -> 2.4% difference (within 5% tolerance)
    ni_pts, sh_pts, eps_pts = _eps_pts(100_000_000, 50_000_000, 2.05)
    flags = _check_eps_reconciliation(ni_pts, sh_pts, eps_pts)
    assert not flags, "2.4% EPS difference is within tolerance"


def test_eps_reconciliation_flagged_above_5pct():
    # computed=2.00, reported=2.20 -> 10% difference
    ni_pts, sh_pts, eps_pts = _eps_pts(100_000_000, 50_000_000, 2.20)
    flags = _check_eps_reconciliation(ni_pts, sh_pts, eps_pts)
    assert _flags_of_type(flags, FLAG_EPS_RECONCILIATION), \
        "10% EPS discrepancy should flag"


def test_eps_reconciliation_skipped_missing_shares():
    ni_pts = [_dp(100_000_000)]
    sh_pts = []
    eps_pts = [_dp(2.00)]
    flags = _check_eps_reconciliation(ni_pts, sh_pts, eps_pts)
    assert not flags, "Missing shares should skip the check"


def test_eps_reconciliation_skipped_missing_eps():
    ni_pts = [_dp(100_000_000)]
    sh_pts = [_dp(50_000_000)]
    eps_pts = []
    flags = _check_eps_reconciliation(ni_pts, sh_pts, eps_pts)
    assert not flags, "Missing reported EPS should skip the check"


def test_eps_reconciliation_skipped_zero_reported_eps():
    ni_pts, sh_pts, eps_pts = _eps_pts(100_000_000, 50_000_000, 0.0)
    flags = _check_eps_reconciliation(ni_pts, sh_pts, eps_pts)
    assert not flags, "Zero reported EPS skips division"


# ---------------------------------------------------------------------------
# 6. Large YoY Change
# ---------------------------------------------------------------------------

def _annual_series(values_by_year):
    """Build FY data points for YoY tests. values_by_year is {year: value}."""
    return [
        _dp(value, end=f"{year}-12-31", start=f"{year}-01-01", fiscal_period="FY")
        for year, value in sorted(values_by_year.items())
    ]


def test_large_yoy_change_flagged():
    # Revenue goes from 100M to 700M in one year (600% change)
    pts = _annual_series({2022: 100_000_000, 2023: 700_000_000})
    flags = _check_large_yoy_change("Revenue", pts)
    assert _flags_of_type(flags, FLAG_LARGE_YOY_CHANGE), \
        "600% YoY change should flag"


def test_large_yoy_change_not_flagged_normal():
    # Revenue grows 30% -- normal
    pts = _annual_series({2022: 100_000_000, 2023: 130_000_000})
    flags = _check_large_yoy_change("Revenue", pts)
    assert not flags, "30% YoY change should not flag"


def test_large_yoy_change_not_flagged_exactly_at_threshold():
    # Exactly 500% change (5x) is the boundary -- flag only fires ABOVE threshold
    pts = _annual_series({2022: 100_000_000, 2023: 600_000_000})
    flags = _check_large_yoy_change("Revenue", pts)
    assert not flags, "Exactly 500% (5x) is the threshold boundary and should not flag"


def test_large_yoy_change_flagged_above_threshold():
    # 501% change
    pts = _annual_series({2022: 100_000_000, 2023: 601_000_000})
    flags = _check_large_yoy_change("Revenue", pts)
    assert _flags_of_type(flags, FLAG_LARGE_YOY_CHANGE), \
        "501% YoY change should flag"


def test_large_yoy_change_skipped_non_consecutive_years():
    # Gap is 2 years (2021 -> 2023) -- 730 days, outside 300-425 day window
    pts = _annual_series({2021: 100_000_000, 2023: 700_000_000})
    flags = _check_large_yoy_change("Revenue", pts)
    assert not flags, "Non-consecutive periods (2-year gap) should not flag"


def test_large_yoy_change_skipped_when_prev_is_zero():
    pts = _annual_series({2022: 0, 2023: 700_000_000})
    flags = _check_large_yoy_change("Revenue", pts)
    assert not flags, "Zero prior value should skip YoY ratio (division by zero guard)"


def test_large_yoy_change_negative_values():
    # Net income goes from -10M to -100M (900% worsening)
    pts = _annual_series({2022: -10_000_000, 2023: -100_000_000})
    flags = _check_large_yoy_change("Net Income", pts)
    assert _flags_of_type(flags, FLAG_LARGE_YOY_CHANGE), \
        "900% worsening net loss should flag"


def test_large_yoy_change_skipped_non_fy():
    # Quarterly data mixed in -- only FY periods should be compared
    pts = [
        _dp(100_000_000, end="2022-12-31", start="2022-01-01", fiscal_period="FY"),
        _dp(700_000_000, end="2023-03-31", start="2023-01-01", fiscal_period="Q1"),
    ]
    flags = _check_large_yoy_change("Revenue", pts)
    assert not flags, "Non-FY periods should not be compared"


# ---------------------------------------------------------------------------
# 7. Missing Critical Data
# ---------------------------------------------------------------------------

def _deduped(items_dict):
    """Build a minimal deduped_line_items structure."""
    return {
        name: {"data": dps, "tag_used": None}
        for name, dps in items_dict.items()
    }


def test_missing_critical_data_flagged():
    # Annual data exists (Total Assets has FY points) but Revenue and Net Income are absent
    deduped = _deduped({
        "Total Assets": [_dp(500_000_000)],
        "Revenue": [],
        "Net Income": [],
    })
    flags = _check_missing_critical_data(deduped)
    assert _flags_of_type(flags, FLAG_MISSING_CRITICAL_DATA), \
        "Annual data present but no Revenue/NI should flag"


def test_missing_critical_data_not_flagged_when_revenue_present():
    deduped = _deduped({
        "Total Assets": [_dp(500_000_000)],
        "Revenue": [_dp(200_000_000)],
        "Net Income": [],
    })
    flags = _check_missing_critical_data(deduped)
    assert not flags, "Revenue present -- missing NI alone should not trigger this flag"


def test_missing_critical_data_not_flagged_when_net_income_present():
    deduped = _deduped({
        "Total Assets": [_dp(500_000_000)],
        "Revenue": [],
        "Net Income": [_dp(50_000_000)],
    })
    flags = _check_missing_critical_data(deduped)
    assert not flags, "Net Income present -- missing Revenue alone should not trigger this flag"


def test_missing_critical_data_not_flagged_when_no_annual_data():
    # No FY periods anywhere -- probably a bad CIK or company with no 10-Ks
    deduped = _deduped({
        "Total Assets": [],
        "Revenue": [],
        "Net Income": [],
    })
    flags = _check_missing_critical_data(deduped)
    assert not flags, "No annual data at all -- skip the check entirely"


def test_missing_critical_data_not_flagged_when_only_quarterly():
    # Only Q1/Q2/Q3 data, no FY -- should not flag
    deduped = _deduped({
        "Total Assets": [_dp(500_000_000, fiscal_period="Q1")],
        "Revenue": [],
        "Net Income": [],
    })
    flags = _check_missing_critical_data(deduped)
    assert not flags, "Only quarterly data -- annual check should not fire"
