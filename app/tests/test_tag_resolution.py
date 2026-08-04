"""test_tag_resolution.py -- per-period tag stitching, on data built by hand.

resolve_line_item used to pick one winning tag per line item and use it for the
whole history, which threw away every year the winner did not happen to carry.
It now resolves period by period. These tests pin the rules down on synthetic
companyfacts payloads, where every input is visible:

  - a period reported by more than one tag goes to the earliest tag in the chain
  - within one tag, an annual report beats any other form
  - within one form rank, the most recently filed entry wins
  - a period only a later tag reports is kept, not dropped
  - adjacent years from different tags raise TAG_TRANSITION on the seam

test_real_filings.py asks the same questions of a real Apple payload.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import line_items
import xbrl_extractor as xbrl


def entry(end, value, filed, start=None, fp="FY", form="10-K"):
    """One raw EDGAR unit entry. start defaults to a full year before end."""
    if start is None:
        start = "{}{}".format(int(end[:4]) - 1, end[4:])
    return {"start": start, "end": end, "val": value, "fy": int(end[:4]),
            "fp": fp, "form": form, "filed": filed, "accn": "accn-" + filed}


def instant(end, value, filed, fp="FY", form="10-K"):
    return {"end": end, "val": value, "fy": int(end[:4]), "fp": fp,
            "form": form, "filed": filed, "accn": "accn-" + filed}


def facts(tags, unit="USD"):
    """Build a companyfacts payload: {tag: [raw entries]}."""
    return {
        "entityName": "Test Co",
        "cik": 1,
        "facts": {"us-gaap": {
            tag: {"units": {unit: entries}} for tag, entries in tags.items()
        }},
    }


def values_by_end(data):
    return {dp["end"]: dp["value"] for dp in data}


def tags_by_end(data):
    return {dp["end"]: dp["tag"] for dp in data}


# ---------------------------------------------------------------------------
# Stitching
# ---------------------------------------------------------------------------

def test_periods_only_an_older_tag_reports_are_kept():
    """The Apple truncation, in miniature: the old years must survive."""
    payload = facts({
        "Revenues": [entry("2016-12-31", 100, "2017-02-01"),
                     entry("2017-12-31", 110, "2018-02-01")],
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            entry("2018-12-31", 120, "2019-02-01"),
            entry("2019-12-31", 130, "2020-02-01")],
    })

    data, tag_used = xbrl.resolve_line_item(payload, "Revenue")

    assert values_by_end(data) == {
        "2016-12-31": 100, "2017-12-31": 110, "2018-12-31": 120, "2019-12-31": 130,
    }
    # tag_used names the source of the most recent year, not of the whole row.
    assert tag_used == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_an_overlapping_period_goes_to_the_earlier_tag_in_the_chain():
    """Chain position is the tiebreak, not recency of filing."""
    payload = facts({
        "Revenues": [entry("2018-12-31", 120, "2019-02-01")],
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            entry("2018-12-31", 125, "2020-02-01"),
            entry("2019-12-31", 130, "2020-02-01")],
    })

    data, _tag_used = xbrl.resolve_line_item(payload, "Revenue")

    assert values_by_end(data)["2018-12-31"] == 120
    assert tags_by_end(data)["2018-12-31"] == "Revenues"


def test_within_one_tag_the_latest_filing_wins():
    """A 10-K/A restating a year beats the original 10-K."""
    payload = facts({
        "Revenues": [entry("2016-12-31", 100, "2017-02-01"),
                     entry("2016-12-31", 105, "2017-08-01", form="10-K/A")],
    })

    data, _tag_used = xbrl.resolve_line_item(payload, "Revenue")

    assert values_by_end(data) == {"2016-12-31": 105}


def test_an_annual_report_outranks_a_later_filing_that_is_not_one():
    """A proxy statement repeating a year does not take it from the 10-K.

    The rounding is what gives it away in the wild, but the rule is about the
    form and not the number: a DEF 14A, an 8-K earnings release, and a 10-Q
    comparative are all repeating a figure some annual report already reported.
    """
    payload = facts({
        "Revenues": [entry("2016-12-31", 100, "2017-02-01"),
                     entry("2016-12-31", 100.5, "2019-04-01", form="DEF 14A")],
    })

    data, _tag_used = xbrl.resolve_line_item(payload, "Revenue")

    assert values_by_end(data) == {"2016-12-31": 100}
    assert data[0]["form"] == "10-K"


def test_the_rank_does_not_reach_across_the_chain():
    """Chain position still decides first; the rank only breaks ties inside a tag.

    Here the later tag in the chain holds the 10-K and the earlier one holds
    only a proxy repetition. The earlier tag still wins the period, because
    which tag means what is a stronger signal than which form said it, and
    reordering that would undo the stitching Session 2 built.
    """
    payload = facts({
        "Revenues": [entry("2016-12-31", 100.5, "2019-04-01", form="DEF 14A")],
        "SalesRevenueNet": [entry("2016-12-31", 100, "2017-02-01")],
    })

    data, _tag_used = xbrl.resolve_line_item(payload, "Revenue")

    assert tags_by_end(data) == {"2016-12-31": "Revenues"}


def test_a_20f_counts_as_an_annual_report():
    """Foreign private issuers file a 20-F, and it is their annual report."""
    payload = facts({
        "Revenues": [entry("2016-12-31", 100, "2017-04-01", form="20-F"),
                     entry("2016-12-31", 100.5, "2018-06-01", form="6-K")],
    })

    data, _tag_used = xbrl.resolve_line_item(payload, "Revenue")

    assert values_by_end(data) == {"2016-12-31": 100}


def test_only_an_annual_report_and_its_amendment_carry_the_rank():
    forms = {"10-K": True, "10-K/A": True, "10-KT": True, "20-F": True,
             "20-F/A": True, "40-F": True, "10-Q": False, "8-K": False,
             "DEF 14A": False, "6-K": False, "S-1": False, "": False,
             None: False}
    assert {f: xbrl.is_annual_report_form(f) for f in forms} == forms


def test_deduplication_ranks_forms_the_same_way_resolution_does():
    """Two orderings of the same question is how a table disagrees with itself."""
    points = [
        {"unit": "USD", "start": "2016-01-01", "end": "2016-12-31", "value": 100,
         "form": "10-K", "filed": "2017-02-01"},
        {"unit": "USD", "start": "2016-01-01", "end": "2016-12-31", "value": 100.5,
         "form": "DEF 14A", "filed": "2019-04-01"},
    ]

    kept = xbrl.deduplicate_period(points)

    assert len(kept) == 1
    assert kept[0]["value"] == 100
    assert kept[0]["form"] == "10-K"


def test_deduplication_still_prefers_the_later_of_two_annual_reports():
    points = [
        {"unit": "USD", "start": "2016-01-01", "end": "2016-12-31", "value": 100,
         "form": "10-K", "filed": "2017-02-01"},
        {"unit": "USD", "start": "2016-01-01", "end": "2016-12-31", "value": 105,
         "form": "10-K/A", "filed": "2017-08-01"},
    ]

    kept = xbrl.deduplicate_period(points)

    assert [dp["value"] for dp in kept] == [105]


def test_a_series_is_returned_oldest_first():
    payload = facts({
        "Revenues": [entry("2018-12-31", 120, "2019-02-01"),
                     entry("2016-12-31", 100, "2017-02-01"),
                     entry("2017-12-31", 110, "2018-02-01")],
    })

    data, _tag_used = xbrl.resolve_line_item(payload, "Revenue")

    assert [dp["end"] for dp in data] == ["2016-12-31", "2017-12-31", "2018-12-31"]


def test_periods_in_different_units_stay_separate():
    """The period key includes the unit, so a shares series never merges into USD."""
    payload = {
        "entityName": "Test Co", "cik": 1,
        "facts": {"us-gaap": {"Revenues": {"units": {
            "USD": [entry("2018-12-31", 120, "2019-02-01")],
            "EUR": [entry("2018-12-31", 100, "2019-02-01")],
        }}}},
    }

    data, _tag_used = xbrl.resolve_line_item(payload, "Revenue")

    assert sorted(dp["unit"] for dp in data) == ["EUR", "USD"]


def test_nothing_reported_resolves_to_nothing():
    data, tag_used = xbrl.resolve_line_item(facts({}), "Revenue")
    assert data == []
    assert tag_used is None


def test_an_unknown_line_item_resolves_to_nothing():
    payload = facts({"Revenues": [entry("2018-12-31", 120, "2019-02-01")]})
    assert xbrl.resolve_line_item(payload, "Not A Line Item") == ([], None)


def test_a_registry_item_outside_tag_map_resolves():
    """Extraction is not limited to the 14 displayed items."""
    payload = facts({"DepreciationDepletionAndAmortization": [
        entry("2018-12-31", 42, "2019-02-01")]})

    data, tag_used = xbrl.resolve_line_item(payload, "D&A")

    assert tag_used == "DepreciationDepletionAndAmortization"
    assert values_by_end(data) == {"2018-12-31": 42}


# ---------------------------------------------------------------------------
# What the existing views extract
# ---------------------------------------------------------------------------

def test_extract_all_line_items_defaults_to_the_items_a_tag_reports():
    """TAG_MAP, not the displayed set: Total Debt is displayed and has no tag."""
    payload = facts({"Revenues": [entry("2018-12-31", 120, "2019-02-01")]})

    extracted = xbrl.extract_all_line_items(payload)

    assert list(extracted) == list(line_items.TAG_MAP)
    assert "Total Debt" not in extracted
    assert extracted["Revenue"]["tag_used"] == "Revenues"
    assert extracted["Net Income"]["data"] == []


def test_extract_all_line_items_takes_an_explicit_set():
    payload = facts({
        "Revenues": [entry("2018-12-31", 120, "2019-02-01")],
        "DepreciationDepletionAndAmortization": [entry("2018-12-31", 42, "2019-02-01")],
    })

    extracted = xbrl.extract_all_line_items(payload, ["Revenue", "D&A"])

    assert list(extracted) == ["Revenue", "D&A"]
    assert extracted["D&A"]["data"][0]["value"] == 42


# ---------------------------------------------------------------------------
# The seam flag
# ---------------------------------------------------------------------------

def _transitions(payload, line_item="Revenue"):
    deduped = xbrl.deduplicate_all_line_items(xbrl.extract_all_line_items(payload))
    flags = xbrl.validate_financials(deduped)
    return [f for f in flags[line_item] if f["flag_type"] == xbrl.FLAG_TAG_TRANSITION]


def test_a_tag_switch_between_adjacent_years_is_flagged():
    payload = facts({
        "Revenues": [entry("2017-12-31", 110, "2018-02-01")],
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            entry("2018-12-31", 120, "2019-02-01")],
    })

    flags = _transitions(payload)

    assert len(flags) == 1
    assert flags[0]["period_end"] == "2018-12-31"
    assert flags[0]["value"] == 120
    assert flags[0]["details"] == {
        "previous_tag": "Revenues",
        "current_tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "previous_period_end": "2017-12-31",
    }


def test_one_tag_throughout_raises_no_seam():
    payload = facts({
        "Revenues": [entry("2017-12-31", 110, "2018-02-01"),
                     entry("2018-12-31", 120, "2019-02-01")],
    })

    assert _transitions(payload) == []


def test_a_gap_in_the_history_is_not_a_seam():
    """Two eras seven years apart are not adjacent, whatever tags they use."""
    payload = facts({
        "Revenues": [entry("2011-12-31", 60, "2012-02-01")],
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            entry("2018-12-31", 120, "2019-02-01")],
    })

    assert _transitions(payload) == []


def test_quarterly_entries_do_not_hide_the_seam():
    """EDGAR stamps fp on the filing, so a 10-K's comparative quarters read "FY".

    Judging annual periods by that label alone would leave the two full years
    non-adjacent in the sorted series, and the seam between them would never be
    found.
    """
    payload = facts({
        "Revenues": [
            entry("2017-12-31", 110, "2018-02-01"),
            entry("2017-12-31", 30, "2018-02-01", start="2017-10-01"),
        ],
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            entry("2018-12-31", 120, "2019-02-01"),
            entry("2018-03-31", 28, "2019-02-01", start="2018-01-01"),
        ],
    })

    flags = _transitions(payload)

    assert len(flags) == 1
    assert flags[0]["period_end"] == "2018-12-31"


def test_the_seam_flag_reaches_the_balance_sheet_too():
    payload = facts({
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": [
            instant("2017-12-31", 500, "2018-02-01")],
        "StockholdersEquity": [instant("2018-12-31", 550, "2019-02-01")],
    })

    flags = _transitions(payload, "Total Equity")

    assert len(flags) == 1
    assert flags[0]["period_end"] == "2018-12-31"
    assert flags[0]["details"]["current_tag"] == "StockholdersEquity"
