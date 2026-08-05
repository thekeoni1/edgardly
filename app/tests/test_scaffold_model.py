"""test_scaffold_model.py -- the three-statement model spec, against real filers.

app/scaffold/three_statement.py decides what a scaffold contains before any of
it becomes a workbook, so this module checks the decisions rather than the file:
which rows exist, which of them are the filer's own numbers, which are
arithmetic, which are holes, and what each of those says about itself.

The three acceptance filers are here for the reasons V2_PLAN Part 4 puts them
in the set. Apple is the clean one, and its balance sheet ties to the dollar.
Honeywell tags no Liabilities element at all, so its liability total has to be
derived and its balance check has to admit that it is then no longer a check.
Kroger tags no inventory and no SG&A, and its cost of revenue row crosses the
one meaning seam in the registry, so every consequence of a by-design blank
shows up on it.

No test here touches the network.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import line_items
import xbrl_extractor as xbrl
from scaffold import three_statement as ts

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

MILLION = 1_000_000

# SIC codes as the submissions API reports them. Not in companyfacts, which is
# why the scope gate takes them separately.
APPLE = (320193, "3571")
HONEYWELL = (773840, "3728")
KROGER = (56873, "5411")
JPMORGAN = (19617, "6021")


def _facts(cik):
    with open(os.path.join(FIXTURES, "cik{}.json".format(cik)), encoding="utf-8") as h:
        return json.load(h)


def _model(company, **kwargs):
    cik, sic = company
    return ts.build_model(cik, _facts(cik), sic, **kwargs)


@pytest.fixture(scope="module")
def apple():
    return _model(APPLE)


@pytest.fixture(scope="module")
def honeywell():
    return _model(HONEYWELL)


@pytest.fixture(scope="module")
def kroger():
    return _model(KROGER)


def _cell(spec, row_name, label):
    row = ts.row_named(spec, row_name)
    assert row is not None, "no row named {}".format(row_name)
    for period in spec.periods:
        if period.label == label:
            return row.cells[period.key]
    raise AssertionError("no period labelled {}".format(label))


def _flags_of(cell, flag_type):
    return [f for f in cell.flags if f["flag_type"] == flag_type]


# ---------------------------------------------------------------------------
# What the model contains
# ---------------------------------------------------------------------------

def test_every_registry_item_is_a_row(apple):
    """All 41, including the three Short-Term Debt components.

    The registry is the vocabulary and the scaffold is the first thing to use
    the whole of it. Phase 1's exit review counted 41 entries: the 38 V2_PLAN
    enumerates plus the three current-liability lines short-term debt is summed
    from, which the plan wrote as a chain and open question 4 showed could not
    be one.
    """
    assert len(line_items.REGISTRY) == 41
    assert {row.item for row in apple.rows if row.item} == set(line_items.REGISTRY)


def test_the_rows_that_are_not_registry_items_are_plugs_and_links(apple):
    """Everything else on the page is arithmetic, and says which kind."""
    extra = {row.name: row.role for row in apple.rows if row.item is None}

    assert all(role in (ts.ROLE_PLUG, ts.ROLE_DERIVED, ts.ROLE_MEMO)
               for role in extra.values())
    plugs = {name for name, role in extra.items() if role == ts.ROLE_PLUG}
    assert len(plugs) == 11
    assert all(name.endswith("(plug to reported total)") for name in plugs)


def test_every_cell_declares_a_state_and_carries_provenance(apple, honeywell, kroger):
    """No cell is in a fourth state, and none is silent about where it came from."""
    for spec in (apple, honeywell, kroger):
        for row in spec.rows:
            for period in ts.historical_periods(spec):
                cell = row.cells[period.key]
                assert cell.state in (ts.CELL_REPORTED, ts.CELL_DERIVED,
                                      ts.CELL_MISSING)
                assert (cell.value is None) == (cell.state == ts.CELL_MISSING)
                if cell.state == ts.CELL_MISSING:
                    assert cell.provenance["message"]
                elif cell.state == ts.CELL_REPORTED:
                    assert cell.provenance["tag"] and cell.provenance["accession"]
                else:
                    assert cell.provenance["formula"]


def test_periods_are_five_years_of_history_and_three_of_model(apple):
    historical = ts.historical_periods(apple)
    forecast = ts.forecast_periods(apple)

    assert [p.label for p in historical] == ["FY2021", "FY2022", "FY2023",
                                             "FY2024", "FY2025"]
    assert [p.label for p in forecast] == ["FY2026E", "FY2027E", "FY2028E"]


def test_krogers_periods_use_its_own_fiscal_year_names(kroger):
    """The scaffold names a year the way the filer's 10-K cover page does.

    Kroger's offset is one, so the year ending 31 January 2026 is FY2025 here
    exactly as it is in the table the user was looking at before asking for a
    scaffold.
    """
    assert kroger.fiscal_year_offset == 1
    historical = ts.historical_periods(kroger)

    assert historical[-1].key == "2026-01-31"
    assert historical[-1].label == "FY2025"


# ---------------------------------------------------------------------------
# The filer's own numbers
# ---------------------------------------------------------------------------

def test_apples_fy2023_figures_are_the_ones_in_its_10k(apple):
    """Spot values against Apple's Form 10-K for the year ended 30 September 2023."""
    assert _cell(apple, "Revenue", "FY2023").value == 383_285 * MILLION
    assert _cell(apple, "Cost of Revenue", "FY2023").value == 214_137 * MILLION
    assert _cell(apple, "Total Assets", "FY2023").value == 352_583 * MILLION
    assert _cell(apple, "Total Liabilities", "FY2023").value == 290_437 * MILLION
    assert _cell(apple, "Total Equity", "FY2023").value == 62_146 * MILLION
    assert _cell(apple, "Cash from Operations", "FY2023").value == 110_543 * MILLION


