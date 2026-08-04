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
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as flask_app
import edgar_api
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

# ---------------------------------------------------------------------------
# Provenance, end to end, on the real payload
# ---------------------------------------------------------------------------

@pytest.fixture
def apple_table(apple_facts, monkeypatch):
    """The table the UI renders and the exports write, FY2015 to FY2025."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: apple_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta",
                        lambda cik: {"sic": "3571", "sic_description": "Electronic Computers"})
    entity, columns, rows, scope = flask_app._build_xbrl_result(320193, 2015, 2025, "annual")
    return entity, columns, {row["line_item"]: row for row in rows}, scope


def test_every_apple_value_declares_a_state(apple_table):
    """The whole grid, 14 items by 11 years, with nothing unaccounted for.

    Every cell is reported. It was 147 of 154 until annual report forms were
    ranked above every other form: the other seven were balance-sheet instants
    whose FY label a later 10-Q had overwritten, and reading the label was the
    only reason they were holes (PROGRESS.md open question 3).
    """
    _entity, columns, rows, _scope = apple_table
    counts = {}
    for row in rows.values():
        for col in columns:
            state = row["cells"][col["key"]]["provenance"]["state"]
            counts[state] = counts.get(state, 0) + 1

    assert sum(counts.values()) == len(line_items.UI_LINE_ITEMS) * len(columns)
    assert counts["reported"] == 154
    assert counts.get("missing", 0) == 0
    assert counts.get("derived", 0) == 0      # Apple tags GrossProfit itself


def test_apples_fy2023_revenue_names_the_filing_it_came_from(apple_table):
    _entity, _columns, rows, _scope = apple_table
    prov = rows["Revenue"]["cells"][FY2023_END]["provenance"]

    assert prov["state"] == "reported"
    assert prov["tag"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert prov["form"] == "10-K"
    # Latest filed wins within a tag, so this value comes from a later 10-K
    # carrying FY2023 as a comparative, and the provenance says which one
    # rather than implying it came from the FY2023 filing.
    assert prov["accession"] == "0000320193-25-000079"
    assert prov["filed"] == "2025-10-31"


def test_one_apple_row_carries_three_different_tags(apple_table):
    """Provenance is per value: the revenue row spans three tag eras."""
    _entity, _columns, rows, _scope = apple_table
    revenue = rows["Revenue"]

    tags = {end: cell["provenance"]["tag"] for end, cell in revenue["cells"].items()}
    assert tags["2015-09-26"] == "SalesRevenueNet"
    assert tags[FY2018_END] == "Revenues"
    assert tags[FY2019_END] == "RevenueFromContractWithCustomerExcludingAssessedTax"

    assert revenue["tag_summary"] == (
        "SalesRevenueNet -> Revenues -> "
        "RevenueFromContractWithCustomerExcludingAssessedTax")


def test_the_seam_is_on_the_value_that_crosses_it(apple_table):
    """FY2019 is the first year reported only under the new tag."""
    _entity, _columns, rows, _scope = apple_table
    revenue = rows["Revenue"]["cells"]

    seams = [f for f in revenue[FY2019_END]["flags"]
             if f["type"] == xbrl.FLAG_TAG_TRANSITION]
    assert len(seams) == 1
    assert "switches XBRL tag" in seams[0]["msg"]
    assert revenue[FY2018_END]["flags"] == []


def test_apples_shadowed_year_end_balance_sheet_comes_back(apple_table, apple_facts):
    """PROGRESS.md open question 3, on the row it was found on.

    Apple's FY2025 total assets used to read "tagged, but not for a period
    Edgardly could confirm as FY2025" and point at the 10-K. Apple had tagged
    it in that 10-K all along: three later 10-Qs repeat the same instant as
    their comparative column, the last of them filed nine months after the
    10-K, and keeping the most recently filed entry meant the row inherited
    that filing's Q3 label. The value never moved, only the label did.
    """
    _entity, _columns, rows, _scope = apple_table
    cell = rows["Total Assets"]["cells"]["2025-09-27"]

    assert cell["value"] == 359_241 * MILLION
    prov = cell["provenance"]
    assert prov["state"] == "reported"
    assert prov["form"] == "10-K"
    assert prov["accession"] == "0000320193-25-000079"

    # The later filings that used to take the row are all still in the payload.
    shadows = [dp for dp in xbrl._extract_tag_data(apple_facts, "Assets")
               if dp["end"] == "2025-09-27" and dp["form"] == "10-Q"]
    assert [dp["fiscal_period"] for dp in shadows] == ["Q1", "Q2", "Q3"]
    assert all(dp["value"] == cell["value"] for dp in shadows)
    assert max(dp["filed"] for dp in shadows) > prov["filed"]


def test_apple_is_in_scope(apple_table):
    """A computer manufacturer that files us-gaap: nothing to refuse."""
    _entity, _columns, _rows, scope = apple_table
    assert scope["in_scope"] is True
    assert scope["message"] == ""
    assert scope["detail"]["taxonomies"] == ["dei", "us-gaap"]


# ---------------------------------------------------------------------------
# The Excel export carries it too
# ---------------------------------------------------------------------------

def test_the_source_tags_sheet_shows_apples_tags_period_by_period(apple_table):
    """PROGRESS.md open question 5: one tag_used per row could not say this."""
    openpyxl = pytest.importorskip("openpyxl")
    entity, columns, rows_by_item, _scope = apple_table
    rows = list(rows_by_item.values())

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "apple.xlsx")
        flask_app._xbrl_write_xlsx(path, entity, columns, rows, "annual")
        wb = openpyxl.load_workbook(path)

        assert "Source Tags" in wb.sheetnames
        ws = wb["Source Tags"]
        assert [ws.cell(1, ci).value for ci in range(1, 8)] == [
            "Line Item", "Period", "Source", "XBRL Tag", "Filed", "Accession", "Notes"]

        # Rows with a period are values; the last line is the legend.
        sheet = {(r[0], r[1]): r for r in ws.iter_rows(min_row=2, values_only=True)
                 if r[0] is not None and r[1] is not None}

        # One line per value, not one per row.
        assert len(sheet) == len(rows) * len(columns)

        assert sheet[("Revenue", "FY2018")][3] == "Revenues"
        assert sheet[("Revenue", "FY2019")][3] == (
            "RevenueFromContractWithCustomerExcludingAssessedTax")
        assert sheet[("Revenue", "FY2018")][5] == "0000320193-18-000145"
        assert "switches XBRL tag" in sheet[("Revenue", "FY2019")][6]

        # And the year a 10-Q's label used to cost this row is on the sheet,
        # named to the 10-K it was reported in.
        assets = sheet[("Total Assets", "FY2025")]
        assert assets[2] == "reported"
        assert assets[3] == "Assets"
        assert assets[5] == "0000320193-25-000079"


def test_reported_apple_values_are_written_in_the_reported_colour(apple_table):
    """The blue font finally means something: it marks the filer's own numbers."""
    openpyxl = pytest.importorskip("openpyxl")
    entity, columns, rows_by_item, _scope = apple_table
    rows = list(rows_by_item.values())

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "apple.xlsx")
        flask_app._xbrl_write_xlsx(path, entity, columns, rows, "annual")
        ws = openpyxl.load_workbook(path)["Financial Data"]

        by_label = {row[0].value: row for row in ws.iter_rows(min_row=4)}
        revenue = next(row for label, row in by_label.items()
                       if label and label.startswith("Revenue "))
        fy2023_col = 3 + [c["key"] for c in columns].index(FY2023_END)

        assert revenue[fy2023_col - 1].value == 383_285
        assert revenue[fy2023_col - 1].font.color.rgb.endswith("0066CC")


def test_the_csv_source_tag_column_names_every_tag_the_row_used(apple_table):
    import csv

    entity, columns, rows_by_item, _scope = apple_table
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "apple.csv")
        flask_app._xbrl_write_csv(path, entity, columns, list(rows_by_item.values()),
                                  "annual")
        with open(path, encoding="utf-8") as handle:
            table = {row[0].split(" (")[0]: row for row in csv.reader(handle)}

    assert table["Revenue"][1] == (
        "SalesRevenueNet -> Revenues -> "
        "RevenueFromContractWithCustomerExcludingAssessedTax")
    assert table["Net Income"][1] == "NetIncomeLoss"


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
