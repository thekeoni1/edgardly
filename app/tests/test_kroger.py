"""test_kroger.py -- the filer whose fiscal year is not a calendar year.

The Kroger Co., CIK 56873, SIC 5411. Regenerate with:

    python scripts/make_fixture.py 56873

Kroger is in the acceptance set for one reason: its fiscal year is 52 or 53
weeks long and ends on the Saturday nearest 31 January, so nothing about it
lines up with a calendar. Three of the nineteen years in this fixture are 53
weeks; the first quarter of every year is 16 weeks, not 13; and the year the
company itself calls fiscal 2025 ended on 31 January 2026. Every one of those
is a way for a period engine that reasons about months, or about EDGAR's
fiscal-period label, to go wrong.

V2_PLAN risk R5 names Kroger as the filer that stresses this, and the period
engine app/periods.py shipped in Session 4A is what it stresses.

Values are checked against Kroger's Form 10-K for the fiscal year ended
31 January 2026, accession 0001104659-26-037723. No test here touches the
network.
"""

import datetime
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as flask_app
import edgar_api
import line_items
import periods
import peer_comparison as pc
import xbrl_extractor as xbrl

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "cik56873.json")

# The company calls this year fiscal 2025. It ended on 31 January 2026.
FISCAL_2025_END = "2026-01-31"
FISCAL_2024_END = "2025-02-01"
# The most recent 53-week year: 371 days, ending a week later than usual.
FISCAL_2023_END = "2024-02-03"

MILLION = 1_000_000


