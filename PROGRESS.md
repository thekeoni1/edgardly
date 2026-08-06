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
| 2026-08-04 | An annual report outranks every other form for the same period | Amends the 2026-08-03 entry above, which said filing date decides within a tag. Rank decides first: 10-K, 10-KT, 10-K405, 10-KSB, 20-F and 40-F, with or without an /A suffix, beat any other form reporting the same period. Filing date still decides inside the rank, so a 10-K/A restatement still beats the 10-K it amends. A 10-Q comparative, an 8-K earnings release and a DEF 14A proxy repeat an annual figure; repeating it is not reporting it, and the repetition is often rounded or recast. Chain position is untouched and still outranks both. |
| 2026-08-04 | A derivation may stand on one other derivation, never two | Amends the 2026-08-03 entry above, which said no derivation is ever built on another. Total Debt is the sum of a long-term balance a filer tags and a short-term balance that most filers do not: Apple, Honeywell, Kroger and JPMorgan all report the current debt lines and none of them reports the total. Stating that in one step is impossible, because whether the short-term side is one reported tag or a sum of components is exactly what varies. So an input may be a value already derived from reported values of the same period, and no deeper: every leaf is still a number a filer tagged, the provenance carries the nested formula and the nested inputs, and the tooltip shows the whole descent. The rest of the 2026-08-03 rule is untouched -- same period, same unit, no neighbouring periods. |
| 2026-08-04 | One derivation may have optional terms, and only for a sum of separately reported lines | Every other rule needs every input: gross profit without a cost of revenue is unknown, not equal to revenue. Short-Term Debt is a sum of three current-liability lines, and a filer carries the ones it has. Apple shows term debt and commercial paper, Honeywell current maturities and one combined borrowings line, Kroger current maturities alone. An absent term there is a line the balance sheet does not have, not a number nobody knows. At least one term must be present, so a total of nothing stays missing rather than becoming zero, and the formula that ships with each value names only the terms that were added. |
| 2026-08-04 | Periods are decided by dates, never by the fiscal_period label | Both views run on app/periods.py. A flow item covers a period when its span is 10 to 14 months (a year) or 2 to 4 months (a quarter); an instant, having no span, is anchored to a period some measurable item already confirmed. EDGAR stamps fp on the filing rather than the fact, so the label describes whoever filed last, not the fact. Nothing invents a period: a value carrying a confirmed end date that covers something else is reported as PERIOD_UNRESOLVED, not shown. |
| 2026-08-04 | A fiscal year is named by the filer's convention, not by its own year's focus value | The name comes from dei DocumentFiscalYearFocus, but what is read from it is the offset between a filing's focus and the calendar year of its own year end, with the commonest offset winning across the filer's annual filings. Face value does not work: Kroger tagged focus 2025 on two consecutive years and Honeywell tagged 2020 on its 2021 annual report, so year-by-year reading puts two columns under one name, and no focus value at all exists for the comparative years a company's first XBRL filing carried. An offset of zero is exactly the old end-year rule, which is also the fallback where a payload names no fiscal year. A filer that changes its fiscal year end changes its convention with it and would need more than one number; none in the acceptance set does. |
| 2026-08-05 | A plug is measured against the total it plugs to | The decisions log's "10 percent of its statement total" is read as the subtotal the plug ties to, not the statement's headline total. A subtotal is never larger than the statement it sits in, so this is the stricter of the two readings, and it names something a reader can act on: "this plug is 32 percent of total current assets" says which section not to trust, where a share of total assets does not. Both readings flag Apple's balance sheet everywhere, so this is not a choice that was made to change an outcome. |
| 2026-08-05 | A forecast cell needs an assumption, an anchor, or neither and then nothing | Three rules, settled together because they are one idea. A row whose assumption column is incomplete produces nothing, enforced by a readiness cell per year that requires that year's inputs and every earlier year's, so a blank Assumptions sheet gives blank forecasts rather than zeros. A row that would have to start from a hole in the last reported column gets no forecast and says which input was missing, because a forecast built on a hole is a guess with a formula in front of it. And a row the filer does not tag in any year of the model gets no forecast either, but for the opposite reason: it is not a hole, whatever it holds is already inside a plug that is carried forward, and modelling it separately would count it twice. The third rule is also what keeps the forecast balance sheet tying, because the cash flow statement's working capital line has to see the same movement the balance sheet does. |
| 2026-08-05 | A quarter is named for the fiscal year it belongs to | The year on a quarter label is the year of the fiscal year the quarter sits inside, which is the first confirmed year end at or after it, named by the same offset a fiscal year is named by. Kroger's fourth quarter ending 31 January 2026 reads Q4 FY2025 and no longer reads "Q4 2026" beside an annual column for the same date reading FY2025; Apple's quarter ending 28 December 2024 reads Q1 FY2025 rather than "Q1 2024", because Apple's first quarter ends the December before its September year end. The calendar year of the end date was the old rule and was wrong for both filers in opposite directions. A quarter in a year that has not closed is placed by projecting the filer's own year length forward, and a quarter with no confirmed year end anywhere keeps the calendar year of its end date, which is the old rule as a fallback. Labels only: no annual label, no value, and no provenance record moves. |
| 2026-08-05 | The balance sheet reports coverage where the other two statements warn | Amends the 2026-08-03 plug entry above, which raised a flag on any plug over 10 percent of the total it plugs to. The threshold and the flag are unchanged on the income statement and the cash flow statement, where they fire on 19 of 44 and 31 of 45 plug cells across the acceptance filers and therefore still single something out. On the balance sheet they fired on 72 of 75, because a 41-item registry meets a real balance sheet with right-of-use assets, deferred tax, vendor non-trade receivables and a dozen other captions it has no item for. Every instance was true and the warning was still worthless, because a reader who sees the same sentence on every subtotal stops reading it, which is worse than not flagging at all. So each balance-sheet section reports the same measurement as a coverage percentage on the Checks sheet: the share of the reported subtotal the registry's own lines account for, written as live arithmetic over the subtotal and its plug. The number was never the problem; the sentence attached to it was. The registry is not widened, which is the other way out and needs its own session and a time-box (V2_PLAN R3). |
| 2026-08-05 | The retained earnings line is a residual to be explained, not a tie to be green | V2_PLAN Part 4's checklist template asks for the retained earnings tie to be green in every historical column. It cannot be for any filer, and the reason is structural rather than a bug: filers charge share retirements, treasury stock and other equity movements to retained earnings and none of those is a registry item. Apple's FY2025 residual is 91,699 million against a buyback of 90,711 million, so the figure is not mysterious, only non-zero. The workbook already labels the row a residual, leaves it uncoloured and reports the number. The checklist line now matches: the checker confirms the residual is explained by buybacks and other equity movements rather than confirming a zero that cannot happen. A line item that can never be signed off is not a check, it is a checklist nobody finishes. The alternative, adding the equity-movement items to the registry so the row can tie, is the same trade-off as the coverage entry above and was rejected for the same reason. |
| 2026-08-04 | A quarter is numbered by position between two fiscal year ends | How far through its fiscal year the period ends, in quarters, rounded to the nearest one, against year ends the engine has already confirmed. Never from fp, which names the filing: Kroger's fourth quarter is carried only by the next year's first-quarter 10-Q, and Honeywell's third quarter of 2020 sits in a 10-Q that is itself mis-stamped Q2. An unclosed year is measured against the filer's median year length; a quarter with no year end before it keeps the label it arrived with, because there is nothing to number from. Numbering decides the name only: which quarters exist still needs a filing to have called the date a quarter, so no value moves into or out of the view. |
| 2026-08-05 | The checklist's value comparison is done by a Claude session; the user reviews the evidence and signs | The acceptance hand-check has two halves and they need different hands. Reading five years of three statements off three filers' 10-Ks and comparing every cell, sign and scale against a workbook is mechanical, high-volume and exactly what a session with network access and the filings open can do without tiring; V2_PLAN R10 is the risk that it never happens because one person has to do all of it. So a Claude session performs the comparison and writes the evidence into the checklist: for every ticked box, a citations block naming the filing by accession, the statement inside it, and the figure read there, so the claim is checkable rather than asserted. What stays with the user is everything a session cannot do or should not certify: opening the workbook by hand in real Excel and watching for a repair dialog, hovering a row label to see the tooltip render, judging whether a plug or a coverage figure is acceptable for their purpose, and signing. The signature therefore certifies that the user has reviewed the evidence and found it sound, not that they recomputed every cell themselves; that is what makes it a signature a person can honestly give. A discrepancy the session finds is written into the breakage log as an open entry with its diagnosis and is never marked resolved by the session that found it, because the same hand should not both report and close a defect. A copy with an open entry against it is still unsignable, which is the rule the log already carried. |

