"""xbrl_extractor.py -- EDGAR XBRL structured financial data extraction.

Stage 1: tag-mapping dictionary, companyfacts fetch, and per-line-item resolution.
Stage 2: deduplication and clean period time-series.
Reuses _rate_limited_get from edgar_api for consistent rate limiting and User-Agent.
"""

import datetime

import line_items
from edgar_api import _rate_limited_get

XBRL_BASE = "https://data.sec.gov/api/xbrl"

# ---------------------------------------------------------------------------
# Tag mapping
#
# The tag chains now live in the line-item registry in line_items.py, which
# holds the whole vocabulary the models need. TAG_MAP is the subset the existing
# views extract and display: the same 14 items, in the same order, as a plain
# dict of canonical name to ordered tag list. Re-exported here because callers
# already reach for xbrl.TAG_MAP.
#
# Add a line item to line_items.REGISTRY; add it to line_items.UI_LINE_ITEMS
# only if it should appear in the existing tables.
# ---------------------------------------------------------------------------
TAG_MAP = line_items.TAG_MAP


def fetch_company_facts(cik):
    """
    Fetch the full companyfacts JSON for a CIK from EDGAR's XBRL API.

    Uses _rate_limited_get (0.1s delay, 429 back-off, correct User-Agent).
    Returns the parsed JSON dict.
    Raises requests.HTTPError on non-2xx responses.
    """
    cik_str = str(int(cik)).zfill(10)
    url = f"{XBRL_BASE}/companyfacts/CIK{cik_str}.json"
    resp = _rate_limited_get(url)
    return resp.json()


def _parse_entries(unit, entries, tag):
    """
    Convert a list of raw EDGAR XBRL unit entries into normalized data-point dicts.
    """
    result = []
    for entry in entries:
        result.append({
            "value": entry.get("val"),
            "unit": unit,
            "start": entry.get("start"),     # absent -> balance-sheet instant
            "end": entry.get("end"),
            "fiscal_year": entry.get("fy"),
            "fiscal_period": entry.get("fp"),
            "form": entry.get("form"),
            "filed": entry.get("filed"),
            "accn": entry.get("accn"),
            "tag": tag,
        })
    return result


def _extract_tag_data(facts_data, tag):
    """
    Return all data points for one us-gaap XBRL tag from a companyfacts dict.
    Returns an empty list if the tag is not present.
    """
    tag_data = facts_data.get("facts", {}).get("us-gaap", {}).get(tag)
    if not tag_data:
        return []

    units_dict = tag_data.get("units", {})
    if not units_dict:
        return []

    result = []
    for unit, entries in units_dict.items():
        result.extend(_parse_entries(unit, entries, tag))
    return result


def _primary_tag(data_points):
    """Return the tag behind the most recent annual data point in a series.

    A stitched series can hold more than one tag, so no single tag speaks for
    all of it. This is the tag a reader asking "where does this row come from?"
    means: the one reporting the latest full year. Every data point still
    carries its own tag, which is what the per-value provenance uses.

    Falls back to the whole series when no data point is labeled annual.
    """
    annual = [dp for dp in data_points if dp.get("fiscal_period") == "FY"]
    pool = annual or data_points
    newest = max(pool, key=lambda dp: (dp.get("end") or "", dp.get("filed") or ""))
    return newest.get("tag")


