"""generate_acceptance.py -- build the three acceptance workbooks and print the checklist.

    python scripts/generate_acceptance.py
    python scripts/generate_acceptance.py --years 5 --out app/exports/acceptance
    python scripts/generate_acceptance.py --live
    python scripts/generate_acceptance.py --only kroger

Apple, Honeywell and Kroger, the three filers V2_PLAN Part 4 puts in the
acceptance set, each built through POST /api/scaffold/three-statement rather
than by calling the scaffold library. That is deliberate: the hand-check is the
gate on what a user gets, and what a user gets comes through the endpoint. A
workbook built any other way could pass a check the app would fail.

By default the payloads come from the committed fixtures, so this runs with no
network and produces the same file twice. A fixture is trimmed by tag and never
by period, amendment or unit, so it cannot disagree with the live API about a
number, only about which line items are present. Pass --live to go to EDGAR
instead.

Nothing this writes is committed. The workbooks are working copies for the
hand-check; docs/acceptance/3s_checklist.md and docs/acceptance/breakage_log.md
are the record that survives.
"""

import argparse
import datetime
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
APP_DIR = os.path.join(ROOT, "app")
sys.path.insert(0, APP_DIR)

FIXTURE_DIR = os.path.join(APP_DIR, "tests", "fixtures")
CHECKLIST = os.path.join(ROOT, "docs", "acceptance", "3s_checklist.md")

# CIK and the SIC the submissions API reports, which companyfacts does not carry
# and the scope gate needs. Kept here rather than read from the fixture so the
# live path needs no special case.
COMPANIES = (
    ("apple", 320193, "Apple Inc.", "AAPL"),
    ("honeywell", 773840, "Honeywell International Inc.", "HON"),
    ("kroger", 56873, "The Kroger Co.", "KR"),
)


def _use_fixtures():
    """Serve the committed payloads instead of EDGAR, for both lookups."""
    import edgar_api
    import xbrl_extractor as xbrl

    def facts(cik):
        path = os.path.join(FIXTURE_DIR, "cik{}.json".format(int(str(cik).strip())))
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def meta(cik):
        return {"sic": facts(cik).get("_fixture", {}).get("company", {}).get("sic")}

    xbrl.fetch_company_facts = facts
    edgar_api.get_company_meta = meta


def _checklist_section(name):
    """One company's copy of the checklist, read out of the document itself.

    Printed rather than rewritten, so there is one checklist and the thing on
    screen cannot drift away from the thing in the repo.
    """
    if not os.path.exists(CHECKLIST):
        return "docs/acceptance/3s_checklist.md not found."
    with open(CHECKLIST, encoding="utf-8") as handle:
        text = handle.read()
    marker = "## Copy"
    for block in text.split(marker)[1:]:
        if name.lower() in block.split("\n", 1)[0].lower():
            return (marker + block).rstrip()
    return "No copy for {} in the checklist.".format(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, default=5,
                        help="historical years per workbook (default 5)")
    parser.add_argument("--forecast-years", type=int, default=3,
                        help="blank forecast columns per workbook (default 3)")
    parser.add_argument("--out", default=os.path.join(APP_DIR, "exports", "acceptance"),
                        help="where the workbooks go (gitignored by default)")
    parser.add_argument("--live", action="store_true",
                        help="fetch from EDGAR instead of the committed fixtures")
    parser.add_argument("--only", help="one company by short name")
    parser.add_argument("--quiet", action="store_true",
                        help="skip printing the checklist copies")
    args = parser.parse_args(argv)

    if not args.live:
        _use_fixtures()

    import app as flask_app

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    flask_app.EXPORTS_DIR = out
    client = flask_app.app.test_client()

    wanted = [c for c in COMPANIES if not args.only or c[0] == args.only.lower()]
    if not wanted:
        parser.error("no company called {}".format(args.only))

    built = []
    for short, cik, name, ticker in wanted:
        response = client.post("/api/scaffold/three-statement", json={
            "cik": str(cik), "years": args.years,
            "forecast_years": args.forecast_years, "format": "xlsx"})
        payload = response.get_json()
        if response.status_code != 200:
            print("{}: REFUSED ({}) {}".format(name, response.status_code,
                                               payload.get("error")))
            continue
        path = os.path.join(out, os.path.relpath(
            payload["download_url"][len("/exports/"):]).replace("/", os.sep))
        built.append((short, cik, name, ticker, payload, path))
        print("{}: {} ({:,} bytes)".format(name, path, os.path.getsize(path)))
        print("   {} historical: {}".format(len(payload["historical"]),
                                            ", ".join(payload["historical"])))
        print("   {} forecast:   {}".format(len(payload["forecast"]),
                                            ", ".join(payload["forecast"])))
        for flag in payload["flags"]:
            print("   [{}] {}".format(flag["flag_type"], flag["message"]))

    if args.quiet or not built:
        return 0

    today = datetime.date.today().isoformat()
    for short, cik, name, ticker, payload, path in built:
        print("\n" + "=" * 78)
        print("    Company:            {}".format(name))
        print("    Ticker / CIK:       {} / {}".format(ticker, cik))
        print("    Scaffold file:      {}".format(path))
        print("    Generated on:       {}{}".format(
            today, "" if args.live else "  (from the committed fixture)"))
        print("    Years in workbook:  {} historical, {} forecast".format(
            len(payload["historical"]), len(payload["forecast"])))
        print("=" * 78 + "\n")
        print(_checklist_section(name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
