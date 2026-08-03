"""test_real_filings.py -- the registry and the resolver against a real filing.

Every other test in this suite builds its own data points. These read a real
companyfacts payload and assert real numbers off a real 10-K, which is the only
way to catch a chain that is plausible but wrong.

The fixture is Apple, CIK 320193, trimmed to the registry's tags. Regenerate it
with:

    python scripts/make_fixture.py 320193

Regenerating adds newly filed years and can restate old ones, so the assertions
here name specific fiscal years and never depend on how many years the file
holds. No test in this module touches the network.

Values are checked against Apple's FY2023 Form 10-K for the fiscal year ended
30 September 2023, in whole dollars as EDGAR reports them.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import line_items
import peer_comparison as pc
import xbrl_extractor as xbrl

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "cik320193.json")

# Apple's FY2023 ended 30 September 2023; FY2018 on 29 September 2018.
FY2023_END = "2023-09-30"
FY2018_END = "2018-09-29"
FY2019_END = "2019-09-28"

MILLION = 1_000_000


@pytest.fixture(scope="module")
def apple_facts():
    with open(FIXTURE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def apple_deduped(apple_facts):
    """The 14 displayed items, resolved and deduplicated -- what the UI renders."""
    return xbrl.deduplicate_all_line_items(xbrl.extract_all_line_items(apple_facts))


def annual_value(facts, line_item, period_end):
    """Resolve one line item and return its value for one full-year period.

    Returns None when the filer reports nothing for that period, which is the
    distinction the whole provenance model rests on: missing is not zero.
    """
    data, _tag = xbrl.resolve_line_item(facts, line_item)
    for dp in xbrl.deduplicate_period(data):
        if dp.get("end") == period_end and xbrl._is_annual_period(dp):
            return dp.get("value")
    return None


def annual_points(facts, line_item):
    data, _tag = xbrl.resolve_line_item(facts, line_item)
    return [dp for dp in xbrl.deduplicate_period(data) if xbrl._is_annual_period(dp)]


# ---------------------------------------------------------------------------
# The fixture itself
# ---------------------------------------------------------------------------

def test_fixture_is_apple(apple_facts):
    assert apple_facts["entityName"] == "Apple Inc."
    assert apple_facts["cik"] == 320193


def test_fixture_holds_nothing_outside_the_registry(apple_facts):
    """The trim is by tag, so anything here must be a tag the registry reads."""
    known = set()
    for item in line_items.REGISTRY.values():
        known.update(item.tags)
    known.update(line_items.DA_COMPONENT_TAGS)

    extra = set(apple_facts["facts"]["us-gaap"]) - known
    assert not extra, "fixture holds tags the registry never reads: {}".format(extra)


def test_fixture_records_how_it_was_made(apple_facts):
    """A committed data file that cannot say where it came from is not evidence."""
    meta = apple_facts["_fixture"]
    assert meta["generator"] == "scripts/make_fixture.py"
    assert "CIK0000320193" in meta["source_url"]
    assert meta["retrieved"]


# ---------------------------------------------------------------------------
# Real FY2023 numbers, straight off the 10-K
# ---------------------------------------------------------------------------

# Line item -> the figure Apple's FY2023 10-K reports, in millions.
FY2023_10K = {
    "Revenue": 383_285,
    "Cost of Revenue": 214_137,
    "Gross Profit": 169_148,
    "Operating Income": 114_301,
    "Net Income": 96_995,
    "Total Assets": 352_583,
    "Total Liabilities": 290_437,
    "Total Equity": 62_146,
    "Cash and Equivalents": 29_965,
    "Long-Term Debt": 95_281,
}


@pytest.mark.parametrize("line_item,millions", sorted(FY2023_10K.items()))
def test_fy2023_matches_the_10k(apple_facts, line_item, millions):
    assert annual_value(apple_facts, line_item, FY2023_END) == millions * MILLION


def test_fy2023_per_share_and_share_counts_match_the_10k(apple_facts):
    assert annual_value(apple_facts, "EPS Basic", FY2023_END) == 6.16
    assert annual_value(apple_facts, "EPS Diluted", FY2023_END) == 6.13
    assert annual_value(apple_facts, "Shares Outstanding (Basic)", FY2023_END) == 15_744_231_000
    assert annual_value(apple_facts, "Shares Outstanding (Diluted)", FY2023_END) == 15_812_547_000


def test_fy2023_cash_flow_items_match_the_10k(apple_facts):
    """None of these are in TAG_MAP; they resolve straight out of the registry."""
    assert annual_value(apple_facts, "Cash from Operations", FY2023_END) == 110_543 * MILLION
    assert annual_value(apple_facts, "Capex", FY2023_END) == 10_959 * MILLION
    assert annual_value(apple_facts, "Stock-Based Compensation", FY2023_END) == 10_833 * MILLION
    assert annual_value(apple_facts, "Buybacks", FY2023_END) == 77_550 * MILLION


def test_fy2023_balance_sheet_balances(apple_facts):
    """Assets = Liabilities + Equity on the real numbers, exactly, not within 5%."""
    assets = annual_value(apple_facts, "Total Assets", FY2023_END)
    liabilities = annual_value(apple_facts, "Total Liabilities", FY2023_END)
    equity = annual_value(apple_facts, "Total Equity", FY2023_END)
    assert assets == liabilities + equity


# ---------------------------------------------------------------------------
# History is no longer truncated at the tag switch
# ---------------------------------------------------------------------------

def test_the_new_revenue_tag_alone_stops_at_fy2017(apple_facts):
    """The reason winner-takes-all truncated Apple, stated as a fact about the data.

    RevenueFromContractWithCustomerExcludingAssessedTax is the tag whose most
    recent annual value is newest, so the old resolver picked it and used it for
    the whole history. It reaches back only as far as the comparatives Apple
    carried into its FY2019 10-K: FY2017. Every year before that was in the same
    companyfacts response and got dropped anyway.
    """
    new_tag_only = xbrl._extract_tag_data(
        apple_facts, "RevenueFromContractWithCustomerExcludingAssessedTax")
    annual_ends = {dp["end"] for dp in new_tag_only if xbrl._is_annual_period(dp)}

    assert min(annual_ends) == "2017-09-30"
    assert "2016-09-24" not in annual_ends
    assert "2010-09-25" not in annual_ends


def test_revenue_history_survives_both_tag_switches(apple_facts):
    """Apple's revenue row spans three tag eras and loses no year to the seams."""
    points = annual_points(apple_facts, "Revenue")
    by_end = {dp["end"]: dp for dp in points}

    # FY2010 and FY2016 predate the tag the old resolver would have picked.
    assert by_end["2010-09-25"]["value"] == 65_225 * MILLION
    assert by_end["2010-09-25"]["tag"] == "SalesRevenueNet"
    assert by_end["2016-09-24"]["value"] == 215_639 * MILLION
    assert by_end["2016-09-24"]["tag"] == "Revenues"
    assert by_end[FY2018_END]["value"] == 265_595 * MILLION
    assert by_end[FY2018_END]["tag"] == "Revenues"

    # Unbroken from FY2007 to the newest year in the fixture.
    assert min(by_end) == "2007-09-29"
    assert len(points) >= 19