## Session log

One entry per work session. Record what shipped, the xfail count after the session, and any
open questions the next session needs to know about.

| Date | Session | Shipped | xfails | Open questions |
| --- | --- | --- | --- | --- |
| 2026-08-03 | Setup | Folded the planning output into the repo: risk register R1 through R10 as V2_PLAN Part 8, decisions log as Part 9, tasks 2.2b and 2.5 added to Phase 2, docs/SESSIONS.md created, this file created. Documentation only, no code changes. | n/a | None |
| 2026-08-03 | 1 | F1 through F5, five commits in the prescribed order. README claims corrected, real SEC User-Agent contact, test suite restored from git history, Total Debt relabeled Long-Term Debt, line-item constants consolidated into app/line_items.py. | 0 | Three, listed below. |
| 2026-08-03 | 2 | V2_PLAN 1.1, 1.2, part of 1.5, and the frontend half of the Session 1 consolidation. Five commits: session prompt amended, registry built, per-period stitching, fixture generator plus the Apple fixture, classification served to the browser. | 0 | Open question 2 closed; 1 and 3 still open; two new ones. |
| 2026-08-03 | 3 | V2_PLAN 1.3 and 1.4, and the rest of 1.5. Four commits: session prompt amended, fixture generator extended plus the JPMorgan and SAP fixtures, provenance and the scope gate, tooltip element moved. | 0 | Open question 5 closed, 3 partly addressed; 1, 3, and 4 still open; one new one. |
| 2026-08-04 | 4A | The period engine, V2_PLAN R5. Four commits: Session 4 split into 4A and 4B, annual report forms ranked above every other form, the Honeywell fixture, one shared period engine in app/periods.py. | 0 | Open questions 3 and 6 closed. 1 sharpened by the Honeywell fixture and still open, as is 4; both go to 4B. One new one, 7. |
| 2026-08-04 | 4B | The chain corrections and the Phase 1 exit review. Six commits: session prompt amended, the Kroger fixture, the Long-Term Debt chain, four more chain corrections, Short-Term Debt summed and Total Debt surfaced, the EPS reconciliation check. Phase 1 declared done. | 1 | Open questions 1, 4 and 7 closed. Two new ones, 8 and 9, both about labels rather than values, both raised by Kroger. |
| 2026-08-04 | 4C | Period names, an interstitial before Phase 2. Three commits: session prompt added, fiscal years named by the filer's own convention, quarters numbered by position. No fixture regenerated and no value changed anywhere. | 0 | Open questions 8 and 9 closed. One new one, 10, about the calendar year a quarter label carries. |
| 2026-08-05 | 5 | The first Phase 2 session: V2_PLAN 2.1, 2.2, 2.2b and 2.5. Four commits: session prompt amended and quarters named for their fiscal year, the model spec in app/scaffold/three_statement.py, the writer kit in app/scaffold/excel.py, the formula-evaluation harness. | 0 | Open question 10 closed. Two new ones, 11 and 12, both raised by measuring the scaffold rather than by building it. |
| 2026-08-05 | 6 | The last Phase 2 session: V2_PLAN 2.3 and 2.4. Three commits: open questions 11 and 12 settled, the endpoint and the button, the acceptance documents and the generator. Phase 2's exit review is written and its last criterion is the user's hand-check, which has not run. | 0 | Open questions 11 and 12 closed. None new. |
| 2026-08-05 | 6H | The delegated half of the acceptance hand-check. Five historical years of all three statements for all three filers compared against the filings on EDGAR, cell by cell, for value, sign and scale; the checklist filled in with a citations block under every table; sixteen open entries written into the breakage log. Documents only: no application code was touched and nothing generated was committed. | 0 | None closed. Sixteen breakage entries open, and Phase 2 still cannot be declared done. |

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

### Session 4A detail

Suite state: 489 tests, all passing, zero xfails. Session 3 left 438. The 51 new
tests are 20 against the Honeywell fixture, 19 for the period engine, 6 for form
ranking on synthetic payloads, and 6 more in the scope-gate module.

Two changes, and the surprise is which one did the work. The prompt expected the
period engine to close the shadowing holes. It was the form ranking that closed
every one of them, because the shadowing and the proxy statement turn out to be
the same defect seen from two sides: a later filing that merely repeats a period
was winning it. Once the annual report wins, the year-end balance sheet keeps its
own FY label and the fp filter has nothing left to drop.

That does not make the engine optional. It is what V2_PLAN R5 asks for, it is
what stops the two views drifting apart again, and it reaches a case ranking
cannot: a fiscal year whose only balance sheet is the comparative column of a
10-Q has no annual report to prefer. No fixture contains one, so app/tests/
test_periods.py builds it by hand along with the year-to-date column and the
multi-year cumulative total that the old "at least 300 days, no ceiling" filter
would have accepted.

**Old versus new, all 14 displayed items, every committed fixture.** Measured by
running the same table off each fixture at three commits: before the session,
after the ranking fix, and after the engine.

| Company | Annual table | Peer table | Quarterly table |
| --- | --- | --- | --- |
| Apple | +21 values, 0 lost, 0 changed | unchanged | +165, -7, 0 changed |
| JPMorgan | +11 values, 0 lost, 0 changed | 5 changed | 0 gained, -6, 0 changed |
| Honeywell | +19 values, 0 lost, 0 changed | 2 changed | +177, -7, 2 changed |
| SAP | unchanged (no us-gaap facts) | unchanged | unchanged |

The annual table is the one the app shows, and it gained 51 values and lost
none. All 51 were blank cells; 50 now come from a 10-K and the 51st is a
derived Gross Profit. Not one number changed. They cluster where a later filing
had relabeled a period: Apple's FY2012 income statement, whose last copy is a
January 2015 8-K carrying no fp at all, and pieces of the year-end balance sheets
of FY2011, FY2013, FY2017, FY2024 and FY2025, each relabeled by a following 10-Q.
Honeywell gains its FY2021 income statement and FY2025 balance sheet the same
way.
JPMorgan gains five years of net income, which had been dropped from this table
entirely rather than shown rounded: the proxy statement that won those periods
carries no FY label, so the row was blank here while the peer table showed the
rounded figure.

Every loss and every changed value, with its explanation:

- **Quarterly, 20 lost cells across three companies, all in 10 dropped columns.**
  Each dropped column is a fiscal year end that had appeared in the quarterly
  view under a quarter label, which is what shadowing produces: Apple's
  2025-09-27 year end shown as "Q3 2025". Every one of those columns is a column
  in the annual view, and every lost cell reappears there with the same value,
  except the two Honeywell debt figures below. A mislabeled column stopped
  existing; no number was lost.
- **Peer, JPMorgan net income, 5 years changed.** 48,300 to 48,334 for FY2021,
  37,700 to 37,676, 49,600 to 49,552, 58,500 to 58,471, and 57,000 to 57,048 for
  FY2025. The proxy statement's rounding gives way to the figure three 10-Ks
  report. This is open question 6 and the correction the session was for.
- **Peer, Honeywell long-term debt, 2 years changed.** 26,826 to 27,265 for
  FY2024 and 28,687 to 29,046 for FY2025. Not a rounding, and the only change
  that is not the proxy correction the session prompt allowed for. Both figures
  are Honeywell's own LongTermDebt tag; the 10-Qs and the 10-K put different
  numbers in it. The 10-Q's 26,826 is exactly Honeywell's balance sheet, being
  LongTermDebtAndCapitalLeaseObligations of 25,479 plus the current portion of
  1,347, and the 10-K's 27,265 is 439 higher. So the row now shows the annual
  report's figure, which for this filer is neither the non-current balance nor
  the balance-sheet total. That is open question 1 with a sharper edge, and 4B
  owns it: the fix is a chain correction, not a resolution change.
- **Quarterly, Honeywell Q2 2025 EPS, 2 values changed.** Basic 4.92 to 2.46 and
  diluted 4.90 to 2.45. Between the 10-Q that first reported that quarter and the
  10-Q filed a year later, Honeywell's weighted average share count for it halves
  from 637.5 to 318.8 million and the EPS doubles, while net income of 1,570
  million is identical in both and in the 10-K. So a share-basis change in 2026 is
  being applied backwards, and the FY2025 10-K predates it. Ranking annual reports
  first means the row shows the basis the 10-K used until the FY2026 10-K restates
  the quarter. Both figures describe the same earnings; only the denominator moved.

The last one has a consequence worth naming: the shares row for that quarter has
no annual-report entry, so it still shows the post-change 318.8 million while the
EPS row shows the pre-change 2.46, and the two no longer reconcile. The check
that exists to catch exactly this did not fire, for a reason that has nothing to
do with this session's changes; see open question 7.

