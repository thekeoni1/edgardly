"""Stage 1 integration tests for peer_comparison module.

Tests make real EDGAR API calls and are marked @pytest.mark.integration.

Run:
    python -m pytest tests/test_peer_comparison_stage1.py -v -m integration -s
"""

import time
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from peer_comparison import fetch_peer_data, fetch_peer_comparison

# -------------------------------------------------------------------------
# Test companies
# -------------------------------------------------------------------------
APPLE     = "320193"   # FYE: late September
MICROSOFT = "789019"   # FYE: late June
ALPHABET  = "1652044"  # FYE: late December  (Google)
JPMORGAN  = "19617"    # FYE: December; bank -- does not report Cost of Revenue

CORE_ITEMS = ["Revenue", "Net Income", "Total Assets"]


# -------------------------------------------------------------------------
# Test 1 -- three-company fetch, core line items
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_three_companies_return_all_data():
    """Fetch Apple, Microsoft, Alphabet for 3 core items over 3 periods."""
    result = fetch_peer_comparison(
        [APPLE, MICROSOFT, ALPHABET], CORE_ITEMS, n_periods=3
    )

    assert len(result["companies"]) == 3, "Should return exactly 3 company results"
    assert result["line_items"] == CORE_ITEMS
    assert result["n_periods"] == 3

    for company in result["companies"]:
        assert company["name"], "Entity name must not be empty"
        assert company["cik"]

        for li in CORE_ITEMS:
            assert li in company["line_items"], (
                f"{company['name']}: line item '{li}' missing from result"
            )
            item = company["line_items"][li]

            # tag_used must be non-None for items all three companies report
            assert item["tag_used"] is not None, (
                f"{company['name']} / {li}: tag_used should not be None"
            )

            periods = item["periods"]
            assert 1 <= len(periods) <= 3, (
                f"{company['name']} / {li}: expected 1-3 periods, got {len(periods)}"
            )

            # Newest-first relative labels
            for i, p in enumerate(periods):
                expected = "FY0" if i == 0 else "FY-{}".format(i)
                assert p["relative_period"] == expected, (
                    f"{company['name']} / {li}: period {i} label should be "
                    f"'{expected}', got '{p['relative_period']}'"
                )
                assert p["period_end"], "period_end must be a non-empty date string"

            # At least FY0 must have an actual value
            fy0 = periods[0]
            assert fy0["value"] is not None, (
                f"{company['name']} / {li}: FY0 value must not be None"
            )
            # source_tag in FY0 must match or be consistent with tag_used
            assert fy0["source_tag"] is not None, (
                f"{company['name']} / {li}: FY0 source_tag must not be None"
            )

        print(f"\n--- {company['name']} (CIK {company['cik']}) ---")
        for li in CORE_ITEMS:
            item = company["line_items"][li]
            print(f"  {li}  [tag: {item['tag_used']}]")
            for p in item["periods"]:
                flags = [f["flag_type"] for f in p["flags"]]
                flag_str = "  FLAGS: " + ", ".join(flags) if flags else ""
                print(
                    f"    {p['relative_period']} ({p['period_end']}): "
                    f"{p['value']}{flag_str}"
                )


# -------------------------------------------------------------------------
# Test 2 -- rate limiting timing
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_rate_limiting_respected():
    """
    Three companies = 3 API calls with 0.1 s minimum per call.
    Total elapsed must be >= 0.3 s.
    """
    start = time.time()
    fetch_peer_comparison([APPLE, MICROSOFT, ALPHABET], ["Revenue"], n_periods=1)
    elapsed = time.time() - start

    print(f"\nElapsed for 3-company fetch: {elapsed:.2f}s")
    assert elapsed >= 0.3, (
        f"Expected >= 0.3 s (3 calls * 0.1 s minimum) but got {elapsed:.2f}s"
    )


