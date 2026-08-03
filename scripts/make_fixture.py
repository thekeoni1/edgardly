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

import line_items                                  # noqa: E402
import xbrl_extractor as xbrl                      # noqa: E402

FIXTURE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "tests", "fixtures")
)

# Taxonomies kept whole. dei carries the entity metadata later phases need and
# is small. An IFRS filer's fixture needs --keep-taxonomy ifrs-full.
DEFAULT_KEEP_WHOLE = ("dei",)


def registry_tags():
    """Every us-gaap tag the registry can read, sorted."""
    tags = set()
    for item in line_items.REGISTRY.values():
        tags.update(item.tags)
    tags.update(line_items.DA_COMPONENT_TAGS)
    return sorted(tags)


def trim(payload, tags, keep_whole):
    """Return a copy of a companyfacts payload holding only the wanted tags.

    us-gaap is filtered to *tags*. Taxonomies named in *keep_whole* survive
    intact. Any other taxonomy is dropped, but its name is recorded in the
    _fixture block so a reader can tell the difference between "this filer had
    no ifrs-full facts" and "the fixture script left them out".
    """
    facts = payload.get("facts", {})
    kept_facts = {}

    us_gaap = facts.get("us-gaap", {})
    kept_facts["us-gaap"] = {tag: us_gaap[tag] for tag in tags if tag in us_gaap}

    for taxonomy in keep_whole:
        if taxonomy in facts and taxonomy != "us-gaap":
            kept_facts[taxonomy] = facts[taxonomy]

    dropped = sorted(set(facts) - set(kept_facts))

    trimmed = {key: value for key, value in payload.items() if key != "facts"}
    trimmed["facts"] = kept_facts
    return trimmed, dropped


def summarize(trimmed, tags, dropped, url):
    """Describe what the trim kept and what it threw away."""
    us_gaap = trimmed["facts"].get("us-gaap", {})
    return {
        "generator": "scripts/make_fixture.py",
        "source_url": url,
        "retrieved": datetime.date.today().isoformat(),
        "trimmed_to": "us-gaap tags in the app/line_items.py registry",
        "registry_tags_requested": len(tags),
        "registry_tags_present": len(us_gaap),
        "registry_tags_absent": sorted(set(tags) - set(us_gaap)),
        "taxonomies_kept": sorted(trimmed["facts"]),
        "taxonomies_dropped": dropped,
    }


def make_fixture(cik, out_path=None, keep_whole=DEFAULT_KEEP_WHOLE):
    """Download, trim, and write one fixture. Returns the path written."""
    cik_str = str(int(cik)).zfill(10)
    url = "{}/companyfacts/CIK{}.json".format(xbrl.XBRL_BASE, cik_str)

    print("fetching {}".format(url))
    payload = xbrl.fetch_company_facts(cik)

    tags = registry_tags()
    trimmed, dropped = trim(payload, tags, keep_whole)
    trimmed["_fixture"] = summarize(trimmed, tags, dropped, url)

    if out_path is None:
        out_path = os.path.join(FIXTURE_DIR, "cik{}.json".format(int(cik)))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # Compact and key-sorted: a fixture is read by tests, not by people, and a
    # stable byte order keeps regeneration diffs to the numbers that changed.
    text = json.dumps(trimmed, sort_keys=True, separators=(",", ":"))
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(text)

    summary = trimmed["_fixture"]
    print("{}: {} of {} registry tags, {:.1f} KB".format(
        payload.get("entityName", cik_str),
        summary["registry_tags_present"], summary["registry_tags_requested"],
        len(text) / 1024.0,
    ))
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
