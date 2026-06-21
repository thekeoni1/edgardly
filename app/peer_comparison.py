"""peer_comparison.py -- Multi-company XBRL peer comparison.

Wraps existing single-company extraction, deduplication, and validation
logic from xbrl_extractor.  Does NOT reimplement tag-mapping, deduplication,
or validation -- calls those functions directly.

Rate limiting is inherited from xbrl_extractor.fetch_company_facts ->
edgar_api._rate_limited_get (0.1 s/call, proper User-Agent, 429 back-off).
"""

import datetime
import xbrl_extractor as xbrl

# Minimum period length (days) for a flow item to count as a full fiscal year.
_MIN_ANNUAL_DAYS = 300

# Line item type classification -- mirrors the constants in app.py.
# Kept here to avoid a circular import (app.py will import peer_comparison).
DOLLAR_LINE_ITEMS = frozenset({
    "Revenue", "Cost of Revenue", "Gross Profit", "Operating Income", "Net Income",
    "Total Assets", "Total Liabilities", "Total Equity", "Cash and Equivalents", "Total Debt",
})
EPS_LINE_ITEMS = frozenset({"EPS Basic", "EPS Diluted"})
SHARE_LINE_ITEMS = frozenset({"Shares Outstanding (Basic)", "Shares Outstanding (Diluted)"})


def _is_valid_annual_flow(dp):
    """
    Return True if dp is a valid annual data point for a FLOW item
    (income statement / cash flow -- has both start and end dates).

    Uses period length (300–425 days) instead of the fiscal_period label.
    Reason: deduplication keeps the most-recently-filed entry per period key,
    and a later DEF 14A or 10-Q sometimes shadows the 10-K entry, leaving
    fiscal_period as None or a quarter label even for a full-year period.
    The period length is a reliable signal: quarterly and YTD entries are
    < 300 days; multi-year cumulative totals are > 425 days.

    Balance-sheet instants (start is None) must be handled separately; see
    _collect_fy_ends.
    """
    start = dp.get("start")
    end = dp.get("end")
    if not start or not end:
        return False
    try:
        days = (
            datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)
        ).days
        return _MIN_ANNUAL_DAYS <= days <= 425
    except (ValueError, TypeError):
        return False


def _collect_fy_ends(deduped, line_items):
    """
    Return the set of confirmed fiscal-year end dates for a company.

    Two-phase approach:
      1. Collect dates from FLOW items (income statement) where fiscal_period=="FY"
         and the period spans at least _MIN_ANNUAL_DAYS.  These are the primary
         anchors for the company's fiscal year calendar.
      2. Also collect dates from BALANCE-SHEET instants (start==None) that are
         explicitly labeled fiscal_period=="FY" in the deduped data.  Some
         companies' 10-K balance sheet entries are not shadowed by later 10-Q
         filings and provide additional anchor dates.

    The union is returned.  Downstream code uses this set to accept a balance-sheet
    instant for any end date in the set, regardless of whether that instant's own
    fiscal_period field was overwritten by a later 10-Q filing (the "shadowing" bug
    described below).

    Background: EDGAR's deduplication (most-recently-filed wins) can leave a
    balance-sheet instant with fiscal_period="Q2" if a later 10-Q includes
    the same balance-sheet date as a comparison period.  Filtering such instants
    by fiscal_period=="FY" alone would miss them.  Using the flow-item anchor set
    as the filter avoids that pitfall.
    """
    flow_fy_ends: set = set()
    bs_fy_ends: set = set()

    for li in line_items:
        info = deduped.get(li) or {}
        for dp in info.get("data", []):
            start = dp.get("start")
            end = dp.get("end")
            if not end:
                continue
            if start is None:
                # Balance-sheet instant: only trust the FY label when it is
                # present (the anchor approach below handles shadowed entries).
                if dp.get("fiscal_period") == "FY":
                    bs_fy_ends.add(end)
            else:
                # Flow item: use period-length filter (see _is_valid_annual_flow)
                if _is_valid_annual_flow(dp):
                    flow_fy_ends.add(end)

    return flow_fy_ends | bs_fy_ends