def resolve_line_item(facts_data, line_item):
    """
    Given companyfacts data and a canonical line-item name, stitch one series
    together from every tag in the item's fallback chain.

    Resolution is per period, not per series.  For each reported period, the
    earliest tag in the chain that reports it wins; within one tag, the most
    recently filed entry wins (a 10-K/A restating a year beats the original).
    A period reported only by a later tag in the chain is kept rather than
    dropped.

    This replaces winner-takes-all resolution, which picked the single tag whose
    most recent annual data point was newest and used that tag for the entire
    history.  That truncated history at a tag switch: when Apple moved from
    Revenues to RevenueFromContractWithCustomerExcludingAssessedTax at FY2018,
    only the years the new tag happened to carry as comparatives survived, even
    though the older years sat in the same companyfacts response.

    Mixing tags across eras is honest, not a fudge: each data point records the
    tag it came from, and validate_financials raises TAG_TRANSITION on the
    boundary year so the seam is visible.

    Accepts any name in the line-item registry, not only the ones in TAG_MAP.

    Returns:
        (list[dict], str)   -- data points sorted by end date, and the tag
                               behind the most recent annual value
        ([], None)          -- if no tag in the chain has any data
    """
    winners = {}
    for tag in line_items.tags_for(line_item):
        from_this_tag = {}
        for dp in _extract_tag_data(facts_data, tag):
            key = _period_key(dp)
            if key in winners:
                continue  # an earlier tag in the chain already reports this period
            incumbent = from_this_tag.get(key)
            if incumbent is None or (dp.get("filed") or "") > (incumbent.get("filed") or ""):
                from_this_tag[key] = dp
        winners.update(from_this_tag)

    if not winners:
        return [], None

    data = sorted(winners.values(), key=lambda dp: dp.get("end") or "")
    return data, _primary_tag(data)


def extract_all_line_items(facts_data, names=None):
    """
    Extract data for a set of line items.

    names defaults to TAG_MAP, the 14 items the existing views display.  Pass an
    explicit sequence of registry names to extract anything else; the registry
    is a superset of TAG_MAP.

    Returns:
        dict keyed by line-item name, each value:
          {"data": list[dict], "tag_used": str | None}
        tag_used is None when no mapped tag has data for that line item.
    """
    if names is None:
        names = TAG_MAP
    return {
        line_item: {"data": data, "tag_used": tag_used}
        for line_item in names
        for data, tag_used in (resolve_line_item(facts_data, line_item),)
    }


def most_recent_annual(data_points):
    """
    From a list of data points, return the one from the most recent annual
    (10-K or 10-K/A) filing, or None if no annual entries exist.
    Sorted by filed date descending so the latest amendment wins.
    """
    annual = [
        dp for dp in data_points
        if dp.get("form") in ("10-K", "10-K/A") and dp.get("fiscal_period") == "FY"
    ]
    if not annual:
        return None
    return max(annual, key=lambda dp: dp.get("filed") or "")


# ---------------------------------------------------------------------------
# Stage 2 -- Deduplication and clean period time-series
# ---------------------------------------------------------------------------

def _period_key(dp):
    """
    Return the identity key for a data point's reported period.

    Uses the explicit start/end dates from the XBRL data -- never inferred
    from filing date or fiscal_year/fiscal_period labels.

    Flow items (income statement): keyed by (unit, start, end)
    Stock items (balance sheet instants): keyed by (unit, None, end)
    """
    return (dp.get("unit"), dp.get("start"), dp.get("end"))


def deduplicate_period(data_points):
    """
    Deduplicate a list of data points for one line item so that each
    distinct reported period appears exactly once.

    When the same period appears more than once (e.g. original 10-K then a
    10-K/A restatement), the entry with the most recently FILED date is kept
    and the earlier filing(s) are discarded.

    Returns a list sorted by end date ascending (oldest period first).
    """
    from collections import defaultdict

    groups = defaultdict(list)
    for dp in data_points:
        groups[_period_key(dp)].append(dp)

    result = []
    for entries in groups.values():
        best = max(entries, key=lambda dp: dp.get("filed") or "")
        result.append(best)

    result.sort(key=lambda dp: dp.get("end") or "")
    return result


def deduplicate_all_line_items(extracted):
    """
    Apply deduplicate_period to every line item in an extract_all_line_items
    result dict.

    Returns a new dict with the same structure but data lists replaced by
    deduplicated, sorted time series.
    """
    return {
        line_item: {
            "data": deduplicate_period(info["data"]),
            "tag_used": info["tag_used"],
        }
        for line_item, info in extracted.items()
    }


# ---------------------------------------------------------------------------
# Stage 3 -- Validation and sanity checks
# ---------------------------------------------------------------------------

