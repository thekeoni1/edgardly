"""test_provenance.py -- every value says which of three things it is.

Reported, derived, or missing. The rules these tests pin down:

  - a reported value names its tag, its filed date, and its accession number,
    per period, so a row stitched from two tags reports two different tags
  - a derived value names the formula and its inputs, and every input must be
    reported for the same period or the value stays missing
  - a missing value carries a pointer: which statement of which filing, with a
    link built from the accession number of a filing that did report the period
  - nothing is ever guessed and nothing is ever zero-filled

Built on synthetic payloads so every input is visible. test_real_filings.py
asks the same questions of a real Apple payload.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as flask_app
import edgar_api
import line_items
import peer_comparison as pc
import xbrl_extractor as xbrl


# Raw EDGAR entries, same shape test_tag_resolution.py builds by hand.

def entry(end, value, filed, start=None, fp="FY", form="10-K"):
    """One flow entry. start defaults to a full year before end."""
    if start is None:
        start = "{}{}".format(int(end[:4]) - 1, end[4:])
    return {"start": start, "end": end, "val": value, "fy": int(end[:4]),
            "fp": fp, "form": form, "filed": filed, "accn": "accn-" + filed}


def instant(end, value, filed, fp="FY", form="10-K"):
    return {"end": end, "val": value, "fy": int(end[:4]), "fp": fp,
            "form": form, "filed": filed, "accn": "accn-" + filed}


def facts(tags, unit="USD"):
    return {
        "entityName": "Test Co",
        "cik": 1,
        "facts": {"us-gaap": {
            tag: {"units": {unit: entries}} for tag, entries in tags.items()
        }},
    }


# ---------------------------------------------------------------------------
# Pointers into EDGAR
# ---------------------------------------------------------------------------

def test_filing_index_url_strips_the_accession_dashes():
    """The archive path wants the digits, and the CIK without its padding."""
    assert xbrl.filing_index_url("0000320193", "0000320193-23-000106") == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/")
    assert xbrl.filing_index_url(320193, "0000320193-23-000106") == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/")


def test_filing_index_url_is_none_when_it_cannot_be_built():
    """No pointer is better than a pointer to nowhere."""
    assert xbrl.filing_index_url(None, "0000320193-23-000106") is None
    assert xbrl.filing_index_url("320193", None) is None
    assert xbrl.filing_index_url("not-a-cik", "0000320193-23-000106") is None


def _entries(*raw):
    return {"entityName": "Test Co", "cik": 1,
            "facts": {"us-gaap": {"Revenues": {"units": {"USD": list(raw)}}}}}


def test_pointers_prefer_the_periods_own_annual_filing():
    """FY2023's own 10-K reported FY2023 first; FY2024's carried it as a comparative."""
    payload = _entries(
        {"end": "2023-12-31", "form": "10-K", "filed": "2024-02-01", "accn": "own-10k"},
        {"end": "2023-12-31", "form": "10-K", "filed": "2025-02-01", "accn": "later-10k"},
        {"end": "2023-12-31", "form": "10-Q", "filed": "2023-11-01", "accn": "a-10q"},
    )
    pointer = xbrl.filing_pointers(payload)["2023-12-31"]
    assert pointer == {"accn": "own-10k", "form": "10-K", "filed": "2024-02-01"}


def test_pointers_fall_back_to_an_interim_filing():
    """An interim filing is a worse pointer than a 10-K, and better than none."""
    payload = _entries(
        {"end": "2023-12-31", "form": "10-Q", "filed": "2024-05-01", "accn": "a-10q"},
    )
    assert xbrl.filing_pointers(payload)["2023-12-31"]["accn"] == "a-10q"


def test_pointers_read_the_payload_not_the_resolved_series():
    """Resolution keeps one entry per period per tag, the latest filed.

    Pointed at that, a missing FY2023 value would cite the FY2024 10-K, which
    reported FY2023 only as a comparative. The pointer has to see the filings
    resolution threw away.
    """
    payload = _entries(
        {"end": "2023-12-31", "form": "10-K", "filed": "2023-11-03", "accn": "fy2023-10k",
         "start": "2023-01-01", "val": 100, "fy": 2023, "fp": "FY"},
        {"end": "2023-12-31", "form": "10-K", "filed": "2024-11-01", "accn": "fy2024-10k",
         "start": "2023-01-01", "val": 100, "fy": 2024, "fp": "FY"},
    )
    resolved, _tag = xbrl.resolve_line_item(payload, "Revenue")
    assert [dp["accn"] for dp in resolved] == ["fy2024-10k"]      # the older one is gone
    assert xbrl.filing_pointers(payload)["2023-12-31"]["accn"] == "fy2023-10k"


# ---------------------------------------------------------------------------
# The three states
# ---------------------------------------------------------------------------

def test_reported_provenance_carries_the_filing_it_came_from():
    dp = {"tag": "Revenues", "filed": "2024-02-01", "accn": "0000320193-24-000001",
          "form": "10-K", "value": 100}
    prov = xbrl.reported_provenance(dp)
    assert prov == {
        "state": "reported",
        "tag": "Revenues",
        "filed": "2024-02-01",
        "accession": "0000320193-24-000001",
        "form": "10-K",
    }


def test_derived_provenance_carries_the_formula_and_its_inputs():
    prov = xbrl.derived_provenance("Revenue - Cost of Revenue", [
        {"name": "Revenue", "value": 100, "tag": "Revenues",
         "filed": "2024-02-01", "accession": "accn-1"},
        {"name": "Cost of Revenue", "value": 60, "tag": "CostOfRevenue",
         "filed": "2024-02-01", "accession": "accn-1"},
    ])
    assert prov["state"] == "derived"
    assert prov["formula"] == "Revenue - Cost of Revenue"
    assert [i["name"] for i in prov["inputs"]] == ["Revenue", "Cost of Revenue"]
    assert prov["inputs"][0]["tag"] == "Revenues"


def test_missing_provenance_names_the_statement_and_links_the_filing():
    """The message form the plan specifies, built out of data already in hand."""
    prov = xbrl.missing_provenance(
        "Gross Profit", "FY2023", cik="0000320193",
        pointer={"accn": "0000320193-23-000106", "form": "10-K", "filed": "2023-11-03"})

    assert prov["state"] == "missing"
    assert prov["flag"] == "NOT_TAGGED"
    assert prov["statement"] == "income statement"
    assert prov["message"] == (
        "Not tagged in XBRL. Check the income statement of the FY2023 10-K: "
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/.")


def test_missing_provenance_still_names_the_statement_without_a_pointer():
    """A filing nobody can identify costs the link, not the explanation."""
    prov = xbrl.missing_provenance("Total Assets", "FY2023", cik="320193", pointer=None)
    assert prov["url"] is None
    assert prov["message"] == (
        "Not tagged in XBRL. Check the balance sheet of the FY2023 10-K.")


def test_missing_provenance_uses_the_statement_the_registry_names():
    """D&A is a cash flow item, so that is where a reader is sent."""
    assert xbrl.missing_provenance("D&A", "FY2023")["statement"] == "cash flow statement"
    assert xbrl.missing_provenance("Capex", "FY2023")["statement"] == "cash flow statement"
    assert xbrl.missing_provenance("EPS Basic", "FY2023")["statement"] == "income statement"


def test_period_label_reads_the_year_off_the_period_end():
    """EDGAR's fy field labels the filing, not the fact, so the date decides."""
    assert xbrl.period_label("2023-09-30", "FY", "annual") == "FY2023"
    assert xbrl.period_label("2023-06-30", "Q3", "quarterly") == "Q3 FY2023"
    assert xbrl.period_label("", "FY", "annual") == ""