One more thing the comparison caught. Ranking annual reports first, on its own,
costs the quarterly view 22 cells for Apple and 36 for Honeywell, because a 10-K
comparative quarter carries the label FY and the quarterly filter wanted a Q. The
engine restores all of them and adds far more. The two changes are only jointly
correct, and the commit between them has a quarterly view worse than either end.
Recorded because the commits are ordered as the session prompt asked, and anyone
bisecting through that commit should know.

Both views now agree cell for cell on all four fixtures. Before the session they
disagreed on 21 cells for Apple, 19 for Honeywell and 11 for JPMorgan, which is
R5 measured rather than asserted; a test in test_periods.py asks every committed
fixture the same question so it cannot drift back.

### Session 4B detail

Suite state: 540 tests, all passing, one xfail. 494 mocked tests run offline in
about 6 seconds; 46 integration tests hit live EDGAR or start a browser and take
about 40 seconds. Session 4A left 489. The 51 new tests are 27 against the Kroger
fixture, 9 more in the Honeywell module, 5 more in the Apple module, 4 for the
registry, 3 for the EPS check on synthetic points, 2 for the scope-gate module's
bank, and 1 for the provenance module.

The one xfail is deliberate and is open question 9: Kroger's fourth quarter comes
out labeled Q1. It is strict, so it fails the moment the label is fixed.

**The Kroger fixture.** CIK 56873, verified as KR against the live ticker lookup
before downloading. Its fiscal year is 52 or 53 weeks and ends on the Saturday
nearest 31 January, which is what it is in the acceptance set for. The period
engine took all of it: nineteen consecutive year ends 364 or 371 days apart with
nothing in between and no year missing, the three 53-week years are the three the
filings name, and the 111-day first quarter is measured as a quarter rather than
rejected. The cell-for-cell view-agreement test in test_periods.py picked the
fixture up on its own and passed on the first run.

Two things about Kroger are wrong and are not fixed here, because both are about
what a period is called rather than what it holds, and both need a decision
rather than a correction. They are open questions 8 and 9.

**Chain corrections, five of them, each against the filing it comes from.**
Every registry chain was resolved against all five fixtures and the result read
against the statements. Five chains were wrong in the same way: the filer reports
the line, tags it with an element the chain does not list, and the row comes back
blank or wrong.

| Chain | Tag added | Evidence | What it moved |
| --- | --- | --- | --- |
| Long-Term Debt | LongTermDebtAndCapitalLeaseObligations, ahead of LongTermDebt | Honeywell's FY2025 balance sheet shows long-term debt of 27,141 million; the LongTermDebt tag holds 29,046, which is neither that nor the 28,687 balance-sheet total including current maturities | Honeywell FY2025 29,046 to 27,141, FY2024 27,265 to 25,440, and the row goes from 17 years across two tags to 18 from one |
| Cost of Revenue | CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization, last | Kroger's income statement line "Merchandise costs ... excluding items shown separately below", 113,240 million for fiscal 2025 | Kroger's cost row goes from 11 years to 19, and its Gross Profit from none to every year |
| PP&E Net | PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization | The two tags agree to the dollar in each filer's transition year: 5,471 million for Honeywell at 2022-12-31, 21,871 for Kroger at 2020-02-01 | Honeywell 15 years to 18, Kroger 12 to 18 |
| Interest Expense | InterestAndDebtExpense, then InterestIncomeExpenseNonoperatingNet | Honeywell's line "Interest and other financial charges", 1,344 million for FY2025; Kroger's "Net interest expense (639)" | Honeywell 0 years to 19, Kroger 17 to 19 |
| Accounts Payable | AccountsPayableTradeCurrent | The two agree to the dollar in the year Kroger tags both, 10,381 million at 2024-02-03 | Kroger 3 years to 18 |

Two of those carry a caveat into the registry rather than out of it. The new cost
tag excludes depreciation and amortization where the others include it, so a row
crossing that seam changes meaning and the seam is flagged. Kroger's interest tag
is a net figure carrying the filer's own sign, so its row reads 441 for fiscal
2023 and -639 for fiscal 2025 while the interest bill went up; the sign note says
so.

Four rows stay blank on purpose, because the only tags available mean something
else. Kroger's inventory is a FIFO amount and a LIFO reserve on two lines with no
net element tagged. Kroger tags no operating expense element the registry reads.
Honeywell tags no Liabilities at all, and no OperatingIncomeLoss before 2022, its
income statement having no such subtotal. A new test lists the three chain tags
no fixture exercises, so a proposed chain cannot pass for a verified one.

**Total Debt, and what it took to show it.** Open question 4 said the fix was a
summed derivation rather than a chain reorder, and open question 1 said the
long-term row had to be strictly non-current first, and both were right: neither
half works alone. Honeywell is the proof. With the old chain its long-term row
read 29,046, which overlaps its current maturities, so any sum would have double
counted; with the old Short-Term Debt chain its short-term side would have been
the borrowings line alone and would have dropped the current maturities entirely.

Short-Term Debt keeps one tag, DebtCurrent, which is the only element that means
the whole current debt balance. Not one of the five fixtures uses it. So for all
of them the row is a sum of three current-liability lines, each now a registry
item of its own with its own tag and filing: current maturities, commercial
paper, and short-term borrowings. The terms are optional and at least one must be
present, which is the first derivation rule in the project to work that way and
is confined to this one; the decisions log records why.

OtherShortTermBorrowings is in no chain deliberately. Apple tags it and
CommercialPaper for 2019-09-28 with the same 5,980 million, so it is an alias for
that line rather than a second balance, and treating it as a term would have
double counted the whole of it.

The results, each against its own balance sheet:

| Filer | Long-term | Short-term | Total Debt |
| --- | --- | --- | --- |
| Apple FY2023 | 95,281 | 9,822 + 5,985 = 15,807 | 111,088 |
| Honeywell FY2025 | 27,141 | 1,546 + 5,893 = 7,439 | 34,580 |
| Kroger fiscal 2025 | 14,509 | 1,366 | 15,875 |
| JPMorgan | not reported | 64,776 | missing |

Apple's is the figure open question 4 named, against the 105,103 the chain used
to produce. Kroger's 15,875 is exactly what Kroger's own LongTermDebt tag holds
for that instant, which is a cross-check from a tag the row does not read.
JPMorgan gets no row: it reports short-term borrowings and no long-term debt, and
a total missing an input stays missing.

Surfacing it needed two smaller things. The provenance model had two missing
flags and needed a third: a row that is arithmetic and blank was being told "not
tagged in XBRL", which is true of Total Debt for every filer that ever lived and
sends a reader hunting for a line no balance sheet carries. DERIVATION_UNAVAILABLE
names the component that was absent instead. And because the short-term half is
itself a sum, the provenance nests one level, so the tooltip and the Source Tags
sheet descend into it and every leaf a reader sees is a tag with a filing behind
it. The decisions log is amended for that one level, with its reason.

The tripwire Session 3 left, asserting Total Debt appeared in no payload, was
retired in the same commit that made it wrong, and replaced by tests that guard
the fix.

**The EPS check, fired for the first time.** Keying on (start, end) rather than
on (unit, start, end) is the whole fix; the three series are in three units and
could never meet. It now also skips periods that are not one quarter or one year,
because a year-to-date column ends on the same day as the quarter that closes it
and a flag reaches a cell by its end date.

Fifty-eight periods flag across the five fixtures. Every one was read; none was
silenced and no tolerance was tuned.

- **Honeywell, one.** The quarter ended 30 June 2025, which is the column Session
  4A went looking for. Net income 1,570 million, 321 million shares, reported EPS
  2.45, computed 4.90.
- **Apple, five.** The quarters either side of its 7-for-1 and 4-for-1 splits. A
  later 10-K restated each quarter's EPS onto the post-split basis and nothing
  ever restated the share count, so the ratio of computed to reported is exactly
  7 for the 2012 and 2013 quarters and exactly 4 for the 2018 and 2019 ones. Both
  rows are the newest figure any filing reports; they cannot be multiplied
  together, which is what the flag says.
- **Kroger and SAP, none.**
- **JPMorgan, fifty-two, one cause.** Its diluted EPS is computed on net income
  available to common shareholders and the check divides total net income, so
  every period is high by the preferred dividend. Proven rather than assumed:
  JPMorgan tags the available-to-common figure for ten of the fifty-two, and
  substituting it brings all ten inside tolerance. Kept, because a reader
  multiplying this bank's diluted share count by its diluted EPS really will not
  get its net income. The tolerance sorts it without help: only three of the
  fifty-two are 2021 or later, as the dividend shrank against earnings.

