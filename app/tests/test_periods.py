"""test_periods.py -- the period engine both views now run on.

The single-company table and the peer table used to answer "is this the FY2025
figure?" differently: one read EDGAR's fiscal_period label, the other measured
the period's dates. They disagreed, and the label was the one that was wrong
(V2_PLAN risk R5, PROGRESS.md open question 3). app/periods.py is the one
answer, and this module pins down what it does.

Most of it runs on payloads built by hand, because the cases that matter are
the ones the committed fixtures happen not to contain: a balance sheet no
annual report ever tagged, a year-to-date column ending on the fiscal year end,
a multi-year cumulative total. The last test in the module asks every fixture
whether the two views now agree, which is the property the whole exercise was
for.
"""

import collections
import datetime
import glob
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as flask_app
import edgar_api
import peer_comparison as pc
import periods
import xbrl_extractor as xbrl

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def entry(start, end, value, filed, fp="FY", form="10-K", fy=None):
    """One EDGAR fact. fy is the filing's dei DocumentFiscalYearFocus.

    It defaults to the calendar year the period ends in, which is what a
    calendar-year filer tags and what every test written before fiscal-year
    naming existed assumed.
    """
    return {"start": start, "end": end, "val": value,
            "fy": int(end[:4]) if fy is None else fy,
            "fp": fp, "form": form, "filed": filed, "accn": "accn-" + filed}


def instant(end, value, filed, fp="FY", form="10-K", fy=None):
    return {"end": end, "val": value, "fy": int(end[:4]) if fy is None else fy,
            "fp": fp, "form": form, "filed": filed, "accn": "accn-" + filed}


def facts(tags, unit="USD"):
    return {
        "entityName": "Test Co", "cik": 1,
        "facts": {"us-gaap": {
            tag: {"units": {unit: entries}} for tag, entries in tags.items()}},
    }


def deduped(payload, names=None):
    return xbrl.deduplicate_all_line_items(
        xbrl.extract_all_line_items(payload, names))


# ---------------------------------------------------------------------------
# Measuring a period
# ---------------------------------------------------------------------------

def test_a_flow_is_measured_and_an_instant_is_not():
    flow = {"start": "2024-01-01", "end": "2024-12-31"}
    assert periods.span_days(flow) == 365
    assert periods.is_instant(flow) is False

    point = {"start": None, "end": "2024-12-31"}
    assert periods.span_days(point) is None
    assert periods.is_instant(point) is True


def test_a_52_53_week_year_is_still_a_year():
    """364 and 371 days, which is what a retailer's fiscal year measures."""
    assert periods.covers_one_period({"start": "2023-01-29", "end": "2024-02-03"})
    assert periods.covers_one_period({"start": "2024-02-04", "end": "2025-02-01"})


def test_a_quarter_is_not_a_year_and_a_year_is_not_a_quarter():
    quarter = {"start": "2024-01-01", "end": "2024-03-31"}
    year = {"start": "2024-01-01", "end": "2024-12-31"}

    assert periods.covers_one_period(quarter, periods.QUARTERLY)
    assert not periods.covers_one_period(quarter, periods.ANNUAL)
    assert periods.covers_one_period(year, periods.ANNUAL)
    assert not periods.covers_one_period(year, periods.QUARTERLY)


def test_a_multi_year_total_is_not_a_year():
    """The old annual filter was "at least 300 days", with no ceiling.

    A three-year cumulative total ending on a fiscal year end would have passed
    it, and being the longest candidate for that date it would have won the
    column outright.
    """
    assert not periods.covers_one_period(
        {"start": "2022-01-01", "end": "2024-12-31"}, periods.ANNUAL)


def test_an_unreadable_date_measures_as_nothing_rather_than_as_zero():
    assert periods.span_days({"start": "not-a-date", "end": "2024-12-31"}) is None
    assert not periods.covers_one_period({"start": "not-a-date", "end": "2024-12-31"})


# ---------------------------------------------------------------------------
# Which periods exist
# ---------------------------------------------------------------------------

def test_a_full_year_confirms_its_period_whatever_it_is_labeled():
    """The label is the thing that cannot be trusted, so it is not consulted."""
    payload = facts({"Revenues": [
        entry("2024-01-01", "2024-12-31", 100, "2025-02-01", fp="Q2", form="10-Q")]})

    assert periods.period_ends(deduped(payload), ["Revenue"]) == {"2024-12-31": "FY"}