def test_a_quarter_with_no_confirmed_year_ends_keeps_its_own_year():
    """Nothing to place the quarter in, so its end date's year stands in.

    The fallback is a name, not a value. Passing no year ends is what a caller
    that has confirmed none does, and the answer is the one the labels carried
    before quarters were named for their fiscal year.
    """
    assert xbrl.period_label("2023-06-30", "Q3", "quarterly", 0, ()) == "Q3 FY2023"
    assert xbrl.period_label("2026-01-31", "Q4", "quarterly", 1, ()) == "Q4 FY2025"


# ---------------------------------------------------------------------------
# End to end through the single-company payload
# ---------------------------------------------------------------------------

TWO_YEARS = ("2022-12-31", "2023-12-31")


def _payload():
    """A filer that reports revenue and cost of revenue but never gross profit."""
    return facts({
        "Revenues": [entry("2022-12-31", 1_000_000_000, "2023-02-01"),
                     entry("2023-12-31", 1_200_000_000, "2024-02-01")],
        "CostOfRevenue": [entry("2022-12-31", 600_000_000, "2023-02-01"),
                          entry("2023-12-31", 700_000_000, "2024-02-01")],
        "Assets": [instant("2022-12-31", 2_000_000_000, "2023-02-01"),
                   instant("2023-12-31", 2_400_000_000, "2024-02-01")],
    })


