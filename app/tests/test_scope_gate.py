"""test_scope_gate.py -- who Edgardly will not build a scaffold for, and why.

Two real fixtures anchor this: JPMorgan Chase (CIK 19617, SIC 6021), a bank the
SIC ranges refuse, and SAP SE (CIK 1000184), a filer that reports only under
IFRS and so has nothing Edgardly can read at all. Regenerate either with:

    python scripts/make_fixture.py 19617
    python scripts/make_fixture.py 1000184

The SIC code comes from EDGAR's submissions API rather than companyfacts, so
make_fixture records it in the fixture's _fixture block; without it the gate
could not be tested offline. No test here touches the network.

The gate governs scaffolds only. Both companies still extract, still compare
against peers, and still export, which these tests check on the real payloads.
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
import xbrl_extractor as xbrl

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BANK_PATH = os.path.join(FIXTURES, "cik19617.json")
IFRS_PATH = os.path.join(FIXTURES, "cik1000184.json")

MILLION = 1_000_000


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def bank_facts():
    return _load(BANK_PATH)


@pytest.fixture(scope="module")
def ifrs_facts():
    return _load(IFRS_PATH)


def _sic(facts):
    return facts["_fixture"]["company"].get("sic")


def _us_gaap(tags):
    return {"entityName": "Test Co", "cik": 1,
            "facts": {"us-gaap": {tag: {"units": {"USD": []}} for tag in tags}}}


# ---------------------------------------------------------------------------
# The SIC ranges
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sic", ["6020", "6021", "6099", "6199", "6311", "6350", "6411"])
def test_financial_sic_codes_are_refused(sic):
    verdict = line_items.is_in_scope(sic, _us_gaap(["Revenues"]))
    assert verdict.in_scope is False
    assert verdict.reason == line_items.SCOPE_FINANCIAL_SIC


@pytest.mark.parametrize("sic", ["6019", "6200", "6310", "6412", "7372", "3711"])
def test_sic_codes_outside_the_ranges_are_allowed(sic):
    """The boundaries are inclusive, and everything past them is ordinary."""
    verdict = line_items.is_in_scope(sic, _us_gaap(["Revenues"]))
    assert verdict.in_scope is True
    assert verdict.reason == line_items.SCOPE_IN
    assert verdict.message == ""


def test_the_refusal_says_exactly_what_the_plan_says_it_says():
    verdict = line_items.is_in_scope("6021", _us_gaap(["Revenues"]))
    assert verdict.message.startswith(
        "Bank and insurance financial statements do not fit the standard "
        "three-statement template; Edgardly will not generate a scaffold for "
        "this company")
    # And it says which code put the company there, so a wrong SIC is arguable.
    assert "SIC code 6021" in verdict.message
    assert verdict.detail["sic_range"] == "bank"


def test_an_unknown_sic_does_not_crash_the_gate():
    """A submissions lookup can fail; the gate then rests on the facts alone."""
    for sic in (None, "", "not-a-code"):
        verdict = line_items.is_in_scope(sic, _us_gaap(["Revenues"]))
        assert verdict.in_scope is True


# ---------------------------------------------------------------------------
# The statement-shape heuristic
# ---------------------------------------------------------------------------

def test_the_heuristic_catches_a_financial_the_sic_missed():
    """No revenue, no cost of revenue, but interest and dividend income: a bank."""
    facts = _us_gaap(["InterestAndDividendIncomeOperating", "Assets", "Liabilities"])
    verdict = line_items.is_in_scope("3711", facts)

    assert verdict.in_scope is False
    assert verdict.reason == line_items.SCOPE_FINANCIAL_SHAPE
    assert verdict.detail["heuristic_matched"] is True
    # The evidence is in the message, so a misclassification can be argued with.
    assert "SIC code (3711) is not a financial one" in verdict.message
    assert "InterestAndDividendIncomeOperating" in verdict.message


def test_the_heuristic_is_quiet_when_the_filer_reports_revenue():
    """JPMorgan tags Revenues, so only the SIC range refuses it, not the shape."""
    facts = _us_gaap(["InterestAndDividendIncomeOperating", "Revenues"])
    verdict = line_items.is_in_scope("3711", facts)
    assert verdict.in_scope is True
    assert verdict.detail["heuristic_matched"] is False


def test_an_ordinary_company_is_not_refused():
    facts = _us_gaap(["Revenues", "CostOfRevenue", "Assets"])
    assert line_items.is_in_scope("7372", facts).in_scope is True


# ---------------------------------------------------------------------------
# IFRS-only filers
# ---------------------------------------------------------------------------

def test_an_ifrs_only_filer_gets_its_own_message(ifrs_facts):
    """Not the bank message: nothing about SAP's statements is bank-shaped."""
    verdict = line_items.is_in_scope(_sic(ifrs_facts), ifrs_facts)

    assert verdict.in_scope is False
    assert verdict.reason == line_items.SCOPE_IFRS_ONLY
    assert verdict.message.startswith("This company reports under IFRS, not US GAAP")
    assert "us-gaap" in verdict.message
    assert line_items.REFUSAL_FINANCIAL not in verdict.message
    assert verdict.detail["taxonomies"] == ["dei", "ifrs-full"]


