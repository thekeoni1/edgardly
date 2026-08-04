"""test_honeywell.py -- the filer that made the shadowing bug reproducible.

Honeywell International, CIK 773840, SIC 3724. Regenerate with:

    python scripts/make_fixture.py 773840

PROGRESS.md open question 3 was found here: Honeywell's 2025-12-31 year-end
balance sheet carries the fiscal-period label "Q2", because the 10-Q filed in
July 2026 repeats that instant as its comparative column and resolution kept
the most recently filed entry. The single-company table read the label and
dropped the year; the peer table anchored on dates and kept it. This module
holds both halves: what the payload actually contains, and what the table makes
of it.

Honeywell also settles two things no other fixture could. It reports no
LongTermDebtNoncurrent, so it is the filer that exercises the LongTermDebt
fallback in open question 1, and it tags no Liabilities at all, so its Total
Liabilities row is a real hole rather than a contrived one.

Values are checked against Honeywell's FY2025 Form 10-K for the year ended
31 December 2025, accession 0000773840-26-000013. No test here touches the
network.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as flask_app
import edgar_api
import line_items
import peer_comparison as pc
import periods
import xbrl_extractor as xbrl

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "cik773840.json")

FY2025_END = "2025-12-31"
FY2024_END = "2024-12-31"

MILLION = 1_000_000


@pytest.fixture(scope="module")
def honeywell_facts():
    with open(FIXTURE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def honeywell_quarters(honeywell_facts):
    """Every quarter end this filer confirms, mapped to the number it is given."""
    deduped = xbrl.deduplicate_all_line_items(
        xbrl.extract_all_line_items(honeywell_facts, list(xbrl.TAG_MAP)))
    return periods.period_ends(deduped, xbrl.TAG_MAP, periods.QUARTERLY)


@pytest.fixture
def honeywell_table(honeywell_facts, monkeypatch):
    """The table the UI renders, FY2015 to FY2025."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: honeywell_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta",
                        lambda cik: {"sic": "3724",
                                     "sic_description": "Aircraft Engines & Engine Parts"})
    entity, columns, rows, scope = flask_app._build_xbrl_result(773840, 2015, 2025, "annual")
    return entity, columns, {row["line_item"]: row for row in rows}, scope


# ---------------------------------------------------------------------------
# The fixture
# ---------------------------------------------------------------------------

def test_fixture_is_honeywell(honeywell_facts):
    assert honeywell_facts["entityName"] == "Honeywell International Inc"
    assert honeywell_facts["cik"] == 773840
    assert honeywell_facts["_fixture"]["company"]["sic"] == "3724"


def test_fixture_holds_nothing_outside_the_registry(honeywell_facts):
    known = set()
    for item in line_items.REGISTRY.values():
        known.update(item.tags)
    known.update(line_items.DA_COMPONENT_TAGS)
    known.update(line_items.SCOPE_HEURISTIC_TAGS)

    extra = set(honeywell_facts["facts"]["us-gaap"]) - known
    assert not extra, "fixture holds tags the registry never reads: {}".format(extra)


def test_an_aerospace_manufacturer_is_in_scope(honeywell_table):
    _entity, _columns, _rows, scope = honeywell_table
    assert scope["in_scope"] is True
    assert scope["message"] == ""


# ---------------------------------------------------------------------------
# The shadowing itself, in the payload
# ---------------------------------------------------------------------------

def test_a_later_10q_relabels_the_year_end_balance_sheet(honeywell_facts):
    """The bug, stated as a property of the data rather than of the code.

    One instant, four filings, one value. Honeywell's FY2025 10-K tagged total
    assets at 31 December 2025; the two 10-Qs that followed repeat the same
    instant as the comparative column of their own balance sheets, and EDGAR
    stamps the fiscal-period label on the filing rather than on the fact. So
    the most recently filed copy of Honeywell's year-end balance sheet is
    labeled Q2, and any rule that keeps the latest filing and then believes the
    label loses the entire fiscal year.
    """
    for_year_end = [dp for dp in xbrl._extract_tag_data(honeywell_facts, "Assets")
                    if dp["end"] == FY2025_END]

    assert {dp["value"] for dp in for_year_end} == {73_681 * MILLION}
    assert sorted((dp["form"], dp["fiscal_period"]) for dp in for_year_end) == [
        ("10-K", "FY"), ("10-Q", "Q1"), ("10-Q", "Q2")]

    latest = max(for_year_end, key=lambda dp: dp["filed"])
    assert latest["form"] == "10-Q"
    assert latest["fiscal_period"] == "Q2"
    assert latest["filed"] > "2026-02-17"      # the 10-K's own filing date