def test_a_reported_value_wins_over_the_arithmetic_that_could_replace_it(apple,
                                                                        honeywell):
    """Gross profit is a tag for Apple and a subtraction for Honeywell.

    The row carries both, and which one a period gets is decided by whether the
    filer tagged it. Reading the arithmetic over a tag the filer supplied would
    be replacing a fact with an inference.
    """
    apple_gross = _cell(apple, "Gross Profit", "FY2023")
    assert apple_gross.state == ts.CELL_REPORTED
    assert apple_gross.provenance["tag"] == "GrossProfit"
    assert apple_gross.value == 169_148 * MILLION

    honeywell_gross = _cell(honeywell, "Gross Profit", "FY2025")
    assert honeywell_gross.state == ts.CELL_DERIVED
    assert honeywell_gross.provenance["formula"] == "Revenue - Cost of Revenue"
    assert honeywell_gross.value == (37_442 - 23_613) * MILLION


def test_total_debt_stands_on_short_term_debt_which_stands_on_three_tags(apple):
    """Two levels of arithmetic, four reported leaves, all of them traceable.

    Apple's FY2023 Total Debt is 111,088 million, the figure open question 4
    named. Nobody tags it, and nobody tags the short-term half either: that is
    current maturities plus commercial paper, and Apple's balance sheet carries
    no other short-term borrowings. The provenance descends through both levels
    so a reader can reach the tags without leaving the value.
    """
    total = _cell(apple, "Total Debt", "FY2023")
    assert total.state == ts.CELL_DERIVED
    assert total.value == 111_088 * MILLION
    assert total.provenance["formula"] == "Short-Term Debt + Long-Term Debt"

    short_term = [entry for entry in total.provenance["inputs"]
                  if entry["name"] == "Short-Term Debt"][0]
    assert short_term["value"] == 15_807 * MILLION
    assert short_term["formula"] == ("Current Maturities of Long-Term Debt "
                                     "+ Commercial Paper")
    assert [nested["tag"] for nested in short_term["inputs"]] == [
        "LongTermDebtCurrent", "CommercialPaper"]

    long_term = [entry for entry in total.provenance["inputs"]
                 if entry["name"] == "Long-Term Debt"][0]
    assert long_term["tag"] == "LongTermDebtNoncurrent"
    assert long_term["accession"]


