# Edgardly v2 session prompts

Six staggered work sessions covering the pre-Phase-1 fixes, Phase 1, and Phase 2 of
docs/V2_PLAN.md. Each prompt is self-contained: paste one into a fresh Claude Code session,
and it loads its own context before doing anything.

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

Read docs/V2_PLAN.md (Part 3) and PROGRESS.md first.

1. Implement the three-state provenance model per V2_PLAN 1.3: every value is reported (tag,
   filed date, accession), derived (formula string), or missing (a flag plus a pointer URL
   built from the accession number, naming the statement to check). Wire it through the API
   payloads, the UI, and both Excel exports; the blue and black font split now reflects
   reported versus derived for real.
2. Implement the out-of-scope gate per V2_PLAN 1.4: SIC 6020 through 6199 and 6311 through
   6411 refused for scaffolds with the exact message in the plan doc; IFRS-only filers get
   their own message instead of a silent empty table. The puller and peer comparison still
   work for these companies.
3. Add fixtures: one bank (rejection test) and one IFRS filer (message test).

Exit criteria: suite green, provenance visible end to end for Apple, refusal messages
tested, PROGRESS.md updated.

## Session 4. Unify the period engine and finish Phase 1 (rest of 1.5, plus R5)

Read docs/V2_PLAN.md (Part 3 and Part 8 R5) and PROGRESS.md first.

1. Make the single-company path (`_build_xbrl_result` in app/app.py) use the peer path's
   date-anchored period engine so shadowed 10-K entries are no longer dropped, and extract
   the shared logic into one module.
2. Add the remaining acceptance fixtures: Honeywell, CIK 773840, and Kroger, CIK 56873.
   Validate every registry chain against all fixtures and correct chains as needed (one-line
   registry edits).
3. Run the Phase 1 exit review against V2_PLAN's exit criteria and record pass or fail per
   criterion in PROGRESS.md.

Exit criteria: suite green, single-company and peer views agree on periods for all fixture
companies, Phase 1 declared done in PROGRESS.md.

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