def test_the_annual_report_is_the_one_the_row_keeps(honeywell_facts):
    """And so the label the row inherits is the 10-K's own."""
    data, _tag = xbrl.resolve_line_item(honeywell_facts, "Total Assets")
    winner = next(dp for dp in xbrl.deduplicate_period(data)
                  if dp["end"] == FY2025_END)

    assert winner["form"] == "10-K"
    assert winner["fiscal_period"] == "FY"
    assert winner["accn"] == "0000773840-26-000013"


def test_a_third_quarter_a_filing_itself_called_the_second_is_numbered_third(
        honeywell_facts, honeywell_quarters):
    """fp is unreliable even where nothing borrowed it.

    Two filings report the quarter ended 30 September 2020. Its own 10-Q, filed
    that October, calls it Q3. The 10-Q filed a year later carries it as a
    comparative and is itself stamped Q2, which it is not either. Resolution
    keeps the later filing, so the label that reached the column was Q2 from a
    filing that was neither. Position between two fiscal year ends does not
    consult the label: 30 September is three quarters of the way through a
    calendar year, and that is the whole argument.
    """
    stamped = sorted((dp["filed"], dp["fiscal_period"])
                     for dp in xbrl._extract_tag_data(honeywell_facts,
                                                      "CostOfGoodsAndServicesSold")
                     if dp["end"] == "2020-09-30" and dp["start"] == "2020-07-01")

    assert stamped == [("2020-10-30", "Q3"), ("2021-10-22", "Q2")]
    assert honeywell_quarters["2020-09-30"] == "Q3"


def test_every_honeywell_quarter_is_numbered_by_its_calendar_month(honeywell_quarters):
    """A December year end makes the right answer checkable by eye.

    Honeywell's quarters end in March, June, September and December, so the
    month says the number and nothing has to be looked up. This is the check
    that the change corrects Kroger without disturbing an ordinary filer.
    """
    expected = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
    wrong = {end: label for end, label in honeywell_quarters.items()
             if expected.get(int(end[5:7])) != label}

    assert wrong == {}


# ---------------------------------------------------------------------------
# The recent years are on the table
# ---------------------------------------------------------------------------

def test_the_table_runs_through_the_most_recent_fiscal_year(honeywell_table):
    _entity, columns, _rows, _scope = honeywell_table
    labels = [c["label"] for c in columns]

    assert labels[-1] == "FY2025"
    assert labels[-2] == "FY2024"
    assert labels == ["FY{}".format(year) for year in range(2015, 2026)]


def test_honeywells_own_mis_tagged_year_does_not_move_the_table(honeywell_facts,
                                                                honeywell_table):
    """A calendar-year filer, and one filing that says otherwise.

    Honeywell's 10-K for the year ended 31 December 2021 tags a fiscal year
    focus of 2020. Sixteen of its seventeen annual filings tag the year they
    end in, so the offset is zero and every label is the one the end-year rule
    already gave. Trusting each year's own focus would have named the 2021
    column FY2020, against a 10-K cover page that says 2021.
    """
    assert xbrl.fiscal_year_offset(honeywell_facts) == 0

    observed = xbrl._annual_report_year_ends(honeywell_facts)
    odd = {end: focus for end, _filed, focus in observed.values()
           if int(end[:4]) != focus}
    assert odd == {"2021-12-31": 2020}

    _entity, columns, _rows, _scope = honeywell_table
    assert {col["key"]: col["label"] for col in columns}["2021-12-31"] == "FY2021"


# Honeywell's FY2025 10-K, in millions, for the year ended 31 December 2025.
FY2025_10K = {
    "Revenue": 37_442,
    "Cost of Revenue": 23_613,
    "Operating Income": 8_127,
    "Net Income": 4_729,
    "Total Assets": 73_681,
    "Total Equity": 15_030,
    "Cash and Equivalents": 12_487,
    "Long-Term Debt": 27_141,
}


@pytest.mark.parametrize("line_item,millions", sorted(FY2025_10K.items()))
def test_fy2025_matches_the_10k(honeywell_table, line_item, millions):
    _entity, _columns, rows, _scope = honeywell_table
    cell = rows[line_item]["cells"][FY2025_END]

    assert cell["value"] == millions * MILLION
    assert cell["provenance"]["state"] == "reported"
    assert cell["provenance"]["form"] == "10-K"