def test_a_sum_of_optional_terms_names_only_the_terms_it_used(honeywell):
    """Honeywell has current maturities and borrowings and no commercial paper."""
    short_term = _cell(honeywell, "Short-Term Debt", "FY2025")

    assert short_term.value == (1_546 + 5_893) * MILLION
    assert short_term.provenance["formula"] == ("Current Maturities of Long-Term "
                                                "Debt + Short-Term Borrowings")
    assert "Commercial Paper" not in short_term.provenance["formula"]


# ---------------------------------------------------------------------------
# Plugs
# ---------------------------------------------------------------------------

def test_a_plug_is_exactly_the_total_less_the_components(apple, honeywell, kroger):
    """The definition, checked on every plug of every filer in every year.

    A plug that is anything other than this is a number somebody chose, and the
    whole point of writing it as arithmetic is that nobody did.
    """
    for spec in (apple, honeywell, kroger):
        for row in spec.rows:
            if row.role != ts.ROLE_PLUG:
                continue
            for period in ts.historical_periods(spec):
                cell = row.cells[period.key]
                if cell.value is None:
                    continue
                total = ts.row_named(spec, row.total).cells[period.key].value
                components = 0.0
                for name, sign in row.components:
                    value = ts.row_named(spec, name).cells[period.key].value
                    if value is not None:
                        components += sign * value
                assert cell.value == pytest.approx(total - components, abs=0.5), (
                    "{} {} {}".format(spec.entity, row.name, period.label))


def test_a_plug_over_a_tenth_of_its_total_says_the_registry_is_too_sparse(apple):
    """Task 2.2b, on a statement where the threshold still says something.

    Apple's investing section is dominated by purchases and maturities of
    marketable securities, none of which is a registry item, so capex is a small
    part of it and the plug is nearly twice the reported subtotal. The flag says
    so rather than letting a section that is almost entirely residual pass for a
    statement.
    """
    cell = _cell(apple, "Other investing activities (plug to reported total)",
                 "FY2025")
    flags = _flags_of(cell, ts.FLAG_PLUG_TOO_LARGE)

    assert len(flags) == 1
    assert flags[0]["details"]["share_of_total"] > ts.PLUG_FLAG_THRESHOLD
    assert flags[0]["details"]["total_row"] == "Cash from Investing"
    assert "too sparse" in flags[0]["message"]


def test_a_plug_within_the_threshold_is_not_flagged(apple):
    """Apple's FY2022 operating adjustments are mostly rows the registry reads."""
    cell = _cell(apple, "Working capital and other operating items "
                        "(plug to reported total)", "FY2022")

    assert cell.value == pytest.approx(2_206 * MILLION, abs=0.5)
    assert _flags_of(cell, ts.FLAG_PLUG_TOO_LARGE) == []


def test_the_plug_flag_appears_once_per_row_in_the_model_summary(apple):
    """Flagged on the cell, and gathered for a caller that wants the headline."""
    rows = {f["details"].get("row") for f in ts.plug_flags(apple)}

    assert "Other investing activities (plug to reported total)" in rows
    assert all(f["flag_type"] == ts.FLAG_PLUG_TOO_LARGE for f in ts.plug_flags(apple))


# ---------------------------------------------------------------------------
# Coverage, which is the same measurement without the sentence
#
# Open question 11, closed on 2026-08-05. The plug-size warning was true on 72
# of 75 balance-sheet plug cells across these three filers, which made it
# useless as a signal however correct each instance was. The balance sheet
# reports the figure instead of warning about it.
# ---------------------------------------------------------------------------

