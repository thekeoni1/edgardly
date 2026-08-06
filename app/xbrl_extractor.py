"""xbrl_extractor.py -- EDGAR XBRL structured financial data extraction.

Stage 1: tag-mapping dictionary, companyfacts fetch, and per-line-item resolution.
Stage 2: deduplication and clean period time-series.
Reuses _rate_limited_get from edgar_api for consistent rate limiting and User-Agent.
"""

import datetime

import line_items
import periods
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


# The forms that are a company's annual report to the SEC: the 10-K and its
# transition and small-business variants for domestic filers, the 20-F and 40-F
# for foreign ones, each with or without an /A amendment suffix.
#
# These are the filings a line item's annual figure belongs to. Everything else
# -- a 10-Q, an 8-K earnings release, a DEF 14A proxy -- may repeat an annual
# number, but repeating it is not reporting it, and a repetition is often
# rounded or reframed for its own purpose.
_ANNUAL_REPORT_FORMS = frozenset({
    "10-K", "10-KT", "10-K405", "10-KSB", "20-F", "40-F",
})


def is_annual_report_form(form):
    """Return True if a form type is the filer's annual report.

    Amendments count: a 10-K/A is still the annual report, and within the rank
    its later filing date is exactly what should let a restatement win.
    """
    if not form:
        return False
    base = str(form).split("/")[0].strip().upper()
    return base in _ANNUAL_REPORT_FORMS


