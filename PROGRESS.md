# Edgardly v2 progress

Running state for the v2 build. docs/V2_PLAN.md is the plan and the single source of truth.
docs/SESSIONS.md holds the session prompts. This file records what actually happened.

## Decisions log

Settled decisions. A later session should not re-litigate these; if one turns out to be
wrong, change it here with a dated note saying why.

| Date | Decision | Detail |
| --- | --- | --- |
| 2026-08-03 | Plug rows are explicit derived formulas | Where tagged components do not sum to the reported total, the scaffold writes a visible plug row such as "Other current assets (plug to reported total)" as a live Excel formula. Never a filled number, never a silent guess. Any plug whose absolute value exceeds 10 percent of its statement total raises a flag saying this filer's XBRL is too sparse for a reliable scaffold. |
| 2026-08-03 | Test suite is restored to the public repo | Commit 4e1d457 removed app/tests and app/pytest.ini in June 2026 with no stated rationale, and git history was the only surviving copy. Every later phase is gated on tests, so the suite lives with the code. |
| 2026-08-03 | The registry holds 38 reported items, not 28 | V2_PLAN 1.1 said 28 but the list underneath it enumerates 38: 14 income statement, 16 balance sheet, 8 cash flow. The enumeration is the specification and the count was simply wrong, so both mentions in V2_PLAN now read 38. No item was added or dropped to reach the number. |
| 2026-08-03 | Per-period resolution prefers chain position, then filing date | For a period reported by more than one tag in a chain, the earlier tag wins; within one tag, the most recently filed entry wins. Filing date does not outrank chain position, because chain order encodes which tag means what, and a later filing is often just a comparative in someone else's 10-K. Checked on Apple: every period where two revenue tags overlap, the two agree to the dollar, so the rule restates nothing. |
| 2026-08-03 | The browser is served its classification by template injection | Not a fetch endpoint. The peer checkbox grid is built during page setup, so a request still in flight would render an empty grid. |
| 2026-08-03 | A derived value needs reported inputs, same period, same unit | Anything else stays missing. No derivation is ever built on another derivation, on a value from a neighbouring period, or across units. This is what keeps "derived" a claim a reader can check rather than a chain of inference. |
| 2026-08-03 | Missing carries two flags, not one | NOT_TAGGED means the filer never tagged the item for the period. PERIOD_UNRESOLVED means a value with that end date exists but no filter could confirm it covers the period, which is what R5 shadowing produces. Telling a reader "not tagged in XBRL" when the filer did tag it would be a false statement, and the two cases warrant different levels of suspicion. |
| 2026-08-03 | Filing pointers are read from the payload, never from a resolved series | Resolution keeps one entry per period per tag, the most recently filed. Pointed at that, a missing FY2023 value cites the FY2024 10-K, which reported FY2023 only as a comparative. The pointer needs the filings resolution discarded. |

## Session log

One entry per work session. Record what shipped, the xfail count after the session, and any
open questions the next session needs to know about.

| Date | Session | Shipped | xfails | Open questions |
| --- | --- | --- | --- | --- |
| 2026-08-03 | Setup | Folded the planning output into the repo: risk register R1 through R10 as V2_PLAN Part 8, decisions log as Part 9, tasks 2.2b and 2.5 added to Phase 2, docs/SESSIONS.md created, this file created. Documentation only, no code changes. | n/a | None |
| 2026-08-03 | 1 | F1 through F5, five commits in the prescribed order. README claims corrected, real SEC User-Agent contact, test suite restored from git history, Total Debt relabeled Long-Term Debt, line-item constants consolidated into app/line_items.py. | 0 | Three, listed below. |
| 2026-08-03 | 2 | V2_PLAN 1.1, 1.2, part of 1.5, and the frontend half of the Session 1 consolidation. Five commits: session prompt amended, registry built, per-period stitching, fixture generator plus the Apple fixture, classification served to the browser. | 0 | Open question 2 closed; 1 and 3 still open; two new ones. |
| 2026-08-03 | 3 | V2_PLAN 1.3 and 1.4, and the rest of 1.5. Four commits: session prompt amended, fixture generator extended plus the JPMorgan and SAP fixtures, provenance and the scope gate, tooltip element moved. | 0 | Open question 5 closed, 3 partly addressed; 1, 3, and 4 still open; one new one. |

### Session 1 detail

Suite state: 307 tests, all passing. 261 mocked tests run offline in about 4
seconds; 46 integration tests hit live EDGAR or start a browser and take about 46
seconds. Zero xfails were needed. The suite came back from commit 4e1d457 with 291
tests; the 16 new ones cover app/line_items.py.

Test triage found one genuine drift and two timing fragilities, all fixed rather
than deferred:

- test_step1 requested the homepage on port 5000. Commit 6073aec moved the app to
  5050 after the June deletion, so the test waited out its timeout against a
  server answering elsewhere. This is precisely the R7 drift the risk register
  anticipated, and it was the only instance.