The message changed rather than the threshold. It used to assert "possible share
count or unit mismatch" and now names the two things it can actually be.

### Session 4C detail

Suite state: 562 tests, all passing, zero xfails. 516 mocked tests run offline in
about 7 seconds; 46 integration tests hit live EDGAR or start a browser and take
about 31 seconds. Session 4B left 541, one of which was the strict xfail this
session was for. The 21 new tests are 14 in the period engine module, 3 more in
the Honeywell module, 2 more in each of the Kroger and Apple modules.

Two label fixes, no value moved, and no fixture regenerated. The whole of both
tables was dumped before and after each change and compared cell by cell across
all five fixtures: every value, every flag, every tag summary, every peer-table
figure and every provenance record is identical, and the only provenance text
that moved is the period name inside a missing-value pointer, which now names
the year its column heading does.

**Where DocumentFiscalYearFocus actually lives.** Step 3 of the session prompt
allowed for the fact not being in the companyfacts payload, and it is not: the
XBRL APIs carry only numeric facts, the focus is a gYear, and
`companyconcept/CIK0000056873/dei/DocumentFiscalYearFocus.json` returns 404. But
no fixture needed regenerating and make_fixture.py needed no extension, because
EDGAR stamps each filing's focus on every fact that filing reported, as the `fy`
field the extraction layer has always copied into `fiscal_year`. The value is the
same one; only the route to it is different. Recorded because the obvious
conclusion from the missing dei tag is that a second download is needed, and it
is not.

**Why the convention is read rather than the value.** The session prompt asked
for the focus from the earliest annual filing that first reported a period end,
which is the lookup filing_pointers does. Taken at face value that is wrong for
Kroger in two ways, both measured:

- Kroger tags focus 2025 on the year ended 1 February 2025 and again on the year
  ended 31 January 2026. Two columns, one name. Its 10-K for the earlier year is
  unambiguous in prose -- "within 120 days after the end of the fiscal year 2024"
  -- so the tag is Kroger's own error, not a convention. The filing for the year
  ended 3 February 2024 carries the same error.
- Kroger's first XBRL filing, the 10-K filed 30 March 2010, carries four years:
  the year ending 30 January 2010 and three comparatives. All four facts carry
  that filing's focus of 2009. Four columns, one name. Apple, Honeywell and
  JPMorgan all have the same shape at the start of their histories.

So what is read is the difference between a filing's focus and the calendar year
of its own year end, and the commonest difference wins. Kroger's nineteen annual
filings vote 17 to 2 for an offset of one; Honeywell's seventeen vote 16 to 1 for
zero, its 2021 annual report having tagged 2020; Apple's eighteen and JPMorgan's
seventeen are unanimous at zero. Every one of Kroger's nineteen columns moves
back a year, no two share a name, and the headings now read the way the filings
behind them do. Nothing else moves, because an offset of zero is the old rule
exactly, which is also the fallback for a payload that names no fiscal year --
SAP, which has no us-gaap facts at all.

A filing's own year end is the latest period end it reports, with two guards: an
end date after the filing date was not reported by that filing, and one more than
400 days before it belongs to an earlier year. Across the four us-gaap fixtures,
all 71 annual filings resolve to their true fiscal year end.

The repair that looks obvious, naming a fiscal year for the calendar year that
holds most of it, is now running code in test_periods.py rather than a sentence.
It agrees with Kroger and disagrees with Nike, whose 31 May year end is named for
the later year, so it would have fixed one filer by breaking another. No Nike
fixture exists and the test filer is synthetic; what it pins is why a rule was
rejected, which no committed fixture can pin.

**Quarter numbering, and the eighteen columns it corrects.** How far through its
fiscal year a period ends, in quarters, rounded to the nearest one, between two
confirmed year ends. Kroger's 16-week first quarter ends 30 percent of the way
through and its second 54 percent, and rounding absorbs both without anything
having to be told what a quarter measures. A quarter in a year that has not
closed is measured against the filer's median year length; a quarter with no year
end before it keeps the label it came with.

| Company | Quarter columns | Renumbered |
| --- | --- | --- |
| Kroger | 60 | 17 |
| Honeywell | 56 | 1 |
| Apple | 55 | 0 |
| JPMorgan | 54 | 0 |

Every one of the eighteen is a correction, and each was read:

- **Kroger, five fourth quarters**, ending 29 January 2022 through 31 January
  2026, which read Q3 or Q1 depending on which filing repeated them last. This is
  open question 9 itself.
- **Kroger, twelve first and second quarters**, every one before fiscal 2019.
  EDGAR numbered them against a calendar year, so the May quarter came back Q2 and
  in a 53-week year the August quarter came back Q3. From fiscal 2019 the filings
  number them the way Kroger does and the two already agreed.
- **Honeywell, the quarter ended 30 September 2020.** Two filings report it. Its
  own 10-Q, filed that October, calls it Q3. The 10-Q filed a year later carries
  it as a comparative and is itself stamped Q2, which it is not either, and being
  later it is the copy resolution keeps. So this is fp being wrong on a filing
  rather than merely borrowed from one, which no other fixture demonstrates.

Which quarters exist is deliberately untouched. A period still needs a filing to
have called it a quarter before it is a column, so the column set is identical
before and after and no value moved into or out of the quarterly view. Numbering
answers what a period is called, not whether it happened, and widening the
existence rule is a change with values behind it that this session was not for.

**What the quarter labels still carry, and it is not right.** A quarter column
keeps the calendar year of its end date, so Kroger's fourth quarter of fiscal
2025 reads "Q4 2026" beside an annual column for the same period end that reads
FY2025. Naming a quarter for the fiscal year it belongs to would fix that and
would also move every Apple quarter, because Apple's first quarter ends in
December: the quarter ending 28 December 2024 reads "Q1 2024" today and is Apple's
first quarter of fiscal 2025. The session prompt asked for Apple's and
Honeywell's quarter labels to be unchanged and they are, so the year component
was left alone and the question is open question 10 rather than a silent change.

### Session 5 detail

Suite state: 650 tests, all passing, zero xfails. 604 mocked tests run offline in
about 27 seconds; 46 integration tests hit live EDGAR or start a browser and take
about 135 seconds. Session 4C left 562. The 88 new tests are 32 for the model
spec, 33 for the workbook, 15 for the formula-evaluation harness, and 8 for the
quarter-label convention.

The session added one dependency, `formulas` 1.3.4, which V2_PLAN R2 names.

**Quarter labels, open question 10.** A quarter now takes the year of the fiscal
year it sits inside rather than the calendar year it ends in. All 223 quarter
columns across the four us-gaap fixtures are relabelled, no column set changes,
and no value, annual label or provenance record moves; the whole of both views
was compared cell by cell before and after. Kroger's 59 columns each move back a
year and Apple's 18 December quarters each move forward one, which is the point:
the two filers were wrong in opposite directions, so no rule that moved only one
of them could have been right.

**The scaffold, and the thing it measures.** app/scaffold/three_statement.py
builds a model spec of 58 rows -- all 41 registry items, eleven plug rows, and
six links and memo lines -- over five historical years and three forecast years,
and app/scaffold/excel.py turns it into the seven-sheet workbook V2_PLAN Part 4
describes. The two modules do not share a concern: the first imports no openpyxl
and the second contains no finance, and every formula the writer emits is a
rendering of an expression the spec handed it.

Across the three acceptance filers, 870 historical cells: 533 reported, 277
derived, 60 missing. Every one is in exactly one of those states and every one
carries provenance, which is Phase 1's guarantee reaching the first thing built
on top of it.

**Plugs are much larger than the plan expected, and that is the finding.**
V2_PLAN R1 anticipated that "some filers may need plugs so large the scaffold is
misleading". It is not some filers. Of 164 plug cells across the three filers,
**122 exceed the 10 percent threshold**, and the concentration is on the balance
sheet: 72 of 75 balance-sheet plug cells are flagged, against 31 of 45 on the
cash flow statement and 19 of 44 on the income statement.

| Filer | Plug cells | Over threshold | IS | BS | CF |
| --- | --- | --- | --- | --- | --- |
| Apple | 55 | 33 | 0 | 25 | 8 |
| Honeywell | 54 | 45 | 10 | 22 | 13 |
| Kroger | 55 | 44 | 9 | 25 | 10 |

Apple's is the clearest case and it is not a defect in Apple's tagging. Its four
tagged current-asset lines are 100,192 million of 147,957 million of current
assets for FY2025; the rest is vendor non-trade receivables and other buckets
the registry has no item for. Its non-current asset plug is 41 percent of total
assets, because the registry reads three non-current lines and Apple's balance
sheet has more. The threshold is doing what the decisions log asked of it and
reporting honestly that a 41-item registry does not reconstruct a balance sheet.