def test_a_nine_month_column_confirms_nothing_annual():
    payload = facts({"Revenues": [
        entry("2024-01-01", "2024-09-30", 70, "2024-10-25", fp="Q3", form="10-Q")]})

    assert periods.period_ends(deduped(payload), ["Revenue"]) == {}


def test_an_instant_the_filer_labeled_confirms_its_own_period():
    """A filer's own label is evidence; a label some later filing left is not.

    This is what gets the earliest year of an XBRL history onto the table when
    no flow item reaches back that far.
    """
    payload = facts({"Assets": [instant("2010-12-31", 500, "2011-02-01")]})

    assert periods.period_ends(deduped(payload), ["Total Assets"]) == {"2010-12-31": "FY"}


def test_an_instant_a_later_filing_relabeled_confirms_nothing_by_itself():
    """And yet the year still appears, because a flow item confirms it.

    The instant is not thrown away for being mislabeled. It is simply not the
    witness: something that can be measured says the period exists, and the
    instant is then matched to it by date.
    """
    payload = facts({
        "Assets": [instant("2024-12-31", 500, "2025-07-25", fp="Q2", form="10-Q")],
        "Revenues": [entry("2024-01-01", "2024-12-31", 100, "2025-02-01")],
    })
    resolved = deduped(payload, ["Total Assets", "Revenue"])

    assert periods.period_ends(resolved, ["Total Assets"]) == {}
    assert periods.period_ends(resolved, ["Total Assets", "Revenue"]) == {"2024-12-31": "FY"}


# ---------------------------------------------------------------------------
# What a fiscal year is called
# ---------------------------------------------------------------------------

def calendar_majority_year(start, end):
    """The repair that looks obvious and is wrong: the year holding most of it.

    Kept as running code rather than as prose, because the whole reason the
    filer's own label is read instead is that this rule disagrees with two real
    filers in opposite directions, and a comment cannot be run.
    """
    first = datetime.date.fromisoformat(start)
    last = datetime.date.fromisoformat(end)
    days = collections.Counter()
    day = first
    while day <= last:
        days[day.year] += 1
        day += datetime.timedelta(days=1)
    return days.most_common(1)[0][0]


def test_a_calendar_year_filer_is_named_for_the_year_it_ends_in():
    """Honeywell's and JPMorgan's shape. The offset is zero, so nothing moves."""
    payload = facts({"Revenues": [
        entry("2024-01-01", "2024-12-31", 100, "2025-02-14")]})

    assert xbrl.fiscal_year_offset(payload) == 0
    assert xbrl.period_label("2024-12-31", fy_offset=0) == "FY2024"


def test_a_late_january_year_end_takes_the_name_the_filer_uses():
    """Kroger's shape: the year ending 31 January 2026 is fiscal 2025.

    Here the rejected rule happens to agree, because eleven of the twelve
    months fall in 2025. The next test is where it does not.
    """
    payload = facts({"Revenues": [
        entry("2025-02-02", "2026-01-31", 100, "2026-03-31", fy=2025)]})

    assert xbrl.fiscal_year_offset(payload) == 1
    assert xbrl.period_label("2026-01-31", fy_offset=1) == "FY2025"
    assert calendar_majority_year("2025-02-02", "2026-01-31") == 2025


def test_a_may_year_end_named_for_the_later_year_is_left_alone():
    """Nike's shape, and the reason the calendar-majority rule was rejected.

    Nike's fiscal year runs June to May, so seven of its twelve months fall in
    the earlier calendar year, and Nike names it for the later one: the year
    ending 31 May 2025 is fiscal 2025. Naming a fiscal year for the calendar
    year that holds most of it would call it FY2024, a name Nike has never used
    for it, and it would do so while fixing Kroger. The filer's own focus says
    2025, the offset is zero, and the end-year rule was right here all along.

    No Nike fixture exists, so this filer is synthetic; what it pins is the
    reason a rule was not adopted, which no committed fixture can pin.
    """
    payload = facts({"Revenues": [
        entry("2024-06-01", "2025-05-31", 100, "2025-07-24", fy=2025)]})

    assert xbrl.fiscal_year_offset(payload) == 0
    assert xbrl.period_label("2025-05-31", fy_offset=0) == "FY2025"
    assert calendar_majority_year("2024-06-01", "2025-05-31") == 2024