- test_fmt_passed_to_download_filing passed fmt='pdf', which makes
  download_filings_batch open a real Chromium. The test checks argument
  forwarding, so the Playwright boundary is now patched as it is in every
  neighboring test. This also lets the mocked suite run in a sandbox, where a
  browser launch hangs outright.
- Cold Chromium startup on this machine takes about 26 seconds, against the
  suite's 30 second default timeout, so the three page-break tests in test_step11
  failed intermittently. Each now carries an explicit 90 second timeout, matching
  what test_download_html_integration already did.

Long-Term Debt was verified against live EDGAR for all three acceptance companies.
Apple resolves via LongTermDebtNoncurrent and FY2023 comes back as 95,281 million,
matching the 10-K. Kroger also resolves via LongTermDebtNoncurrent. Honeywell has
no LongTermDebtNoncurrent at all and falls back to LongTermDebt.

The User-Agent contact is thekeoni@gmail.com, the address already published in
this repository's commit history and matching the GitHub account, rather than a
new address the repo had never carried.

### Session 2 detail

Suite state: 370 tests, all passing, zero xfails. Session 1 left 307. The 63 new
tests are 19 for the registry, 15 for per-period resolution on synthetic
payloads, and 29 against the Apple fixture.

The registry ships all 38 items V2_PLAN 1.1 enumerates, and every chain resolves
against Apple except the thirteen tags Apple does not report at all. All 14
displayed FY2023 values match the FY2023 10-K to the dollar, as do the cash flow
items no view shows yet, and the balance sheet balances exactly rather than
within the 5 percent tolerance the sanity check allows.

Per-period stitching did what it was meant to and nothing else. Apple's revenue
row runs FY2007 to FY2025 across three tag eras, where winner-takes-all started
it at FY2017. Comparing the two resolvers over all 14 items on the live payload:
19 years gained on Revenue, one on Long-Term Debt, none lost anywhere, and not a
single value changed. The 2010 10-K/A that restated Apple's FY2007 revenue from
24,006 to 24,578 million still wins, because latest-filed still decides within a
tag.

Judging which periods are annual turned out to be the subtle part. EDGAR stamps
fiscal_period on the filing, not on the fact, so every comparative quarter inside
a 10-K comes back labeled FY. Filtering on that label alone left Apple's FY2018
and FY2019 rows non-adjacent in the sorted series, with quarterly entries between
them, and the seam flag never fired. Full-year flows are now identified by a 10
to 14 month span, the same test peer_comparison already used.

The fixture is 1.1 MB against 3.8 MB live. Trimming is by tag only: no period,
amendment, or unit inside a kept tag is touched, so the fixture can differ from
the live API about which line items are present but never about a number. That
matters more than a smaller file, because dropping filings would change what
deduplication sees, which is exactly the R5 shadowing behavior Session 4 has to
reproduce.

The FY2018 revenue transition the session prompt names is real but sits one year
off from where the prose implied. Apple's post-ASC-606 tag carries FY2017 and
FY2018 as comparatives, so the old resolver truncated at FY2017, not FY2018, and
the seam in the stitched series falls on FY2019, the first year reported only
under the new tag. Both tags report FY2017 and FY2018 identically, so nothing
was restated by preferring chain position.

### Session 3 detail

Suite state: 438 tests, all passing, zero xfails. Session 2 left 370. The 68 new
tests are 20 for the provenance primitives and the payloads, 34 for the scope gate
and the two new fixtures, 9 more in the Apple real-filing module, 4 for the font
split and the Source Tags sheet in the single-company export, and 1 for the peer
export's.

Provenance is per value, and Apple demonstrates why that matters. Displayed from
FY2015 to FY2025, the revenue row is stitched from three tags, and each cell names
its own: SalesRevenueNet for FY2015, Revenues for FY2018, the ASC 606 tag from
FY2019. The row label under the line item name now reads all three, the Source Tags
sheet gives one line per value rather than one per row, and the seam is marked on
FY2019 where the tag changes. That is open question 5 closed.

Of Apple's 154 displayed values, 147 are reported and 7 are holes. All seven are
balance-sheet instants whose fiscal-period label a later 10-Q overwrote, which is
open question 3 showing up in the single-company table exactly as predicted. This
is why the missing state has two flags: saying "not tagged in XBRL" about Apple's
FY2025 total assets would be false, because Apple tagged it and this table's fp
filter dropped it. Those cells now say so and point at the filing. Session 4 makes
them disappear rather than explaining themselves.

Gross Profit is the first value either table has ever derived. Apple never exercises
it, since Apple tags GrossProfit itself; a filer that does not gets Revenue minus
Cost of Revenue, black rather than blue, italic in the browser, with the formula and
both input tags in the tooltip and on the Source Tags sheet. Both the single-company
and the peer path apply the identical rule so the two views cannot disagree.

The scope gate ships with two real filers behind it. JPMorgan Chase, CIK 19617,
SIC 6021, is refused by the SIC range; its statement-shape heuristic stays quiet
because JPMorgan does tag Revenues, so only the deterministic gate fires, which is
the honest outcome. SAP SE, CIK 1000184, SIC 7372, is a software company the SIC
gate would happily accept and is refused only because it reports no us-gaap facts at
all. Both CIKs were confirmed against the live ticker lookup before use. The heuristic
itself is exercised synthetically, because a correctly classified bank cannot test a
misclassification.

