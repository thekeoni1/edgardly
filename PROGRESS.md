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

## Session log

One entry per work session. Record what shipped, the xfail count after the session, and any
open questions the next session needs to know about.

| Date | Session | Shipped | xfails | Open questions |
| --- | --- | --- | --- | --- |
| 2026-08-03 | Setup | Folded the planning output into the repo: risk register R1 through R10 as V2_PLAN Part 8, decisions log as Part 9, tasks 2.2b and 2.5 added to Phase 2, docs/SESSIONS.md created, this file created. Documentation only, no code changes. | n/a | None |
| 2026-08-03 | 1 | F1 through F5, five commits in the prescribed order. README claims corrected, real SEC User-Agent contact, test suite restored from git history, Total Debt relabeled Long-Term Debt, line-item constants consolidated into app/line_items.py. | 0 | Three, listed below. |

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

## Open questions

1. **LongTermDebt is not strictly non-current.** Honeywell resolves the Long-Term
   Debt row through the us-gaap LongTermDebt tag, whose definition can include
   current maturities, so for that filer the row is slightly broader than its
   label. It is still honest in a way the old Total Debt row was not, but the
   chain needs validating against real fixtures. Do this in Session 2 when the
   registry lands, and again in Session 4 when Honeywell and Kroger fixtures
   arrive.

2. **The frontend still duplicates the unit-class sets.** app/templates/index.html
   carries its own DOLLAR_ITEMS, EPS_ITEMS, SHARE_ITEMS, and ALL_LINE_ITEMS lists.
   Session 1 consolidated only the two Python copies, per the session prompt.
   Removing the third copy needs the browser to read the classification from the
   server, which is worth doing in Session 2 when the registry gives it something
   worth serving.

3. **R5 shadowing is confirmed live, not theoretical.** Honeywell's 2025-12-31
   year-end balance sheet instant carries fiscal_period "Q2" because a later 10-Q
   overwrote the label, so the single-company path drops recent years that the
   peer path keeps. Session 4 is where this gets fixed; noting it here as
   confirmation the risk is real and reproducible with CIK 773840.