def test_stitching_prefers_the_earlier_tag_in_the_chain(apple_facts):
    """FY2016 is reported by two tags; chain order decides, not filing date.

    Both tags report 215,639 for FY2016, so preferring chain position costs
    nothing here. Where two tags disagree the choice would matter, which is why
    every overlap gets checked against a fixture rather than assumed benign.
    """
    chain = line_items.tags_for("Revenue")
    assert chain.index("Revenues") < chain.index("SalesRevenueNet")

    overlapping = {}
    for tag in ("Revenues", "SalesRevenueNet"):
        for dp in xbrl._extract_tag_data(apple_facts, tag):
            if xbrl._is_annual_period(dp) and dp["end"] == "2016-09-24":
                overlapping[tag] = dp["value"]
    assert set(overlapping) == {"Revenues", "SalesRevenueNet"}
    assert overlapping["Revenues"] == overlapping["SalesRevenueNet"] == 215_639 * MILLION

    by_end = {dp["end"]: dp for dp in annual_points(apple_facts, "Revenue")}
    assert by_end["2016-09-24"]["tag"] == "Revenues"


def test_a_restatement_beats_the_original_within_one_tag(apple_facts):
    """Apple's January 2010 10-K/A restated FY2007 upward; the row shows the restatement."""
    original = [dp for dp in xbrl._extract_tag_data(apple_facts, "SalesRevenueNet")
                if xbrl._is_annual_period(dp) and dp["end"] == "2007-09-29"
                and dp["form"] == "10-K"]
    assert original and original[0]["value"] == 24_006 * MILLION

    assert annual_value(apple_facts, "Revenue", "2007-09-29") == 24_578 * MILLION


# ---------------------------------------------------------------------------
# The seam is visible
# ---------------------------------------------------------------------------

def _tag_transitions(flags, line_item):
    return [f for f in flags.get(line_item, [])
            if f["flag_type"] == xbrl.FLAG_TAG_TRANSITION]


def test_the_fy2018_revenue_seam_is_flagged(apple_deduped):
    """Apple left Revenues after FY2018; the first year of the new tag says so."""
    flags = xbrl.validate_financials(apple_deduped)
    seams = {f["period_end"]: f for f in _tag_transitions(flags, "Revenue")}

    assert FY2019_END in seams
    seam = seams[FY2019_END]
    assert seam["details"]["previous_period_end"] == FY2018_END
    assert seam["details"]["previous_tag"] == "Revenues"
    assert seam["details"]["current_tag"] == (
        "RevenueFromContractWithCustomerExcludingAssessedTax")
    assert "switches XBRL tag" in seam["message"]