def _resolution_rank(dp):
    """Order two entries reporting the same period. Higher wins.

    Rank first, filing date second. The rank exists because "most recently
    filed wins" was written for the 10-K/A case, where a later filing genuinely
    is better information, and it does not hold outside it: three JPMorgan 10-Ks
    report FY2023 net income as 49,552 million and a 2026 proxy statement
    repeats it rounded to 49,600, so on filing date alone the proxy took the row
    (PROGRESS.md open question 6). Ranking annual reports above everything else
    settles that without disturbing restatements, which are annual reports too
    and still win on date within the rank.
    """
    return (1 if is_annual_report_form(dp.get("form")) else 0,
            dp.get("filed") or "")


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
    earliest tag in the chain that reports it wins; within one tag, an annual
    report beats any other form, and within one form rank the most recently
    filed entry wins (a 10-K/A restating a year beats the original).  A period
    reported only by a later tag in the chain is kept rather than dropped.

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
            if incumbent is None or _resolution_rank(dp) > _resolution_rank(incumbent):
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

    When the same period appears more than once, an entry from an annual report
    beats an entry from any other form, and among entries of the same rank the
    most recently FILED one is kept (an original 10-K then a 10-K/A restatement:
    the restatement wins). Earlier and lower-ranked filings are discarded.

    The same ordering resolve_line_item uses, and deliberately so: the two ran
    on filing date alone and a proxy statement repeating a rounded annual figure
    took the row from the 10-K that reported it. Two functions applying two
    orderings to the same question is how a table ends up disagreeing with
    itself.

    Returns a list sorted by end date ascending (oldest period first).
    """
    from collections import defaultdict

    groups = defaultdict(list)
    for dp in data_points:
        groups[_period_key(dp)].append(dp)

    result = []
    for entries in groups.values():
        best = max(entries, key=_resolution_rank)
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


def _span_key(dp):
    """Identify a period by its dates alone, so series in different units meet.

    _period_key leads with the unit, which is right for deduplication: two
    values in different units are different facts. It is fatal here. Net income
    is in USD, a share count is in shares, and EPS is in USD-per-share, so no
    two of the three can ever share a _period_key and this check returned
    nothing for every company that has ever been run through it (PROGRESS.md
    open question 7). The dates are the only thing the three can agree on, and
    they are what makes them comparable.
    """
    return (dp.get("start"), dp.get("end"))


def _check_eps_reconciliation(net_income_points, diluted_shares_points, diluted_eps_points,
                               tolerance=0.05):
    """
    Flag periods where (Net Income / Diluted Shares) differs from reported Diluted EPS
    by more than `tolerance` (default 5%).

    Skipped when any of the three values is missing for a period, or when shares = 0.
    Shares are reported in ones; EPS is reported per share.

    Only periods that measure as one quarter or one year are compared. A
    year-to-date column carries the same end date as the quarter that closes
    it, and a flag raised on one would be shown against the other, because a
    flag reaches a cell by its end date. The same rule app/periods.py applies
    to values applies here to the checks on them.

    What the flag means when it fires: the three numbers were reported on
    different bases. A share split or a share-count restatement lands in the
    payload one filing at a time, so a period can hold an EPS recomputed on the
    new basis beside a share count still on the old one. A filer with preferred
    stock is the other case, and a systematic one: its EPS is computed on income
    available to common shareholders, and this check divides total net income,
    so every period comes out high by the preferred dividend.
    """
    shares_by_key = {
        _span_key(dp): dp
        for dp in diluted_shares_points
        if dp.get("value") is not None and dp["value"] != 0
    }
    eps_by_key = {
        _span_key(dp): dp
        for dp in diluted_eps_points
        if dp.get("value") is not None
    }
    flags = []
    for dp in net_income_points:
        ni = dp.get("value")
        if ni is None:
            continue
        if not (periods.covers_one_period(dp, periods.ANNUAL)
                or periods.covers_one_period(dp, periods.QUARTERLY)):
            continue
        key = _span_key(dp)
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
                (f"Net income divided by diluted shares is {computed_eps:.4f}, and the "
                 f"filer reports diluted EPS of {reported_eps:.4f}, a difference of "
                 f"{diff_pct*100:.1f}%. The three figures were reported on different "
                 f"bases: either a share split or share-count restatement has reached "
                 f"one row and not the others, or this filer's EPS is computed on income "
                 f"available to common shareholders and the gap is its preferred "
                 f"dividend"),
                dp.get("end"), reported_eps,
                {"net_income": ni, "shares": shares, "computed_eps": computed_eps,
                 "reported_eps": reported_eps, "diff_pct": diff_pct},
            ))
    return flags


def _check_large_yoy_change(line_item_name, data_points, threshold=5.0):
    """
    Flag year-over-year changes exceeding `threshold` (default 500%, i.e. 5x).

    Only compares consecutive annual periods, adjacent meaning 10 to 14 months
    apart. Skips when the prior-year value is zero (would be division by zero)
    or when either value is None.

    A 500% YoY change is the threshold: value went to >6x or <-4x the prior year.

    Which periods are annual is decided by span through _is_annual_period, not
    by the fiscal_period label, which is the whole of what this check used to
    get wrong. EDGAR stamps fp on the filing rather than the fact, so every
    comparative quarter inside a 10-K comes back labelled FY, and the label is
    the one signal the 2026-08-04 decisions-log entry says never to trust. A
    13-week fourth quarter ends 364 days before the next year end, so the date
    gate admitted it and the check compared a year against a quarter: Apple's
    FY2021 gross profit of 152,836 million was flagged as a 519 percent change
    from the 24,689 of its Q4 FY2020, and Apple's FY2021 net income and two of
    Kroger's rows the same way (breakage log rows 1 and 2). Both values were
    correct and the sentence said "possible tagging error or unit mismatch"
    about them.
    """
    annual = sorted(
        [dp for dp in data_points if dp.get("value") is not None
         and dp.get("end") and _is_annual_period(dp)],
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
            prev_end = datetime.date.fromisoformat(prev_dp["end"])
            curr_end = datetime.date.fromisoformat(curr_dp["end"])
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
    # Every item passed in, plus every item the checks below write to. A caller
    # is free to extract two line items, and a check that names a third must
    # then find an empty list rather than raise.
    flags = {name: [] for name in deduped_line_items}
    for name in ("Revenue", "Net Income", "Total Assets", "EPS Diluted", "_company"):
        flags.setdefault(name, [])

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


# ---------------------------------------------------------------------------
# Stage 4 -- Provenance on every value
#
# Every number Edgardly shows is exactly one of three things, and it says which:
#
#   reported  the filer tagged it. Carries the tag, the filed date, and the
#             accession number of the filing it came from. Because resolution
#             is per period, two cells in one row can name different tags, and
#             the provenance of each says which.
#   derived   Edgardly computed it from reported values. Carries the formula
#             and the provenance of every input, so the arithmetic can be
#             checked without leaving the page.
#   missing   nobody tagged it. Carries a pointer to the statement of the
#             filing where a reader can go find it by hand. Never a zero,
#             never a guess.
#
# The pointer is built out of data already in hand: the accession number of the
# filing that reported the period, and the statement the registry says the item
# lives on.
# ---------------------------------------------------------------------------

PROVENANCE_REPORTED = "reported"
PROVENANCE_DERIVED = "derived"
PROVENANCE_MISSING = "missing"

# The flags a missing value can carry. Distinct from the validation flags
# above: those describe a number that looks wrong, these describe the absence
# of one, and they do not mean the same thing.
#
# NOT_TAGGED       the filer never tagged this item for this period.
# PERIOD_UNRESOLVED the tag holds a value carrying this end date, but not one
#                  Edgardly could confirm covers the period. EDGAR stamps the
#                  fiscal-period label on the filing rather than the fact, so a
#                  later 10-Q can overwrite a year-end balance sheet's label
#                  (PROGRESS.md open question 3). Saying "not tagged" here
#                  would be false, and the difference matters to anyone
#                  deciding whether to go read the filing.
# DERIVATION_UNAVAILABLE the row is arithmetic, never a tag, and at least one
#                  input was not there for this period. Saying "not tagged"
#                  about Total Debt would be true of every filer that ever
#                  lived and would send a reader looking for a line no balance
#                  sheet carries; what is missing is a component, and the
#                  message names it.
# NOT_IN_ANNUAL_REPORT the filer tagged the item for the period, but only in an
#                  interim filing: no annual report presents the line. The
#                  scaffold's historical columns are fiscal years of filed
#                  annual reports, so a figure only a 10-Q carries is shown as
#                  a hole that names the figure and the filing rather than put
#                  into an annual series (decisions log, 2026-08-05). Neither
#                  "not tagged" nor "unresolved" is true of it: the number
#                  exists, is the filer's own, and is sourced -- just not to an
#                  annual report.
# NO_PRIOR_COLUMN the row is arithmetic that reaches back a period, and the
#                  period it reaches back to is before the first column of the
#                  model. Nothing is missing from the filing: what is missing is
#                  a column, and the only three flags above would all say
#                  otherwise. Opening cash in the first historical year is the
#                  case (breakage log row 6).
FLAG_NOT_TAGGED = "NOT_TAGGED"
FLAG_PERIOD_UNRESOLVED = "PERIOD_UNRESOLVED"
FLAG_DERIVATION_UNAVAILABLE = "DERIVATION_UNAVAILABLE"
FLAG_NOT_IN_ANNUAL_REPORT = "NOT_IN_ANNUAL_REPORT"
FLAG_NO_PRIOR_COLUMN = "NO_PRIOR_COLUMN"

SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# Annual forms, in the order a pointer prefers them.
_ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "40-F")


def filing_index_url(cik, accession):
    """Return the EDGAR filing index URL for an accession number, or None.

    The archive path wants the accession with its dashes stripped and the CIK
    without leading zeros, which is not the shape either arrives in.
    """
    if not cik or not accession:
        return None
    digits = str(accession).replace("-", "").strip()
    if not digits:
        return None
    try:
        cik_part = str(int(str(cik).strip()))
    except (TypeError, ValueError):
        return None
    return "{}/{}/{}/".format(SEC_ARCHIVES_BASE, cik_part, digits)


def filing_pointers(facts_data):
    """Map each period end date to the filing a reader should go look at.

    A missing value has no data point of its own to point at, so the pointer
    comes from whatever else the filer did tag for the same period. Annual
    forms win over interim ones, and among those the EARLIEST filed wins: a
    period's own 10-K is the filing that reported it first, while every later
    10-K carries it only as a comparative.

    Reads the companyfacts payload rather than a resolved series, and reads
    every tag in it rather than only the registry's. Resolution already keeps
    one entry per period per tag, the most recently filed, which discards the
    very filing this function exists to find: point Apple's FY2023 hole at a
    resolved series and it names the FY2024 10-K.

    Returns {period_end: {"accn", "form", "filed"}}.
    """
    us_gaap = ((facts_data or {}).get("facts", {}) or {}).get("us-gaap", {}) or {}
    best = {}
    for tag_data in us_gaap.values():
        for entries in (tag_data.get("units", {}) or {}).values():
            for entry in entries:
                end = entry.get("end")
                accn = entry.get("accn")
                if not end or not accn:
                    continue
                form = entry.get("form") or ""
                rank = (_ANNUAL_FORMS.index(form) if form in _ANNUAL_FORMS
                        else len(_ANNUAL_FORMS))
                key = (rank, entry.get("filed") or "9999-99-99")
                incumbent = best.get(end)
                if incumbent is None or key < incumbent[0]:
                    best[end] = (key, {"accn": accn, "form": form,
                                       "filed": entry.get("filed")})
    return {end: pointer for end, (_key, pointer) in best.items()}


# How far after a filer's fiscal year end its annual report can arrive and still
# be that year's report. The SEC allows 60 to 90 days depending on filer status,
# and a late or amended filing stretches it further; 400 days is loose enough to
# admit an amendment filed a year on and tight enough to exclude the next year.
_ANNUAL_REPORT_LAG_DAYS = 400


def _annual_report_year_ends(facts_data):
    """One (period end, fiscal year focus) pair per annual filing in the payload.

    A filing's own fiscal year end is the latest period end it reports: every
    other date in a 10-K is a comparative or an interim column, and nothing in
    a companyfacts payload is dated after the period the filing covers. The two
    guards keep that true where the payload is untidy -- an end date after the
    filing date is not a period the filing reported, and an end date more than
    _ANNUAL_REPORT_LAG_DAYS before it belongs to some earlier year.

    fy is EDGAR's copy of the filing's dei DocumentFiscalYearFocus, the filer's
    own name for the year. It is not in the facts block -- companyfacts carries
    only numeric dei facts, and DocumentFiscalYearFocus is a gYear -- but EDGAR
    stamps it on every fact the filing reported, which is the same value read
    from a place the fixtures already hold.

    Returns {accession: (period_end, filed, fiscal_year_focus)}.
    """
    us_gaap = ((facts_data or {}).get("facts", {}) or {}).get("us-gaap", {}) or {}
    per_filing = {}
    for tag_data in us_gaap.values():
        for entries in (tag_data.get("units", {}) or {}).values():
            for entry in entries:
                accn, end = entry.get("accn"), entry.get("end")
                filed, focus = entry.get("filed"), entry.get("fy")
                if not (accn and end and filed and focus):
                    continue
                if entry.get("fp") != "FY":
                    continue
                if not is_annual_report_form(entry.get("form")):
                    continue
                if end > filed:
                    continue
                try:
                    lag = (datetime.date.fromisoformat(filed)
                           - datetime.date.fromisoformat(end)).days
                except (ValueError, TypeError):
                    continue
                if lag > _ANNUAL_REPORT_LAG_DAYS:
                    continue
                incumbent = per_filing.get(accn)
                if incumbent is None or end > incumbent[0]:
                    per_filing[accn] = (end, filed, int(focus))
    return per_filing


def fiscal_year_offset(facts_data):
    """How far a filer's own name for a fiscal year sits behind the year it ends in.

    Edgardly used to name every fiscal year for the calendar year its period
    ended in, which is right for Apple, Honeywell and JPMorgan and wrong for
    Kroger: the year running 2 February 2025 to 31 January 2026 is FY2026 by
    that rule and fiscal 2025 on Kroger's own 10-K cover page. The obvious
    repair, naming a year for the calendar year that holds most of it, is wrong
    in the other direction -- Nike's year ends 31 May and Nike names it for the
    later year, which that rule would rename (PROGRESS.md open question 8).

    So the name comes from the filer. Each annual filing carries its own fiscal
    year focus and its own year end, and the difference between the two is the
    filer's convention: 0 for a calendar-year filer, 1 for Kroger, 0 again for
    Nike. The convention is what is returned, not the individual values, for
    two reasons. It is stable where the values are not: Kroger tagged focus 2025
    on both the year ended 1 February 2025 and the year ended 31 January 2026,
    and Honeywell tagged 2020 on its 2021 annual report, so taking each year's
    own value at face value would put two columns under one name. And it reaches
    years no annual filing names, which is every year a company's first XBRL
    filing carried as a comparative.

    The commonest difference wins, and the most recent filing breaks a tie. A
    filer that changes its fiscal year end changes its convention with it, and
    this returns the one it used most; no fixture does that, and a filer that
    does needs more than one number.

    Returns 0 when the payload names no fiscal year at all, which is exactly the
    end-year rule this replaces.
    """
    observed = _annual_report_year_ends(facts_data)
    if not observed:
        return 0

    tally = {}
    for end, filed, focus in observed.values():
        try:
            offset = int(end[:4]) - focus
        except (ValueError, TypeError):
            continue
        count, latest = tally.get(offset, (0, ""))
        tally[offset] = (count + 1, max(latest, filed))
    if not tally:
        return 0
    return max(tally, key=lambda offset: (tally[offset][0], tally[offset][1]))


def reported_provenance(dp):
    """Provenance for a value the filer tagged."""
    return {
        "state": PROVENANCE_REPORTED,
        "tag": dp.get("tag"),
        "filed": dp.get("filed"),
        "accession": dp.get("accn"),
        "form": dp.get("form"),
    }


def derived_provenance(formula, inputs):
    """Provenance for a value Edgardly computed.

    inputs is a list of {"name", "value", "tag", "filed", "accession"} dicts,
    one per input, in the order the formula names them. Carrying the inputs and
    not just the formula string is the difference between showing the work and
    asserting it.
    """
    return {
        "state": PROVENANCE_DERIVED,
        "formula": formula,
        "inputs": list(inputs),
    }


def _interim_sentence(interim, period_label):
    """What a NOT_IN_ANNUAL_REPORT blank has to say to be worth more than a gap.

    A hole that says only "not here" sends the reader hunting. This one hands
    over the figure it declined to use, the filing that carries it and the date
    it was filed, so a reader who wants that number can take it deliberately
    rather than be handed it silently in an annual column.
    """
    value = interim.get("value")
    amount = ("{:,.0f}".format(value) if isinstance(value, (int, float))
              else "a figure")
    form = interim.get("form") or "an interim filing"
    filed = interim.get("filed")
    accn = interim.get("accn")
    where = form if not filed else "{} filed {}".format(form, filed)
    if accn:
        where = "{} (accession {})".format(where, accn)
    return ("Reported only in an interim filing. The one figure Edgardly can "
            "find for {} is {}, from the {}; no annual report reports this line "
            "for the period, so the column is left blank rather than taking an "
            "annual figure from a filing that is not an annual report".format(
                period_label or "this period", amount, where))


def missing_provenance(line_item, period_label, cik=None, pointer=None,
                       flag=FLAG_NOT_TAGGED, missing_inputs=(), interim=None,
                       formula=None, opening=None, statement_label=None):
    """Provenance for a value that is not there, with a pointer to go find it.

    pointer is one entry from filing_pointers, or None when no filing for the
    period could be identified, in which case the message names the statement
    but has no link to offer.

    flag says which kind of absence this is; all of them send the reader to the
    same place, and only one of them claims the filer never tagged the item.
    missing_inputs names the components a DERIVATION_UNAVAILABLE was short of,
    and formula overrides the registry's derivation text for a row that is a
    model construct rather than a registry derivation. interim carries the data
    point a NOT_IN_ANNUAL_REPORT blank declined to use.

    opening replaces the whole first sentence, for a caller that knows something
    about the absence this function cannot work out from a line item's name.
    statement_label names the statement the pointer sends the reader to, for a
    row that is not a registry item and so has no statement of its own to look
    up; without it such a row's message reads "Check the FY2021 10-K" and says
    nothing about where in it to look.
    """
    pointer = pointer or {}
    statement = (line_items.missing_pointer_label(line_item)
                 if statement_label is None else statement_label)
    form = pointer.get("form") or "10-K"
    url = filing_index_url(cik, pointer.get("accn"))

    where = "the {} of the".format(statement) if statement else "the"
    target = " ".join(part for part in (where, period_label, form) if part)
    if opening is not None:
        pass
    elif flag == FLAG_PERIOD_UNRESOLVED:
        opening = ("Tagged in XBRL, but not for a period Edgardly could confirm "
                   "as {}".format(period_label or "this period"))
    elif flag == FLAG_NOT_IN_ANNUAL_REPORT:
        opening = _interim_sentence(interim or {}, period_label)
    elif flag == FLAG_DERIVATION_UNAVAILABLE:
        if formula is None:
            rule = line_items.DERIVATIONS.get(line_item)
            formula = rule.formula if rule is not None else ""
        short_of = ", ".join(missing_inputs) or "an input"
        opening = ("No filer tags this; Edgardly computes it as {}. {} is not "
                   "reported for this period".format(formula, short_of))
    else:
        opening = "Not tagged in XBRL"
    message = "{}. Check {}".format(opening, target)
    message += ": {}.".format(url) if url else "."

    return {
        "state": PROVENANCE_MISSING,
        "flag": flag,
        "message": message,
        "statement": statement,
        "period": period_label,
        "form": form,
        "accession": pointer.get("accn"),
        "url": url,
    }


def period_label(period_end, fiscal_period=None, period_type="annual", fy_offset=0,
                 annual_ends=()):
    """Name a period the way the tables name it: FY2023, or Q3 FY2023.

    A fiscal year is named for the calendar year its period ends in, shifted by
    the filer's own convention. fy_offset comes from fiscal_year_offset: Kroger's
    year ending 31 January 2026 is FY2025 because Kroger says so, and Apple's
    offset is zero so nothing about Apple's annual labels moves.

    A quarter is named for the fiscal year it belongs to, not for the calendar
    year it ends in, which is the same year its own annual column carries. The
    two used to disagree about the same date: Kroger's fourth quarter ended
    31 January 2026 read "Q4 2026" beside an annual column reading FY2025, and
    Apple's quarter ending 28 December 2024 read "Q1 2024" when it is Apple's
    first quarter of fiscal 2025 (PROGRESS.md open question 10). Which fiscal
    year a quarter is in comes from closing_fiscal_year, which needs the year
    ends the period engine has already confirmed; annual_ends must be sorted.

    Without confirmed year ends there is nothing to place a quarter in, and the
    calendar year of its end date stands in, which is what the labels carried
    before. That is a name, never a value: no number moves either way.
    """
    if not period_end:
        return ""
    year = str(period_end)[:4]
    if period_type == "annual" or not fiscal_period or fiscal_period == "FY":
        try:
            year = str(int(year) - fy_offset)
        except (ValueError, TypeError):
            pass
        return "FY{}".format(year)

    closing = periods.closing_fiscal_year(period_end, annual_ends)
    try:
        year = str((closing if closing is not None else int(year)) - fy_offset)
    except (ValueError, TypeError):
        pass
    return "{} FY{}".format(fiscal_period, year)


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