def test_a_filer_reporting_both_taxonomies_is_not_refused_as_ifrs():
    """ifrs-full alongside us-gaap is not the same as ifrs-full instead of it."""
    facts = {"facts": {"us-gaap": {"Revenues": {}}, "ifrs-full": {"Revenue": {}}}}
    assert line_items.is_in_scope("7372", facts).in_scope is True


def test_an_empty_us_gaap_block_counts_as_no_us_gaap():
    """A taxonomy present but empty is a filer that tagged nothing in it."""
    facts = {"facts": {"us-gaap": {}, "ifrs-full": {"Revenue": {}}}}
    verdict = line_items.is_in_scope("7372", facts)
    assert verdict.reason == line_items.SCOPE_IFRS_ONLY


def test_the_ifrs_fixture_really_is_ifrs_only(ifrs_facts):
    """The claim the message rests on, checked against the payload itself."""
    assert ifrs_facts["entityName"] == "SAP SE"
    assert "us-gaap" not in ifrs_facts["facts"]
    assert ifrs_facts["facts"]["ifrs-full"]
    assert _sic(ifrs_facts) == "7372"      # software: the SIC gate would allow it


# ---------------------------------------------------------------------------
# The real bank
# ---------------------------------------------------------------------------

def test_the_bank_fixture_is_refused_by_its_sic(bank_facts):
    assert bank_facts["entityName"] == "JPMORGAN CHASE & CO"
    assert _sic(bank_facts) == "6021"

    verdict = line_items.is_in_scope(_sic(bank_facts), bank_facts)
    assert verdict.in_scope is False
    assert verdict.reason == line_items.SCOPE_FINANCIAL_SIC
    assert verdict.detail["reasons"] == [line_items.SCOPE_FINANCIAL_SIC]


def test_the_bank_fixture_records_how_it_was_made(bank_facts):
    meta = bank_facts["_fixture"]
    assert meta["generator"] == "scripts/make_fixture.py"
    assert "CIK0000019617" in meta["source_url"]
    assert meta["company"]["sic_description"] == "National Commercial Banks"


@pytest.mark.parametrize("path", [BANK_PATH, IFRS_PATH])
def test_the_new_fixtures_hold_nothing_the_code_never_reads(path):
    """Trimming is by tag, so every tag present must be one something reads."""
    facts = _load(path)
    known = set(line_items.DA_COMPONENT_TAGS) | set(line_items.SCOPE_HEURISTIC_TAGS)
    for item in line_items.REGISTRY.values():
        known.update(item.tags)

    extra = set(facts["facts"].get("us-gaap", {})) - known
    assert not extra, "fixture holds tags nothing reads: {}".format(extra)


def test_the_puller_still_works_for_a_bank(bank_facts, monkeypatch):
    """Refusing to scaffold a bank is not refusing to read it."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: bank_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta",
                        lambda cik: {"sic": "6021",
                                     "sic_description": "National Commercial Banks"})

    entity, columns, rows, scope = flask_app._build_xbrl_result(19617, 2023, 2023, "annual")
    by_item = {row["line_item"]: row for row in rows}

    assert entity == "JPMORGAN CHASE & CO"
    assert [c["label"] for c in columns] == ["FY2023"]
    assert scope["in_scope"] is False
    assert scope["reason"] == "financial_sic"

    # Real FY2023 figures off JPMorgan's 10-K, in millions.
    assert by_item["Total Assets"]["cells"]["2023-12-31"]["value"] == 3_875_393 * MILLION
    assert by_item["Total Liabilities"]["cells"]["2023-12-31"]["value"] == 3_547_515 * MILLION
    assert by_item["Total Equity"]["cells"]["2023-12-31"]["value"] == 327_878 * MILLION
    assert by_item["Revenue"]["cells"]["2023-12-31"]["value"] == 158_104 * MILLION


def test_a_bank_balance_sheet_still_balances(bank_facts, monkeypatch):
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: bank_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta", lambda cik: {"sic": "6021"})

    _entity, _columns, rows, _scope = flask_app._build_xbrl_result(19617, 2023, 2023, "annual")
    by_item = {row["line_item"]: row for row in rows}

    def value(name):
        return by_item[name]["cells"]["2023-12-31"]["value"]

    assert value("Total Assets") == value("Total Liabilities") + value("Total Equity")


def test_peer_comparison_still_works_for_a_bank(bank_facts, monkeypatch):
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: bank_facts)

    result = pc.fetch_peer_data("19617", ["Revenue", "Total Assets"], n_periods=1)
    assert result["name"] == "JPMORGAN CHASE & CO"
    assets = result["line_items"]["Total Assets"]["periods"][0]
    assert assets["value"] is not None
    assert assets["provenance"]["state"] == "reported"


def test_a_bank_has_holes_where_a_bank_should_have_holes(bank_facts, monkeypatch):
    """No inventory, no current assets: an honest blank with a pointer, not a zero."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: bank_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta", lambda cik: {"sic": "6021"})

    _entity, _columns, rows, _scope = flask_app._build_xbrl_result(19617, 2023, 2023, "annual")
    gross = {row["line_item"]: row for row in rows}["Gross Profit"]
    cell = gross["cells"]["2023-12-31"]

    assert cell["value"] is None
    assert cell["provenance"]["state"] == "missing"
    assert "Check the income statement of the FY2023 10-K" in cell["provenance"]["message"]
    assert "sec.gov/Archives/edgar/data/19617/" in cell["provenance"]["message"]