def test_no_balance_sheet_plug_carries_the_size_warning(apple, honeywell, kroger):
    """The half of the decision that removes something."""
    for spec in (apple, honeywell, kroger):
        for row in spec.rows:
            if row.role != ts.ROLE_PLUG or row.statement != line_items.STATEMENT_BS:
                continue
            for period in ts.historical_periods(spec):
                assert _flags_of(row.cells[period.key], ts.FLAG_PLUG_TOO_LARGE) == [], (
                    "{} {} {}".format(spec.entity, row.name, period.label))


def test_the_warning_survives_where_it_still_says_something(apple, honeywell,
                                                            kroger):
    """And the half that keeps it. Every filer still raises it somewhere."""
    for spec in (apple, honeywell, kroger):
        flagged = ts.plug_flags(spec)
        assert flagged, spec.entity
        for name in {f["details"].get("row") for f in flagged}:
            assert ts.row_named(spec, name).statement in ts.PLUG_FLAG_STATEMENTS


def test_every_balance_sheet_section_reports_its_coverage(apple, honeywell, kroger):
    """One entry per balance-sheet plug, and no entry for any other statement."""
    for spec in (apple, honeywell, kroger):
        expected = [row.total for row in spec.rows
                    if row.role == ts.ROLE_PLUG
                    and row.statement == line_items.STATEMENT_BS]
        assert [entry["total_row"] for entry in spec.coverage] == expected
        assert expected == ["Total Current Assets", "Total Assets",
                            "Total Current Liabilities", "Total Liabilities",
                            "Total Equity"]


def test_coverage_is_the_components_share_of_the_subtotal(apple, honeywell, kroger):
    """The definition, on every section of every filer in every year.

    Coverage and the plug are two readings of one measurement, so they have to
    add to the whole subtotal or one of them is not what it says it is.
    """
    checked = 0
    for spec in (apple, honeywell, kroger):
        for entry in spec.coverage:
            plug = ts.row_named(spec, entry["plug_row"])
            total_row = ts.row_named(spec, entry["total_row"])
            for period in ts.historical_periods(spec):
                share = entry["cells"][period.key]
                total = total_row.cells[period.key].value
                if share is None:
                    assert not total or plug.cells[period.key].value is None
                    continue
                assert share == pytest.approx(
                    1.0 - plug.cells[period.key].value / total, abs=1e-9)
                checked += 1
    assert checked == 75


def test_apples_current_assets_are_two_thirds_of_what_the_registry_reads(apple):
    """The number open question 11 was raised over, now reported rather than warned.

    Apple's four tagged current asset lines are 100,192 million of 147,957
    million of current assets for FY2025. The rest is vendor non-trade
    receivables and other buckets the 41-item registry has no item for, which is
    a fact about the registry rather than a defect in Apple's tagging.
    """
    entry = ts.coverage_for(apple, "Total Current Assets")
    key = [p.key for p in ts.historical_periods(apple) if p.label == "FY2025"][0]

    assert entry["cells"][key] == pytest.approx(100_192.0 / 147_957.0, abs=1e-4)
    assert entry["plug_row"] == "Other current assets (plug to reported total)"


def test_coverage_says_what_it_finds_even_when_it_is_not_a_share(honeywell):
    """Honeywell's retained earnings are more than three times its equity.

    Treasury stock and accumulated other comprehensive income pull the total
    down below the one component the registry reads, so the figure is over 100
    percent. Clamping it, or taking an absolute value to keep it inside the
    range, would hide the only thing it has to say about that section.
    """
    entry = ts.coverage_for(honeywell, "Total Equity")
    key = [p.key for p in ts.historical_periods(honeywell) if p.label == "FY2025"][0]

    assert entry["cells"][key] > 3.0


# ---------------------------------------------------------------------------
# Blanks that are there by design
# ---------------------------------------------------------------------------

def test_a_row_the_filer_does_not_tag_is_present_and_explained(kroger):
    """Kroger's inventory is two lines the registry does not read, so the row is blank.

    It is a FIFO amount and a LIFO reserve with no net element tagged, which
    Session 4B established. The row still exists, still says which statement to
    open, and is never quietly given a number.
    """
    cell = _cell(kroger, "Inventory", "FY2025")

    assert cell.value is None
    assert cell.state == ts.CELL_MISSING
    assert cell.provenance["flag"] == xbrl.FLAG_NOT_TAGGED
    assert "balance sheet" in cell.provenance["message"]
    assert cell.provenance["url"]