FLAG_NEGATIVE_REVENUE = "NEGATIVE_REVENUE"
FLAG_NET_INCOME_EXCEEDS_REVENUE = "NET_INCOME_EXCEEDS_REVENUE"
FLAG_BALANCE_SHEET_MISMATCH = "BALANCE_SHEET_MISMATCH"
FLAG_ZERO_AMONG_NONZERO = "ZERO_AMONG_NONZERO"
FLAG_EPS_RECONCILIATION = "EPS_RECONCILIATION_MISMATCH"
FLAG_LARGE_YOY_CHANGE = "LARGE_YOY_CHANGE"
FLAG_MISSING_CRITICAL_DATA = "MISSING_CRITICAL_DATA"
FLAG_TAG_TRANSITION = "TAG_TRANSITION"


def _make_flag(flag_type, message, period_end, value, details=None):
    return {
        "flag_type": flag_type,
        "message": message,
        "period_end": period_end,
        "value": value,
        "details": details or {},
    }


def _instant_key(dp):
    """Period key for balance-sheet instants: (unit, end). start is ignored."""
    return (dp.get("unit"), dp.get("end"))


def _check_negative_revenue(revenue_points):
    return [
        _make_flag(
            FLAG_NEGATIVE_REVENUE,
            f"Revenue is negative ({dp['value']:,})",
            dp.get("end"), dp["value"],
        )
        for dp in revenue_points
        if dp.get("value") is not None and dp["value"] < 0
    ]


_MIN_REVENUE_FOR_RATIO_CHECK = 10_000_000  # $10M -- skip ratio check for tiny/pre-revenue companies


def _check_net_income_vs_revenue(net_income_points, revenue_points):
    """Flag periods where |net income| > 3x |revenue|.

    Only applies when |revenue| >= $10M; below that threshold the ratio is
    almost always a false positive for development-stage or pre-revenue companies.
    """
    rev_by_key = {
        _period_key(dp): dp
        for dp in revenue_points
        if dp.get("value") is not None
    }
    flags = []
    for dp in net_income_points:
        ni = dp.get("value")
        if ni is None:
            continue
        rev_dp = rev_by_key.get(_period_key(dp))
        if rev_dp is None:
            continue
        rev = rev_dp.get("value")
        if not rev:  # None or zero
            continue
        if abs(rev) < _MIN_REVENUE_FOR_RATIO_CHECK:
            continue
        ratio = abs(ni) / abs(rev)
        if ratio > 3:
            flags.append(_make_flag(
                FLAG_NET_INCOME_EXCEEDS_REVENUE,
                f"Net income ({ni:,}) is {ratio:.1f}x revenue ({rev:,}) -- possible tag error",
                dp.get("end"), ni,
                {"revenue": rev, "ratio": ratio},
            ))
    return flags


def _check_balance_sheet_equation(assets_pts, liabilities_pts, equity_pts):
    """
    For matching instant periods, flag if:
        |Assets - (Liabilities + Equity)| > 5% of |Assets|

    5% tolerance (up from 1%) avoids false positives on companies with small
    amounts of mezzanine equity or noncontrolling interests that don't map
    neatly to any standard equity XBRL tag.
    """
    liab_by = {_instant_key(dp): dp for dp in liabilities_pts if dp.get("value") is not None}
    eq_by   = {_instant_key(dp): dp for dp in equity_pts if dp.get("value") is not None}

    flags = []
    for dp in assets_pts:
        assets = dp.get("value")
        if not assets:
            continue
        key = _instant_key(dp)
        liab_dp = liab_by.get(key)
        eq_dp   = eq_by.get(key)
        if liab_dp is None or eq_dp is None:
            continue
        liab = liab_dp["value"]
        eq   = eq_dp["value"]
        implied = liab + eq
        diff = abs(assets - implied)
        if diff > 0.05 * abs(assets):
            pct = 100 * diff / abs(assets)
            flags.append(_make_flag(
                FLAG_BALANCE_SHEET_MISMATCH,
                (f"Assets ({assets:,}) != Liabilities ({liab:,}) + Equity ({eq:,}) "
                 f"= {implied:,}; gap={diff:,} ({pct:.2f}%)"),
                dp.get("end"), assets,
                {"assets": assets, "liabilities": liab, "equity": eq,
                 "implied": implied, "diff": diff, "diff_pct": pct},
            ))
    return flags


