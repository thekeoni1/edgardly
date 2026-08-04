# Edgardly v2 session prompts

Staggered work sessions covering the pre-Phase-1 fixes, Phase 1, and Phase 2 of
docs/V2_PLAN.md. Each prompt is self-contained: paste one into a fresh Claude Code session,
and it loads its own context before doing anything. Session 4 was split into 4A and 4B once
it was clear how much moved with the period engine; the entry says why. Session 4C is a
short interstitial that settles the two naming questions Phase 1's exit review left open.

Rules of use:

- Do not start session N+1 until session N's exit criteria are met.
- Every session begins by reading docs/V2_PLAN.md and PROGRESS.md, and ends by updating
  PROGRESS.md.
- Two constraints are inviolable in every session: never guess or auto-fill a financial
  value, and keep all v1 features working.

## Session 1. Restore the foundation (F1 through F5, docs first)

Read docs/V2_PLAN.md (Parts 1 and 2) and PROGRESS.md first. This session is pre-Phase-1
fixes only, no new features. Order matters: documentation accuracy comes first so the repo
stops making unverifiable claims before any code moves.

1. README corrections per V2_PLAN F4: remove the LTM claim, the SIC and filer-category
   search-filter claim, and the "color-coded hardcoded vs. calculated" claim; soften
   "populated financial model". Sweep any other doc that makes claims (run.bat and
   run.command comments, docstrings that overstate). Plain prose, no em dashes. Commit.
2. Replace the placeholder User-Agent contact in app/edgar_api.py with a real address.
   Commit.
3. Restore the test suite from git history: `git checkout 4e1d457^ -- app/tests
   app/pytest.ini`, restore pytest and pytest-timeout to app/requirements.txt. Run the
   suite. Fix quick failures; mark anything slow to fix as xfail with a reason comment and
   list them in PROGRESS.md. Time-box triage. Commit.
4. Fix the Total Debt row honestly: it currently picks one of DebtCurrent, LongTermDebt, or
   the combined tag instead of summing. Relabel per V2_PLAN F2, adjust tests, and update the
   README's extracted-items list to match the new label. Commit.
5. Consolidate the duplicated line-item classification sets and scale thresholds from
   app/app.py and app/peer_comparison.py into a new app/line_items.py (constants only this
   session; the registry comes next session). Commit.

Constraints: never guess or auto-fill financial values anywhere; keep all v1 features
working; follow existing code style and test conventions.

Exit criteria: full suite green (xfails documented), five separate commits in the order
above, PROGRESS.md updated with the xfail count and any surprises.

## Session 2. Registry and per-period resolution (1.1, 1.2, and part of 1.5)

Read docs/V2_PLAN.md (Part 3) and PROGRESS.md first.

1. Build the canonical line-item registry in app/line_items.py per V2_PLAN 1.1: every
   reported item enumerated there, with fallback chains, statement, kind, and unit metadata,
   and derivation rules for Total Debt and EBITDA. TAG_MAP moves here and xbrl_extractor
   imports it for compatibility. In the Long-Term Debt entry, note that the LongTermDebt
   fallback can include current maturities (see PROGRESS.md open question 1).
2. Replace winner-takes-all tag resolution with per-period stitching per V2_PLAN 1.2,
   including the TAG_TRANSITION flag at seams. Peer comparison must keep working unchanged.
3. Create scripts/make_fixture.py (downloads a companyfacts payload and trims it to registry
   tags) and commit the first fixture: Apple, CIK 320193. Add tests asserting real FY2023
   numbers from the fixture, the FY2018 revenue tag transition, and D&A resolving from the
   cash flow statement.
4. Serve line-item classification from the server (small JSON endpoint or template injection
   from app/line_items.py) and delete the duplicated DOLLAR_ITEMS, EPS_ITEMS, SHARE_ITEMS,
   and ALL_LINE_ITEMS lists from app/templates/index.html, closing PROGRESS.md open
   question 2.

Constraints: no network in tests; never guess values; existing 14-item UI behavior
unchanged.

Exit criteria: suite green including the new fixture tests, Apple history no longer
truncated at the tag switch, index.html no longer holds its own line-item lists,
PROGRESS.md updated.

## Session 3. Provenance and scope gate (1.3, 1.4)

Read docs/V2_PLAN.md (Part 3) and PROGRESS.md first, including open questions 1, 3, 4, and 5
from Sessions 1 and 2.

0. Amend this Session 3 entry to match the steps below, so the doc reflects what the session
   actually does. Commit separately or with step 1.
