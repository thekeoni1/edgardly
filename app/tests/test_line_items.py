"""test_line_items.py -- automated tests for the shared line-item constants.

Two things are under test:
  - the scale functions map a magnitude to the right (factor, label) pair,
    including at the threshold boundaries
  - app.py and peer_comparison.py really do share one definition, so the
    single-company table and the peer table can never disagree about units

That second group is the reason this module exists; the constants were
duplicated in both callers before.
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


def test_every_extracted_line_item_has_a_unit_class():
    """No line item may render without a known unit, or it would be shown unscaled."""
    import xbrl_extractor as xbrl

    classified = (
        line_items.DOLLAR_LINE_ITEMS
        | line_items.EPS_LINE_ITEMS
        | line_items.SHARE_LINE_ITEMS
    )
    unclassified = set(xbrl.TAG_MAP) - classified
    assert not unclassified, "TAG_MAP items with no unit class: {}".format(unclassified)


def test_no_unit_class_names_an_item_that_is_not_extracted():
    import xbrl_extractor as xbrl

    classified = (
        line_items.DOLLAR_LINE_ITEMS
        | line_items.EPS_LINE_ITEMS
        | line_items.SHARE_LINE_ITEMS
    )
    stale = classified - set(xbrl.TAG_MAP)
    assert not stale, "Unit classes name line items that are never extracted: {}".format(stale)


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
