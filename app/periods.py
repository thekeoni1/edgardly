"""periods.py -- which periods a filer reports, and which value covers each one.

One engine, two callers. The single-company table and the peer comparison each
had their own answer to "is this data point the fiscal year 2025 figure?", and
the answers disagreed. The peer path judged a flow item by the length of the
period it covers and accepted a balance-sheet instant whose end date matched a
period the flow items had already confirmed. The single-company path read
EDGAR's fiscal_period label and believed it.

The label cannot be believed. EDGAR stamps fp on the filing rather than on the
fact, so a 10-Q that carries the previous year-end balance sheet as its
comparative column hands that instant the label "Q2", and resolution keeping
the most recently filed entry means the 10-Q's copy is the one that survives.
Honeywell's 2025-12-31 total assets is exactly this: 73,681 million, reported
in the FY2025 10-K, labeled Q2 by the July 2026 10-Q that repeated it. Reading
the label dropped the whole year from the single-company table while the peer
table showed it (PROGRESS.md open question 3, V2_PLAN risk R5).

So dates decide:

  - A flow item covers one period when its start and end are the right distance
    apart. Ten to fourteen months is a fiscal year, which 52/53-week filers and
    year-end changes need it to be; two to four months is a quarter.
  - An instant has no span to measure, so it is anchored instead: an instant
    whose end date is a period end this company has already confirmed is that
    period's balance sheet, whatever any filing called it.

What this engine will not do is invent a period. A date nothing confirms is not
a column, and a value that carries a confirmed end date but covers something
other than the period stays out and is reported as PERIOD_UNRESOLVED rather
than shown. The point is to stop discarding what filers did report, not to
start guessing at what they did not.
"""

import datetime

ANNUAL = "annual"
QUARTERLY = "quarterly"

# A full fiscal year, in days. Wide on purpose: 52/53-week filers land on 364 or
# 371, and a fiscal-year-end change produces a genuine long or short year.
ANNUAL_DAYS = (300, 425)
# One quarter. Wide for the same reason, and to admit the 14-week quarter a
# 53-week year carries.
QUARTER_DAYS = (60, 130)

QUARTER_LABELS = ("Q1", "Q2", "Q3", "Q4")


def span_days(dp):
    """How many days a flow data point covers, or None if it is not a flow.

    An instant has no start, and a malformed date is not a span either. Both
    come back None so callers cannot mistake either for a zero-length period.
    """
    start, end = dp.get("start"), dp.get("end")
    if not start or not end:
        return None
    try:
        return (datetime.date.fromisoformat(end)
                - datetime.date.fromisoformat(start)).days
    except (ValueError, TypeError):
        return None


def is_instant(dp):
    """True for a balance-sheet instant: an end date and no start."""
    return dp.get("start") is None and bool(dp.get("end"))


def window_for(period_type):
    return ANNUAL_DAYS if period_type == ANNUAL else QUARTER_DAYS


def covers_one_period(dp, period_type=ANNUAL):
    """True if a flow data point covers exactly one period of this length.

    This is the test the fiscal_period label cannot do: a 10-K's comparative
    quarters all come back labeled FY, and a nine-month year-to-date column
    inside a 10-Q looks annual to anything reading labels. Instants return
    False; they are not flows and are anchored by period_ends instead.
    """
    days = span_days(dp)
    if days is None:
        return False
    low, high = window_for(period_type)
    return low <= days <= high


def period_ends(deduped, names=None, period_type=ANNUAL):
    """Return {period end date: period label} for the periods a filer confirms.

    A period is confirmed by either of two witnesses:

      - a flow item covering the right span of days, whatever it is labeled
      - an instant the filer itself labeled as this period

    The second is what gets the first fiscal year of a company's XBRL history
    onto the table when no flow item reaches back that far, and it is safe
    because it takes the filer's own label rather than overriding it. Instants
    that were labeled by some other filing are picked up by points_by_end,
    which only has to match a date once some other item has confirmed it.

    names limits which line items may witness a period; it defaults to every
    item in the dict. Ordering is not significant except for the label of a
    quarter, where the first witness names it.
    """
    if names is None:
        names = list(deduped)

    ends = {}
    for name in names:
        info = deduped.get(name) or {}
        for dp in info.get("data", []):
            end = dp.get("end")
            if not end:
                continue
            fp = dp.get("fiscal_period")
            if period_type == ANNUAL:
                if is_instant(dp):
                    if fp == "FY":
                        ends.setdefault(end, "FY")
                elif covers_one_period(dp, ANNUAL):
                    ends.setdefault(end, "FY")
            else:
                if fp not in QUARTER_LABELS:
                    continue
                if is_instant(dp) or covers_one_period(dp, QUARTERLY):
                    ends.setdefault(end, fp)
    return ends


def points_by_end(data_points, ends, period_type=ANNUAL):
    """Pick the one data point that covers each confirmed period.

    ends is any container of period end dates, usually the keys of period_ends
    narrowed to the years a view displays.

    Where a filer reports more than one candidate for the same end date, the
    longest span wins: a full year beats the nine-month year-to-date column
    that ends on the same day. Instants have no span and there is only ever one
    of them per date after deduplication, so the rule never has to arbitrate
    between two balance sheets.

    A data point whose end date is confirmed but whose span belongs to some
    other period is left out. It is not the period's value, and the caller
    reports that absence as PERIOD_UNRESOLVED rather than as an untagged item.
    """
    chosen = {}
    for dp in data_points:
        end = dp.get("end")
        if not end or end not in ends:
            continue
        if not is_instant(dp) and not covers_one_period(dp, period_type):
            continue
        incumbent = chosen.get(end)
        if incumbent is None or (span_days(dp) or 0) > (span_days(incumbent) or 0):
            chosen[end] = dp
    return chosen