The threshold was not tuned to quieten this, because the decisions log fixes it
at 10 percent and a settled decision is not re-litigated by measuring an
inconvenient result. What the number means for Session 6 is open question 11.

The flag is measured against the total the plug ties to rather than against the
statement's headline total. Both readings of "its statement total" flag Apple's
balance sheet everywhere; the local one is the stricter, since a subtotal is
never larger than the statement it sits in, and it names something a reader can
act on.

**By-design blanks behave as the session prompt required.** A row the filer does
not tag is present, missing, flagged and explained, and the plug that absorbs it
names it: Kroger's current-asset plug says it swallowed inventory and short-term
investments, and its operating plug says it swallowed SG&A and R&D. Honeywell
tags no Liabilities element for any year, so its liability total is derived as
assets less equity -- the balance sheet equation solved for the one term the
filer left untagged, which is exact -- and the balance check row is flagged
CHECK_NOT_AVAILABLE, left uncoloured, and says it is zero because it was made
zero. Apple's and Kroger's balance checks are real and are zero to the dollar in
all five years.

**The seam travels.** Kroger's cost of revenue chain ends in an element that
excludes depreciation where the others include it. Its FY2018 seam flag now
reaches gross profit and the operating plug above it, each message naming the
row the flag started on rather than the row below. Apple's FY2015 cash flow seam
reaches two levels up to closing cash the same way.

**Two bugs the harness caught that nothing else would have.** Both are exactly
the failure mode R2 predicts: formula text that openpyxl writes happily and no
human would spot without opening Excel.

- The operating income forecast subtracted its plug. The plug is a signed
  residual and has to be added: it is negative for Kroger, whose whole operating
  cost lands in it, and positive for Honeywell, whose operating income includes
  items the three rows above it do not. Invisible on Apple, whose plug is exactly
  zero in every year.
- The working capital line lost its forecast for Kroger, because the rule that
  refuses to model forward from a hole treated Kroger's untagged inventory as
  one. The balance sheet then moved while the cash flow statement did not see it,
  and the forecast balance check broke by 4.47 billion. The fix distinguishes a
  hole in an otherwise reported row from a line the filer does not carry at all:
  the first refuses a forecast, the second contributes nothing, which is both the
  truth and what keeps the statements agreeing.

Neither is visible in the historical columns, and neither would have failed a
test that only re-read formula strings.

**Formula vocabulary.** No exception proved necessary. The scaffold writes only
cell references, the four arithmetic operators, and IF, OR and ISBLANK; the
conditional formatting adds AND, ABS and ISNUMBER. All eight evaluate under the
`formulas` library, and a test reads every formula in a generated workbook and
fails if a ninth appears, so the constraint cannot lapse silently. There is no
manual-check burden to record because nothing was left unevaluated.

**Excel, opened for real.** The workbooks were opened in Excel 16.0 on this
machine through COM automation, with a full recalculation forced. All seven
sheets, all 48 defined names and all 401 cell comments survived intact in every
file, and Excel's own arithmetic put the balance check at zero in all five
historical columns for all three filers and in all three forecast columns of a
workbook with its assumptions filled. Nothing was stripped, which is the damage a
repair does and the observable signature R4 is about.

That is stronger than a formula check and weaker than the acceptance checklist's
line. Automation runs with alerts suppressed, so what was verified is that no
content was lost and everything recalculated, not that no dialog would have been
shown. The interactive open stays on the checklist for Session 6.

**What the forecast does and does not do.** Fifteen assumptions per year, all
blank. Every forecast cell is guarded by a readiness cell that is true only when
its year's inputs and every earlier year's are filled, so a blank sheet produces
blank forecasts, a filled one produces three statements that tie, and clearing it
again empties them with no leftovers. All three are tested by evaluation rather
than asserted.

Rows with no driver get no forecast and say why: the per-share rows, because a
share count needs a repurchase price this tool should not invent, and any row the
filer never tags, because whatever it holds is already inside a plug that is
carried forward and modelling it separately would count it twice.

The forecast balance sheet ties by construction rather than by luck, and the one
piece of real modelling in it is worth naming: the equity plug is the only plug
not held flat, because stock compensation builds paid-in capital and buybacks
consume equity, and holding it flat leaves the balance check short by exactly
those two.

**What the acceptance checklist will not get.** V2_PLAN's template asks for the
retained earnings tie to be green in every historical column. It cannot be, for
any of the three filers, and the reason is structural rather than a bug: filers
charge share retirements, treasury stock and other equity movements to retained
earnings and none of those is a registry item. Apple's FY2025 residual is 91,699
million, almost exactly its buyback. So the row is labelled a residual, is left
uncoloured, and reports the number instead of failing a test it was never going
to pass. Open question 12.

### Session 6 detail

Suite state: 683 tests, all passing, zero xfails. 637 mocked tests run offline in
about 70 seconds; 46 integration tests hit live EDGAR or start a browser and take
about 49 seconds. Session 5 left 650. The 33 new tests are 20 for the endpoint and
the button, 10 for coverage and the flag summary, 2 for the workbook, and 1 in the
evaluation harness.

**Open question 11, and what it cost to close.** The threshold is untouched at 10
percent. What moved is where the flag is raised: the income statement and the cash
flow statement keep it, the balance sheet reports the same measurement as a
coverage percentage on the Checks sheet. Flagged plug cells across the three
filers fall from 122 to 50, which is exactly the 72 balance-sheet ones, and 75
measured cells take their place, five sections over five years per filer.

Coverage is written as arithmetic over two cells the balance sheet already shows,
the subtotal less its plug over the subtotal, rather than as a percentage this
code computed and typed in. So it is one minus the plug's share by construction; a
test asserts that identity on all 75 cells, and the evaluation harness asserts
Excel's own answer matches the spec on the 50 belonging to Apple and Honeywell.

Nothing is clamped and no absolute value is taken:

| Section | Apple FY2025 | Honeywell FY2025 | Kroger FY2025 |
| --- | --- | --- | --- |
| Total current assets | 68 | 88 | 38 |
| Total assets | 59 | 85 | 84 |
| Total current liabilities | 55 | 59 | 66 |
| Total liabilities | 85 | 86 | 74 |
| Total equity | -19 | 339 | 486 |

The equity row is the one that proves the point. It has a single component,
retained earnings, measured against a total that treasury stock and accumulated
other comprehensive income pull down, so it runs from minus 34 to plus 486 percent
across these filers and every one of those is the honest reading. Forcing it into
a nought-to-one range would have hidden the only thing that section has to say.
The sheet's note says what above 100 and below zero mean, and says that a figure
far from 100 limits the breakdown above it and never the subtotal itself.

**Open question 12** is a document change and nothing else. The workbook already
labelled the retained earnings row a residual, already left it uncoloured and
already reported the number; only the checklist asked for a green tie that cannot
happen. What the residual actually is, per filer, is worth knowing before the
hand-check, because it is not uniformly large: Apple's runs 79 to 97 billion, which
is its buyback programme, Honeywell's is 19 to 83 million in three years and minus
1,624 million in FY2025, and Kroger's is 4 to 27 million. A checker who expects a
big number everywhere would misread two of the three.

**The endpoint decides nothing.** POST /api/scaffold/three-statement fetches the
payload, looks up the SIC the gate needs, calls build_model and write_workbook,
and turns a refusal into a response. The test that matters builds the same spec
directly and compares the two workbooks cell for cell across all seven sheets,
because the way scaffold rules leak into app.py is one convenience at a time and
nothing else would notice.

Refusals carry the gate's own sentence and write no file at all: not an empty
workbook, not one with the refusal typed into it. JPMorgan is refused on SIC 6021,
SAP on reporting no us-gaap facts, and an insurer on SIC alone, which is tested by
serving Apple's payload under SIC 6311 since no insurer fixture exists. That last
one is the honest test of a deterministic gate: the refusal is the code, and a
filer with perfectly ordinary tagging is still refused. CSV is refused too, since
flattening seven linked sheets to values destroys the only thing the workbook is
for.

A failed SIC lookup does not stop a scaffold. The submissions API is a second
request and is allowed to fail; refusing to build anything when it does would make
an unrelated outage look like a verdict about the company.

**Two bugs in the flag summary, found by looking at its output rather than by a
test.** The summary moved from excel.py to three_statement.py in the same commit,
because a statement about flags is not an Excel concern and the endpoint needed it
too.

- It keyed on (flag type, row), and a flag that names no row has no row. Kroger
  tags no SG&A, R&D, inventory, short-term investments, commercial paper or
  short-term borrowings, and all six of those messages collapsed into one line:
  the Checks sheet reported one and silently dropped five. It now keys on the
  message where there is no row.
