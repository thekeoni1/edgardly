"""peer_comparison.py -- Multi-company XBRL peer comparison.

Wraps existing single-company extraction, deduplication, and validation
logic from xbrl_extractor.  Does NOT reimplement tag-mapping, deduplication,
or validation -- calls those functions directly.

Rate limiting is inherited from xbrl_extractor.fetch_company_facts ->
edgar_api._rate_limited_get (0.1 s/call, proper User-Agent, 429 back-off).
"""

import line_items
import periods
import xbrl_extractor as xbrl

# Canonical definitions live in line_items.py, shared with app.py.
# Re-exported here because callers already reach for pc.DOLLAR_LINE_ITEMS.
DOLLAR_LINE_ITEMS = line_items.DOLLAR_LINE_ITEMS
EPS_LINE_ITEMS = line_items.EPS_LINE_ITEMS
SHARE_LINE_ITEMS = line_items.SHARE_LINE_ITEMS


# The date-anchored period logic this module used to own now lives in
# periods.py, unchanged in behavior, because the single-company table needed the
# same answers and was giving itself different ones (V2_PLAN R5). What is left
# here is what this view does with the periods: how many, in what order, and
# with what labels.


# Items this table may fill by arithmetic when the filer tags no value of its
# own, in the order they have to be computed. Taken from the registry, which is
# also where the single-company table takes it, so the two views can never
# disagree about what a number is.
_DERIVED_ITEMS = line_items.DERIVED_UI_ITEMS
_UI_LINE_ITEMS = line_items.UI_LINE_ITEMS
_DERIVATION_INPUT_ITEMS = line_items.DERIVATION_INPUT_ITEMS


def _derivation_input(name, period):
    """One entry of a derived value's provenance, describing where it came from."""
    prov = period.get("provenance") or {}
    entry = {
        "name": name,
        "value": period.get("value"),
        "tag": period.get("source_tag"),
        "filed": prov.get("filed"),
        "accession": prov.get("accession"),
    }
    if prov.get("state") == xbrl.PROVENANCE_DERIVED:
        entry["formula"] = prov.get("formula")
        entry["inputs"] = prov.get("inputs", [])
    return entry


def _fill_derived_periods(result_items):
    """Compute the values the filer left untagged but the table can prove.

    Same rule as the single-company path: an input must be reported for the
    same period, or already derived from values that were, and nesting stops
    at that one level. Written as a module-level function because
    fetch_peer_data's own parameter shadows the line_items module.
    """
    usable = (xbrl.PROVENANCE_REPORTED, xbrl.PROVENANCE_DERIVED)

    for name in _DERIVED_ITEMS:
        rule = line_items.DERIVATIONS.get(name)
        target = result_items.get(name)
        if rule is None or target is None:
            continue
        sources = [(input_name, result_items.get(input_name))
                   for input_name, _sign in rule.inputs]

        for idx, period in enumerate(target.get("periods", [])):
            if period.get("value") is not None:
                continue

            inputs = []
            for input_name, info in sources:
                candidates = (info or {}).get("periods", [])
                source = candidates[idx] if idx < len(candidates) else None
                state = (source or {}).get("provenance", {}).get("state")
                if (source is None or source.get("value") is None
                        or state not in usable
                        or source.get("period_end") != period.get("period_end")):
                    continue
                inputs.append((input_name, source))

            values = {n: p["value"] for n, p in inputs}
            used = line_items.inputs_used(name, values)
            if not used:
                continue
            inputs = [(n, p) for n, p in inputs if n in used]

            value = line_items.derive(name, values)
            if value is None:
                continue

            period["value"] = value
            period["period_start"] = inputs[0][1].get("period_start")
            period["provenance"] = xbrl.derived_provenance(
                line_items.formula_for(name, values),
                [_derivation_input(n, p) for n, p in inputs])