def test_fy2025_per_share_figures_match_the_10k(honeywell_table):
    _entity, _columns, rows, _scope = honeywell_table

    assert rows["EPS Basic"]["cells"][FY2025_END]["value"] == 7.40
    assert rows["EPS Diluted"]["cells"][FY2025_END]["value"] == 7.36
    assert rows["Shares Outstanding (Basic)"]["cells"][FY2025_END]["value"] == 639_000_000
    assert rows["Shares Outstanding (Diluted)"]["cells"][FY2025_END]["value"] == 642_800_000


def test_the_year_before_is_reported_on_the_basis_the_latest_10k_uses(
        honeywell_facts, honeywell_table):
    """FY2024 revenue reads 34,717, not the 38,498 first reported for it.

    Honeywell spun off Solstice Advanced Materials in October 2025, and its
    FY2025 10-K restates FY2024 for discontinued operations. Two annual reports
    cover FY2024, so the rank is a tie and the later one wins, which is the
    filing-date rule doing exactly what it was written for.
    """
    _entity, _columns, rows, _scope = honeywell_table
    cell = rows["Revenue"]["cells"][FY2024_END]

    assert cell["value"] == 34_717 * MILLION
    assert cell["provenance"]["accession"] == "0000773840-26-000013"

    # The figure the FY2024 10-K itself reported is still in the payload, and
    # still the one the row would show if no later annual report existed.
    original = next(
        dp for dp in xbrl._extract_tag_data(
            honeywell_facts, "RevenueFromContractWithCustomerExcludingAssessedTax")
        if dp["end"] == FY2024_END and dp["start"] == "2024-01-01"
        and dp["accn"] == "0000773840-25-000010")
    assert original["value"] == 38_498 * MILLION


# ---------------------------------------------------------------------------
# What Honeywell does not tag
# ---------------------------------------------------------------------------

def test_total_liabilities_is_a_hole_because_honeywell_tags_no_such_item(
        honeywell_facts, honeywell_table):
    """Not one year of it, and the table says so on every one of them.

    Honeywell reports no us-gaap Liabilities fact at all. That is the untagged
    case the NOT_TAGGED flag exists for, and it is a different sentence from
    the one Apple's relabeled balance sheets used to get.
    """
    assert "Liabilities" not in honeywell_facts["facts"]["us-gaap"]

    _entity, columns, rows, _scope = honeywell_table
    for col in columns:
        prov = rows["Total Liabilities"]["cells"][col["key"]]["provenance"]
        assert prov["state"] == "missing"
        assert prov["flag"] == xbrl.FLAG_NOT_TAGGED
        assert prov["statement"] == "balance sheet"
        assert "sec.gov/Archives/edgar/data/773840/" in prov["message"]


def test_long_term_debt_is_the_balance_sheet_non_current_line(honeywell_facts,
                                                              honeywell_table):
    """PROGRESS.md open question 1, settled on the filer it was written about.

    Honeywell tags no LongTermDebtNoncurrent, so before this correction the row
    fell through to LongTermDebt, which is not the non-current balance and for
    this filer is not the balance-sheet total either. Honeywell does report the
    non-current line, under the tag a filer uses when debt and finance leases
    share one caption, and putting that tag ahead of LongTermDebt is the whole
    of the fix.

    27,141 is the "Long-term debt" line of Honeywell's FY2025 balance sheet.
    29,046 is what LongTermDebt holds for the same instant, 1,905 above it and
    359 above even the balance sheet's debt including current maturities, which
    is why no chain position could have made that tag the right answer.
    """
    assert list(line_items.tags_for("Long-Term Debt")) == [
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
    ]
    assert "LongTermDebtNoncurrent" not in honeywell_facts["facts"]["us-gaap"]

    _entity, _columns, rows, _scope = honeywell_table
    cell = rows["Long-Term Debt"]["cells"][FY2025_END]
    assert cell["value"] == 27_141 * MILLION
    assert cell["provenance"]["tag"] == "LongTermDebtAndCapitalLeaseObligations"

    # The tag the row used to resolve through still holds its own figure.
    old = xbrl.deduplicate_period(
        xbrl._extract_tag_data(honeywell_facts, "LongTermDebt"))
    assert {dp["value"] for dp in old if dp["end"] == FY2025_END} == {29_046 * MILLION}