- A plug flagged in five years reported the first year's percentage under a line
  saying it happened in all five. Kroger's operating plug read "773 percent of
  operating income (5 of 5 historical periods)" when it reaches 1,720 percent in
  another of those five. The summary now reports the worst year and says
  "reaches" so the number reads as a range rather than a fact about one column.

Both were invisible to the suite, which checked that a line existed rather than
that it said the right thing, and both are now tested.

**The button, driven in a real browser offline.** Chromium against the committed
fixtures: Apple builds and the confirmation names the file, the columns and what
the workbook flags; JPMorgan shows the gate's refusal in its own element rather
than as an error, and no file appears on disk. No page errors, and the single
console line is Chromium noting the 422 itself, which is unavoidable for a fetch
that returns a non-2xx status and is not a fault in the page.

**The three acceptance workbooks.** Built through the endpoint by
scripts/generate_acceptance.py, five historical years and three forecast columns
each, from the committed fixtures. Nothing generated is committed; app/exports is
gitignored and the workbooks are working copies for the hand-check.

Opened in Excel 16.0 on this machine through COM automation with a full
recalculation forced. All seven sheets, all 48 defined names and all 402 or 403
cell comments survive in every file. Excel's own arithmetic puts the balance check
at zero in all five historical columns for all three filers, and its coverage
figures match the model spec to the digit shown. Kroger's cash tie is zero in
every column; Apple's and Honeywell's carry the currency residuals their filings
report.

That is the same automation check Session 5 ran and it has the same limit: alerts
are suppressed, so what is verified is that no content was lost and everything
recalculated, not that no repair dialog would have been shown. The interactive
open is a line on each checklist copy and only the user can tick it.

**What is not done.** The hand-check itself. Three checklist copies exist, all
three are unsigned, and the breakage log is empty because nothing has been checked
rather than because nothing was found. Phase 2's exit review below records that as
the one open criterion.

### Session 6H detail

The value comparison half of the acceptance hand-check, run against the three
workbooks dated 2026-08-05 in app/exports/acceptance and against the filings
themselves on EDGAR over live network. No test was run and no application code
was read except to diagnose what the comparison found; the only writes are
docs/acceptance/3s_checklist.md, docs/acceptance/breakage_log.md and this file.

**What was compared.** Every historical cell of the income statement, balance
sheet and cash flow statement for Apple, Honeywell and Kroger, five years each,
against the rendered statements of the filings the Source Tags sheet cites --
thirteen 10-Ks, one 10-Q, and EDGAR's companyconcept API wherever a figure could
not be found on the face of any statement or note. Value, sign and scale in every case, plus every blank's
flag message and pointer, the Checks sheet's balance check, cash tie, retained
earnings residual and all twenty-five coverage percentages per filer, and the
flag summary. Sixteen source tags were traced end to end rather than the nine the
checklist asks for, three per statement per company. The checklist now carries a
citations block under every table naming the accession, the statement inside it
and the figures read there, so each tick is checkable.

**What came out clean.** Apple's income statement and cash flow statement match
its filings in all five years, line for line and sign for sign, including the
interest expense that lives in a note rather than on the face and disappears
after FY2023. Its balance sheet matches in four of five. Kroger's income
statement and cash flow statement match in all five years, its cash tie is zero
in every column because that filer has neither restricted cash nor a currency
effect, and its three known quirks were confirmed against EDGAR rather than
assumed: companyconcept returns 404 for both SellingGeneralAndAdministrativeExpense
and ResearchAndDevelopmentExpense on this filer, and its four InventoryNet facts
all end in 2010. Honeywell's balance check is zero by construction and both flags
that say so are present and correct. Every retained-earnings residual on all
three filers was explained to the dollar off the filings' own equity statements,
and the three are three different stories: Apple's is a buyback plus share-
settlement withholding, Honeywell's three small ones are dividend timing and its
FY2025 one is the 1,651 million Solstice spin-off, Kroger's four are dividend
timing alone because it charges repurchases to treasury stock. The forecast
mechanics were driven through the evaluation harness on all three workbooks:
219, 222 and 207 forecast formula cells, all blank with the Assumptions sheet as
shipped, all numeric with one unremarkable set typed in, no cell evaluating to an
error either way, and all three checks zero in all three forecast columns.

**What did not.** Sixteen entries, all open. Four have a named line of code and
no defensible reading. The largest is that the YoY sanity check selects its
series on the `fiscal_period` label the 2026-08-04 decisions-log entry says never
to trust, so a 10-K's comparative fourth quarter is admitted as an annual point:
Apple's FY2021 gross profit is flagged against Apple's Q4 FY2020, and Kroger's
FY2021 operating income against a Kroger quarter. `_is_annual_period` is defined
three functions below and is the span test that would exclude it. Apple's FY2025
intangibles row carries a figure from a 10-Q that no Apple balance sheet shows,
and takes the whole balance where the row is non-current, so 2,208 million of
current-portion intangibles is counted in two sections at once. The blank
opening-cash message is malformed -- "Edgardly computes it as ." -- and names an
input that is reported.

Five more are places where a settled rule produces a row that does not match the
filing's own line, and each needs a decision rather than a patch. Honeywell's
Operating Income is its segment profit, taken from the segment note because its
income statement has no such subtotal, and three rows stand on it. Honeywell's
Intangibles is the finite-lived half of a caption that includes indefinite-lived
intangibles. Kroger's two debt rows are strict debt against captions that include
finance leases, so both read below the line they sit beside, by 1,691 million in
FY2025. And the most-recent-annual-report rule puts Honeywell's FY2022 on the
pre-spin basis and its FY2023 on the post-spin one, so revenue falls from 35,466
to 33,009 between adjacent columns and nothing says the fall did not happen.
TAG_TRANSITION marks a change of element and has nothing to say about a change of
basis inside one element.

Three are the documents disagreeing with the filings rather than the code. The
checklist asks for Kroger's FY2018 seam flag, which cannot exist in a workbook
whose five columns are all on the far side of that seam; the seam is in the row's
note instead, correctly worded. It asks that Kroger's headings match the fiscal
years its cover pages name, and two of the five cover pages disagree with their
own filings' statements, which is open question 8 seen from the checker's side.
And the Session 6 detail above says Apple's cash-tie residual is a currency
effect; Apple reports no currency line, and its residual is the year-on-year
change in restricted cash.

**What the numbers say where they were only ever reported.** The coverage
percentages read the way Session 6 predicted and every low one has an
identifiable plug behind it. Apple's lowest cell is equity at minus 33.6 percent
in FY2024, whose plug is paid-in capital less accumulated other comprehensive
loss; Honeywell's is current liabilities at 54.0 percent in FY2022, whose plug is
its accrued liabilities line in one piece; Kroger's is current assets at 25.6
percent in FY2022, whose plug is store deposits in-transit, FIFO inventory less
the LIFO reserve, and prepaids, to the dollar. Not one of the twenty-five per
filer was a surprise with the balance sheet open beside it, which is what that
line of the checklist asks.

**What remains for the user.** Three things per copy, all left blank and named as
such above each sitting log: opening the workbook by hand in real Excel and
watching for a repair dialog, which automation cannot see because it suppresses
alerts; hovering a row label to confirm the tooltip renders, the text for which
is verified present in every case; and the signature. Then the sixteen breakage
entries, none of which this session may close. No copy is signable until they are
resolved, which is the rule the log already carried and the reason Phase 2 is
still not done.

## Phase 2 exit review