def _explain_underivable_periods(result_items, cik, pointers, fy_offset=0):
    """Say which component was missing where an arithmetic-only row is blank.

    Runs before the derivation inputs are dropped, for the same reason and with
    the same message as the single-company path.
    """
    derived_only = [name for name in _UI_LINE_ITEMS
                    if name in line_items.DERIVATIONS and name not in line_items.REGISTRY]

    for name in derived_only:
        rule = line_items.DERIVATIONS[name]
        target = result_items.get(name)
        if target is None:
            continue
        for idx, period in enumerate(target.get("periods", [])):
            if period.get("value") is not None:
                continue
            absent = []
            for input_name, _sign in rule.inputs:
                candidates = (result_items.get(input_name) or {}).get("periods", [])
                source = candidates[idx] if idx < len(candidates) else None
                if source is None or source.get("value") is None:
                    absent.append(input_name)
            end = period.get("period_end")
            period["provenance"] = xbrl.missing_provenance(
                name, xbrl.period_label(end, fy_offset=fy_offset), cik,
                pointers.get(end), xbrl.FLAG_DERIVATION_UNAVAILABLE, absent)


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

    # What the caller asked for, plus the rest of the displayed set and the
    # derivation inputs. The extras are computed with and then dropped: the
    # sanity checks read items a caller asking for two rows would not have
    # requested, and Total Debt is built from four rows nobody asks for.
    requested = list(line_items)
    wanted = requested + [name for name in list(_UI_LINE_ITEMS) + list(_DERIVATION_INPUT_ITEMS)
                          if name not in requested]

    raw = xbrl.extract_all_line_items(facts, wanted)
    deduped = xbrl.deduplicate_all_line_items(raw)
    all_flags = xbrl.validate_financials(deduped)

    # Collect all confirmed FY end dates for this company. Only the requested
    # items may witness a period: a derivation input is fetched to be added up,
    # not to put a year on the table that the caller's own items do not show.
    fy_ends = periods.period_ends(deduped, requested, periods.ANNUAL)
    sorted_ends = sorted(fy_ends, reverse=True)[:n_periods]

    # Where to send a reader who wants a value nobody tagged. Built from the
    # payload rather than the resolved series, which keeps only whichever
    # filing reported each period last.
    pointers = xbrl.filing_pointers(facts)

    # The filer's own name for a fiscal year, so a pointer in this view names
    # the same year the single-company table's heading does.
    fy_offset = xbrl.fiscal_year_offset(facts)

    result_items = {}
    for li in wanted:
        info = deduped.get(li) or {}
        tag_used = info.get("tag_used")
        item_flags = all_flags.get(li, [])
        all_dps = info.get("data", [])

        # Which data point covers each confirmed fiscal year: flow items by the
        # span they cover, instants by the date they carry.
        chosen = periods.points_by_end(all_dps, fy_ends, periods.ANNUAL)

        item_periods = []
        for i, end in enumerate(sorted_ends):
            rel_label = "FY0" if i == 0 else "FY-{}".format(i)
            dp = chosen.get(end)
            if dp is None:
                # A value carrying this end date that did not survive the
                # annual filter is not an untagged item, and does not get told
                # it is one.
                tagged = any(other.get("end") == end and other.get("value") is not None
                             for other in all_dps)
                item_periods.append({
                    "relative_period": rel_label,
                    "period_end": end,
                    "period_start": None,
                    "value": None,
                    "source_tag": None,
                    "flags": [],
                    "provenance": xbrl.missing_provenance(
                        li, xbrl.period_label(end, fy_offset=fy_offset), cik,
                        pointers.get(end),
                        xbrl.FLAG_PERIOD_UNRESOLVED if tagged else xbrl.FLAG_NOT_TAGGED),
                })
            else:
                period_flags = [
                    {"flag_type": f["flag_type"], "message": f["message"]}
                    for f in item_flags
                    if f.get("period_end") == end
                ]
                item_periods.append({
                    "relative_period": rel_label,
                    "period_end": end,
                    "period_start": dp.get("start"),
                    "value": dp["value"],
                    "source_tag": dp.get("tag"),
                    "flags": period_flags,
                    "provenance": xbrl.reported_provenance(dp),
                })

        result_items[li] = {"tag_used": tag_used, "periods": item_periods}

    _fill_derived_periods(result_items)
    _explain_underivable_periods(result_items, cik, pointers, fy_offset)
    result_items = {name: info for name, info in result_items.items()
                    if name in requested}

    return {"name": entity, "cik": cik, "line_items": result_items}


def fetch_peer_comparison(ciks, line_items=None, n_periods=3, progress_callback=None):
    """
    Fetch XBRL data for multiple companies sequentially.

    Sequential (not parallel) to respect EDGAR rate limits.  Each company
    requires exactly one API call via xbrl.fetch_company_facts; the 0.1 s
    minimum delay is enforced inside edgar_api._rate_limited_get.

    Args:
        ciks:              list of CIK strings or ints
        line_items:        line items to include; defaults to the displayed set,
                           which is the reported items plus derived Total Debt
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
        line_items = list(_UI_LINE_ITEMS)

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

    Thresholds come from line_items.dollar_scale_for, the same function the
    single-company table uses:
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
        dollar_factor, dollar_label = line_items.dollar_scale_for(max_rev)
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

    if max_shares is not None:
        share_factor, share_label = line_items.share_scale_for(max_shares)
    else:
        share_factor, share_label = line_items.DEFAULT_SHARE_SCALE

    return {
        "dollar_factor": dollar_factor,
        "dollar_label": dollar_label,
        "share_factor": share_factor,
        "share_label": share_label,
    }
