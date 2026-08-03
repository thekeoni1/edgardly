"""line_items.py -- canonical line-item classification and display scaling.

Single home for the facts that describe what a line item IS, independent of how
any one view renders it: which unit class it belongs to, and how a magnitude maps
to a display scale.

These sets and thresholds previously lived in both app.py and peer_comparison.py.
Two copies meant the single-company table and the peer table could silently
disagree about whether a value is dollars, a per-share amount, or a share count.

The v2 line-item registry (canonical names, XBRL tag chains, statement, flow vs
instant, derivation rules) lands in this module next; these constants are the
first piece of it.
"""

# ---------------------------------------------------------------------------
# Unit classification
#
# Every line item currently extracted falls into exactly one of these three
# sets. The classification drives number formats, scale factors, and the
# column headers that name the units.
# ---------------------------------------------------------------------------

DOLLAR_LINE_ITEMS = frozenset({
    "Revenue", "Cost of Revenue", "Gross Profit", "Operating Income", "Net Income",
    "Total Assets", "Total Liabilities", "Total Equity", "Cash and Equivalents",
    "Long-Term Debt",
})

EPS_LINE_ITEMS = frozenset({"EPS Basic", "EPS Diluted"})

SHARE_LINE_ITEMS = frozenset({"Shares Outstanding (Basic)", "Shares Outstanding (Diluted)"})


# ---------------------------------------------------------------------------
# Display scaling
#
# A scale is a (factor, label) pair: divide raw values by factor, and print
# label in the header so the reader knows the units. EPS is never scaled.
# ---------------------------------------------------------------------------

# Above this, dollars are shown in millions; above the next one, in thousands.
DOLLAR_MILLIONS_THRESHOLD = 1_000_000_000
DOLLAR_THOUSANDS_THRESHOLD = 10_000_000

# Above this, share counts are shown in millions rather than thousands.
SHARE_MILLIONS_THRESHOLD = 1_000_000_000

# Used when no value is available to size the table from.
DEFAULT_DOLLAR_SCALE = (1, "$")
DEFAULT_SHARE_SCALE = (1_000, "000s")


def dollar_scale_for(value):
    """Return the (factor, label) dollar scale appropriate for *value*.

    Sign is irrelevant to scale, so the magnitude is what gets compared.
    """
    magnitude = abs(value)
    if magnitude > DOLLAR_MILLIONS_THRESHOLD:
        return 1_000_000, "$mm"
    if magnitude > DOLLAR_THOUSANDS_THRESHOLD:
        return 1_000, "$000s"
    return 1, "$"


def share_scale_for(value):
    """Return the (factor, label) share-count scale appropriate for *value*."""
    if abs(value) > SHARE_MILLIONS_THRESHOLD:
        return 1_000_000, "mm"
    return 1_000, "000s"