1. Implement the three-state provenance model per V2_PLAN 1.3, per value, not per row: every
   data point is reported (tag, filed date, accession -- the tag can differ across periods in
   a stitched row), derived (formula string), or missing (a flag plus a pointer URL built
   from the accession number, naming the statement to check). Wire it through the API
   payloads, the UI, and both Excel exports. The Source Tags sheet must show per-period tags
   and TAG_TRANSITION seams instead of one tag_used per row (PROGRESS.md open question 5).
   The blue and black font split now reflects reported versus derived for real.
2. Do not surface Total Debt in any view or export this session. Its derivation is knowingly
   understated for filers that skip DebtCurrent (open question 4) and is fixed in Session 4.
3. Implement the out-of-scope gate per V2_PLAN 1.4: SIC 6020 through 6199 and 6311 through
   6411 refused for scaffolds with the exact message in the plan doc; IFRS-only filers get
   their own message instead of a silent empty table. The puller and peer comparison still
   work for these companies. SIC codes come from the submissions API, not companyfacts;
   extend scripts/make_fixture.py if the fixtures need that data captured.
4. Add fixtures with scripts/make_fixture.py: one large bank (rejection test) and one
   IFRS-only filer (message test). Verify the CIKs against the live ticker lookup before
   committing; note the choices in PROGRESS.md.

Constraints: no network in tests; never guess values; existing 14-item UI behavior unchanged
apart from provenance display.

Exit criteria: suite green, provenance visible end to end for Apple including per-period tags
in the Source Tags sheet, refusal messages tested against the new fixtures, PROGRESS.md
updated.

## Session 4A. Unify the period engine (rest of 1.5, plus R5)

Session 4 was one session covering the period engine, the last two fixtures, the chain
corrections, and the Phase 1 exit review. That is more than one sitting can hold: unifying
resolution moves numbers for every company, and the comparison that proves it moved them
correctly has to happen in the same session as the change. So the engine work and the
validation it needs are 4A, and the chain corrections and the exit review are 4B.

Read docs/V2_PLAN.md (Part 3, Part 8 R5) and PROGRESS.md first, especially open questions 3
and 6.

0. Amend this Session 4 entry into 4A and 4B entries, in the same file update. Commit
   separately or with step 1.
1. Fix resolution ranking per open question 6: annual report forms (10-K, 10-K/A, 20-F and
   variants) outrank other forms; filing date decides within a rank. Apply identically in
   resolve_line_item and deduplicate_period. The JPMorgan fixture test asserting 49,600 must
   now assert 49,552 for all five affected years.
2. Add the Honeywell fixture (CIK 773840) with scripts/make_fixture.py. Add a test
   reproducing the shadowing bug before the fix: the 2025-12-31 instant labeled Q2, recent
   years missing from the single-company path.
3. Unify the period engine per V2_PLAN and R5: make `_build_xbrl_result` in app/app.py use
   the peer path's date-anchored logic, extracting the shared engine into one module.
   Apple's 7 PERIOD_UNRESOLVED holes must resolve to reported values; Honeywell's dropped
   years must appear; the PERIOD_UNRESOLVED flag stays in the codebase for values that
   genuinely cannot be date-confirmed.
4. Compare old versus new resolution across all 14 displayed items on all committed
   fixtures; record gains, losses, and changed values in PROGRESS.md. Losses and changed
   values need an explanation each, or they are bugs.

Constraints: no network in tests; never guess values; peer comparison results must not
change except where a proxy-statement value is corrected to the 10-K figure.

Exit criteria: suite green, Apple single-company table has zero PERIOD_UNRESOLVED holes,
Honeywell recent years present, JPMorgan FY2023 net income reads 49,552, PROGRESS.md
updated.

## Session 4B. Chain corrections and the Phase 1 exit review

Read docs/V2_PLAN.md (Part 3) and PROGRESS.md first, especially open questions 1, 4, and 7
and the Session 4A detail.

0. Amend this Session 4B entry to match the steps below. Commit separately or with step 1.
1. Add the Kroger fixture (CIK 56873) with scripts/make_fixture.py; its late-January
   52/53-week FYE is the point. Confirm the cell-for-cell view-agreement test in
   test_periods.py picks it up automatically, and add Kroger-specific period tests.
2. Correct the Long-Term Debt chain per open question 1:
   LongTermDebtAndCapitalLeaseObligations ahead of LongTermDebt. Honeywell's row must show
   its balance-sheet non-current line (25,479 for 2024-12-31); assert the old 27,265 does
   not win. Keep the registry caveat accurate for filers still landing on LongTermDebt.
3. Validate every registry chain against all five fixtures (Apple, Honeywell, Kroger,
   JPMorgan, SAP). Correct chains with one-line registry edits; record each correction and
   its evidence in PROGRESS.md.