def test_a_plug_that_swallowed_a_blank_row_says_which_one(kroger):
    """The difference between a plug and a place to hide things.

    Kroger's inventory really is inside its current assets; what is absent is
    the tag. So the plug is bigger by that amount, and it names the line it
    absorbed rather than presenting itself as ordinary residual.
    """
    cell = _cell(kroger, "Other current assets (plug to reported total)", "FY2025")
    flags = _flags_of(cell, ts.FLAG_PLUG_ABSORBS_BLANK)

    assert len(flags) == 1
    assert flags[0]["details"]["absorbed"] == ["Short-Term Investments", "Inventory"]
    assert "does not tag" in flags[0]["message"]


def test_krogers_operating_cost_lands_in_the_plug_and_the_plug_says_so(kroger):
    """Kroger tags no SG&A element the registry reads, and none for R&D either."""
    cell = _cell(kroger, "Other operating items, net (plug to reported total)",
                 "FY2025")
    absorbed = _flags_of(cell, ts.FLAG_PLUG_ABSORBS_BLANK)[0]["details"]["absorbed"]

    assert absorbed == ["SG&A", "R&D"]
    assert _cell(kroger, "SG&A", "FY2025").value is None
    # Operating income less gross profit: the whole of Kroger's operating cost.
    assert cell.value == pytest.approx((1_890 - 34_402) * MILLION, abs=0.5)


def test_a_missing_derived_row_names_the_input_it_was_short_of(honeywell):
    """Honeywell reports no operating income for FY2021, and EBITDA says which."""
    cell = _cell(honeywell, "EBITDA", "FY2021")

    assert cell.value is None
    assert cell.provenance["flag"] == xbrl.FLAG_DERIVATION_UNAVAILABLE
    assert "Operating Income" in cell.provenance["message"]


# ---------------------------------------------------------------------------
# Honeywell's untagged liability total
# ---------------------------------------------------------------------------

def test_honeywells_liabilities_are_derived_from_the_balance_sheet_equation(honeywell):
    """It tags no Liabilities element for any year, so the identity supplies it."""
    cell = _cell(honeywell, "Total Liabilities", "FY2025")

    assert cell.state == ts.CELL_DERIVED
    assert cell.value == (73_681 - 15_030) * MILLION
    assert cell.provenance["formula"] == "Total Assets - Total Equity"
    assert len(_flags_of(cell, ts.FLAG_TOTAL_DERIVED)) == 1


def test_a_derived_liability_total_disarms_the_balance_check(honeywell, apple):
    """The check cannot be Assets = Liabilities + Equity verbatim for this filer.

    Deriving the missing side is exact, not approximate, and it is the only way
    to build the rest of the liability section. What it costs is the check,
    which then holds because it was made to rather than because the statement
    was tested, and the row has to say that instead of showing a green zero.
    """
    balance = [c for c in honeywell.checks if c["name"].startswith("Balance")][0]

    assert balance["tie"] is False
    assert [f["flag_type"] for f in balance["flags"]] == [ts.FLAG_CHECK_NOT_AVAILABLE]
    assert "Total Liabilities" in balance["flags"][0]["message"]
    for period in ts.historical_periods(honeywell):
        assert balance["cells"][period.key].value == pytest.approx(0.0, abs=0.5)

    # Apple tags the element, so for Apple it is a real check and it passes.
    apple_balance = [c for c in apple.checks if c["name"].startswith("Balance")][0]
    assert apple_balance["tie"] is True
    assert apple_balance["flags"] == ()


def test_the_balance_check_is_zero_for_the_filers_that_tag_all_three_totals(apple,
                                                                           kroger):
    for spec in (apple, kroger):
        balance = [c for c in spec.checks if c["name"].startswith("Balance")][0]
        for period in ts.historical_periods(spec):
            assert balance["cells"][period.key].value == pytest.approx(0.0, abs=0.5), (
                "{} {}".format(spec.entity, period.label))