@pytest.fixture
def built(monkeypatch):
    """_build_xbrl_result over the synthetic payload, network fully patched out."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: _payload())
    monkeypatch.setattr(edgar_api, "get_company_meta",
                        lambda cik: {"sic": "7372", "sic_description": "Software"})
    entity, columns, rows, scope = flask_app._build_xbrl_result(1, 2022, 2023, "annual")
    return entity, columns, {row["line_item"]: row for row in rows}, scope


def test_every_cell_of_the_table_is_in_exactly_one_state(built):
    """No hole in the grid: 14 line items times 2 years, all accounted for."""
    _entity, columns, rows, _scope = built
    states = {}
    for row in rows.values():
        assert set(row["cells"]) == set(TWO_YEARS)
        for col in columns:
            prov = row["cells"][col["key"]]["provenance"]
            assert prov["state"] in ("reported", "derived", "missing")
            states[prov["state"]] = states.get(prov["state"], 0) + 1

    assert sum(states.values()) == len(line_items.UI_LINE_ITEMS) * len(TWO_YEARS)
    assert states["reported"] == 6      # revenue, cost of revenue, assets, two years
    assert states["derived"] == 2       # gross profit, two years


def test_a_reported_cell_names_its_own_filing(built):
    _entity, _columns, rows, _scope = built
    cell = rows["Revenue"]["cells"]["2023-12-31"]
    assert cell["value"] == 1_200_000_000
    assert cell["provenance"] == {
        "state": "reported", "tag": "Revenues", "filed": "2024-02-01",
        "accession": "accn-2024-02-01", "form": "10-K",
    }


def test_gross_profit_is_derived_where_the_filer_tags_none(built):
    """Arithmetic on two reported values in the same table, with the work shown."""
    _entity, _columns, rows, _scope = built
    cell = rows["Gross Profit"]["cells"]["2023-12-31"]

    assert cell["value"] == 500_000_000
    prov = cell["provenance"]
    assert prov["state"] == "derived"
    assert prov["formula"] == "Revenue - Cost of Revenue"
    assert [(i["name"], i["value"], i["tag"]) for i in prov["inputs"]] == [
        ("Revenue", 1_200_000_000, "Revenues"),
        ("Cost of Revenue", 700_000_000, "CostOfRevenue"),
    ]


def test_a_missing_cell_points_at_the_filing_that_would_hold_it(built):
    """Net income is untagged here, so the cell says where a reader should look."""
    _entity, _columns, rows, _scope = built
    cell = rows["Net Income"]["cells"]["2023-12-31"]

    assert cell["value"] is None
    prov = cell["provenance"]
    assert prov["state"] == "missing"
    assert prov["statement"] == "income statement"
    assert prov["message"] == (
        "Not tagged in XBRL. Check the income statement of the FY2023 10-K: "
        "https://www.sec.gov/Archives/edgar/data/1/accn20240201/.")


def test_a_value_is_never_derived_from_a_derived_value(monkeypatch):
    """Gross profit needs both inputs reported; one derived input is not enough.

    Cost of revenue is untagged here, so gross profit cannot be computed. The
    honest answer is a missing cell, not a chain of inference.
    """
    payload = facts({
        "Revenues": [entry("2023-12-31", 1_200_000_000, "2024-02-01")],
    })
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: payload)
    monkeypatch.setattr(edgar_api, "get_company_meta", lambda cik: {"sic": "7372"})

    _entity, _columns, rows, _scope = flask_app._build_xbrl_result(1, 2023, 2023, "annual")
    by_item = {row["line_item"]: row for row in rows}
    assert by_item["Gross Profit"]["cells"]["2023-12-31"]["provenance"]["state"] == "missing"
    assert by_item["Gross Profit"]["cells"]["2023-12-31"]["value"] is None


def test_the_row_tag_label_names_every_tag_the_row_used(monkeypatch):
    """One tag_used cannot describe a row stitched out of two tag eras."""
    payload = facts({
        "Revenues": [entry("2022-12-31", 100, "2023-02-01")],
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            entry("2023-12-31", 120, "2024-02-01")],
    })
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: payload)
    monkeypatch.setattr(edgar_api, "get_company_meta", lambda cik: {"sic": "7372"})

    _entity, _columns, rows, _scope = flask_app._build_xbrl_result(1, 2022, 2023, "annual")
    revenue = next(row for row in rows if row["line_item"] == "Revenue")

    assert revenue["tag_summary"] == (
        "Revenues -> RevenueFromContractWithCustomerExcludingAssessedTax")
    assert revenue["cells"]["2022-12-31"]["provenance"]["tag"] == "Revenues"
    assert revenue["cells"]["2023-12-31"]["provenance"]["tag"] == (
        "RevenueFromContractWithCustomerExcludingAssessedTax")


def test_total_debt_is_displayed_now_that_its_derivation_is_right(built):
    """The tripwire that stood here has been tripped on purpose.

    Session 3 left a test asserting Total Debt appeared in no payload, because
    its derivation was a chain pick that understated Apple by the whole of its
    commercial paper. Session 4B replaced the chain with a sum of the current
    liability lines a filer actually reports, so the row is now correct and is
    shown. The test that guarded the gap is replaced by one that guards the
    fix: the row is displayed, it is derived rather than reported, and it
    carries the arithmetic that produced it.
    """
    _entity, _columns, rows, _scope = built
    assert "Total Debt" in rows
    assert "Total Debt" in line_items.UI_LINE_ITEMS
    assert "Total Debt" in line_items.DERIVATIONS
    assert "Total Debt" not in line_items.REGISTRY      # arithmetic, never a tag


def test_a_row_with_no_debt_lines_at_all_says_which_input_was_missing(built):
    """The synthetic payload here tags revenue and nothing else.

    "Not tagged in XBRL, check the balance sheet" would be true of Total Debt
    for every filer that has ever filed, and would send a reader looking for a
    line no balance sheet carries. The message names the component instead.
    """
    _entity, columns, rows, _scope = built
    prov = rows["Total Debt"]["cells"][columns[0]["key"]]["provenance"]

    assert prov["state"] == "missing"
    assert prov["flag"] == xbrl.FLAG_DERIVATION_UNAVAILABLE
    assert prov["message"].startswith(
        "No filer tags this; Edgardly computes it as Short-Term Debt + Long-Term Debt.")
    assert "Short-Term Debt, Long-Term Debt is not reported" in prov["message"]


# ---------------------------------------------------------------------------
# The peer path tells the same story
# ---------------------------------------------------------------------------

def test_peer_periods_carry_the_same_three_states(monkeypatch):
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: _payload())

    result = pc.fetch_peer_data("1", ["Revenue", "Cost of Revenue", "Gross Profit",
                                      "Net Income"], n_periods=2)
    items = result["line_items"]

    revenue = items["Revenue"]["periods"][0]
    assert revenue["provenance"]["state"] == "reported"
    assert revenue["provenance"]["tag"] == "Revenues"
    assert revenue["provenance"]["accession"] == "accn-2024-02-01"

    gross = items["Gross Profit"]["periods"][0]
    assert gross["value"] == 500_000_000
    assert gross["provenance"]["state"] == "derived"
    assert gross["provenance"]["formula"] == "Revenue - Cost of Revenue"

    missing = items["Net Income"]["periods"][0]
    assert missing["value"] is None
    assert missing["provenance"]["state"] == "missing"
    assert "Check the income statement of the FY2023 10-K" in missing["provenance"]["message"]


def test_peer_gross_profit_stays_missing_without_both_inputs(monkeypatch):
    """The peer table applies the same rule as the single-company table."""
    payload = facts({"Revenues": [entry("2023-12-31", 1_200_000_000, "2024-02-01")]})
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: payload)

    result = pc.fetch_peer_data("1", ["Revenue", "Gross Profit"], n_periods=1)
    gross = result["line_items"]["Gross Profit"]["periods"][0]
    assert gross["value"] is None
    assert gross["provenance"]["state"] == "missing"