Run 2026-08-05 against the exit criteria in V2_PLAN Part 4. Five of six pass on
evidence in the repo. The sixth is the acceptance hand-check, which is the user's
and has not run, so **Phase 2 is not yet declared done.** This section is filled
in and dated at the moment the three signed copies exist and the breakage log is
empty or fully resolved; nothing else is waiting on it.

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| A workbook with linked historical IS, BS and CF, real cross-sheet formulas, and forecast columns wired to a blank Assumptions sheet | Pass | Seven sheets in the order V2_PLAN names them, 58 rows over five historical and three forecast columns. Every derived cell is a formula over other cells rather than a number, every forecast cell references a named assumption or another forecast cell, and the evaluation harness computes all of it and compares 184 derived historical cells against the spec. |
| Plug rows are explicit derived formulas, never filled numbers, with the size flag of task 2.2b | Pass, with the 2026-08-05 amendment | Eleven plug rows, each written as the reported total less the components, tested cell by cell against that definition on all three filers. The size flag stays on the income statement and cash flow, where 50 cells raise it; the balance sheet reports per-section coverage instead, which is the same measurement without a sentence that fired on 72 of 75 cells. |
| The endpoint and UI button exist and surface refusals | Pass | POST /api/scaffold/three-statement, tested against five fixtures, returning the scope gate's exact message and no file for a bank, an insurer and an IFRS-only filer. The button is in the XBRL view and was driven in a real browser offline for both an acceptance and a refusal. |
| Formula-evaluation harness, with the vocabulary constrained to what it evaluates | Pass | 16 tests in test_formula_eval.py. Nothing evaluates to an error, the balance check is zero in every historical column, blank assumptions produce blank forecasts and filled ones produce three statements that tie. The vocabulary is still the eight functions Session 5 recorded; coverage needed none of them, being two references and two operators. |
| Acceptance harness exists: checklist and breakage log | Pass | docs/acceptance/3s_checklist.md, three resumable copies with a sitting log each, and docs/acceptance/breakage_log.md with the rule that every entry ends fixed or as a flagged blank. Two lines depart from V2_PLAN Part 4's template and say so in the document. |
| All three checklists signed off, every discrepancy fixed or converted into a flagged blank | **Open** | Amended after Session 6H. The value comparison has now run: five historical years of all three statements for all three filers against the filings on EDGAR, with a citations block under every table. It found sixteen discrepancies, all open in the breakage log, so no copy is signable -- not because nothing has been checked, which was the position when this row was first written, but because plenty has and it found things. What is left before a signature is a decision on each of the sixteen, the three interactive items per copy that only the user can do, and the signature itself. V2_PLAN R10 named this as a solo bottleneck; delegating the comparison is what the 2026-08-05 decisions-log entry does about it, and it leaves the judgement where it belongs. |

Two things the hand-check should expect rather than log as bugs, both established
before it starts. Honeywell's balance check is zero by construction, because it
tags no Liabilities element and its total is derived from the identity the check
tests; the row is flagged and left uncoloured for that reason. And Kroger's
inventory, SG&A and R&D rows are blank because it tags no element for them, with
the plug beside each saying what it absorbed. Everything else is fair game.

## Phase 1 exit review

Run 2026-08-04 against the exit criteria in V2_PLAN Part 3. All four pass, so
**Phase 1 is done.** Phase 2 begins at Session 5.

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| Registry covers all 38 items with tests against real fixtures | Pass | 41 entries: the 38 the plan enumerates plus the three current-liability lines Short-Term Debt sums, which the plan wrote as a chain and which open question 4 showed could not be one. Every chain resolves against all five fixtures; the only entry that resolves for none is Short-Term Debt itself, whose one tag no fixture uses, and which is derived for all five. Three chain tags are exercised by no fixture and a test names them, so a proposal cannot pass for a verified chain. |
| Every value in the API payload and exports carries reported, derived or missing provenance | Pass | 1,185 values across the five fixtures in the single-company table, every one in exactly one of the three states: 913 reported, 81 derived, 191 missing. The peer table returns the same counts for the same companies, and test_periods.py asserts value and state agree cell for cell on every fixture. The Excel Source Tags sheet writes one line per value, checked at rows times columns for each fixture, and the CSV names every tag a row used. |
| Banks, insurers and IFRS filers get explicit messages | Pass | JPMorgan Chase is refused on the SIC range with the message V2_PLAN fixes, SAP SE on having no us-gaap facts at all, and the statement-shape heuristic is exercised synthetically because a correctly classified bank cannot test a misclassification. Neither refusal touches the puller: JPMorgan's table still loads and its balance sheet still ties. test_scope_gate.py. |
| Existing single-company and peer features unchanged from the user's point of view except for honest labels | Pass, with one deliberate addition | Every v1 feature is still covered by the restored suite, all green. The changes a user sees are the ones the plan asked for: honest labels, three-state provenance, per-value source tags, refusal messages, and years that used to be dropped. The addition is the Total Debt row, which V2_PLAN 1.1 lists as a derived item and Session 3 deliberately withheld until its derivation was right. |

Two caveats recorded rather than waived. Open questions 8 and 9 are both about
what a period is called, not what it holds: Kroger's fiscal 2025 is labelled
FY2026, and its fourth quarter is labelled Q1. No value is wrong in either case
and the annual table, which is the one the app shows, is unaffected by the
second. They matter first at Phase 2's hand-check, where a column heading that
disagrees with the 10-K's own will cost the checker time, so they should be
settled before Session 6.

**Both were settled in Session 4C**, before Phase 2 began, and neither moved a
value. Kroger's annual headings now read the way its own 10-K cover pages do and
its fourth quarters are numbered Q4. The residue is open question 10, which is
about the calendar year a quarter label carries rather than about the quarter.

## Open questions

1. **Closed.** The Long-Term Debt chain gains
   LongTermDebtAndCapitalLeaseObligations between LongTermDebtNoncurrent and
   LongTermDebt, and despite its name it is a non-current balance: its current
   half is a separate tag the row does not read. Honeywell's row now reads
   27,141 million for FY2025, its balance sheet's own long-term debt line,
   against the 29,046 the LongTermDebt tag holds, and comes from one tag for all
   eighteen years where the old chain seamed at every restatement.

   One number came out other than predicted, and the reason is worth keeping.
   This entry expected FY2024 to read 25,479. It reads 25,440, because
   Honeywell's FY2025 10-K re-presents the 2024 balance sheet for the Solstice
   spin-off and moves 39 million of debt into liabilities held for sale. Both
   are the same line, and the row takes the one the most recent annual report
   gives, which is the same rule that already puts FY2024 revenue at 34,717
   rather than the 38,498 first reported. What the correction promised is what
   it delivered: 27,265 stops winning, and so does the 26,826 the 10-Qs put in
   the same tag. Tests assert all three.

   The caveat stays in the registry because the LongTermDebt fallback stays, and
   it now names who reaches it: Apple for FY2012 and FY2013, when it carried no
   current maturities for the tag to be broader by, and JPMorgan throughout, for
   which no scaffold is generated anyway.

2. **Closed.** app/templates/index.html no longer carries its own DOLLAR_ITEMS,
   EPS_ITEMS, SHARE_ITEMS, or ALL_LINE_ITEMS. The homepage injects
   line_items.classification_for_client() and the page builds its sets from that.
   A test reads the template source and fails if a hardcoded list reappears.

3. **Closed.** R5 shadowing is fixed, and it was the same defect as open question
   6 rather than a separate one. Honeywell's 2025-12-31 balance sheet carried the
   label "Q2" because the July 2026 10-Q repeated it and won on filing date;
   ranking annual reports first hands the period back to the 10-K, which labeled
   it FY, and the relabeling never happens. Apple's seven PERIOD_UNRESOLVED cells
   are gone the same way, and its table is now 154 reported values out of 154.
   The period engine in app/periods.py then removed the mechanism rather than
   just this instance: both views judge a period by dates, so neither can be told
   a fiscal year is a quarter again. The flag itself stays, for a value that
   carries a period's end date while covering some other span; test_periods.py
   holds the case, since no committed fixture has one.

4. **Closed.** Short-Term Debt keeps one tag, DebtCurrent, which is the only
   element that means a filer's whole current debt balance, and is otherwise a
   sum of three current-liability lines that are now registry items of their own:
   current maturities of long-term debt, commercial paper, and short-term
   borrowings. Not one of the five fixtures tags DebtCurrent, so for all of them
   the row is the sum. The terms are optional and at least one must be present,
   which is the first rule in the project to work that way; the decisions log
   records why, and why it is confined to this one.

   Apple's FY2023 Total Debt reads 111,088 million, the figure this entry named,
   against the 105,103 the chain produced. Honeywell's FY2025 reads 34,580,
   which is 27,141 plus 1,546 plus 5,893 off the face of its balance sheet with
   nothing counted twice, and that needed open question 1 fixed first: on the old
   chain its long-term row overlapped its own current maturities. Kroger's reads
   15,875, which is exactly what Kroger's own LongTermDebt tag holds for that
   instant, a cross-check from a tag the row does not read. JPMorgan gets no row,
   because it reports no long-term debt and a total missing an input stays
   missing.

   OtherShortTermBorrowings is deliberately in no chain: Apple tags it and
   CommercialPaper for the same instant with the same 5,980 million, so it is an
   alias for that line and would have double counted the whole of it.

   Total Debt is now displayed in both tables, both workbooks and the CSV. The
   tripwire Session 3 left was retired in the commit that made it wrong, and
   replaced by tests that guard the fix.