def test_the_retained_earnings_row_is_a_residual_and_does_not_claim_to_tie(apple):
    """Apple charges its share retirements to retained earnings, so it never ties.

    Ninety-one billion of the FY2025 residual is the buyback. Calling this a
    tie and colouring it red every year would train a reader to ignore the
    Checks sheet, so it is labelled a residual and left uncoloured.
    """
    residual = [c for c in apple.checks if c["name"].startswith("Retained")][0]

    assert residual["tie"] is False
    assert residual["cells"]["2025-09-27"].value == pytest.approx(
        -91_699 * MILLION, abs=0.5)
    assert "not a tie" in residual["note"]


def test_the_cash_tie_holds_for_kroger_and_shows_honeywells_currency_effect(kroger,
                                                                           honeywell):
    """A residual here is the exchange rate effect no registry item reads."""
    kroger_tie = [c for c in kroger.checks if c["name"].startswith("Cash tie")][0]
    for period in ts.historical_periods(kroger)[1:]:
        assert kroger_tie["cells"][period.key].value == pytest.approx(0.0, abs=0.5)

    honeywell_tie = [c for c in honeywell.checks
                     if c["name"].startswith("Cash tie")][0]
    assert honeywell_tie["cells"]["2025-12-31"].value == pytest.approx(
        -837 * MILLION, abs=0.5)


def test_the_first_year_has_no_opening_cash_and_says_so(apple):
    """Nothing precedes the first column, so the cash tie cannot run for it."""
    opening = _cell(apple, "Cash, beginning of period", "FY2021")
    tie = [c for c in apple.checks if c["name"].startswith("Cash tie")][0]

    assert opening.value is None
    assert tie["cells"]["2021-09-25"].value is None


# ---------------------------------------------------------------------------
# Flags that travel
# ---------------------------------------------------------------------------

def test_a_row_crossing_the_cost_of_revenue_seam_inherits_its_flag(kroger):
    """The seam changes what a row means, so it changes what everything above it means.

    Kroger's cost chain ends in an element that excludes depreciation where the
    others include it. Its gross profit is that cost subtracted from revenue,
    so gross profit crosses the seam too, and so does the operating plug built
    on gross profit. A reader looking at gross profit sees the seam without
    having to know what gross profit is made of.
    """
    spec = _model(KROGER, history_years=20)
    seam_year = "FY2018"

    cost = _cell(spec, "Cost of Revenue", seam_year)
    assert len(_flags_of(cost, xbrl.FLAG_TAG_TRANSITION)) == 1

    gross = _cell(spec, "Gross Profit", seam_year)
    inherited = _flags_of(gross, xbrl.FLAG_TAG_TRANSITION)
    assert len(inherited) == 1
    assert inherited[0]["details"]["inherited_from"] == "Cost of Revenue"
    assert "Gross Profit stands on Cost of Revenue" in inherited[0]["message"]

    plug = _cell(spec, "Other operating items, net (plug to reported total)",
                 seam_year)
    assert _flags_of(plug, xbrl.FLAG_TAG_TRANSITION)[0]["details"][
        "inherited_from"] == "Cost of Revenue"


def test_an_inherited_flag_names_the_row_it_started_on_not_the_one_above_it(apple):
    """Two steps up the arithmetic and the origin is still the reported row."""
    spec = _model(APPLE, history_years=20)
    cell = _cell(spec, "Cash, end of period", "FY2015")
    inherited = _flags_of(cell, xbrl.FLAG_TAG_TRANSITION)

    assert [f["details"]["inherited_from"] for f in inherited] == ["Cash from Operations"]


# ---------------------------------------------------------------------------
# Forecasts
# ---------------------------------------------------------------------------

