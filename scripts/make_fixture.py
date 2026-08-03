"""make_fixture.py -- build a trimmed companyfacts fixture for the test suite.

Downloads one company's XBRL companyfacts payload from EDGAR and strips it to
the tags the line-item registry actually reads, so the committed fixture is a
fraction of the original and the tests that use it stay network-free.

    python scripts/make_fixture.py 320193
    python scripts/make_fixture.py 320193 --out app/tests/fixtures/apple.json
    python scripts/make_fixture.py 1000184 --keep-taxonomy ifrs-full

Nothing inside a kept tag is touched: every reported period, every amendment,
every unit comes across exactly as EDGAR served it. Trimming is by tag only, so
a fixture can never disagree with the live API about a number, only about which
line items are present.

The fixture also records the company's SIC code, which the scope gate needs and
companyfacts does not carry. It comes from a second endpoint, the submissions
API, so a fixture is two downloads rather than one.

Regeneration is reproducible: run the same command and the output is
byte-identical apart from the retrieval date in the _fixture block.
"""

import argparse
import datetime
import json
import os
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")
sys.path.insert(0, os.path.abspath(APP_DIR))

import edgar_api                                   # noqa: E402
import line_items                                  # noqa: E402
import xbrl_extractor as xbrl                      # noqa: E402

FIXTURE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "tests", "fixtures")
)

# Taxonomies kept whole. dei carries the entity metadata later phases need and
# is small. Pass --keep-taxonomy to add one, for instance to keep an IFRS
# filer's ifrs-full facts entire rather than trimmed to the probe tags below.
DEFAULT_KEEP_WHOLE = ("dei",)

# Enough of the ifrs-full taxonomy to prove a filer really does report under
# IFRS, and no more. Edgardly reads no IFRS tags, so a fixture that carried all
# of them would be storing hundreds of facts nothing can use; the scope gate
# only needs to see that the taxonomy is there and us-gaap is not. A fixture
# trimmed this way cannot be used to judge IFRS coverage, and its _fixture
# block says so.
IFRS_PROBE_TAGS = (
    "Assets", "CashAndCashEquivalents", "CostOfSales", "Equity", "GrossProfit",
    "Liabilities", "ProfitLoss", "Revenue",
)


def registry_tags():
    """Every us-gaap tag the extraction layer can read, sorted.

    Wider than the registry's own chains: the D&A component fallback and the
    scope gate's statement-shape heuristic both read tags no line item lists.
    """
    tags = set()
    for item in line_items.REGISTRY.values():
        tags.update(item.tags)
    tags.update(line_items.DA_COMPONENT_TAGS)
    tags.update(line_items.SCOPE_HEURISTIC_TAGS)
    return sorted(tags)


def wanted_tags():
    """Map each trimmed taxonomy to the tags kept from it."""
    return {"us-gaap": registry_tags(), "ifrs-full": sorted(IFRS_PROBE_TAGS)}


def trim(payload, wanted, keep_whole):
    """Return a copy of a companyfacts payload holding only the wanted tags.

    Each taxonomy named in *wanted* is filtered to its tag list. Taxonomies
    named in *keep_whole* survive intact and are not filtered. Any other
    taxonomy is dropped, but its name is recorded in the _fixture block so a
    reader can tell the difference between "this filer had no ifrs-full facts"
    and "the fixture script left them out".
    """
    facts = payload.get("facts", {})
    kept_facts = {}

    for taxonomy, tags in wanted.items():
        if taxonomy in keep_whole or taxonomy not in facts:
            continue
        # A taxonomy the filer does not use must stay absent rather than become
        # an empty block: the scope gate reads "no us-gaap facts" as a fact
        # about the filer, and an empty dict would hide it.
        available = facts[taxonomy]
        kept_facts[taxonomy] = {tag: available[tag] for tag in tags if tag in available}

    for taxonomy in keep_whole:
        if taxonomy in facts:
            kept_facts[taxonomy] = facts[taxonomy]

    dropped = sorted(set(facts) - set(kept_facts))

    trimmed = {key: value for key, value in payload.items() if key != "facts"}
    trimmed["facts"] = kept_facts
    return trimmed, dropped