def test_the_2024_row_shows_the_restated_non_current_line_not_the_old_total(
        honeywell_facts, honeywell_table):
    """The number open question 1 predicted, and the reason it is not that number.

    Open question 1 was written off the FY2024 10-K, where the non-current line
    reads 25,479 and LongTermDebt reads 27,265, and it expected the corrected
    row to show 25,479. It shows 25,440, because Honeywell's FY2025 10-K
    re-presents the 2024 balance sheet for the Solstice spin-off and moves 39
    million of debt into liabilities held for sale. Both figures are the same
    balance-sheet line; the row takes the one the most recent annual report
    gives, which is the rule that already puts FY2024 revenue at 34,717 rather
    than the 38,498 first reported.

    What matters for the correction is the other assertion: 27,265 does not win
    any more, and neither does 26,826, the balance-sheet total the 10-Qs put in
    the same tag.
    """
    _entity, _columns, rows, _scope = honeywell_table
    cell = rows["Long-Term Debt"]["cells"][FY2024_END]

    assert cell["value"] == 25_440 * MILLION
    assert cell["provenance"]["accession"] == "0000773840-26-000013"
    assert cell["value"] not in (27_265 * MILLION, 26_826 * MILLION)

    # Both of the figures it beat, still in the payload, from the filings named.
    for_2024 = xbrl._extract_tag_data(honeywell_facts, "LongTermDebt")
    by_form = {(dp["form"], dp["value"]) for dp in for_2024 if dp["end"] == FY2024_END}
    assert ("10-K", 27_265 * MILLION) in by_form
    assert ("10-Q", 26_826 * MILLION) in by_form

    original = xbrl._extract_tag_data(
        honeywell_facts, "LongTermDebtAndCapitalLeaseObligations")
    assert {dp["value"] for dp in original
            if dp["end"] == FY2024_END and dp["accn"] == "0000773840-25-000010"} == {
        25_479 * MILLION}


def test_total_debt_ties_to_the_balance_sheet_without_double_counting(honeywell_table):
    """PROGRESS.md open questions 1 and 4 are the same arithmetic seen twice.

    Honeywell's FY2025 balance sheet carries three debt lines: long-term debt
    27,141, current maturities 1,546, and commercial paper and other short-term
    borrowings 5,893. They add to 34,580 and the row says 34,580.

    Both halves of the fix are load-bearing. Before the chain correction the
    long-term row read 29,046, a figure that overlaps the current maturities
    and is 1,905 above the balance-sheet line, so any sum built on it
    double-counted. Before the summed derivation the short-term side was one
    tag, which for this filer would have been the borrowings alone and would
    have dropped the current maturities entirely.
    """
    _entity, _columns, rows, _scope = honeywell_table
    cell = rows["Total Debt"]["cells"][FY2025_END]

    assert cell["value"] == (27_141 + 1_546 + 5_893) * MILLION
    assert cell["value"] == 34_580 * MILLION

    prov = cell["provenance"]
    inputs = {entry["name"]: entry for entry in prov["inputs"]}
    assert inputs["Long-Term Debt"]["value"] == 27_141 * MILLION

    short_term = inputs["Short-Term Debt"]
    assert short_term["value"] == 7_439 * MILLION
    assert short_term["formula"] == (
        "Current Maturities of Long-Term Debt + Short-Term Borrowings")
    assert {(i["name"], i["value"], i["tag"]) for i in short_term["inputs"]} == {
        ("Current Maturities of Long-Term Debt", 1_546 * MILLION,
         "LongTermDebtAndCapitalLeaseObligationsCurrent"),
        ("Short-Term Borrowings", 5_893 * MILLION, "ShortTermBorrowings"),
    }

    # Honeywell tags no commercial paper instant, so the term that would have
    # overlapped its combined borrowings line is absent rather than added.
    assert "Commercial Paper" not in {i["name"] for i in short_term["inputs"]}


def test_the_whole_honeywell_debt_row_now_comes_from_one_tag(honeywell_table):
    """No seam, where the old chain produced one at every year Honeywell restated."""
    _entity, columns, rows, _scope = honeywell_table
    tags = {cell["provenance"].get("tag")
            for cell in rows["Long-Term Debt"]["cells"].values()}

    assert tags == {"LongTermDebtAndCapitalLeaseObligations"}
    assert rows["Long-Term Debt"]["tag_summary"] == "LongTermDebtAndCapitalLeaseObligations"


def _annual(facts, name):
    data, _tag = xbrl.resolve_line_item(facts, name)
    return {dp["end"]: dp for dp in xbrl.deduplicate_period(data)
            if xbrl._is_annual_period(dp)}


def test_the_interest_row_reads_honeywells_own_interest_line(honeywell_facts):
    """Honeywell tags neither InterestExpense nor InterestExpenseDebt, ever.

    Its income statement calls the line "Interest and other financial charges"
    and tags it InterestAndDebtExpense, which bundles other financing costs in
    with interest. Adding that tag to the end of the chain turns nineteen blank
    years into nineteen reported ones; the registry note says what the number
    includes, because the label alone would overstate its precision.
    """
    us_gaap = honeywell_facts["facts"]["us-gaap"]
    assert "InterestExpense" not in us_gaap
    assert "InterestExpenseDebt" not in us_gaap

    by_end = _annual(honeywell_facts, "Interest Expense")
    assert by_end[FY2025_END]["value"] == 1_344 * MILLION
    assert by_end[FY2025_END]["tag"] == "InterestAndDebtExpense"
    assert by_end[FY2024_END]["value"] == 1_048 * MILLION


