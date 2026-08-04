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
| 2026-08-04 | Periods are decided by dates, never by the fiscal_period label | Both views run on app/periods.py. A flow item covers a period when its span is 10 to 14 months (a year) or 2 to 4 months (a quarter); an instant, having no span, is anchored to a period some measurable item already confirmed. EDGAR stamps fp on the filing rather than the fact, so the label describes whoever filed last, not the fact. Nothing invents a period: a value carrying a confirmed end date that covers something else is reported as PERIOD_UNRESOLVED, not shown. |

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

## Open questions

1. **LongTermDebt is not strictly non-current, and for Honeywell it is not the
   balance sheet either.** Honeywell resolves the Long-Term Debt row through the
   us-gaap LongTermDebt tag, whose definition can include current maturities, so
   for that filer the row is broader than its label. Session 2 wrote the caveat
   into the registry entry and into the Total Debt derivation note, since summing
   a LongTermDebt row with Short-Term Debt double-counts the current maturities.
   The Honeywell fixture, added in Session 4A, settles what the tag holds and
   makes it worse than expected. For 2024-12-31 Honeywell's 10-Qs tag LongTermDebt
   as 26,826 million, which is exactly the balance sheet:
   LongTermDebtAndCapitalLeaseObligations of 25,479 plus a current portion of
   1,347. The FY2024 10-K tags the same instant as 27,265, another 439 higher.
   Since Session 4A ranks the annual report first, the row shows 27,265, a figure
   that is neither the non-current balance nor the balance-sheet total. Honeywell
   does report LongTermDebtAndCapitalLeaseObligations, which is the non-current
   line the row claims to be, so this looks like a one-line chain correction.
   Session 4B owns it, together with open question 4, because the two share the
   same arithmetic.

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

4. **Short-Term Debt understates for filers that skip DebtCurrent.** Apple tags
   no DebtCurrent, so the row falls through to LongTermDebtCurrent, which is
   current maturities only, and misses the 5,985 million of commercial paper on
   the FY2023 balance sheet. The derived Total Debt is short by exactly that
   amount: 105,103 million against a real 111,088 million. A test asserts both
   figures rather than hiding the gap. Closing it needs a summed derivation
   (current maturities plus commercial paper plus short-term borrowings), not a
   chain reorder, because a chain picks one tag and the components have to add.
   Decide in Session 4B alongside the other chain corrections, and alongside open
   question 1, whose Honeywell evidence is the other half of the same sum. Until
   then, no view
   shows Total Debt, so nothing user-facing is wrong today. Session 3 kept it that
   way deliberately and left a test that fails the moment Total Debt appears in a
   payload, so the next session has to fix the derivation before surfacing it.

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

7. **The EPS reconciliation check has never fired on real data.** It looks up
   net income, diluted shares and diluted EPS by _period_key, which is
   (unit, start, end). Net income is in USD, shares are in shares, and EPS is in
   USD/shares, so the keys can never match and the check returns nothing for
   every company. Its tests pass because the helper builds all three points with
   the same unit. Found in Session 4A while looking for the flag that should have
   caught Honeywell's Q2 2025 column, where EPS of 2.46 sits beside a share count
   of 318.8 million and net income of 1,570 million because the EPS figure comes
   from the FY2025 10-K and the share count from a 10-Q filed after Honeywell
   halved its shares. Left alone deliberately: fixing it raises new flags on
   every company, and Session 4A was constrained not to change peer results
   beyond the proxy correction. The fix is to key the three series on
   (start, end) and ignore the unit, which is the only thing they can agree on.