def test_one_mis_tagged_year_does_not_rename_the_rest():
    """The reason the convention is read rather than each year's own focus.

    Kroger tagged focus 2025 on the year ended 1 February 2025 and again on the
    year ended 31 January 2026, and Honeywell tagged 2020 on its 2021 annual
    report. Taking each year's value at face value would put two columns under
    one name. The commonest difference between focus and end year wins, so the
    two mis-tagged years here are outvoted by the three that agree.
    """
    payload = facts({"Revenues": [
        entry("2021-01-31", "2022-01-29", 100, "2022-03-29", fy=2021),
        entry("2022-01-30", "2023-01-28", 100, "2023-03-28", fy=2022),
        entry("2023-01-29", "2024-02-03", 100, "2024-04-02", fy=2024),   # mis-tagged
        entry("2024-02-04", "2025-02-01", 100, "2025-04-01", fy=2025),   # mis-tagged
        entry("2025-02-02", "2026-01-31", 100, "2026-03-31", fy=2025),
    ]})

    assert xbrl.fiscal_year_offset(payload) == 1


def test_a_year_no_annual_filing_ever_named_still_gets_the_convention():
    """A first XBRL filing carries its comparatives, and names none of them.

    All four of these years arrive in one 10-K with one fiscal year focus, so
    reading a focus per year would put four columns under a single name. The
    convention reaches years no filing names; the individual values cannot.
    """
    payload = facts({"Revenues": [
        entry("2006-01-29", "2007-02-03", 60, "2010-03-30", fy=2009),
        entry("2007-02-04", "2008-02-02", 70, "2010-03-30", fy=2009),
        entry("2008-02-03", "2009-01-31", 80, "2010-03-30", fy=2009),
        entry("2009-02-01", "2010-01-30", 90, "2010-03-30", fy=2009),
    ]})
    offset = xbrl.fiscal_year_offset(payload)

    assert offset == 1
    assert [xbrl.period_label(end, fy_offset=offset) for end in
            ("2007-02-03", "2008-02-02", "2009-01-31", "2010-01-30")] == [
        "FY2006", "FY2007", "FY2008", "FY2009"]


def test_only_an_annual_filing_gets_to_name_the_fiscal_year():
    """A 10-Q's focus is the year it is filed into, not the year it reports.

    Kroger's first-quarter 10-Q for fiscal 2026 carries the previous fourth
    quarter, and its focus is 2026. Letting it speak would move the whole
    table by a year.
    """
    payload = facts({"Revenues": [
        entry("2025-02-02", "2026-01-31", 100, "2026-03-31", fy=2025),
        entry("2025-11-09", "2026-01-31", 25, "2026-06-15", fy=2026,
              fp="Q1", form="10-Q"),
    ]})

    assert xbrl.fiscal_year_offset(payload) == 1


def test_a_filer_that_names_no_fiscal_year_keeps_the_end_year_rule():
    """Offset zero is the old rule exactly, so the fallback changes nothing."""
    unlabeled = {"start": "2024-01-01", "end": "2024-12-31", "val": 100,
                 "fp": "FY", "form": "10-K", "filed": "2025-02-14", "accn": "a"}

    assert xbrl.fiscal_year_offset(facts({"Revenues": [unlabeled]})) == 0
    assert xbrl.fiscal_year_offset({}) == 0
    assert xbrl.fiscal_year_offset(None) == 0


def test_a_focus_stamped_on_a_period_the_filing_cannot_have_reported_is_ignored():
    """The two guards on which end date is a filing's own.

    A period ending after the filing date was not reported by it, and one
    ending more than a year before it belongs to an earlier year. Without both,
    an untidy payload can hand a filing the wrong year end and invent an
    offset out of it.
    """
    payload = facts({"Revenues": [
        entry("2024-01-01", "2024-12-31", 100, "2025-02-14"),
        entry("2025-01-01", "2025-12-31", 110, "2025-02-14"),      # after the filing
    ]})

    assert xbrl.fiscal_year_offset(payload) == 0


# ---------------------------------------------------------------------------
# What a quarter is called
# ---------------------------------------------------------------------------

# Kroger's calendar, which is the one that breaks everything: a 52-week year
# ending on the Saturday nearest 31 January, in quarters of 16, 12, 12 and 12
# weeks rather than four equal thirteens.
KROGER_YEAR_ENDS = ["2024-02-03", "2025-02-01", "2026-01-31"]