def test_property_survives_the_lease_accounting_change(honeywell_facts):
    """The same successor element Kroger needs, agreeing to the dollar here too."""
    by_end = _annual(honeywell_facts, "PP&E Net")
    successor = ("PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulated"
                 "DepreciationAndAmortization")

    assert by_end[FY2025_END]["value"] == 4_629 * MILLION
    assert by_end[FY2025_END]["tag"] == successor

    overlap = "2022-12-31"
    values = {dp["tag"]: dp["value"]
              for tag in ("PropertyPlantAndEquipmentNet", successor)
              for dp in xbrl._extract_tag_data(honeywell_facts, tag)
              if dp["end"] == overlap and dp["form"] == "10-K"}
    assert len(values) == 2
    assert set(values.values()) == {5_471 * MILLION}


def test_gross_profit_is_derived_once_honeywell_stops_tagging_it(honeywell_table):
    """The first fixture where the derivation actually fires on real numbers.

    Honeywell tagged GrossProfit through FY2020 and stopped. Apple never
    exercises the rule because Apple tags it throughout.
    """
    _entity, _columns, rows, _scope = honeywell_table
    cells = rows["Gross Profit"]["cells"]

    assert cells["2020-12-31"]["provenance"]["state"] == "reported"

    derived = cells[FY2025_END]
    assert derived["provenance"]["state"] == "derived"
    assert derived["provenance"]["formula"] == "Revenue - Cost of Revenue"
    assert derived["value"] == (37_442 - 23_613) * MILLION
    assert [i["name"] for i in derived["provenance"]["inputs"]] == [
        "Revenue", "Cost of Revenue"]


# ---------------------------------------------------------------------------
# The column the EPS check exists for
# ---------------------------------------------------------------------------

def _eps_flags(facts):
    deduped = xbrl.deduplicate_all_line_items(xbrl.extract_all_line_items(facts))
    return [f for f in xbrl.validate_financials(deduped)["EPS Diluted"]
            if f["flag_type"] == xbrl.FLAG_EPS_RECONCILIATION]


def test_the_q2_2025_share_basis_mismatch_is_flagged(honeywell_facts):
    """PROGRESS.md open question 7, on the column that exposed it.

    Honeywell halved its share count in 2026, and the restatement reached the
    rows one filing at a time. For the quarter ended 30 June 2025 the EPS comes
    from the FY2025 10-K, which predates the change, and the share count from a
    10-Q filed after it. So the column holds net income of 1,570 million beside
    321 million shares and an EPS of 2.45, and 1,570 over 321 is 4.90. Both
    figures describe the same earnings; only the denominator moved.

    Session 4A went looking for the flag that should have caught this and found
    a check that had never fired for anyone. This is it firing.
    """
    flags = {f["period_end"]: f for f in _eps_flags(honeywell_facts)}

    assert "2025-06-30" in flags
    detail = flags["2025-06-30"]["details"]
    assert detail["net_income"] == 1_570 * MILLION
    assert detail["reported_eps"] == 2.45
    assert round(detail["computed_eps"], 2) == 4.90
    assert detail["diff_pct"] > 0.5


def test_that_is_the_only_column_honeywell_fails_on(honeywell_facts):
    """One flag, not a rash of them: the check has to be quiet to mean anything."""
    assert [f["period_end"] for f in _eps_flags(honeywell_facts)] == ["2025-06-30"]


# ---------------------------------------------------------------------------
# The two views agree
# ---------------------------------------------------------------------------

def test_the_peer_table_shows_the_same_years_and_the_same_numbers(
        honeywell_facts, honeywell_table, monkeypatch):
    """The divergence R5 is about: one company, two views, one answer."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: honeywell_facts)
    _entity, columns, rows, _scope = honeywell_table

    peer = pc.fetch_peer_data("773840", list(xbrl.TAG_MAP), n_periods=11)

    single_ends = [c["key"] for c in columns]
    peer_ends = [p["period_end"]
                 for p in peer["line_items"]["Total Assets"]["periods"]]
    assert sorted(peer_ends) == single_ends

    for name, info in peer["line_items"].items():
        for period in info["periods"]:
            assert period["value"] == rows[name]["cells"][period["period_end"]]["value"], (
                "{} {}".format(name, period["period_end"]))