def company_meta(cik):
    """Fetch the SIC code and filer category from the submissions API.

    A separate endpoint from companyfacts, and the only place the SIC code
    exists, so the scope gate cannot be tested offline without it. A failure
    here is recorded rather than raised: a fixture with no SIC is still a
    usable fixture for everything else.
    """
    try:
        return dict(edgar_api.get_company_meta(cik) or {})
    except Exception as exc:                       # noqa: BLE001 -- reported, not swallowed
        print("could not fetch company metadata: {}".format(exc))
        return {"error": str(exc)}


def summarize(trimmed, wanted, dropped, url, meta):
    """Describe what the trim kept and what it threw away."""
    us_gaap = trimmed["facts"].get("us-gaap", {})
    requested = wanted["us-gaap"]
    return {
        "generator": "scripts/make_fixture.py",
        "source_url": url,
        "retrieved": datetime.date.today().isoformat(),
        "trimmed_to": "us-gaap tags read by app/line_items.py; ifrs-full to probe tags only",
        "registry_tags_requested": len(requested),
        "registry_tags_present": len(us_gaap),
        "registry_tags_absent": sorted(set(requested) - set(us_gaap)),
        "ifrs_probe_tags": sorted(trimmed["facts"].get("ifrs-full", {})),
        "taxonomies_kept": sorted(trimmed["facts"]),
        "taxonomies_dropped": dropped,
        "company": meta,
    }


def make_fixture(cik, out_path=None, keep_whole=DEFAULT_KEEP_WHOLE):
    """Download, trim, and write one fixture. Returns the path written."""
    cik_str = str(int(cik)).zfill(10)
    url = "{}/companyfacts/CIK{}.json".format(xbrl.XBRL_BASE, cik_str)

    print("fetching {}".format(url))
    payload = xbrl.fetch_company_facts(cik)
    meta = company_meta(cik)

    wanted = wanted_tags()
    trimmed, dropped = trim(payload, wanted, keep_whole)
    trimmed["_fixture"] = summarize(trimmed, wanted, dropped, url, meta)

    if out_path is None:
        out_path = os.path.join(FIXTURE_DIR, "cik{}.json".format(int(cik)))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # Compact and key-sorted: a fixture is read by tests, not by people, and a
    # stable byte order keeps regeneration diffs to the numbers that changed.
    text = json.dumps(trimmed, sort_keys=True, separators=(",", ":"))
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(text)

    summary = trimmed["_fixture"]
    print("{}: {} of {} registry tags, SIC {}, {:.1f} KB".format(
        payload.get("entityName", cik_str),
        summary["registry_tags_present"], summary["registry_tags_requested"],
        summary["company"].get("sic") or "unknown",
        len(text) / 1024.0,
    ))
    if summary["ifrs_probe_tags"]:
        print("ifrs-full present, trimmed to probe tags: {}".format(
            ", ".join(summary["ifrs_probe_tags"])))
    if summary["registry_tags_absent"]:
        print("not reported by this filer: {}".format(
            ", ".join(summary["registry_tags_absent"])))
    print("wrote {}".format(out_path))
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cik", help="company CIK, with or without leading zeros")
    parser.add_argument("--out", default=None,
                        help="output path (default: app/tests/fixtures/cik<CIK>.json)")
    parser.add_argument("--keep-taxonomy", action="append", default=None,
                        metavar="NAME",
                        help="keep this taxonomy whole instead of dropping it; "
                             "repeatable. Defaults to {}".format(", ".join(DEFAULT_KEEP_WHOLE)))
    args = parser.parse_args(argv)

    keep_whole = tuple(args.keep_taxonomy) if args.keep_taxonomy else DEFAULT_KEEP_WHOLE
    make_fixture(args.cik, args.out, keep_whole)
    return 0


if __name__ == "__main__":
    sys.exit(main())