def test_a_quarter_is_numbered_by_where_it_sits_in_its_year():
    """16 weeks in is still the first quarter, and 54 percent through the second."""
    assert periods.quarter_of("2025-05-24", KROGER_YEAR_ENDS) == "Q1"
    assert periods.quarter_of("2025-08-16", KROGER_YEAR_ENDS) == "Q2"
    assert periods.quarter_of("2025-11-08", KROGER_YEAR_ENDS) == "Q3"
    assert periods.quarter_of("2026-01-31", KROGER_YEAR_ENDS) == "Q4"


def test_the_quarter_that_closes_the_year_is_the_fourth_not_the_first():
    """The whole of open question 9, in one line.

    A fourth quarter ends on the fiscal year end, so the only filing that
    carries it as a quarter is the following year's first-quarter 10-Q, and
    EDGAR stamps that filing's label on it. Position does not care what
    carried it.
    """
    payload = facts({"Revenues": [
        entry("2024-02-04", "2025-02-01", 95, "2025-04-01", fy=2024),
        entry("2025-02-02", "2026-01-31", 100, "2026-03-31", fy=2025),
        entry("2025-11-09", "2026-01-31", 25, "2026-06-15", fy=2026,
              fp="Q1", form="10-Q"),
    ]})
    resolved = deduped(payload, ["Revenue"])

    assert periods.period_ends(resolved, ["Revenue"], periods.QUARTERLY) == {
        "2026-01-31": "Q4"}


def test_a_quarter_in_a_year_that_has_not_closed_uses_the_filers_year_length():
    """There is no year end after it yet, so the years already reported stand in."""
    assert periods.quarter_of("2026-05-23", KROGER_YEAR_ENDS) == "Q1"
    assert periods.quarter_of("2026-08-15", KROGER_YEAR_ENDS) == "Q2"


def test_the_year_length_is_the_median_so_one_odd_year_cannot_stretch_it():
    assert periods.typical_year_days(KROGER_YEAR_ENDS) == 364

    # A 53-week year is 371 days and is outvoted by the 52-week years around it.
    with_long_year = ["2023-01-28"] + KROGER_YEAR_ENDS
    assert periods.typical_year_days(with_long_year) == 364

    assert periods.typical_year_days(["2024-12-31"]) == 365
    assert periods.typical_year_days([]) == 365


def test_a_quarter_with_no_fiscal_year_end_before_it_keeps_the_label_it_arrived_with():
    """Nothing to number against is not a licence to guess.

    A filer whose first confirmed fiscal year end comes after this quarter
    gives the engine no year to place it in. The filing's own label is then the
    only evidence there is, and it is kept rather than replaced by a number
    nothing supports.
    """
    payload = facts({"Revenues": [
        entry("2024-01-01", "2024-03-31", 25, "2024-04-25", fp="Q1", form="10-Q")]})
    resolved = deduped(payload, ["Revenue"])

    assert periods.quarter_of("2024-03-31", []) is None
    assert periods.period_ends(resolved, ["Revenue"], periods.QUARTERLY) == {
        "2024-03-31": "Q1"}


def test_numbering_decides_what_a_quarter_is_called_not_whether_it_happened():
    """The boundary this change deliberately did not cross.

    A 10-K's comparative quarters carry the label FY, and a period no filing
    ever called a quarter is still not a quarter column. Numbering answers the
    name; which columns exist is untouched, so no value moved into or out of
    the quarterly view.
    """
    payload = facts({"Revenues": [
        entry("2024-01-01", "2024-12-31", 100, "2025-02-14"),
        entry("2024-04-01", "2024-06-30", 25, "2025-02-14"),      # labeled FY by the 10-K
        entry("2023-01-01", "2023-12-31", 90, "2024-02-14"),
    ]})
    resolved = deduped(payload, ["Revenue"])

    assert periods.quarter_of("2024-06-30", ["2023-12-31", "2024-12-31"]) == "Q2"
    assert periods.period_ends(resolved, ["Revenue"], periods.QUARTERLY) == {}


# ---------------------------------------------------------------------------
# Which year a quarter is called after (open question 10)
# ---------------------------------------------------------------------------

# Apple's calendar, which breaks the rule from the other side: the fiscal year
# ends in September, so the first quarter of each year ends the December before.
APPLE_YEAR_ENDS = ["2023-09-30", "2024-09-28", "2025-09-27"]