def test_a_row_the_filer_never_reports_gets_no_forecast(apple, kroger):
    """Whatever it holds is already inside a plug, so modelling it counts it twice.

    Apple carries no goodwill and no short-term borrowings; Kroger tags no
    inventory. Every one of those is inside the plug beside it, which is held
    flat, and forecasting the line separately would add it a second time.
    """
    for spec, name in ((apple, "Goodwill"), (apple, "Short-Term Borrowings"),
                       (kroger, "Inventory"), (kroger, "SG&A")):
        row = ts.row_named(spec, name)
        assert row.forecast is None, name
        assert [f["flag_type"] for f in row.flags] == [ts.FLAG_NO_REPORTED_HISTORY]
        assert "count it twice" in row.flags[0]["message"]


def test_a_row_the_filer_does_report_keeps_its_forecast(apple):
    for name in ("Revenue", "Accounts Receivable", "PP&E Net", "Long-Term Debt",
                 "Retained Earnings", "Capex", "Dividends Paid"):
        assert ts.row_named(apple, name).forecast is not None, name


def test_the_per_share_rows_have_no_forecast_and_give_the_reason(apple):
    """A share count needs a repurchase price, which this tool will not invent."""
    for name in ("EPS Basic", "EPS Diluted", "Shares Outstanding (Basic)",
                 "Shares Outstanding (Diluted)"):
        row = ts.row_named(apple, name)
        assert row.forecast is None
        assert row.flags[0]["flag_type"] == ts.FLAG_NO_FORECAST_DRIVER
        assert "should invent" in row.flags[0]["message"]


def _assumptions_reached(spec):
    reached = set()
    for row in spec.rows:
        if row.forecast is not None:
            reached.update(ts.assumptions_in(row.forecast))
    return reached


def test_the_assumption_set_is_blank_and_complete(apple, kroger):
    """Fifteen inputs, each named, each with the units it is entered in.

    Apple exercises all fifteen. Kroger exercises twelve: it tags no inventory,
    no SG&A and no R&D, so those three rows have no forecast and the three
    inputs that would drive them drive nothing. They stay on the sheet, because
    the sheet is the same for every filer and an analyst who overwrites one of
    those blank rows by hand will want the input beside it.
    """
    assert len(apple.assumptions) == 15
    assert {a.unit for a in apple.assumptions} == {"percent", "days", "currency"}
    assert "rev_growth" in ts.ASSUMPTION_KEYS
    assert "net_debt_issuance" in ts.ASSUMPTION_KEYS

    assert _assumptions_reached(apple) == set(ts.ASSUMPTION_KEYS)
    assert set(ts.ASSUMPTION_KEYS) - _assumptions_reached(kroger) == {
        "dio", "sga_pct_rev", "rnd_pct_rev"}


def test_every_forecast_expression_reaches_only_rows_the_model_has(apple, honeywell,
                                                                  kroger):
    """A reference to a row that is not there would be a silent zero in Excel."""
    for spec in (apple, honeywell, kroger):
        names = {row.name for row in spec.rows}
        for row in spec.rows:
            if row.forecast is None:
                continue
            for _kind, target, offset in ts.refs_in(row.forecast):
                assert target in names, "{} -> {}".format(row.name, target)
                assert offset in (0, -1)


# ---------------------------------------------------------------------------
# Filers that get no scaffold at all
# ---------------------------------------------------------------------------

def test_a_bank_gets_the_refusal_and_no_half_built_model():
    """The gate governs scaffolds, and a refusal is the whole of the answer."""
    spec = _model(JPMORGAN)

    assert spec.scope.in_scope is False
    assert spec.scope.reason == line_items.SCOPE_FINANCIAL_SIC
    assert "three-statement template" in spec.scope.message
    assert spec.rows == ()
    assert spec.periods == ()


def test_an_ifrs_filer_gets_its_own_message():
    spec = ts.build_model(1000184, _facts(1000184), "7372")

    assert spec.scope.in_scope is False
    assert spec.scope.reason == line_items.SCOPE_IFRS_ONLY
    assert spec.rows == ()
