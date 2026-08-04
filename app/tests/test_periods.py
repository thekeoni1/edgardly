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


def entry(start, end, value, filed, fp="FY", form="10-K"):
    return {"start": start, "end": end, "val": value, "fy": int(end[:4]),
            "fp": fp, "form": form, "filed": filed, "accn": "accn-" + filed}


def instant(end, value, filed, fp="FY", form="10-K"):
    return {"end": end, "val": value, "fy": int(end[:4]), "fp": fp,
            "form": form, "filed": filed, "accn": "accn-" + filed}


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
