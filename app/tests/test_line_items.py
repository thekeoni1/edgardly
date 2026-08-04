"""test_line_items.py -- automated tests for the line-item registry.

Four things are under test:
  - the scale functions map a magnitude to the right (factor, label) pair,
    including at the threshold boundaries
  - every caller really does share one definition, so the single-company table,
    the peer table, and the browser can never disagree about units
  - the registry is structurally sound: every entry classified, every chain
    non-empty, no tag claimed twice
  - derivations compute what their formula says, and go missing rather than
    guessing when an input is absent

Whether a chain resolves to the right number for a real filer is a separate
question, answered against committed fixtures in test_real_filings.py.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import line_items
import peer_comparison as pc
import app as app_module


# ---------------------------------------------------------------------------
# Unit classification
# ---------------------------------------------------------------------------

def test_the_three_unit_sets_are_disjoint():
    assert not (line_items.DOLLAR_LINE_ITEMS & line_items.EPS_LINE_ITEMS)
    assert not (line_items.DOLLAR_LINE_ITEMS & line_items.SHARE_LINE_ITEMS)
    assert not (line_items.EPS_LINE_ITEMS & line_items.SHARE_LINE_ITEMS)


def _classified():
    return (
        line_items.DOLLAR_LINE_ITEMS
        | line_items.EPS_LINE_ITEMS
        | line_items.SHARE_LINE_ITEMS
    )


def test_every_registry_line_item_has_a_unit_class():
    """No line item may render without a known unit, or it would be shown unscaled."""
    known = set(line_items.REGISTRY) | set(line_items.DERIVATIONS)
    unclassified = known - _classified()
    assert not unclassified, "Registry items with no unit class: {}".format(unclassified)


def test_no_unit_class_names_an_item_the_registry_does_not_define():
    known = set(line_items.REGISTRY) | set(line_items.DERIVATIONS)
    stale = _classified() - known
    assert not stale, "Unit classes name line items that do not exist: {}".format(stale)


# ---------------------------------------------------------------------------
# Callers share one definition
# ---------------------------------------------------------------------------

def test_peer_comparison_reuses_the_shared_sets():
    assert pc.DOLLAR_LINE_ITEMS is line_items.DOLLAR_LINE_ITEMS
    assert pc.EPS_LINE_ITEMS is line_items.EPS_LINE_ITEMS
    assert pc.SHARE_LINE_ITEMS is line_items.SHARE_LINE_ITEMS


def test_app_reuses_the_shared_sets():
    assert app_module._DOLLAR_LINE_ITEMS is line_items.DOLLAR_LINE_ITEMS
    assert app_module._EPS_LINE_ITEMS is line_items.EPS_LINE_ITEMS
    assert app_module._SHARE_LINE_ITEMS is line_items.SHARE_LINE_ITEMS


# ---------------------------------------------------------------------------
# Dollar scaling
# ---------------------------------------------------------------------------

def test_dollar_scale_billions_render_in_millions():
    assert line_items.dollar_scale_for(383_285_000_000) == (1_000_000, "$mm")


def test_dollar_scale_hundreds_of_millions_render_in_thousands():
    assert line_items.dollar_scale_for(250_000_000) == (1_000, "$000s")


def test_dollar_scale_small_values_render_unscaled():
    assert line_items.dollar_scale_for(4_000_000) == (1, "$")


def test_dollar_scale_ignores_sign():
    assert line_items.dollar_scale_for(-383_285_000_000) == (1_000_000, "$mm")
    assert line_items.dollar_scale_for(-250_000_000) == (1_000, "$000s")


def test_dollar_scale_thresholds_are_exclusive():
    """Exactly at a threshold the smaller scale still applies."""
    assert line_items.dollar_scale_for(line_items.DOLLAR_MILLIONS_THRESHOLD) == (1_000, "$000s")
    assert line_items.dollar_scale_for(line_items.DOLLAR_THOUSANDS_THRESHOLD) == (1, "$")


def test_dollar_scale_of_zero_is_unscaled():
    assert line_items.dollar_scale_for(0) == (1, "$")


# ---------------------------------------------------------------------------
# Share scaling
# ---------------------------------------------------------------------------

def test_share_scale_large_counts_render_in_millions():
    assert line_items.share_scale_for(15_600_000_000) == (1_000_000, "mm")


def test_share_scale_smaller_counts_render_in_thousands():
    assert line_items.share_scale_for(45_000_000) == (1_000, "000s")


def test_share_scale_threshold_is_exclusive():
    assert line_items.share_scale_for(line_items.SHARE_MILLIONS_THRESHOLD) == (1_000, "000s")


def test_share_scale_ignores_sign():
    assert line_items.share_scale_for(-15_600_000_000) == (1_000_000, "mm")


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_defaults_are_valid_scales():
    assert line_items.DEFAULT_DOLLAR_SCALE == (1, "$")
    assert line_items.DEFAULT_SHARE_SCALE == (1_000, "000s")


# ---------------------------------------------------------------------------
# The registry
#
# Structural checks only. Whether a chain resolves to the right number for a
# real filer is what the fixtures in test_real_filings.py are for.
# ---------------------------------------------------------------------------

def test_registry_covers_every_item_the_plan_enumerates():
    """V2_PLAN 1.1: 14 income statement, 16 balance sheet, 8 cash flow."""
    by_statement = {}
    for item in line_items.REGISTRY.values():
        by_statement.setdefault(item.statement, []).append(item.name)

    assert len(by_statement[line_items.STATEMENT_IS]) == 14
    assert len(by_statement[line_items.STATEMENT_BS]) == 16
    assert len(by_statement[line_items.STATEMENT_CF]) == 8
    assert len(line_items.REGISTRY) == 38


def test_every_registry_entry_is_well_formed():
    statements = {line_items.STATEMENT_IS, line_items.STATEMENT_BS, line_items.STATEMENT_CF}
    kinds = {line_items.KIND_FLOW, line_items.KIND_INSTANT}
    units = {line_items.UNIT_DOLLAR, line_items.UNIT_EPS, line_items.UNIT_SHARES}

    for name, item in line_items.REGISTRY.items():
        assert item.name == name, "registry key and entry name disagree: {}".format(name)
        assert item.statement in statements, name
        assert item.kind in kinds, name
        assert item.unit in units, name
        assert item.tags, "{} has no tag chain".format(name)
        assert len(set(item.tags)) == len(item.tags), "{} repeats a tag".format(name)


def test_balance_sheet_items_are_instants_and_the_rest_are_flows():
    """Wrong kind means wrong period key, which silently mixes up a series."""
    for name, item in line_items.REGISTRY.items():
        if item.statement == line_items.STATEMENT_BS:
            assert item.kind == line_items.KIND_INSTANT, name
        else:
            assert item.kind == line_items.KIND_FLOW, name


def test_no_tag_is_claimed_by_two_line_items():
    """One tag feeding two rows would double-count it somewhere downstream."""
    owner = {}
    for name, item in line_items.REGISTRY.items():
        for tag in item.tags:
            assert tag not in owner, "{} is claimed by both {} and {}".format(
                tag, owner.get(tag), name)
            owner[tag] = name


def test_the_registry_says_which_of_its_tags_no_filer_has_ever_exercised():
    """Every chain runs against every committed fixture, and this is the residue.

    A tag that no fixture reports has never been shown to mean what the
    registry says it means. That is allowed -- the market is wider than five
    filers -- but it is a proposal rather than a verified fact, and the list of
    proposals has to be visible or it quietly becomes a claim.

    Adding a tag to a chain without a fixture behind it fails here until it is
    named. Adding a fixture that exercises one of these fails here too, which
    is the direction the list should move in.
    """
    import glob
    import json

    fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    reported = set()
    for path in glob.glob(os.path.join(fixture_dir, "cik*.json")):
        with open(path, encoding="utf-8") as handle:
            reported |= set(json.load(handle)["facts"].get("us-gaap", {}))

    unexercised = {tag
                   for item in line_items.REGISTRY.values()
                   for tag in item.tags
                   if tag not in reported}

    assert unexercised == {
        # Filers that gross up sales taxes collected into revenue. None of the
        # five is a retailer that does; Kroger reports net of them.
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        # The bundled payables-and-accruals element. All five split them.
        "AccountsPayableAndAccruedLiabilitiesCurrent",
        # The one tag that states a filer's whole current debt balance. Not one
        # of the five uses it, which is exactly why Short-Term Debt cannot be a
        # chain pick and has to sum its components.
        "DebtCurrent",
    }


def test_long_term_debt_entry_records_the_current_maturities_caveat():
    """PROGRESS.md open question 1 lives where the chain is written, not only in a doc."""
    note = line_items.REGISTRY["Long-Term Debt"].note
    assert "current maturities" in note
    assert "LongTermDebt" in note


def test_tags_for_reaches_past_the_extraction_set():
    """Registry items outside TAG_MAP still resolve; that is what makes it a superset."""
    assert "D&A" not in line_items.TAG_MAP
    assert line_items.tags_for("D&A")[0] == "DepreciationDepletionAndAmortization"
    assert line_items.tags_for("Revenue")[0] == "Revenues"
    assert line_items.tags_for("Total Debt") == ()      # derived, never a tag
    assert line_items.tags_for("No Such Item") == ()


# ---------------------------------------------------------------------------
# The extraction set stays where it was
# ---------------------------------------------------------------------------

def test_tag_map_is_the_fourteen_displayed_items_in_display_order():
    assert list(line_items.TAG_MAP) == list(line_items.UI_LINE_ITEMS)
    assert list(line_items.TAG_MAP) == [
        "Revenue", "Cost of Revenue", "Gross Profit", "Operating Income", "Net Income",
        "EPS Basic", "EPS Diluted",
        "Shares Outstanding (Basic)", "Shares Outstanding (Diluted)",
        "Total Assets", "Total Liabilities", "Total Equity",
        "Cash and Equivalents", "Long-Term Debt",
    ]


def test_tag_map_chains_come_from_the_registry():
    for name, tags in line_items.TAG_MAP.items():
        assert tags == list(line_items.REGISTRY[name].tags)


def test_xbrl_extractor_reexports_the_registry_tag_map():
    """One dict, not a copy, so the chains can never drift apart."""
    import xbrl_extractor as xbrl

    assert xbrl.TAG_MAP is line_items.TAG_MAP


# ---------------------------------------------------------------------------
# Derivation rules
# ---------------------------------------------------------------------------

def test_total_debt_is_the_sum_of_both_components():
    value = line_items.derive("Total Debt", {
        "Short-Term Debt": 15_000, "Long-Term Debt": 95_281,
    })
    assert value == 110_281
    assert line_items.DERIVATIONS["Total Debt"].formula == "Short-Term Debt + Long-Term Debt"


def test_ebitda_adds_back_d_and_a():
    value = line_items.derive("EBITDA", {"Operating Income": 114_301, "D&A": 11_519})
    assert value == 125_820


def test_gross_profit_derivation_subtracts_cost_of_revenue():
    value = line_items.derive("Gross Profit", {"Revenue": 383_285, "Cost of Revenue": 214_137})
    assert value == 169_148


def test_a_missing_input_makes_the_result_missing_never_zero():
    """The inviolable rule: never guess or auto-fill a financial value."""
    assert line_items.derive("Total Debt", {"Short-Term Debt": None,
                                            "Long-Term Debt": 95_281}) is None
    assert line_items.derive("Total Debt", {"Long-Term Debt": 95_281}) is None
    assert line_items.derive("EBITDA", {"Operating Income": 114_301}) is None


def test_every_derivation_names_its_inputs_in_its_formula():
    for name, rule in line_items.DERIVATIONS.items():
        assert rule.inputs, "{} derives from nothing".format(name)
        for input_name, sign in rule.inputs:
            assert sign in (1, -1), name
            assert input_name in rule.formula, (
                "{} formula does not name its input {}".format(name, input_name))


def test_derivation_inputs_are_registry_items_or_documented_raw_tags():
    """A derivation pointing at a name nothing resolves would silently never fire."""
    for name, rule in line_items.DERIVATIONS.items():
        for input_name, _ in rule.inputs:
            if name == "D&A":
                continue  # its inputs are raw tags; see DA_COMPONENT_TAGS
            assert input_name in line_items.REGISTRY, (
                "{} derives from unknown item {}".format(name, input_name))


# ---------------------------------------------------------------------------
# What the browser is served
# ---------------------------------------------------------------------------

def test_client_classification_matches_the_python_sets():
    payload = line_items.classification_for_client()

    assert payload["ui_line_items"] == list(line_items.UI_LINE_ITEMS)
    assert set(payload["dollar"]) == set(line_items.DOLLAR_LINE_ITEMS)
    assert set(payload["eps"]) == set(line_items.EPS_LINE_ITEMS)
    assert set(payload["shares"]) == set(line_items.SHARE_LINE_ITEMS)


def test_client_classification_is_json_serializable_and_stable():
    import json

    first = json.dumps(line_items.classification_for_client())
    second = json.dumps(line_items.classification_for_client())
    assert first == second


def test_the_homepage_injects_the_classification():
    client = app_module.app.test_client()
    page = client.get("/").get_data(as_text=True)

    assert "const LINE_ITEMS = " in page
    for name in line_items.UI_LINE_ITEMS:
        assert '"{}"'.format(name) in page, "{} never reached the page".format(name)
    assert '"Long-Term Debt"' in page
    # Registry items the existing views never show travel with the classification,
    # so a future view knows their units without asking again.
    assert '"Stock-Based Compensation"' in page


def test_the_template_keeps_no_line_item_lists_of_its_own():
    """The third copy is gone and must not come back.

    app.py and peer_comparison.py were consolidated in Session 1; index.html
    kept typing its own DOLLAR_ITEMS, EPS_ITEMS, SHARE_ITEMS, and
    ALL_LINE_ITEMS, so the browser could disagree with the server about whether
    a value is dollars, a per-share amount, or a share count.
    """
    template = os.path.join(os.path.dirname(__file__), "..", "templates", "index.html")
    with open(template, encoding="utf-8") as handle:
        source = handle.read()

    assert "{{ line_item_classification|tojson }}" in source
    assert 'new Set(["' not in source, "a hardcoded unit-class list is back in the template"
    for name in ("EPS Basic", "EPS Diluted", "Cash and Equivalents", "Long-Term Debt",
                 "Shares Outstanding (Basic)", "Total Liabilities"):
        assert name not in source, "{} is hardcoded in the template".format(name)