# Line items where an exact-zero value is suspicious given non-zero peers.
# Long-Term Debt and Cash are excluded -- a company paying off all debt, or
# burning through cash, are legitimate business outcomes, not data errors.
_ZERO_CHECK_LINE_ITEMS = frozenset({
    "Revenue", "Net Income", "Total Assets", "Total Liabilities",
})


def _check_zero_among_nonzero(line_item_name, data_points):
    """
    Flag data points with value exactly 0 when the rest of the series has
    substantial nonzero values.

    Restricted to line items where zero is genuinely suspicious (Revenue,
    Net Income, Total Assets, Total Liabilities). Cash and Long-Term Debt are
    excluded because legitimate business events routinely produce zero there.
    """
    if line_item_name not in _ZERO_CHECK_LINE_ITEMS:
        return []
    import statistics
    nonzero = [abs(dp["value"]) for dp in data_points
               if dp.get("value") not in (None, 0)]
    if not nonzero:
        return []
    median_abs = statistics.median(nonzero)
    if median_abs < 1000:  # Skip EPS / ratio series
        return []
    return [
        _make_flag(
            FLAG_ZERO_AMONG_NONZERO,
            (f"{line_item_name} is exactly zero while other periods have "
             f"substantial values (series median={median_abs:,.0f})"),
            dp.get("end"), 0,
            {"series_median": median_abs},
        )
        for dp in data_points
        if dp.get("value") == 0
    ]


def _check_eps_reconciliation(net_income_points, diluted_shares_points, diluted_eps_points,
                               tolerance=0.05):
    """
    Flag periods where (Net Income / Diluted Shares) differs from reported Diluted EPS
    by more than `tolerance` (default 5%).

    Skipped when any of the three values is missing for a period, or when shares = 0.
    Shares are reported in ones; EPS is reported per share.
    """
    shares_by_key = {
        _period_key(dp): dp
        for dp in diluted_shares_points
        if dp.get("value") is not None and dp["value"] != 0
    }
    eps_by_key = {
        _period_key(dp): dp
        for dp in diluted_eps_points
        if dp.get("value") is not None
    }
    flags = []
    for dp in net_income_points:
        ni = dp.get("value")
        if ni is None:
            continue
        key = _period_key(dp)
        shares_dp = shares_by_key.get(key)
        eps_dp = eps_by_key.get(key)
        if shares_dp is None or eps_dp is None:
            continue
        shares = shares_dp["value"]
        reported_eps = eps_dp["value"]
        if reported_eps == 0:
            continue
        computed_eps = ni / shares
        diff_pct = abs(computed_eps - reported_eps) / abs(reported_eps)
        if diff_pct > tolerance:
            flags.append(_make_flag(
                FLAG_EPS_RECONCILIATION,
                (f"Computed EPS ({computed_eps:.4f}) differs from reported Diluted EPS "
                 f"({reported_eps:.4f}) by {diff_pct*100:.1f}% -- possible share count "
                 f"or unit mismatch"),
                dp.get("end"), reported_eps,
                {"net_income": ni, "shares": shares, "computed_eps": computed_eps,
                 "reported_eps": reported_eps, "diff_pct": diff_pct},
            ))
    return flags