5. **Closed.** The Excel Source Tags sheet is one line per value, in both the
   single-company and the peer workbook: line item, period, state, tag, filed
   date, accession, and a note carrying the derivation formula, the missing
   pointer, or the TAG_TRANSITION seam. The row-level Source Tag column, which is
   all the CSV can hold, now names every tag the row used in period order rather
   than one standing in for all of them.

6. **Closed.** Annual report forms now outrank every other form for the same
   period, and filing date decides inside the rank, in both resolve_line_item and
   deduplicate_period. JPMorgan's five shadowed years read 48,334, 37,676, 49,552,
   58,471 and 57,048 million, each from a 10-K. The proxy's rounded figures are
   still in the payload and test_scope_gate.py asserts both, so the rule cannot
   quietly revert. See the Session 4A detail for everything else the change moved.

7. **Closed.** The three series now meet on (start, end) and ignore the unit,
   which is the only thing net income in USD, a share count in shares, and EPS in
   USD-per-share can agree on. The check also skips periods that are not one
   quarter or one year: a year-to-date column ends on the same day as the quarter
   that closes it, and a flag reaches a cell by its end date, so the flag would
   have been shown against the wrong numbers.

   Fifty-eight periods flag across the five fixtures and every one was read.
   Honeywell's Q2 2025 is one of them, which is what the check was wanted for.
   Apple contributes five, the quarters either side of its two stock splits,
   where a later 10-K restated the EPS and nothing ever restated the share count,
   so the ratio between reported and computed is exactly the split factor. Kroger
   and SAP contribute none. JPMorgan contributes fifty-two, all one cause: its
   EPS is computed on income available to common shareholders while the check
   divides total net income, so every period is high by the preferred dividend.
   That was proven rather than assumed, by substituting the available-to-common
   figure for the ten periods JPMorgan tags it and watching all ten come inside
   tolerance. They are kept, because a reader multiplying that bank's diluted
   share count by its diluted EPS really will not get its net income; the
   tolerance sorts the rest, and only three of the fifty-two are 2021 or later.

   Nothing was silenced and no tolerance was tuned. The message changed: it used
   to assert "possible share count or unit mismatch" and now names the two things
   it can be. Using available-to-common as the numerator where a filer reports it
   would close JPMorgan's fifty-two properly, and is worth a later session; it
   needs another registry item and another fixture regeneration for a filer no
   scaffold is generated for.

8. **Closed.** A fiscal year is named the way its filer names it. The source is
   the dei DocumentFiscalYearFocus this entry named, and it is in the payload
   after all, though not where the entry expected: the XBRL APIs carry only
   numeric facts, so the focus is in no dei block and companyconcept returns
   404 for it, but EDGAR stamps each filing's focus on every fact that filing
   reported, as the `fy` field the extraction layer already copies. No fixture
   was regenerated and make_fixture.py needed no change.

   What is read from it is not the focus of the filing that first reported each
   period, which this entry proposed and which is wrong twice over for the very
   filer that raised the question. Kroger tags focus 2025 on both the year ended
   1 February 2025 and the year ended 31 January 2026, which would put two
   columns under one name, and its own 10-K prose for the earlier year says
   fiscal year 2024, so the tag is an error rather than a convention. And the
   four years Kroger's first XBRL filing carried all take that filing's single
   focus of 2009, which would put four columns under one name; every filer has
   that shape at the start of its history.

   So the offset between a filing's focus and the calendar year of its own year
   end is what is read, and the commonest offset wins. Kroger's nineteen annual
   filings vote 17 to 2 for one; Honeywell's seventeen vote 16 to 1 for zero,
   its 2021 annual report having tagged 2020; Apple and JPMorgan are unanimous
   at zero. Kroger's nineteen columns each move back a year, no two share a
   name, and no other filer moves at all, because zero is the old end-year rule
   exactly and is also the fallback where a payload names no fiscal year.

   The rejected repair is now running code rather than prose: test_periods.py
   builds a synthetic Nike-shaped filer, a 31 May year end named for the later
   year, and asserts that naming a fiscal year for the calendar year holding
   most of it would rename it FY2024 while fixing Kroger.

9. **Closed.** Quarters are numbered by how far through their fiscal year they
   end, in quarters, rounded to the nearest one, between two year ends the
   engine has already confirmed. Kroger's fourth quarter reads Q4 and the strict
   xfail in test_kroger.py is a plain passing test.

   Eighteen columns change across the five fixtures and every one is a
   correction. Kroger gains seventeen: the five fourth quarters this entry
   named, and twelve first and second quarters from before fiscal 2019 that
   EDGAR had numbered against a calendar year. Honeywell gains one, the quarter
   ended 30 September 2020, whose surviving copy sits in a 10-Q that is itself
   mis-stamped Q2 -- fp being wrong on a filing rather than borrowed from one,
   which no other fixture shows. Apple's 55 quarter ends and JPMorgan's 54 are
   unchanged.

   Which quarters exist was deliberately not touched: a period still needs a
   filing to have called it a quarter before it is a column, so the column set
   and every value in it are identical before and after. Numbering answers what
   a period is called, not whether it happened.

10. **Closed.** A quarter is named for the fiscal year it belongs to, which is
    the year ending on the first confirmed year end at or after it, named by
    the same offset open question 8 introduced. Kroger's fourth quarter reads
    Q4 FY2025 where it read "Q4 2026", and Apple's quarter ending 28 December
    2024 reads Q1 FY2025 where it read "Q1 2024". Both were wrong in opposite
    directions under the calendar-year rule, which is why fixing one filer's
    labels by hand would have broken the other's.

    All 223 quarter columns across the four us-gaap fixtures are relabelled and
    no column set changes. Honeywell's 55 and JPMorgan's 54 gain the FY prefix
    and keep their year, being calendar-year filers whose quarters end inside
    the year they are named for. Apple's 18 December quarters each move forward
    a year and its other 37 keep theirs. Kroger's 59 all move back a year, its
    offset being one. Every annual label, every value and every provenance
    record is identical before and after; the comparison was run cell by cell
    over both views on all five fixtures.

    A quarter of a fiscal year that has not closed has no year end after it, so
    the filer's own median year length projects where the next one falls, which
    is the stand-in quarter numbering already used for the same case. A quarter
    with no confirmed year end anywhere keeps the calendar year of its end
    date, which is exactly the rule this replaces.

11. **Closed.** The second of the three ways out was taken: the threshold is
    untouched and what changed is where the flag is raised. The income
    statement and the cash flow statement keep it, because there it still
    singles something out. The balance sheet reports the same measurement as a
    per-section coverage percentage on the Checks sheet, written as live
    arithmetic over the subtotal and its plug rather than as a number this code
    computed and typed in.

    That removes 72 flagged cells and adds 25 measured ones per filer, five
    sections over five years. Coverage is the components' share of the
    subtotal, so it is one minus the plug's share and the two readings cannot
    disagree; a test asserts the identity on all 75 cells across the three
    filers, and the evaluation harness asserts the workbook's own arithmetic
    agrees with the spec on 50 of them.

    What the numbers say now they are reported rather than warned about:

    | Section | Apple FY2025 | Honeywell FY2025 | Kroger FY2025 |
    | --- | --- | --- | --- |
    | Total current assets | 68 | 88 | 38 |
    | Total assets | 59 | 85 | 84 |
    | Total current liabilities | 55 | 59 | 66 |
    | Total liabilities | 85 | 86 | 74 |
    | Total equity | -19 | 339 | 486 |

    Nothing is clamped and no absolute value is taken. Equity has one
    component, retained earnings, measured against a total that treasury stock
    and accumulated other comprehensive income pull down, so the figure runs
    from minus 34 to plus 486 percent across these filers and every one of
    those is the honest reading. Forcing it into a nought-to-one range would
    hide the only thing that section has to say. The sheet's note says what
    above 100 and below zero mean, and says that a figure far from 100 limits
    the breakdown above it and never the subtotal itself, which is the filer's
    own reported number either way.

    The registry was not widened. That is the honest fix and the expensive one,
    it is exactly the open-ended tag archaeology V2_PLAN R3 warns against, and
    it needs its own session and a time-box.

12. **Closed.** The checklist line changes rather than the registry. It now
    reads that the retained earnings residual is explained by buybacks and
    other equity movements, and the checker records the figure and what
    accounts for it instead of confirming a zero that cannot happen for any
    filer. The workbook is unchanged: the row was already labelled a residual,
    already left uncoloured, and already reported its number.

    Adding the equity-movement items so the row could tie is the same trade-off
    as open question 11 and was rejected for the same reason. A line item that
    can never be signed off is not a check; it is a checklist nobody finishes.

    docs/acceptance/3s_checklist.md says where it departs from V2_PLAN Part 4's
    template and why, because the template is the planning-time original and
    Part 9's convention is that the running copy of a decision lives here.
