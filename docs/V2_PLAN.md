# Edgardly v2 Plan

Written 2026-08-01. Scope: turn Edgardly from a data puller into a model scaffolder that
generates the mechanical skeleton of standard finance models in Excel, with real historicals
from filings and every judgment input left blank for the analyst. The tool never fills in
assumptions, forecasts, or price targets.

## Part 1. Audit of the current data layer

### What is pulled today

All XBRL extraction is driven by `TAG_MAP` in `app/xbrl_extractor.py` (lines 18-70).
It covers 14 line items, all from the `us-gaap` taxonomy:

Revenue, Cost of Revenue, Gross Profit, Operating Income, Net Income, EPS Basic,
EPS Diluted, Shares Outstanding (Basic), Shares Outstanding (Diluted), Total Assets,
Total Liabilities, Total Equity, Cash and Equivalents, Total Debt.

Nothing from the cash flow statement is pulled. There is no D&A, capex, interest expense,
tax expense, SG&A, R&D, working capital detail, retained earnings, dividends, or buybacks.
The `ifrs-full` and `dei` taxonomies are never read, so foreign private issuers that file
under IFRS come back completely empty with no explanation.

### Fallback chains

Five items have chains (Revenue has 4 tags, Cost of Revenue 3, Net Income 2, Total Equity 2,
Total Debt 3). The other nine are single tags.

Resolution is winner-takes-all per line item: `resolve_line_item` picks the one tag whose
most recent annual data point is newest, and uses that tag's data for the entire history.
Two consequences:

1. History truncation after tag switches. When a company moved from `Revenues` to
   `RevenueFromContractWithCustomerExcludingAssessedTax` (Apple, FY2018), only the periods
   the new tag happens to include as comparatives survive. Older years reported solely under
   the old tag are dropped, even though they are sitting in the same companyfacts response.
2. Total Debt is semantically wrong. The chain (`DebtCurrent`, `LongTermDebt`,
   `DebtLongtermAndShorttermCombinedAmount`) is treated as pick-one, but total debt is a sum
   of current and long-term. If `DebtCurrent` wins, the row labeled Total Debt shows only
   current debt. This can be materially understated today.

### Missing-tag behavior

No crashes and no silent zeros: a missing value renders as "Not reported" or "N/A" in grey
italic, and a line item with no tag at all shows "not found" on the Source Tags sheet. The
only flag for missingness is `MISSING_CRITICAL_DATA`, raised only when Revenue and Net Income
are both absent. There is no pointer to where in the filing to look, and no derivation is
ever attempted (a company that reports no `GrossProfit` tag shows blank even though
Revenue minus Cost of Revenue is on the same sheet). The D&A-buried-in-COGS scenario cannot
arise yet because D&A is not extracted at all.

### Source-tag transparency

Genuinely good and end-to-end. Every data point carries its tag, filed date, and accession
number from `_parse_entries` through the UI tooltips, the CSV Source Tag column, and the
Excel Source Tags sheet. One gap: the export code distinguishes "extracted" (blue) from
"calculated" (black) fonts, but every current line item is classed as extracted, so the
calculated style never fires. There is no provenance category for derived or missing values
yet; Phase 1 adds both.

### Fiscal-period alignment

The peer path (`peer_comparison.py`) is the strong one. It anchors each company's fiscal
calendar on actual period end dates: flow items qualify as annual by period length
(300-425 days) rather than trusting the `fp` label, and balance sheet instants are accepted
when their end date matches a confirmed fiscal year end. This survives non-calendar fiscal
years, 52/53-week years, and the "shadowing" problem where a later 10-Q overwrites the
fiscal-period label on a 10-K data point. Companies are then aligned by relative index
(FY0, FY-1), which is the right call for peers with different year ends.

The single-company path (`_build_xbrl_result` in `app/app.py`) does not use this logic. It
filters by the `fp` label directly, so the same shadowing the peer module works around can
silently drop a year from the single-company table. The two paths should share one period
engine.

Also: the README mentions LTM alignment, but no LTM computation exists anywhere in the code.
Quarterly view has holes for Q4 because EDGAR often lacks discrete Q4 flow values (only FY),
and no Q4 = FY minus Q1-Q3 derivation is attempted.

### Excel export capabilities