Neither refusal touches the puller. JPMorgan's FY2023 table still loads with total
assets of 3,875,393 million, and its balance sheet ties to the dollar. SAP's table
is still empty, but it now says why instead of suggesting a wider year range.

Three things turned up that the plan did not anticipate:

- Filing pointers cannot be built from resolved data. Resolution keeps one entry per
  period per tag, so Apple's FY2023 pointer came back naming the FY2024 10-K, which
  carried FY2023 only as a comparative. Reading the payload directly fixes it, and
  the pointers now name each period's own filing.
- The trim was inventing an empty us-gaap block for filers that have none, which read
  to the gate as a us-gaap filer with nothing tagged. SAP came back in scope on the
  first attempt. Both the trim and the gate now treat an empty taxonomy as absent.
- The tooltip element sat after the script that looks it up, so it had always been
  null and no tooltip in the app had ever rendered. Found by driving the real page
  against the fixtures rather than trusting the tests, which never touch it.

That check ran the actual UI offline against the committed fixtures: all three
provenance states reach the screen, the IFRS refusal replaces the empty-table
message, and the browser console is clean.

The first full-suite run of the session hit the cold-Chromium timeout Session 1
documented; the rerun was clean and every later run has been.

## Open questions

1. **LongTermDebt is not strictly non-current.** Honeywell resolves the Long-Term
   Debt row through the us-gaap LongTermDebt tag, whose definition can include
   current maturities, so for that filer the row is slightly broader than its
   label. Session 2 wrote the caveat into the registry entry itself, where anyone
   editing the chain will see it, and into the Total Debt derivation note, since
   summing a LongTermDebt row with Short-Term Debt double-counts the current
   maturities. The Apple fixture cannot settle it: Apple reports
   LongTermDebtNoncurrent, so it never exercises the fallback. Still needs the
   Honeywell fixture in Session 4.

2. **Closed.** app/templates/index.html no longer carries its own DOLLAR_ITEMS,
   EPS_ITEMS, SHARE_ITEMS, or ALL_LINE_ITEMS. The homepage injects
   line_items.classification_for_client() and the page builds its sets from that.
   A test reads the template source and fails if a hardcoded list reappears.

3. **R5 shadowing is confirmed live, not theoretical.** Honeywell's 2025-12-31
   year-end balance sheet instant carries fiscal_period "Q2" because a later 10-Q
   overwrote the label, so the single-company path drops recent years that the
   peer path keeps. Session 4 is where this gets fixed; noting it here as
   confirmation the risk is real and reproducible with CIK 773840. Session 3
   found the same thing in the Apple fixture: seven of the fourteen displayed
   rows lose a balance-sheet year to it, including FY2025 total assets. Those
   cells are no longer silent. They carry the PERIOD_UNRESOLVED flag, which says
   the value is tagged but could not be confirmed to cover the period, and they
   point at the filing. That is a description of the bug, not a fix for it.

4. **Short-Term Debt understates for filers that skip DebtCurrent.** Apple tags
   no DebtCurrent, so the row falls through to LongTermDebtCurrent, which is
   current maturities only, and misses the 5,985 million of commercial paper on
   the FY2023 balance sheet. The derived Total Debt is short by exactly that
   amount: 105,103 million against a real 111,088 million. A test asserts both
   figures rather than hiding the gap. Closing it needs a summed derivation
   (current maturities plus commercial paper plus short-term borrowings), not a
   chain reorder, because a chain picks one tag and the components have to add.
   Decide in Session 4 alongside the other chain corrections. Until then, no view
   shows Total Debt, so nothing user-facing is wrong today. Session 3 kept it that
   way deliberately and left a test that fails the moment Total Debt appears in a
   payload, so the next session has to fix the derivation before surfacing it.

5. **Closed.** The Excel Source Tags sheet is one line per value, in both the
   single-company and the peer workbook: line item, period, state, tag, filed
   date, accession, and a note carrying the derivation formula, the missing
   pointer, or the TAG_TRANSITION seam. The row-level Source Tag column, which is
   all the CSV can hold, now names every tag the row used in period order rather
   than one standing in for all of them.

6. **A proxy statement outranks the 10-K it restates nothing in.** Three JPMorgan
   10-Ks report FY2023 net income as 49,552 million. A DEF 14A filed in April 2026
   repeats the same period rounded to 49,600 million, and because deduplication
   keeps the most recently filed entry, the proxy wins. Five years of the row are
   affected the same way. The rule was written for 10-K/A restatements, where a
   later filing genuinely is better information; a proxy statement is not a
   restatement. The fix is to rank annual report forms above everything else
   before falling back to filing date, in both resolve_line_item and
   deduplicate_period. It was left alone in Session 3 because changing resolution
   semantics moves numbers for every company and belongs with the period-engine
   work and the full fixture validation in Session 4. A test in
   test_scope_gate.py asserts both figures, so the change announces itself.