# -------------------------------------------------------------------------
# Test 3 -- different fiscal year-ends produce distinct FY0 dates
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_different_fiscal_year_ends():
    """
    Apple (Sept), Microsoft (June), Alphabet (Dec) must have distinct FY0 dates
    that match the known month of each company's fiscal year-end.
    """
    result = fetch_peer_comparison(
        [APPLE, MICROSOFT, ALPHABET], ["Revenue"], n_periods=3
    )

    by_cik = {c["cik"]: c for c in result["companies"]}

    def fy0_end(cik):
        periods = by_cik[cik]["line_items"]["Revenue"]["periods"]
        assert periods, f"CIK {cik} should have at least one Revenue period"
        return periods[0]["period_end"]

    apple_end  = fy0_end(APPLE)
    msft_end   = fy0_end(MICROSOFT)
    alpha_end  = fy0_end(ALPHABET)

    print(f"\nFY0 period_end dates:")
    print(f"  Apple     ({APPLE}):    {apple_end}")
    print(f"  Microsoft ({MICROSOFT}): {msft_end}")
    print(f"  Alphabet  ({ALPHABET}):  {alpha_end}")

    # All three must be distinct (different fiscal year-end calendars)
    assert len({apple_end, msft_end, alpha_end}) == 3, (
        "Apple, Microsoft, and Alphabet must have different FY0 end dates"
    )

    # Apple FYE: September (month 09)
    assert apple_end[5:7] == "09", (
        f"Apple FY should end in September but got month {apple_end[5:7]} ({apple_end})"
    )

    # Microsoft FYE: June (month 06)
    assert msft_end[5:7] == "06", (
        f"Microsoft FY should end in June but got month {msft_end[5:7]} ({msft_end})"
    )

    # Alphabet FYE: December (month 12)
    assert alpha_end[5:7] == "12", (
        f"Alphabet FY should end in December but got month {alpha_end[5:7]} ({alpha_end})"
    )

    # Confirm each company has at least 2 historical periods in the result
    for cik, name in [(APPLE, "Apple"), (MICROSOFT, "Microsoft"), (ALPHABET, "Alphabet")]:
        periods = by_cik[cik]["line_items"]["Revenue"]["periods"]
        assert len(periods) >= 2, f"{name} should have at least 2 Revenue periods"
        # Labels must be sequential
        for i, p in enumerate(periods):
            expected = "FY0" if i == 0 else "FY-{}".format(i)
            assert p["relative_period"] == expected


# -------------------------------------------------------------------------
# Test 4 -- missing line item returns None (not 0 or absent)
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_missing_line_item_returns_none():
    """
    JPMorgan Chase (CIK 19617) is a bank and does not report Cost of Revenue
    (no CostOfRevenue / CostOfGoodsAndServicesSold tag in its XBRL).
    All periods for that item must carry value=None and source_tag=None.
    """
    result = fetch_peer_data(JPMORGAN, ["Revenue", "Cost of Revenue"], n_periods=3)

    print(f"\nJPMorgan name: {result['name']}")
    cogs = result["line_items"]["Cost of Revenue"]
    rev  = result["line_items"]["Revenue"]

    print(f"  Revenue  tag_used: {rev['tag_used']}")
    print(f"  Revenue  FY0 value: {rev['periods'][0]['value'] if rev['periods'] else 'no periods'}")

    print(f"  Cost of Revenue  tag_used: {cogs['tag_used']}")
    print(f"  Cost of Revenue  periods:")
    for p in cogs["periods"]:
        print(f"    {p['relative_period']} ({p['period_end']}): value={p['value']}, tag={p['source_tag']}")

    # Revenue must be present (confirms fetch succeeded)
    assert rev["periods"], "JPMorgan Revenue should have at least one period"
    assert rev["periods"][0]["value"] is not None, "JPMorgan Revenue FY0 value must not be None"

    # Cost of Revenue must be absent (all None) for a bank
    for p in cogs["periods"]:
        assert p["value"] is None, (
            f"JPMorgan Cost of Revenue should be None for period "
            f"{p['period_end']} but got {p['value']}"
        )
        assert p["source_tag"] is None, (
            f"JPMorgan Cost of Revenue source_tag should be None but got {p['source_tag']}"
        )