def _check_large_yoy_change(line_item_name, data_points, threshold=5.0):
    """
    Flag year-over-year changes exceeding `threshold` (default 500%, i.e. 5x).

    Only compares consecutive annual periods (12-month flow items or year-end
    balance sheet instants). Skips when the prior-year value is zero (would be
    division by zero) or when either value is None.

    A 500% YoY change is the threshold: value went to >6x or <-4x the prior year.
    Only compares FY periods whose end dates are 10-14 months apart, to avoid
    false positives from gaps in historical XBRL data (e.g. early filings with
    different reporting bases creating phantom large changes across many years).
    """
    from datetime import datetime
    annual = sorted(
        [dp for dp in data_points if dp.get("fiscal_period") == "FY"
         and dp.get("value") is not None and dp.get("end")],
        key=lambda dp: dp.get("end") or ""
    )
    flags = []
    for i in range(1, len(annual)):
        prev_dp = annual[i - 1]
        curr_dp = annual[i]
        prev = prev_dp["value"]
        curr = curr_dp["value"]
        if prev == 0 or prev is None:
            continue
        try:
            prev_end = datetime.strptime(prev_dp["end"], "%Y-%m-%d")
            curr_end = datetime.strptime(curr_dp["end"], "%Y-%m-%d")
            days_apart = (curr_end - prev_end).days
            if not (300 <= days_apart <= 425):  # 10-14 months
                continue
        except (ValueError, TypeError):
            continue
        change_pct = abs(curr - prev) / abs(prev)
        if change_pct > threshold:
            flags.append(_make_flag(
                FLAG_LARGE_YOY_CHANGE,
                (f"{line_item_name} changed by {change_pct*100:.0f}% YoY "
                 f"({prev:,} -> {curr:,}) -- possible tagging error or unit mismatch"),
                annual[i].get("end"), curr,
                {"prior_value": prev, "current_value": curr, "change_pct": change_pct},
            ))
    return flags


def _is_annual_period(dp):
    """Return True if a data point covers one full fiscal year.

    Flow items are judged by period length, not by the fiscal_period label:
    EDGAR stamps fp on the filing, not the fact, so every comparative quarter
    inside a 10-K comes back labeled "FY".  A 10 to 14 month span is the honest
    signal.  Instants have no span to measure, so the label is all there is.
    """
    start, end = dp.get("start"), dp.get("end")
    if not end:
        return False
    if start is None:
        return dp.get("fiscal_period") == "FY"
    try:
        days = (datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)).days
    except (ValueError, TypeError):
        return False
    return 300 <= days <= 425


def _consecutive_annual_pairs(data_points):
    """Yield (previous, current) pairs of adjacent annual periods in a series.

    Adjacent means the two end dates are 10 to 14 months apart.  The date gate
    matters: XBRL histories have holes, and without it a 2012 period sitting
    next to a 2019 one would read as adjacent.
    """
    annual = sorted(
        [dp for dp in data_points if _is_annual_period(dp)],
        key=lambda dp: dp.get("end") or "",
    )
    for i in range(1, len(annual)):
        prev_dp, curr_dp = annual[i - 1], annual[i]
        try:
            prev_end = datetime.date.fromisoformat(prev_dp["end"])
            curr_end = datetime.date.fromisoformat(curr_dp["end"])
        except (ValueError, TypeError, KeyError):
            continue
        if 300 <= (curr_end - prev_end).days <= 425:
            yield prev_dp, curr_dp


def _check_tag_transition(line_item_name, data_points):
    """
    Flag the boundary year where a series switches from one XBRL tag to another.

    Per-period resolution stitches a single series out of every tag in a line
    item's fallback chain, so a company that changed tags mid-history keeps all
    of its years.  That is the point, but it means adjacent values in one row
    can come from different tags, and the two tags may not mean exactly the same
    thing.  This flag makes the seam visible on the first year of the new tag
    instead of leaving it buried in per-value provenance.

    Informational, like every other flag here: it never removes or alters data.
    """
    flags = []
    for prev_dp, curr_dp in _consecutive_annual_pairs(data_points):
        prev_tag = prev_dp.get("tag")
        curr_tag = curr_dp.get("tag")
        if not prev_tag or not curr_tag or prev_tag == curr_tag:
            continue
        flags.append(_make_flag(
            FLAG_TAG_TRANSITION,
            (f"{line_item_name} switches XBRL tag here: the period ending "
             f"{prev_dp.get('end')} comes from {prev_tag}, this one from {curr_tag}. "
             f"The two tags may not cover exactly the same items"),
            curr_dp.get("end"), curr_dp.get("value"),
            {"previous_tag": prev_tag, "current_tag": curr_tag,
             "previous_period_end": prev_dp.get("end")},
        ))
    return flags