# The five years JPMorgan's April 2026 proxy statement repeats, each rounded to
# the nearest hundred million: what the 10-K reports, and what the proxy says.
PROXY_SHADOWED_NET_INCOME = {
    "2021-12-31": (48_334, 48_300),
    "2022-12-31": (37_676, 37_700),
    "2023-12-31": (49_552, 49_600),
    "2024-12-31": (58_471, 58_500),
    "2025-12-31": (57_048, 57_000),
}


def test_the_proxy_statement_really_does_repeat_these_years(bank_facts):
    """The defect this fixture was committed to reproduce, stated as data.

    A DEF 14A filed in April 2026 carries five years of net income rounded to
    the nearest hundred million. Nothing here is about resolution yet: it
    records that both numbers are genuinely in the payload, so the test below
    is choosing between them rather than asserting one exists.
    """
    entries = [dp for dp in xbrl._extract_tag_data(bank_facts, "NetIncomeLoss")
               if xbrl._is_annual_period(dp)]

    for end, (reported, rounded) in PROXY_SHADOWED_NET_INCOME.items():
        for_period = [dp for dp in entries if dp["end"] == end]
        from_10k = {dp["value"] for dp in for_period if dp["form"] == "10-K"}
        from_proxy = {dp["value"] for dp in for_period if dp["form"] == "DEF 14A"}

        assert from_10k == {reported * MILLION}, end
        assert from_proxy == {rounded * MILLION}, end
        # The proxy is the most recently filed of the two, which is what made
        # it win before annual forms were ranked above everything else.
        latest = max(for_period, key=lambda dp: dp["filed"])
        assert latest["form"] == "DEF 14A", end


@pytest.mark.parametrize("end,reported", sorted(
    (end, values[0]) for end, values in PROXY_SHADOWED_NET_INCOME.items()))
def test_the_banks_own_10k_outranks_the_proxy_that_rounds_it(bank_facts, end, reported):
    """PROGRESS.md open question 6, closed: the annual report wins the row.

    "Most recently filed wins" was written for 10-K/A restatements, where a
    later filing really is better information. A proxy statement is not a
    restatement, and rounding a year to the nearest hundred million is not new
    information about it. Ranking annual report forms above every other form
    settles it, and filing date still decides inside the rank.
    """
    data, _tag = xbrl.resolve_line_item(bank_facts, "Net Income")
    winner = next(dp for dp in xbrl.deduplicate_period(data)
                  if dp["end"] == end and xbrl._is_annual_period(dp))

    assert winner["value"] == reported * MILLION
    assert winner["form"] == "10-K"
    assert xbrl.reported_provenance(winner)["form"] == "10-K"


def test_a_restatement_still_beats_the_original_within_the_annual_rank(bank_facts):
    """Ranking forms must not cost the thing the date rule was there for.

    JPMorgan's FY2013 net income was 17,923 million in the 10-K that first
    reported it and 17,886 in the one filed two years later. Both are annual
    reports, so the rank is a tie and the later filing still takes the row.
    """
    for_2013 = [dp for dp in xbrl._extract_tag_data(bank_facts, "NetIncomeLoss")
                if dp["end"] == "2013-12-31" and xbrl._is_annual_period(dp)]
    assert {dp["value"] for dp in for_2013} == {17_923 * MILLION, 17_886 * MILLION}

    data, _tag = xbrl.resolve_line_item(bank_facts, "Net Income")
    winner = next(dp for dp in xbrl.deduplicate_period(data)
                  if dp["end"] == "2013-12-31" and xbrl._is_annual_period(dp))
    assert winner["value"] == 17_886 * MILLION
    assert winner["filed"] == "2016-02-23"


