"""Stage 2 tests for peer_comparison.select_peer_scale.

Unit tests (no API calls) cover all scale-selection branches.
Integration tests (marked @pytest.mark.integration) confirm the full
fetch → scale pipeline with real EDGAR data.

Run unit tests:
    python -m pytest tests/test_peer_comparison_stage2.py -v
Run integration tests:
    python -m pytest tests/test_peer_comparison_stage2.py -v -m integration -s
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from peer_comparison import fetch_peer_comparison, select_peer_scale

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _make_result(companies_spec, line_items=None, n_periods=1):
    """
    Build a minimal comparison_result dict for unit-testing select_peer_scale.

    companies_spec: list of dicts with keys:
        "name", "cik",
        "revenue"  (FY0 value, or None),
        "assets"   (FY0 value, or None),
        "diluted_shares" (FY0 value, or None)
    """
    companies = []
    for spec in companies_spec:
        def _periods(val):
            return [{"relative_period": "FY0", "period_end": "2025-12-31",
                     "period_start": None, "value": val, "source_tag": None, "flags": []}]

        companies.append({
            "name": spec.get("name", "Test Co"),
            "cik": spec.get("cik", "000000"),
            "line_items": {
                "Revenue": {
                    "tag_used": "Revenues" if spec.get("revenue") is not None else None,
                    "periods": _periods(spec.get("revenue")),
                },
                "Total Assets": {
                    "tag_used": "Assets" if spec.get("assets") is not None else None,
                    "periods": _periods(spec.get("assets")),
                },
                "Shares Outstanding (Diluted)": {
                    "tag_used": None,
                    "periods": _periods(spec.get("diluted_shares")),
                },
            },
        })
    return {
        "companies": companies,
        "line_items": list(companies[0]["line_items"]) if companies else [],
        "n_periods": n_periods,
    }


# -------------------------------------------------------------------------
# Unit Test 1 -- large-cap set confirms $mm scale
# -------------------------------------------------------------------------

def test_large_cap_scale_is_millions():
    """
    All three companies have > $1 B revenue.  The largest (Apple $416 B)
    drives the table to $mm scale.  Verified both dollar and share labels.
    """
    result = _make_result([
        {"name": "Apple",     "cik": "320193",  "revenue": 416_000_000_000, "diluted_shares": 15_100_000_000},
        {"name": "Microsoft", "cik": "789019",  "revenue": 282_000_000_000, "diluted_shares": 7_400_000_000},
        {"name": "Alphabet",  "cik": "1652044", "revenue": 403_000_000_000, "diluted_shares": 12_200_000_000},
    ])
    scale = select_peer_scale(result)

    assert scale["dollar_factor"] == 1_000_000, (
        f"Expected dollar_factor=1_000_000 ($mm) for large-cap set, got {scale['dollar_factor']}"
    )
    assert scale["dollar_label"] == "$mm"

    # All three have > 1 B shares → share scale should be mm
    assert scale["share_factor"] == 1_000_000
    assert scale["share_label"] == "mm"

    # Spot-check: Apple revenue in $mm = 416_000 (rounded)
    apple_rev_scaled = 416_000_000_000 / scale["dollar_factor"]
    assert apple_rev_scaled == 416_000.0


# -------------------------------------------------------------------------
# Unit Test 2 -- largest company drives scale even in a mixed set
# -------------------------------------------------------------------------

def test_largest_company_drives_scale_in_mixed_set():
    """
    A large-cap ($416 B revenue → $mm alone) is paired with a mid-cap
    ($400 M revenue → $000s alone).  The large-cap must win and the entire
    table must use $mm scale.  This proves the 'max across all companies'
    rule, not per-company scale.
    """
    result = _make_result([
        {"name": "Large Corp", "cik": "111111", "revenue": 416_000_000_000},
        {"name": "Mid Corp",   "cik": "222222", "revenue":     400_000_000},  # $400 M → $000s alone
    ])
    scale = select_peer_scale(result)

    # Large Corp's $416 B must drive the table to $mm
    assert scale["dollar_factor"] == 1_000_000, (
        "Large Corp's $416 B revenue should drive scale to $mm, "
        f"but got factor={scale['dollar_factor']} label='{scale['dollar_label']}'"
    )
    assert scale["dollar_label"] == "$mm"

    # Mid Corp's $400 M revenue expressed in $mm = 400 -- small but not zero
    mid_corp_scaled = 400_000_000 / scale["dollar_factor"]
    assert mid_corp_scaled == 400.0, (
        f"Mid Corp's revenue in $mm should be 400.0, got {mid_corp_scaled}"
    )


# -------------------------------------------------------------------------
# Additional unit tests covering other branches
# -------------------------------------------------------------------------

def test_thousands_scale_for_midcap_only():
    """A mid-cap ($500 M revenue) alone → $000s scale."""
    result = _make_result([{"revenue": 500_000_000}])
    scale = select_peer_scale(result)
    assert scale["dollar_factor"] == 1_000
    assert scale["dollar_label"] == "$000s"


def test_actual_scale_for_small_cap():
    """A tiny company ($5 M revenue) → actual $ scale (factor=1)."""
    result = _make_result([{"revenue": 5_000_000}])
    scale = select_peer_scale(result)
    assert scale["dollar_factor"] == 1
    assert scale["dollar_label"] == "$"


def test_revenue_none_falls_back_to_total_assets():
    """If no company has FY0 Revenue, Total Assets drives the dollar scale."""
    result = _make_result([
        {"revenue": None, "assets": 350_000_000_000},  # > $1 B → $mm
    ])
    scale = select_peer_scale(result)
    assert scale["dollar_factor"] == 1_000_000
    assert scale["dollar_label"] == "$mm"


def test_share_scale_millions_when_above_1b():
    """Companies with > 1 B shares → share factor = 1_000_000 (mm)."""
    result = _make_result([
        {"revenue": 100_000_000_000, "diluted_shares": 2_000_000_000},   # 2 B shares
    ])
    scale = select_peer_scale(result)
    assert scale["share_factor"] == 1_000_000
    assert scale["share_label"] == "mm"


def test_share_scale_thousands_when_below_1b():
    """Companies with < 1 B shares → share factor = 1_000 (000s)."""
    result = _make_result([
        {"revenue": 100_000_000_000, "diluted_shares": 500_000_000},   # 500 M shares
    ])
    scale = select_peer_scale(result)
    assert scale["share_factor"] == 1_000
    assert scale["share_label"] == "000s"


def test_largest_share_count_drives_share_scale():
    """
    Mixed set: one company with < 1 B shares and one with > 1 B.
    The larger share count should drive the table to mm scale.
    """
    result = _make_result([
        {"revenue": 10_000_000_000, "diluted_shares":   300_000_000},  # 300 M → 000s alone
        {"revenue": 50_000_000_000, "diluted_shares": 2_000_000_000},  # 2 B → mm
    ])
    scale = select_peer_scale(result)
    assert scale["share_factor"] == 1_000_000
    assert scale["share_label"] == "mm"


def test_no_companies_returns_default():
    """Empty company list returns the large-cap default ($mm)."""
    result = {"companies": [], "line_items": [], "n_periods": 3}
    scale = select_peer_scale(result)
    assert scale["dollar_factor"] == 1_000_000
    assert scale["dollar_label"] == "$mm"


# -------------------------------------------------------------------------
# Integration Test 1 -- large-cap set with real EDGAR data
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_large_cap_integration_confirms_millions():
    """
    Fetch Apple, Microsoft, Alphabet from EDGAR and confirm $mm scale.
    """
    CIKS = ["320193", "789019", "1652044"]
    result = fetch_peer_comparison(CIKS, ["Revenue", "Total Assets",
                                          "Shares Outstanding (Diluted)"], n_periods=1)
    scale = select_peer_scale(result)

    print("\nIntegration scale result:", scale)
    for c in result["companies"]:
        rev = c["line_items"]["Revenue"]["periods"][0]["value"]
        print(f"  {c['name']}: Revenue FY0 = {rev:,}" if rev else f"  {c['name']}: Revenue = None")

    assert scale["dollar_factor"] == 1_000_000, (
        f"Expected $mm for Apple/MSFT/Alphabet, got {scale}"
    )
    assert scale["dollar_label"] == "$mm"
    # All three have billions of shares
    assert scale["share_factor"] == 1_000_000
    assert scale["share_label"] == "mm"


# -------------------------------------------------------------------------
# Integration Test 2 -- size-mismatch: largest drives scale
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_size_mismatch_largest_drives_scale():
    """
    Fetch real Apple data ($416 B revenue → $mm on its own) and pair it with
    a synthetic mid-cap company ($400 M revenue → $000s on its own).
    Verify that the combined table scale is $mm -- Apple's revenue wins.

    The 'largest drives scale' rule is the critical behavior: a small peer in
    the same comp set must NOT pull the scale down to $000s.
    """
    APPLE = "320193"
    apple_result = fetch_peer_comparison([APPLE], ["Revenue"], n_periods=1)
    apple_company = apple_result["companies"][0]
    apple_fy0_rev = apple_company["line_items"]["Revenue"]["periods"][0]["value"]

    print(f"\nApple FY0 Revenue (real EDGAR): {apple_fy0_rev:,}")
    assert apple_fy0_rev > 1_000_000_000, (
        f"Apple should have > $1 B revenue for this test to be meaningful; got {apple_fy0_rev:,}"
    )

    # Synthetic mid-cap peer: $400 M revenue → $000s on its own
    MID_CAP_REVENUE = 400_000_000
    mid_cap = {
        "name": "Mid Corp (synthetic)",
        "cik": "000000",
        "line_items": {
            "Revenue": {
                "tag_used": "Revenues",
                "periods": [{
                    "relative_period": "FY0",
                    "period_end": "2025-12-31",
                    "period_start": "2025-01-01",
                    "value": MID_CAP_REVENUE,
                    "source_tag": "Revenues",
                    "flags": [],
                }],
            }
        },
    }

    # Verify mid-cap alone would be $000s
    standalone_scale = select_peer_scale({
        "companies": [mid_cap], "line_items": ["Revenue"], "n_periods": 1,
    })
    print(f"Mid-cap standalone scale: {standalone_scale['dollar_label']}")
    assert standalone_scale["dollar_factor"] == 1_000, (
        f"Mid-cap ($400 M) alone should be $000s; got {standalone_scale}"
    )

    # Paired with Apple: Apple's $416 B must drive the table to $mm
    combined_result = {
        "companies": [apple_company, mid_cap],
        "line_items": ["Revenue"],
        "n_periods": 1,
    }
    combined_scale = select_peer_scale(combined_result)
    print(f"Combined (Apple + mid-cap $400M) scale: {combined_scale['dollar_label']}")

    assert combined_scale["dollar_factor"] == 1_000_000, (
        f"Apple's ${apple_fy0_rev // 1_000_000_000}B revenue should drive combined scale "
        f"to $mm even with a $000s peer; got {combined_scale}"
    )
    assert combined_scale["dollar_label"] == "$mm"