4. Fix Short-Term Debt per open question 4: a summed derivation (current maturities plus
   commercial paper plus short-term borrowings, each term optional but at least one
   present), never a chain pick. Apple's derived Total Debt must equal 111,088 million for
   FY2023, and the Honeywell sum must not double-count current maturities now that step 2
   makes the long-term row strictly non-current. Then surface Total Debt in views and
   exports as a derived value with its formula in provenance, and retire the tripwire test
   deliberately in the same commit.
5. Fix the EPS reconciliation check per open question 7: key net income, shares, and EPS on
   (start, end), ignoring unit. Assert it flags Honeywell's Q2 2025 mixed-basis column.
   Review every new flag it raises across the fixtures: each is either a genuine mismatch
   (keep, document) or a tolerance problem (tune, document). Never silence one without a
   reason in PROGRESS.md.
6. Run the Phase 1 exit review against V2_PLAN's exit criteria; record pass or fail per
   criterion in PROGRESS.md and declare Phase 1 done only if all pass.

Constraints: no network in tests; never guess values; a chain that resolves nothing for a
filer stays a flagged blank, never a substitute.

Exit criteria: suite green, single-company and peer views agree on periods for all fixture
companies, Phase 1 declared done in PROGRESS.md.

## Session 4C. Period names

A short interstitial before Phase 2. Phase 1's exit review passed with two caveats, open
questions 8 and 9, and both are about what a period is called rather than what it holds.
They are settled here because Phase 2's hand-check is the first place a column heading that
disagrees with the filer's own costs somebody time.

Read PROGRESS.md open questions 8 and 9 and the Session 4B detail first.

0. Amend this Session 4C entry to match the steps below. Commit separately or with step 1.
1. Fix fiscal-year naming per open question 8: take the label from the filer's dei
   DocumentFiscalYearFocus, read from the earliest annual filing that first reported the
   period end (the same lookup filing_pointers uses), falling back to the current end-year
   rule only when no focus value exists. Kroger's 2025-02-02 to 2026-01-31 year must read
   FY2025; Apple's and Honeywell's labels must not change; add a synthetic test for a
   Nike-shaped filer (May FYE named for the later year) to pin the reason the
   calendar-majority rule was rejected.
2. Fix quarter numbering per open question 9: number quarters by position between two
   confirmed fiscal year ends, from dates the engine already has, instead of trusting the
   filing's fp. The strict xfail in test_kroger.py must flip to a pass. Verify quarter
   labels are unchanged for Apple and Honeywell.
3. Regenerate no fixtures; both fixes read data already captured. If DocumentFiscalYearFocus
   turns out not to be in the companyfacts payload (it is a dei fact), extend
   make_fixture.py to capture it and regenerate; note which path was taken in PROGRESS.md.

Constraints: no network in tests; never guess values; annual values, provenance, and peer
alignment must be byte-identical before and after, labels only.

Exit criteria: suite green with the OQ9 xfail now a plain pass, Kroger headers match its
10-K cover page, PROGRESS.md updated and open questions 8 and 9 closed.

## Session 5. Scaffold engine and Excel kit (2.1, 2.2, 2.2b, 2.5)

Read docs/V2_PLAN.md (Part 4 and Part 8 R1, R2, R4) and PROGRESS.md first.

1. Build app/scaffold/three_statement.py: the model spec of rows, periods, and provenance,
   including plug rows per the decisions log, and flag any plug exceeding 10 percent of its
   statement total.
2. Build app/scaffold/excel.py as a reusable kit per V2_PLAN 2.2: statement blocks, asm_*
   named inputs, forecast rows guarded with IF(ISBLANK(...)), check rows, and provenance
   comments. Do not hardcode sheet names or column counts.
3. Add the formula-evaluation harness using the `formulas` library: tests generate a workbook
   from a fixture, evaluate it, and assert that the balance check equals zero and that
   forecasts are blank when assumptions are blank. Constrain scaffold formulas to what the
   library evaluates.

Exit criteria: suite green including evaluated-formula tests for Apple, and the workbook
opens in Excel with no repair prompt (manual check, noted in PROGRESS.md).

## Session 6. Endpoint, UI, and acceptance (2.3, 2.4)

Read docs/V2_PLAN.md (Part 4) and PROGRESS.md first.

1. Add POST /api/scaffold/three-statement plus a UI button, with refusal messages surfaced.
2. Create docs/acceptance/3s_checklist.md and docs/acceptance/breakage_log.md from the
   templates in V2_PLAN Part 4.
3. Generate scaffolds for Apple, Honeywell, and Kroger. The human hand-checks them against
   the 10-Ks using the checklist, which is resumable across sittings. Fix or convert to
   flagged blanks everything logged.

Exit criteria: three signed checklists, breakage log empty or all entries resolved, Phase 2
declared done in PROGRESS.md. Phase 3 planning happens only after the trading comps course
gate opens.