def _best_dp_for_end(dps, end_date):
    """
    Among data points with a specific end date, return the one with the longest
    period (prefers the full-year entry over any mislabeled partials).
    For instants (start==None), period length is 0 and the first match is used.
    """
    candidates = [dp for dp in dps if dp.get("end") == end_date]
    if not candidates:
        return None

    def _days(dp):
        s, e = dp.get("start"), dp.get("end")
        if not s or not e:
            return 0
        try:
            return (datetime.date.fromisoformat(e) - datetime.date.fromisoformat(s)).days
        except (ValueError, TypeError):
            return 0

    return max(candidates, key=_days)


def fetch_peer_data(cik, line_items, n_periods=5):
    """
    Fetch, extract, deduplicate, and validate XBRL data for one company.

    All heavy lifting (tag resolution, deduplication, validation) is delegated
    to xbrl_extractor.  This function handles period selection and result
    structuring.

    Args:
        cik:        company CIK (str or int)
        line_items: list of canonical line-item names (keys of xbrl.TAG_MAP).
                    Items not in TAG_MAP are returned with all-None periods.
        n_periods:  how many most-recent fiscal years to include (newest first
                    as FY0, FY-1, FY-2, ...)

    Returns:
        {
            "name": str,        -- entity name from EDGAR companyfacts
            "cik":  str,
            "line_items": {
                <name>: {
                    "tag_used": str | None,
                    "periods": [    -- sorted newest-first, len <= n_periods
                        {
                            "relative_period": "FY0" | "FY-1" | "FY-2" | ...,
                            "period_end":      "YYYY-MM-DD",
                            "period_start":    "YYYY-MM-DD" | None,
                            "value":           number | None,
                            "source_tag":      str | None,
                            "flags":           [{"flag_type": str, "message": str}]
                        },
                        ...
                    ]
                },
                ...
            }
        }
    """
    cik = str(cik)
    facts = xbrl.fetch_company_facts(cik)
    entity = facts.get("entityName", cik)

    raw = xbrl.extract_all_line_items(facts)
    deduped = xbrl.deduplicate_all_line_items(raw)
    all_flags = xbrl.validate_financials(deduped)

    # Collect all confirmed FY end dates for this company.
    fy_ends = _collect_fy_ends(deduped, line_items)
    sorted_ends = sorted(fy_ends, reverse=True)[:n_periods]

    result_items = {}
    for li in line_items:
        info = deduped.get(li) or {}
        tag_used = info.get("tag_used")
        item_flags = all_flags.get(li, [])
        all_dps = info.get("data", [])

        # Select valid annual data points for this line item.
        # Flow items: strict filter (fiscal_period=="FY", period >= 300 days).
        # Balance-sheet instants: accept any entry whose end date is a confirmed
        # FY end date -- the flow items' dates serve as the anchor so that instants
        # overwritten in deduplication (fp!=FY) are still included.
        annual_dps = []
        for dp in all_dps:
            start = dp.get("start")
            end = dp.get("end")
            if not end:
                continue
            if start is None:
                # Balance-sheet instant: accept if end is a confirmed FY date
                if end in fy_ends:
                    annual_dps.append(dp)
            else:
                # Flow item: strict annual filter
                if _is_valid_annual_flow(dp):
                    annual_dps.append(dp)

        periods = []
        for i, end in enumerate(sorted_ends):
            rel_label = "FY0" if i == 0 else "FY-{}".format(i)
            dp = _best_dp_for_end(annual_dps, end)
            if dp is None:
                periods.append({
                    "relative_period": rel_label,
                    "period_end": end,
                    "period_start": None,
                    "value": None,
                    "source_tag": None,
                    "flags": [],
                })
            else:
                period_flags = [
                    {"flag_type": f["flag_type"], "message": f["message"]}
                    for f in item_flags
                    if f.get("period_end") == end
                ]
                periods.append({
                    "relative_period": rel_label,
                    "period_end": end,
                    "period_start": dp.get("start"),
                    "value": dp["value"],
                    "source_tag": dp.get("tag"),
                    "flags": period_flags,
                })

        result_items[li] = {"tag_used": tag_used, "periods": periods}

    return {"name": entity, "cik": cik, "line_items": result_items}