`openpyxl` exports are static values plus formatting (accounting number formats, borders
under subtotals, freeze panes, native line charts). Real formulas exist in exactly one
place: the sanity-check rows (`_write_xlsx_sanity_checks`) write live `=IF(AND(ISNUMBER(...)))`
formulas with conditional formatting. No named ranges, no cross-sheet references, no forecast
columns exist yet. openpyxl supports everything Phase 2 needs (cross-sheet formulas, defined
names, comments). One caveat to design around: openpyxl writes formulas without cached
results, so formula cells display values only after Excel recalculates on open. Automated
tests can assert formula text but not computed results; hand-checking in real Excel is a
required part of acceptance.

### Test suite

The 291 tests do not exist in the working tree. Commit 4e1d457 (June 2026, "Remove test
suite from public repo") deleted `app/tests/` (24 files, 5716 lines), `pytest.ini`, and the
pytest dependencies. They survive only in git history. All 291 were synthetic or mocked:
no test ever used a real-filing fixture, and no test hits the network. Coverage was good
for what it was: every validation check with known-good and known-bad data, dedup logic,
period selection, Excel export structure (re-reading written workbooks), download manager
with mocked HTTP, ticker search. But the extraction pipeline has never been tested against
an actual companyfacts payload.

### README claims vs reality

Per the constraint that README claims stay verifiable, these need correction:

- "aligned by relative fiscal period (LTM, FY0, FY-1...)": LTM is not implemented.
- "search by ... SIC code or sector, SEC filer category": no such search filter exists in
  the UI or API. SIC and filer category appear only as columns in the metadata export.
- "color-coded hardcoded vs. calculated cells": no calculated cells exist yet.
- "get from a company name to a populated financial model": overstates v1; fair for v2 later.

### Other issues found

- `HEADERS` in `edgar_api.py` uses the placeholder `contact@example.com`. SEC asks for a
  real contact in the User-Agent and blocks abusers; this should be a real address.
- Line-item classification sets and dollar/share scale thresholds are duplicated in three
  places (`app.py`, `peer_comparison.py`, and implicitly in the frontend). Drift risk.
- `most_recent_annual` in `xbrl_extractor.py` appears unused.

## Part 2. Fixes before Phase 1

These land first, each independently shippable, repo stays working throughout.

F1. Restore the test suite. `git checkout 4e1d457^ -- app/tests app/pytest.ini`, restore
    pytest and pytest-timeout to `app/requirements.txt`, run it, fix any drift. If keeping
    tests out of the public repo was deliberate, move them to a private location instead,
    but the plan assumes tests live with the code. Every later phase builds on this.
    Files: app/tests/ (restored), app/pytest.ini, app/requirements.txt.

F2. Fix Total Debt semantics. Short term: relabel the current row honestly (for example
    "Long-Term Debt" with its own chain) so no row claims to be a total it is not.
    The real fix (sum of components with a derived provenance) arrives in Phase 1.
    Files: app/xbrl_extractor.py, tests.

F3. Real User-Agent contact. Files: app/edgar_api.py.

F4. README corrections listed above. Files: README.md.

F5. Consolidate line-item classification and scale constants into one module so Phase 1
    has a single place to extend. Files: new app/line_items.py, app/app.py,
    app/peer_comparison.py, tests.

## Part 3. Phase 1, data layer hardening

Goal: a canonical registry of the line items the three models need, per-period tag
resolution, explicit provenance on every value, flagged blanks with filing pointers,
and out-of-scope filer rejection. No model code yet. Existing UI and exports keep working
on the same 14 items they show today; the registry is a superset.

### 1.1 Canonical line-item registry

New module `app/line_items.py`. Each entry: canonical name, statement (IS, BS, CF),
kind (flow or instant), unit class (dollar, eps, shares), fallback tag chain, optional
derivation rule, sign convention note. `TAG_MAP` moves here; `xbrl_extractor` imports it
for backward compatibility.

Proposed registry (28 items reported, plus derived):

Income statement:
- Revenue: Revenues, RevenueFromContractWithCustomerExcludingAssessedTax,
  RevenueFromContractWithCustomerIncludingAssessedTax, SalesRevenueNet, SalesRevenueGoodsNet
- Cost of Revenue: CostOfRevenue, CostOfGoodsAndServicesSold, CostOfGoodsSold,
  CostOfServices
- Gross Profit: GrossProfit; derived fallback: Revenue - Cost of Revenue
- SG&A: SellingGeneralAndAdministrativeExpense, GeneralAndAdministrativeExpense
- R&D: ResearchAndDevelopmentExpense
- Operating Income: OperatingIncomeLoss
- Interest Expense: InterestExpense, InterestExpenseDebt, InterestIncomeExpenseNet
- Pretax Income: IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest,
  IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments
- Income Tax Expense: IncomeTaxExpenseBenefit
- Net Income: NetIncomeLoss, ProfitLoss
- EPS Basic, EPS Diluted, Shares Basic, Shares Diluted: as today

Balance sheet:
- Cash and Equivalents: CashAndCashEquivalentsAtCarryingValue,
  CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents
- Short-Term Investments: ShortTermInvestments, MarketableSecuritiesCurrent
- Accounts Receivable: AccountsReceivableNetCurrent, ReceivablesNetCurrent
- Inventory: InventoryNet
- Total Current Assets: AssetsCurrent
- PP&E Net: PropertyPlantAndEquipmentNet
- Goodwill: Goodwill
- Intangibles: FiniteLivedIntangibleAssetsNet, IntangibleAssetsNetExcludingGoodwill
- Total Assets: Assets
- Accounts Payable: AccountsPayableCurrent, AccountsPayableAndAccruedLiabilitiesCurrent
- Total Current Liabilities: LiabilitiesCurrent
- Short-Term Debt: DebtCurrent, LongTermDebtCurrent, ShortTermBorrowings
- Long-Term Debt: LongTermDebtNoncurrent, LongTermDebt
- Total Liabilities: Liabilities
- Total Equity: StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest,
  StockholdersEquity
- Retained Earnings: RetainedEarningsAccumulatedDeficit

Cash flow statement:
- Cash from Operations: NetCashProvidedByUsedInOperatingActivities,
  NetCashProvidedByUsedInOperatingActivitiesContinuingOperations
- D&A (cash flow source, per the design rule): DepreciationDepletionAndAmortization,
  DepreciationAmortizationAndAccretionNet, Depreciation plus AmortizationOfIntangibleAssets
  as a summed derivation when only components exist
- Stock-Based Compensation: ShareBasedCompensation
- Capex: PaymentsToAcquirePropertyPlantAndEquipment, PaymentsToAcquireProductiveAssets
- Cash from Investing: NetCashProvidedByUsedInInvestingActivities
- Cash from Financing: NetCashProvidedByUsedInFinancingActivities
- Dividends Paid: PaymentsOfDividends, PaymentsOfDividendsCommonStock
- Buybacks: PaymentsForRepurchaseOfCommonStock

Derived (never a reported tag; always carries its formula as provenance):
- Total Debt = Short-Term Debt + Long-Term Debt
- EBITDA = Operating Income + D&A
- Net Working Capital components as needed by the scaffold

Exact chains get validated against the acceptance-company fixtures during implementation;
the registry format makes corrections one-line changes.

Files: app/line_items.py (new), app/xbrl_extractor.py, tests/test_line_items.py (new).

### 1.2 Per-period tag resolution

Replace winner-takes-all with per-period stitching: for each confirmed fiscal period,
consider candidates from every tag in the chain, prefer earlier chain position, break ties
by most recent filed date. Each value already records its own tag, so a series can honestly
mix tags across eras. Add a continuity flag (`TAG_TRANSITION`) on the boundary year when
adjacent periods come from different tags, so the seam is visible rather than hidden.
This also fixes the Apple-style history truncation.

Files: app/xbrl_extractor.py (resolve_line_item and callers), app/peer_comparison.py,
tests.

### 1.3 Provenance on every value

Every output value becomes one of exactly three things:
- reported: value plus tag, filed date, accession number
- derived: value plus formula string naming its inputs (which are themselves reported)
- missing: no value, plus a flag and a pointer

The pointer for missing values is buildable from data already in hand: the accession number
of the period's 10-K gives a filing index URL
(https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/), and the registry knows which
statement the item lives on. Message form: "Not tagged in XBRL. Check the income statement
of the FY2023 10-K: <link>." Never a guess, never a zero.

Files: app/xbrl_extractor.py, app/line_items.py, app/app.py (UI payloads and exports show
the three states; the existing blue/black font split finally becomes meaningful),
app/templates/index.html, tests.

### 1.4 Out-of-scope filer rejection

`edgar_api.get_company_meta` already returns SIC. Add `is_in_scope(sic, facts)` to
`line_items.py`: SIC 6020-6199 (banks and credit institutions) and 6311-6411 (insurance)
are rejected for scaffolds with a clear message ("Bank and insurance financial statements
do not fit the standard three-statement template; Edgardly will not generate a scaffold
for this company"). A secondary heuristic (no Revenue or Cost of Revenue tags but
InterestAndDividendIncomeOperating present) catches financials misclassified by SIC.
The existing puller and peer comparison keep working for these companies; only scaffold
generation refuses. IFRS-only filers (facts contain ifrs-full but not us-gaap) get their
own explicit message instead of today's silent all-blank table.

Files: app/line_items.py, app/edgar_api.py, app/app.py, tests.

### 1.5 Real-filing test fixtures

Add `app/tests/fixtures/` with trimmed companyfacts JSON for the acceptance companies
(Part 4 candidates) plus one bank (rejection test) and one IFRS filer. A committed script
`scripts/make_fixture.py` downloads a companyfacts payload and strips it to the tags in the
registry, keeping fixture files small and regeneration reproducible. All tests stay
network-free. New tests assert real numbers: Apple FY2023 revenue equals 383,285 (in
millions) from the fixture, the tag transition seam is flagged, D&A resolves from the cash
flow statement, and so on.

Files: scripts/make_fixture.py (new), app/tests/fixtures/ (new),
app/tests/test_real_filings.py (new).

Phase 1 exit criteria: registry covers all 28 items with tests against real fixtures;
every value in the API payload and exports carries reported/derived/missing provenance;
banks, insurers, and IFRS filers get explicit messages; existing single-company and peer
features unchanged from the user's point of view except for honest labels.

## Part 4. Phase 2, the 3-statement scaffold

Goal: an Excel workbook with linked historical IS, BS, CF, real cross-sheet formulas,
forecast columns wired to a blank Assumptions sheet. The tool does plumbing; the analyst
does thinking.

### Workbook design

Sheets: Assumptions, Income Statement, Balance Sheet, Cash Flow, Schedules, Checks,
Source Tags.

- Historical columns: reported values written as static numbers with provenance carried in
  cell comments (tag, filed date, accession) and the blue reported / black derived font
  convention. Derived historicals (EBITDA, Total Debt) are written as live Excel formulas
  over the reported rows, not precomputed numbers, so the workbook itself shows the math.
- Assumptions sheet: named input cells (revenue growth by year, gross margin, SG&A percent
  of revenue, D&A percent of revenue or of PP&E, capex percent of revenue, working capital
  days, tax rate, dividend policy), all blank with grey input styling. Each named range like
  `asm_rev_growth_y1`.
- Forecast columns: every cell is a formula referencing prior columns and Assumptions named
  ranges, guarded with IF(ISBLANK(...), "", ...) so an empty assumptions box produces empty
  forecasts, never zeros pretending to be forecasts.
- Linkages (the actual point of the exercise):
  net income flows from IS to the retained earnings roll-forward and to CF top line;
  D&A and working capital deltas bridge NI to cash from operations; capex drives the PP&E
  roll-forward on Schedules; financing rows drive the debt schedule; ending cash on CF ties
  to cash on BS; balance check row computes Assets - Liabilities - Equity per column with
  the existing green/red conditional formatting.
- Checks sheet: balance check, cash tie, retained earnings tie, per column, live formulas.

### Tasks

2.1 Scaffold data assembly: `app/scaffold/__init__.py`, `app/scaffold/three_statement.py`.
    Pulls the registry series for n historical years, runs scope gate, returns a structured
    model spec (rows, periods, provenance) independent of Excel.
    Files: app/scaffold/three_statement.py (new), tests.

2.2 Excel writer kit: `app/scaffold/excel.py` with reusable primitives: write a statement
    block, define a named input, write a forecast formula row, write a check row, attach
    provenance comment. Built as a kit because Phases 3 and 4 reuse it.
    Files: app/scaffold/excel.py (new), tests that re-read the workbook and assert formula
    strings, named ranges, and historical values.

2.2b Plug rows and the plug-size flag (see Part 8, R1). Where tagged components do not sum
    to the reported total, the scaffold writes an explicit derived plug row, for example
    "Other current assets (plug to reported total)", as a live Excel formula rather than a
    filled number. Any plug whose absolute value exceeds 10 percent of its statement total
    raises a flag saying this filer's XBRL is too sparse for a reliable scaffold.
    Files: app/scaffold/three_statement.py, app/scaffold/excel.py, tests.

2.3 Flask endpoint and UI: POST /api/scaffold/three-statement (cik, years, format), a
    button in the XBRL view, refusal messages surfaced in the UI.
    Files: app/app.py, app/templates/index.html, tests.

2.4 Acceptance harness: docs/acceptance/3s_checklist.md (template below) and
    docs/acceptance/breakage_log.md. Automated tests cannot replace the hand check because
    openpyxl cannot compute formula results.

2.5 Formula-evaluation harness (see Part 8, R2). Tests generate a workbook from a fixture,
    evaluate it with the `formulas` library, and assert that the balance check equals zero
    and that every forecast cell is blank when the Assumptions sheet is blank. The scaffold's
    formula vocabulary stays within what the library can evaluate. This narrows but does not
    replace the hand check.
    Files: app/requirements.txt, app/tests/test_formula_eval.py (new).

### Acceptance test definition

Generate the scaffold for three deliberately different companies and hand-check every
number against the actual 10-K:

1. Apple (AAPL, CIK 320193): mega-cap tech, September fiscal year end, known revenue tag
   switch at FY2018, exercises per-period stitching.
2. Honeywell (HON, CIK 773840): classic industrial, calendar year end, clean segments,
   pension items that must land as flagged blanks rather than guesses. (Caterpillar and
   Deere were considered and rejected for this slot: their captive finance arms blur the
   line the bank/insurer gate is meant to draw.)
3. Kroger (KR, CIK 56873): known-messy filer for this purpose: 52/53-week fiscal year
   ending late January, so period-length logic and fiscal-year labeling are stressed, plus
   thin XBRL tagging in older years.

Stretch (optional fourth): Boeing (BA, CIK 12927), negative shareholders' equity, tests
sign conventions and the equity roll-forward.

Checklist template (one copy per company per run, lives in docs/acceptance/):

    Company:            Ticker/CIK:
    Scaffold file:      Generated on:
    10-K checked:       (accession number, link)

    For each of IS / BS / CF, for each historical year:
    [ ] Every line matches the 10-K statement exactly (value and sign)
    [ ] Values the 10-K shows but Edgardly left blank: listed with the flag message shown
    [ ] Values Edgardly shows that the 10-K does not: listed (this is a bug, log it)
    [ ] Source tag spot check: 3 random cells traced tag -> filing viewer
    Checks sheet:
    [ ] Balance check green in every historical column
    [ ] Cash tie green in every historical column
    [ ] Retained earnings tie green in every historical column
    Forecast mechanics (enter dummy assumptions, then delete them):
    [ ] With assumptions filled, all three statements populate and checks stay green
    [ ] With assumptions blank, all forecast cells are blank (no zeros, no leftovers)
    Sign-off:           Date:

Breakage log: docs/acceptance/breakage_log.md, one table (date, company, sheet/cell,
expected, got, root cause, fix commit).

Phase 2 exit criteria: all three checklists signed off with every discrepancy either fixed
or converted into a flagged blank with a pointer.

## Part 5. Phase 3 and later (less detail, decisions flagged)

### Phase 3, trading comps

Scaffold: comp set table with EV/EBITDA, EV/Revenue, P/E, enterprise value built up from
filings: market cap input, plus total debt, minus cash and short-term investments, plus
noncontrolling interest and preferred where reported.

Design decisions to make before building (recommendations in Part 6):
- Share price source. EDGAR has no prices. Recommendation: a blank price-per-share input
  cell per company; EV and multiples are formulas off it. Preserves the no-vendor,
  no-guessing principles. Revisit only if a free, licensable source appears.
- Share count for market cap: cover-page dei tag EntityCommonStockSharesOutstanding (a
  point-in-time count) versus weighted diluted. Recommendation: cover-page count for market
  cap, clearly labeled with its as-of date; diluted effects are analyst judgment inputs.
- LTM. Comps want LTM EBITDA/Revenue. This requires period algebra (FY plus interim minus
  prior interim) in the data layer. Build the period-algebra module in Phase 3, but Phase 1
  data structures already keep quarterly points, so nothing needs re-architecting.
- NCI and preferred in EV: pull ReedeemableNoncontrollingInterest / MinorityInterest and
  PreferredStockValue as registry additions; missing means flagged blank in the EV bridge.

### Phase 4, DCF

Historicals plus formula-wired forecast, terminal value block, and WACC block all
referencing a blank assumptions box. Reuses the Phase 2 excel kit and the Phase 2 forecast
engine for FCF build (EBIT, taxes, D&A, capex, working capital deltas all already wired).
Decision to flag: keep the DCF a separate workbook or a sheet family added to the
3-statement workbook. Recommendation: separate workbook generated from the same data pull,
because gating each scaffold on a course milestone argues for independent artifacts.

### Phase 5, football field

A summary chart of valuation ranges across available methods. Depends on each scaffold
emitting a standard output block (method name, low, high, midpoint cells at known named
ranges). Decision to flag: cross-workbook links are fragile and path-dependent.
Recommendation: the football field workbook contains blank linked-input cells per method
that the analyst pastes or types values into, plus the chart wired to those cells
(openpyxl stacked-bar with invisible base series). No live links between files.

Design decisions that Phase 2 would otherwise lock in, called out now:
- The excel kit (2.2) must not hardcode sheet names or column counts; comps and DCF have
  different shapes.
- Provenance comments and named-range naming conventions (`asm_*`, `out_*`) become the
  contract all later scaffolds follow; settle them in Phase 2 review.
- Period columns must be typed (FY vs LTM vs quarter) in the model spec now so Phase 3 can
  add LTM columns without changing the writer interface.

## Part 6. Open design questions and recommendations

1. Test suite location: restore into the public repo, or keep private? Recommendation:
   restore publicly. The README leans on verifiability, and every phase here is gated on
   tests. If there was a specific reason for removal (fixture size, embarrassment, license),
   solve that reason instead of hiding the suite.
2. Fixture size: full companyfacts payloads are multi-megabyte. Recommendation: commit
   trimmed fixtures produced by scripts/make_fixture.py, which strips to registry tags.
   Deterministic, small, regenerable.
3. Historical cells in scaffolds: static values versus formulas pointing at a raw Data
   sheet. Recommendation: static values with provenance comments. A Data sheet indirection
   adds fragility without analyst value; the Source Tags sheet already provides the audit
   trail.
4. Named ranges versus cell references: Recommendation: named ranges for Assumptions inputs
   only; plain cell references for statement-to-statement links, matching standard modeling
   convention and keeping formulas readable.
5. Excel library: stay on openpyxl (can re-read workbooks in tests, already a dependency)
   rather than xlsxwriter (write-only). Accept that formula cells display after first
   recalc in Excel; document it in the workbook's cover cell.
6. Non-USD and IFRS filers: Recommendation: explicit rejection message for scaffolds in v2,
   puller unaffected. Supporting IFRS well is a project of its own.
7. Scope gate strictness: SIC-only versus SIC plus statement-shape heuristic.
   Recommendation: both, with the heuristic result shown in the refusal message so
   misclassifications are debuggable.
8. Quarterly and LTM timing: build period algebra in Phase 1 or Phase 3? Recommendation:
   Phase 3, but Phase 1 keeps quarterly data points in the model spec so no rework is
   needed.
9. REITs and other statement-shape outliers (utilities, E&P): in or out of scope for the
   3-statement scaffold? Recommendation: allow with a warning banner rather than reject;
   they fit the template loosely, and the flagged-blank mechanism degrades honestly.

## Part 7. Sequencing summary

Around classes, each numbered task above is sized to be independently shippable and leaves
the repo working:

- Pre-phase fixes F1-F5: small, do first, F1 before everything.
- Phase 1: 1.1 -> 1.2 -> 1.3 -> 1.4 -> 1.5 in order; 1.4 and 1.5 can swap.
- Phase 2: 2.1 -> 2.2 -> 2.3 -> 2.4; acceptance hand-check is the gate.
- Phase 3+ gated on the matching Wall Street Prep course, per the project rule.

## Part 8. Risk register

Written 2026-08-03, ordered by expected damage. Each risk names its mitigation and the
residual exposure that remains after mitigation.

### Technical risks

**R1. Tags are not statements (the big one).** XBRL companyfacts gives isolated tagged
values, not the filing's statement structure. Components frequently do not sum to reported
totals (missing "other" buckets, filer-specific rollups), so a naively assembled balance
sheet will not tie and the cash flow statement will not bridge. This is the conceptual gap
between v1 (pull tags) and v2 (scaffold statements).

Mitigation: the plug-row decision (derived, formula-visible, never a guess); tie-out checks
in every workbook; the acceptance hand-check gate. Residual risk: some filers may need plugs
so large the scaffold is misleading, so any plug exceeding 10 percent of its statement total
raises a flag that says this filer's XBRL is too sparse rather than shipping junk.
Implemented as task 2.2b.

**R2. Formula correctness cannot be verified automatically.** openpyxl writes formula text
but computes nothing. A wiring bug, for example a wrong row offset after a layout change,
ships silently and only a human opening Excel sees it.

Mitigation: a formula-evaluation harness in Phase 2 using the `formulas` Python library
(pip-installable, evaluates .xlsx in CI, handles IF, ISBLANK, SUM), plus the hand-check
checklist as the release gate. Residual: the library may not cover every function, so the
scaffold's formula vocabulary stays constrained to what it can evaluate. Implemented as
task 2.5.

**R3. Tag-chain whack-a-mole.** The 28-item registry chains are educated guesses until they
run against real filers, and D&A, debt, and intangibles tagging varies enormously. Endless
per-company patching could eat the whole fall.

Mitigation: chains are validated only against the acceptance fixtures (AAPL, HON, KR, BA,
one bank, one IFRS filer), not the whole market; everything else degrades to flagged blanks
by design; registry additions are one-line changes; tag archaeology is time-boxed per
session.

**R4. Excel file corruption.** Malformed defined names, comments, or conditional formatting
can trigger Excel's "repaired records" dialog, which strips content and destroys trust in
the tool.

Mitigation: workbook re-read tests on every export; "opens clean in real Excel, no repair
prompt" is a line item on the acceptance checklist; openpyxl features such as named ranges
and comments are introduced one at a time with tests.

**R5. Fiscal-period edge cases.** Fiscal year end changes mid-history create stub periods,
restatements shift comparatives, and 52/53-week years are handled today only in the peer
path. The single-company path trusts `fp` labels and diverges from the peer path.

Mitigation: Phase 1 unifies both paths on the peer engine's date-anchored logic; stub
periods get flagged, never force-fit; Kroger is in the acceptance set specifically to
stress this.

**R6. SEC API exposure.** The placeholder User-Agent (`contact@example.com`) invites
blocking, and API schema drift would break extraction.

Mitigation: a real contact lands in Session 1; all tests run against committed fixtures so
the suite stays green offline; the live smoke check stays manual.

### Process risks

**R7. Test restore drift.** The code moved after the June 2026 deletion (port change,
launcher work), so some of the 291 restored tests may fail for stale reasons and a session
could sink into archaeology.

Mitigation: Session 1 time-boxes triage. Failing tests get fixed if the fix is quick,
otherwise they are marked xfail with a reason and logged in PROGRESS.md. The xfail count is
tracked and burned down.

**R8. Context loss between sessions.** New sessions will not know the decisions made during
planning, and re-deriving them risks contradiction, for example a future session helpfully
auto-filling missing values.

Mitigation: docs/V2_PLAN.md is the single source of truth; PROGRESS.md logs per-session
state and decisions; every session prompt in docs/SESSIONS.md starts by pointing at both and
restates the two inviolable constraints (never guess values, keep v1 features working).

**R9. Scope and schedule.** A freshman working around classes plus course-gated phases means
long gaps and a temptation to leave the repo mid-refactor.

Mitigation: session prompts are sized to be finishable in one sitting and each ends with
suite green, commit, update PROGRESS.md. Phases 3 and later stay unplanned in detail until
their course gate opens.

**R10. Solo acceptance bottleneck.** Hand-checking three companies' full statements against
10-Ks is hours of careful manual work with no shortcut.

Mitigation: the checklist is per company and resumable, so it can spread across sessions;
automated fixture tests shrink what the human must check down to formula results and
completeness.

## Part 9. Decisions log

Decisions that are settled and must not be re-litigated by a later session. PROGRESS.md
carries the running copy of this log; entries here are the planning-time originals.

1. **Plug rows.** Statement gaps are handled with explicit derived plug rows, for example
   "Other current assets (plug to reported total)", written as live Excel formulas so the
   math is visible in the workbook. A plug is never a guess and never a silent fill. Any
   plug exceeding 10 percent of its statement total raises a flag (task 2.2b). Confirmed by
   the user during planning.

2. **Test suite location.** The suite is restored to the public repo. Commit 4e1d457
   (June 2026) removed it with no stated rationale, the surrounding commits were portfolio
   polish, and no branch, stash, or on-disk copy exists anywhere, so git history was the only
   copy. Restoring publicly is the safest option and every later phase is gated on tests.