def test_a_quarter_belongs_to_the_year_that_has_not_closed_when_it_does():
    """The fiscal year a quarter sits in is the one ending at or after it."""
    assert periods.closing_fiscal_year("2024-12-28", APPLE_YEAR_ENDS) == 2025
    assert periods.closing_fiscal_year("2025-06-28", APPLE_YEAR_ENDS) == 2025

    # A quarter that is itself a year end closes its own year, which is why the
    # comparison has to be inclusive. Kroger's fourth quarter is the case.
    assert periods.closing_fiscal_year("2026-01-31", KROGER_YEAR_ENDS) == 2026
    assert periods.closing_fiscal_year("2025-05-24", KROGER_YEAR_ENDS) == 2026


def test_a_quarter_past_the_last_confirmed_year_end_projects_the_next_one():
    """The year has not closed, so the filer's own year length says where it will."""
    assert periods.closing_fiscal_year("2026-05-23", KROGER_YEAR_ENDS) == 2027
    assert periods.closing_fiscal_year("2026-06-27", APPLE_YEAR_ENDS) == 2026


def test_no_confirmed_year_end_places_no_quarter():
    assert periods.closing_fiscal_year("2024-03-31", []) is None
    assert periods.closing_fiscal_year("", KROGER_YEAR_ENDS) is None


def test_a_quarter_is_named_for_its_fiscal_year_not_its_calendar_year():
    """Open question 10, both filers it was about, in one place.

    Kroger's fourth quarter ends 31 January 2026 and used to read "Q4 2026"
    beside an annual column for the same date reading FY2025. Apple's first
    quarter ends in December and used to read a year early. Both now read the
    year of the annual column they belong under.
    """
    assert xbrl.period_label("2026-01-31", "Q4", "quarterly", 1,
                             KROGER_YEAR_ENDS) == "Q4 FY2025"
    assert xbrl.period_label("2025-05-24", "Q1", "quarterly", 1,
                             KROGER_YEAR_ENDS) == "Q1 FY2025"
    assert xbrl.period_label("2024-12-28", "Q1", "quarterly", 0,
                             APPLE_YEAR_ENDS) == "Q1 FY2025"
    assert xbrl.period_label("2025-06-28", "Q3", "quarterly", 0,
                             APPLE_YEAR_ENDS) == "Q3 FY2025"


def test_naming_a_quarter_for_its_fiscal_year_leaves_the_annual_label_alone():
    """The annual column for the same date reads what it read before."""
    assert xbrl.period_label("2026-01-31", "FY", "annual", 1,
                             KROGER_YEAR_ENDS) == "FY2025"
    assert xbrl.period_label("2025-09-27", "FY", "annual", 0,
                             APPLE_YEAR_ENDS) == "FY2025"


# ---------------------------------------------------------------------------
# Which value covers a period
# ---------------------------------------------------------------------------

def test_a_balance_sheet_no_annual_report_ever_tagged_still_reaches_the_table():
    """The case ranking forms cannot reach, and the reason dates decide.

    Here the only copy of the 2024 year-end balance sheet is the comparative
    column of a 10-Q. There is no annual report to prefer and no FY label to
    read; the end date is the only evidence, and it is enough.
    """
    payload = facts({
        "Assets": [instant("2024-12-31", 500, "2025-04-25", fp="Q1", form="10-Q")],
        "Revenues": [entry("2024-01-01", "2024-12-31", 100, "2025-02-01")],
    })
    resolved = deduped(payload, ["Total Assets", "Revenue"])
    ends = periods.period_ends(resolved, ["Total Assets", "Revenue"])

    chosen = periods.points_by_end(resolved["Total Assets"]["data"], ends)

    assert chosen["2024-12-31"]["value"] == 500
    assert chosen["2024-12-31"]["form"] == "10-Q"


def test_the_full_year_beats_the_year_to_date_column_ending_on_the_same_day():
    payload = facts({"Revenues": [
        entry("2024-01-01", "2024-12-31", 100, "2025-02-01"),
        entry("2024-10-01", "2024-12-31", 28, "2025-02-01"),
    ]})
    resolved = deduped(payload, ["Revenue"])

    chosen = periods.points_by_end(resolved["Revenue"]["data"], {"2024-12-31"})

    assert chosen["2024-12-31"]["value"] == 100


def test_a_value_that_covers_some_other_period_does_not_fill_the_column():
    payload = facts({"Revenues": [
        entry("2024-04-01", "2024-12-31", 70, "2025-02-01")]})
    resolved = deduped(payload, ["Revenue"])

    assert periods.points_by_end(resolved["Revenue"]["data"], {"2024-12-31"}) == {}