def fetch_peer_comparison(ciks, line_items=None, n_periods=3, progress_callback=None):
    """
    Fetch XBRL data for multiple companies sequentially.

    Sequential (not parallel) to respect EDGAR rate limits.  Each company
    requires exactly one API call via xbrl.fetch_company_facts; the 0.1 s
    minimum delay is enforced inside edgar_api._rate_limited_get.

    Args:
        ciks:              list of CIK strings or ints
        line_items:        line items to include; defaults to all TAG_MAP keys
        n_periods:         fiscal years per company, most-recent first
        progress_callback: optional callable(fetched_so_far, total, company_name)
                           called just BEFORE each fetch begins, and once more
                           after the last fetch with fetched_so_far == total

    Returns:
        {
            "companies":  [<fetch_peer_data result>, ...],  -- same order as ciks
            "line_items": [...],
            "n_periods":  int,
        }
    """
    if line_items is None:
        line_items = list(xbrl.TAG_MAP.keys())

    companies = []
    total = len(ciks)

    for i, cik in enumerate(ciks):
        if progress_callback:
            progress_callback(i, total, str(cik))
        companies.append(fetch_peer_data(str(cik), line_items, n_periods))

    if progress_callback:
        progress_callback(total, total, "")

    return {"companies": companies, "line_items": line_items, "n_periods": n_periods}


# ---------------------------------------------------------------------------
# Stage 2 -- Scale selection
# ---------------------------------------------------------------------------

def select_peer_scale(comparison_result):
    """
    Determine display scales for an entire peer comparison table.

    Dollar scale is driven by the LARGEST absolute FY0 Revenue across all
    companies (falls back to the largest Total Assets if no company has FY0
    Revenue data).  This ensures one consistent scale for the entire table,
    so a large-cap and a small-cap in the same comp set are always shown in
    the same units.

    Share scale is independent of dollar scale and is driven by the LARGEST
    absolute FY0 diluted (or basic) share count.

    EPS items are never scaled (they are per-share values).

    Thresholds match app.py _detect_dollar_scale:
        Revenue > $1 B  →  $mm   (factor = 1_000_000)
        Revenue > $10 M →  $000s (factor = 1_000)
        Revenue ≤ $10 M →  $     (factor = 1)

    Args:
        comparison_result: dict returned by fetch_peer_comparison

    Returns:
        {
            "dollar_factor": int,   -- divisor to apply to dollar values
            "dollar_label":  str,   -- "$mm", "$000s", or "$"
            "share_factor":  int,   -- divisor to apply to share counts
            "share_label":   str,   -- "mm" or "000s"
        }
    """
    def _dollar_scale(val):
        v = abs(val)
        if v > 1_000_000_000:
            return 1_000_000, "$mm"
        if v > 10_000_000:
            return 1_000, "$000s"
        return 1, "$"

    def _fy0_value(company, line_item):
        """Return FY0 value for a line item, or None if absent."""
        info = company["line_items"].get(line_item) or {}
        periods = info.get("periods", [])
        if periods:
            return periods[0].get("value")
        return None

    companies = comparison_result.get("companies", [])

    # Dollar scale: max absolute FY0 Revenue across all companies
    max_rev = max(
        (abs(_fy0_value(c, "Revenue"))
         for c in companies
         if _fy0_value(c, "Revenue") is not None),
        default=None,
    )

    if max_rev is None:
        # Fallback: max absolute FY0 Total Assets
        max_rev = max(
            (abs(_fy0_value(c, "Total Assets"))
             for c in companies
             if _fy0_value(c, "Total Assets") is not None),
            default=None,
        )

    if max_rev is not None:
        dollar_factor, dollar_label = _dollar_scale(max_rev)
    else:
        dollar_factor, dollar_label = 1_000_000, "$mm"  # sensible default

    # Share scale: max absolute FY0 share count across all companies
    max_shares = None
    for share_item in ("Shares Outstanding (Diluted)", "Shares Outstanding (Basic)"):
        candidates = [
            abs(_fy0_value(c, share_item))
            for c in companies
            if _fy0_value(c, share_item) is not None
        ]
        if candidates:
            max_shares = max(candidates)
            break  # diluted takes priority; only fall back to basic if no diluted

    if max_shares is not None and max_shares > 1_000_000_000:
        share_factor, share_label = 1_000_000, "mm"
    else:
        share_factor, share_label = 1_000, "000s"

    return {
        "dollar_factor": dollar_factor,
        "dollar_label": dollar_label,
        "share_factor": share_factor,
        "share_label": share_label,
    }