# ---------------------------------------------------------------------------
# What the user sees
# ---------------------------------------------------------------------------

def test_an_ifrs_filer_gets_a_message_instead_of_a_silent_empty_table(
        ifrs_facts, monkeypatch):
    """The table is empty either way; the difference is that it now says why."""
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: ifrs_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta",
                        lambda cik: {"sic": "7372",
                                     "sic_description": "Services-Prepackaged Software"})

    entity, columns, rows, scope = flask_app._build_xbrl_result(
        1000184, 2015, 2025, "annual")

    assert entity == "SAP SE"
    assert columns == []
    assert all(row["cells"] == {} for row in rows)
    assert scope["in_scope"] is False
    assert scope["reason"] == "ifrs_only"
    assert scope["message"].startswith("This company reports under IFRS")


def test_the_scope_verdict_survives_a_failed_sic_lookup(bank_facts, monkeypatch):
    """A submissions outage must not take the puller down with it."""
    def _boom(cik):
        raise RuntimeError("submissions API unavailable")

    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: bank_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta", _boom)

    _entity, columns, _rows, scope = flask_app._build_xbrl_result(
        19617, 2023, 2023, "annual")

    assert columns              # the data still loads
    assert scope["detail"]["sic_lookup"] == "unavailable"
    assert scope["detail"]["sic"] is None
    # Without the SIC there is nothing left to refuse this filer on, and the
    # gate says so rather than guessing.
    assert scope["in_scope"] is True


def test_the_extract_endpoint_carries_the_scope_verdict(bank_facts, monkeypatch):
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: bank_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta", lambda cik: {"sic": "6021"})

    client = flask_app.app.test_client()
    response = client.post("/api/xbrl/extract", json={
        "cik": "19617", "start_year": 2023, "end_year": 2023, "period_type": "annual",
    })
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["scope"]["in_scope"] is False
    assert payload["scope"]["message"].startswith(
        "Bank and insurance financial statements do not fit")
    assert payload["rows"]


# ---------------------------------------------------------------------------
# What the corrected EPS check says about a bank
# ---------------------------------------------------------------------------

def test_jpmorgans_eps_never_reconciles_and_the_reason_is_preferred_stock(bank_facts):
    """Fifty-two flagged periods, every one of them true, and one cause.

    JPMorgan's diluted EPS is computed on net income available to common
    shareholders. This check divides total net income, so every period comes
    out high by the preferred dividend: about 8 percent of a normal year, and
    far more where earnings were small and the dividend was not, which is why
    2009 shows gaps of 40 and 150 percent.

    Nothing is silenced. A reader multiplying this bank's diluted share count
    by its diluted EPS will not get its net income, and being told so is
    correct; the message names preferred dividends as one of the two things it
    can be. Proof of the cause rather than assertion: JPMorgan tags the
    available-to-common figure for ten of these periods, and substituting it
    brings all ten inside tolerance.
    """
    deduped = xbrl.deduplicate_all_line_items(xbrl.extract_all_line_items(bank_facts))
    flags = [f for f in xbrl.validate_financials(deduped)["EPS Diluted"]
             if f["flag_type"] == xbrl.FLAG_EPS_RECONCILIATION]

    assert len(flags) == 52
    assert all(f["details"]["computed_eps"] > f["details"]["reported_eps"]
               for f in flags if f["details"]["reported_eps"] > 0), (
        "a preferred dividend can only make computed EPS too high, never too low")
    assert "preferred" in flags[0]["message"]


def test_a_bank_out_of_scope_for_scaffolds_still_gets_its_flags(bank_facts, monkeypatch):
    """The gate refuses a scaffold. It does not make the puller quieter.

    FY2018 rather than FY2023 because the gap is proportional: JPMorgan's
    preferred dividend was 5.7 percent of its 2018 earnings and under the 5
    percent tolerance by 2021, so its recent years reconcile and its older ones
    do not. That is the check behaving as a tolerance should.
    """
    monkeypatch.setattr(xbrl, "fetch_company_facts", lambda cik: bank_facts)
    monkeypatch.setattr(edgar_api, "get_company_meta", lambda cik: {"sic": "6021"})

    _entity, _columns, rows, scope = flask_app._build_xbrl_result(
        19617, 2018, 2023, "annual")
    by_item = {row["line_item"]: row for row in rows}

    assert scope["in_scope"] is False

    def _reconciliation(end):
        return [f for f in by_item["EPS Diluted"]["cells"][end]["flags"]
                if f["type"] == xbrl.FLAG_EPS_RECONCILIATION]

    assert _reconciliation("2018-12-31")
    assert not _reconciliation("2023-12-31")