@pytest.fixture(scope="module")
def kroger_facts():
    with open(FIXTURE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def kroger_table(kroger_facts, monkeypatch):
    """The whole table, every year the fixture reaches."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: kroger_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta",
                        lambda cik: {"sic": "5411",
                                     "sic_description": "Retail-Grocery Stores"})
    entity, columns, rows, scope = flask_app._build_xbrl_result(56873, 2005, 2035, "annual")
    return entity, columns, {row["line_item"]: row for row in rows}, scope


def _deduped(facts, names=None):
    names = names or xbrl.TAG_MAP
    return xbrl.deduplicate_all_line_items(xbrl.extract_all_line_items(facts, names))


def _days(earlier, later):
    return (datetime.date.fromisoformat(later)
            - datetime.date.fromisoformat(earlier)).days


# ---------------------------------------------------------------------------
# The fixture
# ---------------------------------------------------------------------------

def test_fixture_is_kroger(kroger_facts):
    assert kroger_facts["entityName"] == "KROGER CO"
    assert kroger_facts["cik"] == 56873
    assert kroger_facts["_fixture"]["company"]["sic"] == "5411"


def test_fixture_holds_nothing_outside_the_registry(kroger_facts):
    known = set()
    for item in line_items.REGISTRY.values():
        known.update(item.tags)
    known.update(line_items.DA_COMPONENT_TAGS)
    known.update(line_items.SCOPE_HEURISTIC_TAGS)

    extra = set(kroger_facts["facts"]["us-gaap"]) - known
    assert not extra, "fixture holds tags the registry never reads: {}".format(extra)


def test_a_grocer_is_in_scope(kroger_table):
    """SIC 5411 is nowhere near the bank and insurance ranges."""
    _entity, _columns, _rows, scope = kroger_table
    assert scope["in_scope"] is True
    assert scope["message"] == ""


# ---------------------------------------------------------------------------
# 52 and 53 week years
# ---------------------------------------------------------------------------

def test_every_kroger_year_is_52_or_53_weeks_and_none_is_lost(kroger_table):
    """The whole point of the fixture, measured rather than assumed.

    Consecutive fiscal year ends are 364 days apart in a 52-week year and 371
    in a 53-week one. Nothing in between and nothing outside: a gap of any
    other length would mean the engine had either invented a year or dropped
    one, and either would show up here as an unexpected number of days.
    """
    _entity, columns, _rows, _scope = kroger_table
    ends = [col["key"] for col in columns]

    gaps = [_days(ends[i - 1], ends[i]) for i in range(1, len(ends))]
    assert set(gaps) == {364, 371}
    assert gaps.count(371) == 3      # fiscal 2012, 2017 and 2023


def test_the_53_week_years_are_the_ones_the_filings_say_they_are(kroger_table):
    _entity, columns, _rows, _scope = kroger_table
    ends = [col["key"] for col in columns]

    long_years = [ends[i] for i in range(1, len(ends)) if _days(ends[i - 1], ends[i]) == 371]
    assert long_years == ["2013-02-02", "2018-02-03", FISCAL_2023_END]


def test_a_53_week_year_is_measured_as_a_year_not_rejected_as_too_long(kroger_facts):
    """371 days has to pass the annual window, and 130 days has to fail it.

    The window is wide on purpose. A ceiling tight enough to exclude a 53-week
    year would drop three of Kroger's nineteen years, and the filer would look
    like it had stopped reporting in those years rather than like it had used a
    calendar every retailer uses.
    """
    revenue = _deduped(kroger_facts, ["Revenue"])["Revenue"]["data"]
    long_year = next(dp for dp in revenue
                     if dp["end"] == FISCAL_2023_END and dp.get("start") == "2023-01-29")

    assert _days(long_year["start"], long_year["end"]) == 370   # 371st day inclusive
    assert periods.covers_one_period(long_year, periods.ANNUAL)
    assert not periods.covers_one_period(long_year, periods.QUARTERLY)


def test_kroger_16_week_first_quarter_is_still_one_quarter(kroger_facts):
    """Kroger's year is 16 + 12 + 12 + 12 weeks, not four equal thirteens.

    A quarter window built around 13 weeks would throw away every first
    quarter this company has ever reported.
    """
    revenue = _deduped(kroger_facts, ["Revenue"])["Revenue"]["data"]
    first_quarter = next(dp for dp in revenue
                         if dp.get("start") == "2025-02-02" and dp["end"] == "2025-05-24")

    assert _days(first_quarter["start"], first_quarter["end"]) == 111   # 16 weeks
    assert periods.covers_one_period(first_quarter, periods.QUARTERLY)
    assert not periods.covers_one_period(first_quarter, periods.ANNUAL)


def test_the_year_end_full_year_beats_the_fourth_quarter_ending_the_same_day(
        kroger_facts, kroger_table):
    """Two flows end on 31 January 2026, and only one of them is the year.

    Kroger's first-quarter 10-Q for fiscal 2026 carries the fourth quarter of
    fiscal 2025 as its comparative, an 84-day flow ending on the fiscal year
    end. It survives deduplication because it is a different period, not a
    duplicate. The annual column takes the longest span that covers the period,
    so it takes the year.
    """
    net_income = _deduped(kroger_facts, ["Net Income"])["Net Income"]["data"]
    spans = sorted(_days(dp["start"], dp["end"])
                   for dp in net_income if dp["end"] == FISCAL_2025_END and dp.get("start"))
    assert spans == [83, 363]

    _entity, _columns, rows, _scope = kroger_table
    assert rows["Net Income"]["cells"][FISCAL_2025_END]["value"] == 1_016 * MILLION


# ---------------------------------------------------------------------------
# What the table reads
# ---------------------------------------------------------------------------

# Kroger's fiscal 2025 Form 10-K, in millions, for the year ended 31 Jan 2026.
FISCAL_2025_10K = {
    "Revenue": 147_642,
    "Operating Income": 1_890,
    "Net Income": 1_016,
    "Total Assets": 49_953,
    "Total Liabilities": 44_017,
    "Total Equity": 5_936,
    "Cash and Equivalents": 3_334,
}


@pytest.mark.parametrize("line_item,millions", sorted(FISCAL_2025_10K.items()))
def test_fiscal_2025_matches_the_10k(kroger_table, line_item, millions):
    _entity, _columns, rows, _scope = kroger_table
    cell = rows[line_item]["cells"][FISCAL_2025_END]

    assert cell["value"] == millions * MILLION
    assert cell["provenance"]["state"] == "reported"
    assert cell["provenance"]["form"] == "10-K"


def test_the_53_week_year_reads_off_its_own_10k(kroger_table):
    """Fiscal 2023 is the extra week, and its sales are correspondingly larger."""
    _entity, _columns, rows, _scope = kroger_table

    assert rows["Revenue"]["cells"][FISCAL_2023_END]["value"] == 150_039 * MILLION
    assert rows["Net Income"]["cells"][FISCAL_2023_END]["value"] == 2_164 * MILLION


def test_fiscal_2025_per_share_figures_match_the_10k(kroger_table):
    _entity, _columns, rows, _scope = kroger_table

    assert rows["EPS Basic"]["cells"][FISCAL_2025_END]["value"] == 1.55
    assert rows["EPS Diluted"]["cells"][FISCAL_2025_END]["value"] == 1.54
    assert rows["Shares Outstanding (Basic)"]["cells"][FISCAL_2025_END]["value"] == 652_000_000


def test_the_column_is_named_for_the_calendar_year_the_fiscal_year_ends_in(kroger_table):
    """A naming divergence worth stating out loud rather than discovering later.

    Edgardly names a fiscal year for the calendar year its period ends in, so
    the year ending 31 January 2026 is FY2026 here. Kroger calls that same year
    fiscal 2025, and so does its 10-K cover page. Neither name is wrong; they
    are different conventions, and a late-January year end is where they part.

    The obvious repair -- name a fiscal year for the calendar year that holds
    most of it -- is not obviously right either: it would rename Nike's year
    ending 31 May 2025, which Nike calls fiscal 2025, to FY2024. Getting this
    right means reading the filer's own DocumentFiscalYearFocus from the filing
    that first reported the period, which is a piece of work of its own. See
    PROGRESS.md open question 8.
    """
    _entity, columns, _rows, _scope = kroger_table
    by_end = {col["key"]: col["label"] for col in columns}

    assert by_end[FISCAL_2025_END] == "FY2026"
    assert by_end[FISCAL_2024_END] == "FY2025"
    assert by_end[FISCAL_2023_END] == "FY2024"


@pytest.mark.xfail(reason="quarter labels still come from EDGAR's fp, which names the "
                          "filing rather than the fact. PROGRESS.md open question 9.",
                   strict=True)
def test_the_fourth_quarter_is_not_labelled_the_first(kroger_facts):
    """R5 shadowing, still alive in the quarterly view.

    The flow from 9 November 2025 to 31 January 2026 is Kroger's fourth
    quarter. The only filing that carries it is the first-quarter 10-Q of
    fiscal 2026, which reports it as a comparative, and EDGAR stamps that
    filing's fiscal-period label on the fact. So the quarterly view confirms
    the period from its dates, correctly, and then takes its name from a label
    that belongs to a different quarter.

    Annual columns are unaffected: they are labelled FY from the period type,
    never from fp, which is why the annual table and the peer table agree.
    """
    deduped = _deduped(kroger_facts)
    quarters = periods.period_ends(deduped, xbrl.TAG_MAP, periods.QUARTERLY)

    assert quarters[FISCAL_2025_END] == "Q4"


# ---------------------------------------------------------------------------
# Chain corrections Kroger forced
# ---------------------------------------------------------------------------

def test_merchandise_costs_reach_the_cost_of_revenue_row(kroger_table):
    """Kroger's cost line is tagged with the element that excludes D&A.

    None of CostOfRevenue, CostOfGoodsAndServicesSold, CostOfGoodsSold or
    CostOfServices carries it after fiscal 2017, so the row -- and the gross
    profit under it -- was blank for the eight most recent years while the
    number sat in the payload.
    """
    _entity, columns, rows, _scope = kroger_table
    cells = rows["Cost of Revenue"]["cells"]

    assert cells[FISCAL_2025_END]["value"] == 113_240 * MILLION
    assert cells[FISCAL_2023_END]["value"] == 116_675 * MILLION
    assert cells[FISCAL_2025_END]["provenance"]["tag"] == (
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization")

    # Unbroken from the first year Kroger tagged a cost line at all.
    reported = [col["key"] for col in columns
                if cells[col["key"]]["provenance"]["state"] == "reported"]
    assert reported == [col["key"] for col in columns[1:]]


def test_gross_profit_is_derived_because_kroger_reports_no_such_line(kroger_table):
    """Kroger's income statement goes from sales to operating profit.

    There is no gross profit line to tag and Kroger tags none, so every year of
    this row is arithmetic on two reported values and says so.
    """
    _entity, _columns, rows, _scope = kroger_table
    cell = rows["Gross Profit"]["cells"][FISCAL_2025_END]

    assert cell["value"] == (147_642 - 113_240) * MILLION
    assert cell["provenance"]["state"] == "derived"
    assert cell["provenance"]["formula"] == "Revenue - Cost of Revenue"


def test_the_cost_row_flags_the_year_it_changes_tag(kroger_table):
    """The new tag excludes D&A and the old ones do not, so the seam matters."""
    _entity, _columns, rows, _scope = kroger_table
    seams = {end: [f for f in cell["flags"] if f["type"] == xbrl.FLAG_TAG_TRANSITION]
             for end, cell in rows["Cost of Revenue"]["cells"].items()}

    assert seams["2019-02-02"], "the first year only the new tag reports"
    assert not seams[FISCAL_2025_END]


def _instants(facts, name):
    """Resolve a registry item outside the fourteen displayed ones, by end date."""
    data, _tag = xbrl.resolve_line_item(facts, name)
    return {dp["end"]: dp for dp in xbrl.deduplicate_period(data)
            if dp.get("start") is None}


def test_property_survives_the_lease_accounting_change(kroger_facts):
    """ASC 842 moved finance-lease assets into the PP&E caption and the tag with it.

    PropertyPlantAndEquipmentNet stops at fiscal 2019 for this filer. The
    successor element continues the same balance-sheet line, and the two agree
    exactly in the year Kroger tags both.
    """
    by_end = _instants(kroger_facts, "PP&E Net")

    assert by_end[FISCAL_2025_END]["value"] == 24_260 * MILLION
    assert by_end[FISCAL_2025_END]["tag"] == (
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulated"
        "DepreciationAndAmortization")

    overlap = "2020-02-01"
    assert by_end[overlap]["value"] == 21_871 * MILLION
    both = {dp["tag"]: dp["value"] for tag in (
                "PropertyPlantAndEquipmentNet",
                "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulated"
                "DepreciationAndAmortization")
            for dp in xbrl._extract_tag_data(kroger_facts, tag)
            if dp["end"] == overlap and dp["form"] == "10-K"}
    assert len(both) == 2
    assert set(both.values()) == {21_871 * MILLION}


def test_trade_payables_fill_the_years_before_kroger_switched_element(kroger_facts):
    by_end = _instants(kroger_facts, "Accounts Payable")

    assert by_end[FISCAL_2025_END]["value"] == 10_488 * MILLION
    assert by_end[FISCAL_2025_END]["tag"] == "AccountsPayableCurrent"
    assert by_end["2023-01-28"]["tag"] == "AccountsPayableTradeCurrent"


def test_the_net_interest_line_carries_the_filers_own_sign(kroger_table):
    """A caveat the registry states, exercised rather than asserted.

    Kroger's income statement shows "Net interest expense (639)" and tags it
    -639. The tags earlier in the chain report an expense as a positive number,
    so a row that crosses from one to the other changes sign while the company's
    interest bill goes up. The registry's sign note says so and the seam is
    flagged; nothing here is corrected, because both numbers are what the filer
    reported.
    """
    _entity, _columns, rows, _scope = kroger_table
    cells = rows["Interest Expense"]["cells"] if "Interest Expense" in rows else None
    assert cells is None      # not one of the fourteen displayed items

    facts = json.load(open(FIXTURE_PATH, encoding="utf-8"))
    data, _tag = xbrl.resolve_line_item(facts, "Interest Expense")
    by_end = {dp["end"]: dp for dp in xbrl.deduplicate_period(data)
              if dp.get("start") and xbrl._is_annual_period(dp)}

    assert by_end[FISCAL_2023_END]["value"] == 441 * MILLION
    assert by_end[FISCAL_2023_END]["tag"] == "InterestExpense"
    assert by_end[FISCAL_2025_END]["value"] == -639 * MILLION
    assert by_end[FISCAL_2025_END]["tag"] == "InterestIncomeExpenseNonoperatingNet"


def test_total_debt_is_a_sum_of_one_term_where_that_is_all_kroger_has(kroger_table):
    """The optional-term rule at its narrowest, and a cross-check on the answer.

    Kroger carries no commercial paper and no short-term borrowings, so its
    short-term debt is the current maturities line alone. The sum comes to
    15,875 million, which is exactly what Kroger's own LongTermDebt tag holds
    for the same instant: the element that means long-term debt including
    current maturities. Two different routes to the same number, one of them
    the filer's own.
    """
    _entity, _columns, rows, _scope = kroger_table
    cell = rows["Total Debt"]["cells"][FISCAL_2025_END]

    assert cell["value"] == (14_509 + 1_366) * MILLION
    assert cell["value"] == 15_875 * MILLION

    short_term = next(entry for entry in cell["provenance"]["inputs"]
                      if entry["name"] == "Short-Term Debt")
    assert short_term["formula"] == "Current Maturities of Long-Term Debt"
    assert [i["tag"] for i in short_term["inputs"]] == ["LongTermDebtCurrent"]

    facts = json.load(open(FIXTURE_PATH, encoding="utf-8"))
    combined = [dp for dp in xbrl._extract_tag_data(facts, "LongTermDebt")
                if dp["end"] == FISCAL_2025_END and dp["form"] == "10-K"]
    assert {dp["value"] for dp in combined} == {15_875 * MILLION}


def test_the_debt_rows_exclude_finance_leases_as_their_labels_promise(kroger_table):
    """Kroger's captions bundle leases in; the rows do not, and should not.

    The balance sheet reads "Long-term debt including obligations under finance
    leases 15,764" against the row's 14,509, the difference being 1,255 of
    lease liabilities that Kroger tags separately. A row called Long-Term Debt
    that quietly included finance leases would be the wrong answer to its own
    label. The gap is the filer's presentation, not a missing number.
    """
    _entity, _columns, rows, _scope = kroger_table
    assert rows["Long-Term Debt"]["cells"][FISCAL_2025_END]["value"] == 14_509 * MILLION

    facts = json.load(open(FIXTURE_PATH, encoding="utf-8"))
    leases = [dp for dp in xbrl._extract_tag_data(facts, "FinanceLeaseLiabilityNoncurrent")
              if dp["end"] == FISCAL_2025_END]
    assert leases == [], "the fixture keeps only registry tags; leases are not one"


def test_what_kroger_leaves_blank_stays_blank(kroger_table, kroger_facts):
    """Three rows this session deliberately did not fill.

    Kroger tags no operating expense element the registry reads, and no net
    inventory: its balance sheet carries FIFO inventory and a LIFO reserve as
    two lines, and netting them is a derivation nobody has written. Filling
    either from a tag that means something else would be a wrong answer rather
    than a missing one, so both stay flagged blanks with a pointer.
    """
    _entity, columns, rows, _scope = kroger_table
    assert "FIFOInventoryAmount" not in kroger_facts["facts"]["us-gaap"]

    for name in ("Inventory", "SG&A"):
        data, _tag = xbrl.resolve_line_item(kroger_facts, name)
        recent = [dp for dp in data if dp["end"] >= "2020-01-01"]
        assert recent == [], name

    prov = rows["Total Liabilities"]["cells"][FISCAL_2025_END]["provenance"]
    assert prov["state"] == "reported"      # Kroger, unlike Honeywell, does tag it


# ---------------------------------------------------------------------------
# The two views agree
# ---------------------------------------------------------------------------

def test_the_peer_table_shows_the_same_years_and_the_same_numbers(
        kroger_facts, kroger_table, monkeypatch):
    """The fiscal calendar is where the two views used to part company."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: kroger_facts)
    _entity, columns, rows, _scope = kroger_table

    peer = pc.fetch_peer_data("56873", list(xbrl.TAG_MAP), n_periods=len(columns))

    peer_ends = [p["period_end"]
                 for p in peer["line_items"]["Total Assets"]["periods"]]
    assert sorted(peer_ends) == [col["key"] for col in columns]

    for name, info in peer["line_items"].items():
        for period in info["periods"]:
            assert period["value"] == rows[name]["cells"][period["period_end"]]["value"], (
                "{} {}".format(name, period["period_end"]))