# ---------------------------------------------------------------------------
# What the single-company table does with all of that
# ---------------------------------------------------------------------------

@pytest.fixture
def table_of(monkeypatch):
    """Build the single-company table from a payload built by hand."""
    def _build(payload, start_year=2024, end_year=2024, period_type="annual"):
        monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: payload)
        monkeypatch.setattr(edgar_api, "get_company_meta", lambda cik: {"sic": "3571"})
        entity, columns, rows, scope = flask_app._build_xbrl_result(
            1, start_year, end_year, period_type)
        return columns, {row["line_item"]: row for row in rows}
    return _build


def test_the_table_shows_a_year_only_a_10q_ever_tagged(table_of):
    payload = facts({
        "Assets": [instant("2024-12-31", 500, "2025-04-25", fp="Q1", form="10-Q")],
        "Revenues": [entry("2024-01-01", "2024-12-31", 100, "2025-02-01")],
    })

    columns, rows = table_of(payload)

    assert [c["label"] for c in columns] == ["FY2024"]
    cell = rows["Total Assets"]["cells"]["2024-12-31"]
    assert cell["value"] == 500
    assert cell["fp"] == "FY"                      # the column's label, not the 10-Q's
    assert cell["provenance"]["state"] == "reported"
    assert cell["provenance"]["form"] == "10-Q"


def test_a_year_to_date_column_leaves_the_cell_unresolved_rather_than_wrong(table_of):
    """PERIOD_UNRESOLVED is still needed, and this is what it is for now.

    The filer tagged revenue with this year end, so saying "not tagged in XBRL"
    would be false. What it tagged covers nine months of the year, so putting
    it in the FY2024 column would be worse. The cell says exactly that and
    points at the filing.
    """
    payload = facts({
        "Assets": [instant("2024-12-31", 500, "2025-02-01")],
        "Revenues": [entry("2024-04-01", "2024-12-31", 70, "2025-02-01")],
    })

    _columns, rows = table_of(payload)
    prov = rows["Revenue"]["cells"]["2024-12-31"]["provenance"]

    assert prov["state"] == "missing"
    assert prov["flag"] == xbrl.FLAG_PERIOD_UNRESOLVED
    assert prov["message"].startswith(
        "Tagged in XBRL, but not for a period Edgardly could confirm as FY2024")


def test_a_multi_year_total_does_not_become_the_year(table_of):
    payload = facts({
        "Assets": [instant("2024-12-31", 500, "2025-02-01")],
        "Revenues": [entry("2024-01-01", "2024-12-31", 100, "2025-02-01"),
                     entry("2022-01-01", "2024-12-31", 280, "2025-02-01")],
    })

    _columns, rows = table_of(payload)

    assert rows["Revenue"]["cells"]["2024-12-31"]["value"] == 100


# ---------------------------------------------------------------------------
# The two views agree, on every fixture
# ---------------------------------------------------------------------------

def _fixture_paths():
    return sorted(glob.glob(os.path.join(FIXTURE_DIR, "cik*.json")))


@pytest.mark.parametrize("path", _fixture_paths(),
                         ids=lambda p: os.path.basename(p)[:-5])
def test_both_views_report_the_same_periods_and_the_same_values(path, monkeypatch):
    """R5's mitigation, checked rather than asserted.

    Every committed fixture, all fourteen displayed items, every year either
    view will show. A number that appears in one table and not the other, or
    differs between them, fails here.
    """
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)

    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: payload)
    monkeypatch.setattr(edgar_api, "get_company_meta", lambda cik: {"sic": "3571"})

    cik = payload["cik"]
    _entity, columns, rows, _scope = flask_app._build_xbrl_result(cik, 1995, 2035, "annual")
    by_item = {row["line_item"]: row for row in rows}
    peer = pc.fetch_peer_data(str(cik), list(xbrl.TAG_MAP), n_periods=40)

    single_ends = sorted(c["key"] for c in columns)
    peer_ends = sorted({p["period_end"]
                        for info in peer["line_items"].values()
                        for p in info["periods"]})
    assert single_ends == peer_ends

    for name, info in peer["line_items"].items():
        for period in info["periods"]:
            end = period["period_end"]
            assert period["value"] == by_item[name]["cells"][end]["value"], (
                "{} {} {}".format(os.path.basename(path), name, end))
            assert (period["provenance"]["state"]
                    == by_item[name]["cells"][end]["provenance"]["state"])