def _check_missing_critical_data(deduped_line_items):
    """
    Flag if annual (FY) periods exist in any line item but both Revenue and
    Net Income are completely absent across all mapped tags.

    A 10-K with no revenue and no net income at all is almost certainly a
    tag-mapping gap, not a genuine reporting omission.
    """
    def _has_annual(name):
        data = deduped_line_items.get(name, {}).get("data", [])
        return any(dp.get("fiscal_period") == "FY" for dp in data)

    def _any_annual_data():
        for info in deduped_line_items.values():
            if any(dp.get("fiscal_period") == "FY" for dp in info.get("data", [])):
                return True
        return False

    if not _any_annual_data():
        return []

    if not _has_annual("Revenue") and not _has_annual("Net Income"):
        return [_make_flag(
            FLAG_MISSING_CRITICAL_DATA,
            ("Annual (10-K) periods detected but both Revenue and Net Income are "
             "absent across all mapped XBRL tags -- likely a tag-mapping gap"),
            None, None,
            {"revenue_tag_used": deduped_line_items.get("Revenue", {}).get("tag_used"),
             "net_income_tag_used": deduped_line_items.get("Net Income", {}).get("tag_used")},
        )]
    return []


def validate_financials(deduped_line_items):
    """
    Run all sanity checks on a deduplicated line-items dict.

    Returns a dict keyed by line-item name; each value is a list of flag dicts.
    An empty list means no flags for that line item.
    Balance-sheet equation flags are attached to "Total Assets".

    Flags are purely informational -- they never modify or remove data.
    """
    flags = {name: [] for name in deduped_line_items}
    flags["_company"] = []

    def _data(name):
        return deduped_line_items.get(name, {}).get("data", [])

    flags["Revenue"].extend(_check_negative_revenue(_data("Revenue")))

    flags["Net Income"].extend(
        _check_net_income_vs_revenue(_data("Net Income"), _data("Revenue"))
    )

    flags["Total Assets"].extend(
        _check_balance_sheet_equation(
            _data("Total Assets"), _data("Total Liabilities"), _data("Total Equity")
        )
    )

    for name, info in deduped_line_items.items():
        flags[name].extend(_check_zero_among_nonzero(name, info.get("data", [])))

    for name, info in deduped_line_items.items():
        flags[name].extend(_check_tag_transition(name, info.get("data", [])))

    flags["EPS Diluted"].extend(
        _check_eps_reconciliation(
            _data("Net Income"),
            _data("Shares Outstanding (Diluted)"),
            _data("EPS Diluted"),
        )
    )

    # YoY check restricted to income statement flow items where unit mismatches
    # are the primary concern. Balance sheet and EPS items are excluded:
    # equity changes dramatically with capital raises/IPOs (not data errors),
    # and EPS is better validated by the reconciliation check.
    _YOY_CHECK_ITEMS = {"Revenue", "Net Income", "Gross Profit", "Operating Income",
                        "Cost of Revenue"}
    for name, info in deduped_line_items.items():
        if name in _YOY_CHECK_ITEMS:
            flags[name].extend(_check_large_yoy_change(name, info.get("data", [])))

    flags["_company"].extend(_check_missing_critical_data(deduped_line_items))

    return flags


def flag_summary(all_flags):
    """
    Return a list of (line_item, flag) tuples for every raised flag, sorted
    by line item then period_end.
    """
    result = []
    for line_item, item_flags in all_flags.items():
        for flag in item_flags:
            result.append((line_item, flag))
    result.sort(key=lambda x: (x[0], x[1].get("period_end") or ""))
    return result