def test_a_row_that_never_changed_tag_carries_no_seam(apple_deduped):
    """The flag has to be quiet where nothing happened, or it means nothing."""
    flags = xbrl.validate_financials(apple_deduped)
    assert _tag_transitions(flags, "Net Income") == []
    assert _tag_transitions(flags, "Total Assets") == []


# ---------------------------------------------------------------------------
# D&A comes off the cash flow statement
# ---------------------------------------------------------------------------

def test_d_and_a_resolves_from_the_cash_flow_statement(apple_facts):
    """The design rule: D&A is read where filers actually tag it.

    On the income statement it is buried inside cost of sales and operating
    expenses. Apple tags no income-statement depreciation line at all; the
    figure lives in the cash flow statement's add-backs.
    """
    entry = line_items.REGISTRY["D&A"]
    assert entry.statement == line_items.STATEMENT_CF
    assert entry.tags[0] == "DepreciationDepletionAndAmortization"

    data, tag_used = xbrl.resolve_line_item(apple_facts, "D&A")
    assert tag_used == "DepreciationDepletionAndAmortization"
    assert annual_value(apple_facts, "D&A", FY2023_END) == 11_519 * MILLION


def test_d_and_a_is_not_one_of_the_displayed_items(apple_deduped):
    """Registry superset, unchanged UI: D&A resolves but no existing view shows it."""
    assert "D&A" in line_items.REGISTRY
    assert "D&A" not in line_items.TAG_MAP
    assert "D&A" not in apple_deduped


# ---------------------------------------------------------------------------
# Missing stays missing
# ---------------------------------------------------------------------------

def test_an_untagged_item_comes_back_absent_not_zero(apple_facts):
    """Apple reports no goodwill or intangibles for FY2023. Absent, not zero."""
    assert annual_value(apple_facts, "Goodwill", FY2023_END) is None
    assert annual_value(apple_facts, "Intangibles", FY2023_END) is None


def test_a_chain_falls_through_to_the_first_tag_the_filer_uses(apple_facts):
    """Apple tags no CostOfRevenue at all, so the second link in the chain carries it."""
    assert line_items.tags_for("Cost of Revenue")[0] == "CostOfRevenue"
    assert "CostOfRevenue" not in apple_facts["facts"]["us-gaap"]

    data, tag_used = xbrl.resolve_line_item(apple_facts, "Cost of Revenue")
    assert tag_used == "CostOfGoodsAndServicesSold"
    assert data


# ---------------------------------------------------------------------------
# Derivations on real numbers
# ---------------------------------------------------------------------------

def test_ebitda_derives_from_real_fy2023_figures(apple_facts):
    values = {
        "Operating Income": annual_value(apple_facts, "Operating Income", FY2023_END),
        "D&A": annual_value(apple_facts, "D&A", FY2023_END),
    }
    assert line_items.derive("EBITDA", values) == (114_301 + 11_519) * MILLION


def test_total_debt_sums_both_components_and_still_misses_commercial_paper(apple_facts):
    """The sum is right; its inputs are only as complete as the filer's tagging.

    Apple's FY2023 balance sheet carries $5,985M of commercial paper, and Apple
    does not tag DebtCurrent. The Short-Term Debt chain falls through to
    LongTermDebtCurrent, which is current maturities only, so the derived total
    is short by exactly the commercial paper. Recorded here rather than papered
    over: closing the gap needs a summed derivation, not a chain reorder, and
    that is a Session 4 decision.
    """
    short_term = annual_value(apple_facts, "Short-Term Debt", FY2023_END)
    long_term = annual_value(apple_facts, "Long-Term Debt", FY2023_END)
    assert short_term == 9_822 * MILLION
    assert long_term == 95_281 * MILLION

    total = line_items.derive("Total Debt", {
        "Short-Term Debt": short_term, "Long-Term Debt": long_term,
    })
    assert total == short_term + long_term
    assert total == 105_103 * MILLION

    commercial_paper = 5_985 * MILLION
    assert total + commercial_paper == 111_088 * MILLION


# ---------------------------------------------------------------------------
# Peer comparison keeps working
# ---------------------------------------------------------------------------

def test_peer_comparison_reads_the_same_stitched_series(apple_facts, monkeypatch):
    """Both paths run through resolve_line_item, so both gained the same history."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: apple_facts)

    result = pc.fetch_peer_data("320193", ["Revenue", "Net Income"], n_periods=10)

    assert result["name"] == "Apple Inc."
    revenue = result["line_items"]["Revenue"]
    assert revenue["tag_used"] == "RevenueFromContractWithCustomerExcludingAssessedTax"

    by_end = {p["period_end"]: p for p in revenue["periods"]}
    assert by_end[FY2023_END]["value"] == 383_285 * MILLION
    assert by_end[FY2018_END]["value"] == 265_595 * MILLION
    assert by_end[FY2018_END]["source_tag"] == "Revenues"
