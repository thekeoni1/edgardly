# Three-statement scaffold acceptance checklist

The gate on Phase 2. Automated tests cannot replace this: openpyxl computes no
formulas, the evaluation harness computes them but cannot tell whether a row is
the right row or whether a tag means what the registry says it means, and
nothing in the suite has ever opened a workbook in Excel and looked at it. What
is left for a human is exactly this document.

One copy per company per run, three of them below. Work through a copy against
the company's actual 10-K, not against anything Edgardly produced. It is
resumable: tick boxes as you go, write the date in the sitting log at the end of
each copy, and stop wherever you like. Nothing here has to be finished in one
sitting, and R10 in V2_PLAN's risk register exists because it will not be.

## Who ticks what

Settled 2026-08-05 and recorded in PROGRESS.md's decisions log. The value
comparison is performed by a Claude session with the filings open: every ticked
box carries a citations block naming the filing by accession, the statement
inside it, and the figure read there, so a tick is checkable rather than
asserted. What is reserved for the user is what a session cannot do or should
not certify: opening the workbook by hand in real Excel, hovering a row label to
watch the tooltip render, judging whether a plug or a coverage figure is
acceptable for their purpose, and signing. The signature certifies review of the
evidence below, not personal recomputation of every cell.

A box left unticked has its reason written under it. A box reserved for the user
is left blank and named as such above each sitting log.

## How to generate a workbook

Through the app, so the thing being checked is the thing a user gets:

1. Start the app, load the company in the XBRL view, set the year range.
2. Click Build 3-Statement Model.
3. The confirmation names the file and the folder it went to.

Or against the committed fixtures with no network, which produces the same
workbook from the same payloads:

    python scripts/generate_acceptance.py

Nothing generated is committed. The workbooks are working copies; this document
and the breakage log are the record.

## What to do with anything you find

Every discrepancy goes in docs/acceptance/breakage_log.md, whether or not it
looks important, and before you decide what it is. Each entry is then either
fixed or converted into a flagged blank with a pointer to the filing, which is
the same standard the rest of the tool holds: a value Edgardly cannot stand
behind is shown as missing and explained, never quietly corrected and never
guessed.

Do not sign a copy off with entries still open against it.

## Two lines that differ from the plan's template

V2_PLAN Part 4 carries the planning-time original of this template. Two lines
are amended here, both settled on 2026-08-05 and both recorded in PROGRESS.md's
decisions log with their reasons.

**Retained earnings.** The template asks for the retained earnings tie to be
green in every historical column. It cannot be, for any filer, and the reason is
structural rather than a bug: filers charge share retirements, treasury stock
and other equity movements to retained earnings, and none of those is a registry
item. Apple's FY2025 residual is 91,699 million against a buyback of 90,711
million, so the figure is not mysterious, only non-zero. The workbook labels the
row a residual, leaves it uncoloured and reports the number, and the line below
asks you to confirm the residual is explained rather than to confirm a zero that
cannot happen.

**Coverage.** A plug over 10 percent of the total it plugs to raised a warning
on 72 of 75 balance-sheet plug cells across these three filers, which made it
useless however true each instance was. The income statement and the cash flow
statement keep the warning, where it still singles something out. The balance
sheet reports the same measurement as a per-section coverage percentage on the
Checks sheet, and the line below asks you to read those figures rather than to
count warnings.

---

## Copy 1. Apple

    Company:            Apple Inc.
    Ticker / CIK:       AAPL / 320193
    Scaffold file:      app/exports/acceptance/Apple_Inc/
                        Apple_Inc_3Statement_2026-08-05_1632.xlsx
    Generated on:       2026-08-05 16:32, from the committed fixture
    Years in workbook:  FY2021 to FY2025 historical, FY2026E to FY2028E forecast
    10-K checked:       FY2025 0000320193-25-000079 (filed 2025-10-31)
                        FY2024 0000320193-24-000123 (filed 2024-11-01)
                        FY2023 0000320193-23-000106 (filed 2023-11-03)
                        FY2022 0000320193-22-000108 (filed 2022-10-28)
                        https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=320193&type=10-K

Each historical year's own accession is on the Source Tags sheet, one line per
value, so a year sourced from a later filing's comparative column says so.

### Income statement, per historical year

| Year | Every line matches the 10-K, value and sign | Blanks the 10-K fills: listed with the flag message shown | Values Edgardly shows that the 10-K does not: listed, and logged as bugs | Source tag spot check, 3 random cells traced to the filing viewer |
| --- | --- | --- | --- | --- |
| FY2021 | [x] | [x] | [x] | [x] |
| FY2022 | [x] | [x] | [x] | [x] |
| FY2023 | [x] | [x] | [x] | [x] |
| FY2024 | [x] | [x] | [x] | [x] |
| FY2025 | [x] | [x] | [x] | [x] |

Citations. Read off CONSOLIDATED STATEMENTS OF OPERATIONS (R3) in each filing,
and off Consolidated Financial Statement Details -- Other Income/(Expense), Net
(R53) for the interest line, which Apple discloses in a note and not on the face.

- FY2021, 0000320193-23-000106, statements of operations, Sep. 25 2021 column:
  net sales 365,817; cost of sales 212,981; gross margin 152,836; R&D 21,914;
  SG&A 21,973; operating income 108,949; pretax 109,207; tax 14,527; net income
  94,680; EPS 5.67 basic and 5.61 diluted; 16,701,272 and 16,864,919 thousand
  shares. Interest expense 2,645 from R53 of the same filing.
- FY2022, 0000320193-23-000106 (comparative) and 0000320193-24-000123:
  394,328; 223,546; 170,782; 26,251; 25,094; 119,437; 119,103; 19,300; 99,803;
  6.15 and 6.11; 16,215,963 and 16,325,819 thousand. Interest expense 2,931, R53.
- FY2023, 0000320193-25-000079 (comparative) and 0000320193-23-000106:
  383,285; 214,137; 169,148; 29,915; 24,932; 114,301; 113,736; 16,741; 96,995;
  6.16 and 6.13; 15,744,231 and 15,812,547 thousand. Interest expense 3,933, R53.
- FY2024, 0000320193-25-000079, Sep. 28 2024 column: 391,035; 210,352; 180,683;
  31,370; 26,097; 123,216; 123,485; 29,749; 93,736; 6.11 and 6.08; 15,343,783 and
  15,408,095 thousand. No interest expense line and no note giving one.
- FY2025, 0000320193-25-000079, Sep. 27 2025 column: 416,161; 220,960; 195,201;
  34,550; 27,601; 133,050; 132,729; 20,719; 112,010; 7.49 and 7.46; 14,948,500 and
  15,004,697 thousand. No interest expense line and no note giving one.

All figures are in millions in the filing and in whole units in the workbook;
the scale is right in every cell checked. Signs: Apple presents cost of sales,
operating expenses and the tax provision as positive deductions and the workbook
carries them positive, which is the convention its row notes state. Interest
expense is shown by Apple as (3,933) inside other income/(expense) and is carried
positive as an expense, per the same convention.

Blanks: interest expense FY2024 and FY2025, each shown blank with "Not tagged in
XBRL. Check the income statement of the FY2024/FY2025 10-K" and the filing index
URL. Apple stopped publishing the other-income breakdown after FY2023, so the
10-K does not fill them either; the plug beside them carries a PLUG_ABSORBS_BLANK
flag naming the line it absorbed. The operating plug is exactly zero in all five
years because Apple's total operating expenses are R&D plus SG&A and nothing else.

Extras: none on this statement. Two spurious LARGE_YOY_CHANGE flags sit on FY2021
gross profit and net income and are logged (breakage log rows 1 and 2); they are
flags on correct values, not extra values.

Tags traced: Revenue FY2021, RevenueFromContractWithCustomerExcludingAssessedTax,
0000320193-23-000106 -> statements of operations, Sep. 25 2021, 365,817. Interest
Expense FY2023, InterestExpense, 0000320193-23-000106 -> R53 Other
Income/(Expense), Net, interest expense (3,933). Net Income FY2025, NetIncomeLoss,
0000320193-25-000079 -> statements of operations, Sep. 27 2025, 112,010.

### Balance sheet, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
| FY2021 | [x] | [x] | [x] | [x] |
| FY2022 | [x] | [x] | [x] | [x] |
| FY2023 | [x] | [x] | [x] | [x] |
| FY2024 | [x] | [x] | [x] | [x] |
| FY2025 | [ ] | [x] | [x] | [x] |

FY2025 is not ticked for a match: the Intangibles row shows 13,301,000,000, which
is on no Apple balance sheet, and the figure it does show mixes a current and a
non-current amount. Breakage log rows 3 and 4.

Citations. Read off CONSOLIDATED BALANCE SHEETS (R5) in each filing.

- FY2021, 0000320193-22-000108, Sep. 25 2021 column: cash 34,940; marketable
  securities current 27,699; receivables 26,278; inventories 6,580; total current
  assets 134,836; PP&E 39,440; total assets 351,002; accounts payable 54,763; term
  debt current 9,613; commercial paper 6,000; total current liabilities 125,481;
  term debt non-current 109,106; total liabilities 287,912; retained earnings
  5,562; total equity 63,090.
- FY2022, 0000320193-22-000108, Sep. 24 2022 column: 23,646; 24,658; 28,184;
  4,946; 135,405; 42,117; 352,755; 64,115; 11,128; 9,982; 153,982; 98,959;
  302,083; accumulated deficit (3,068); 50,672.
- FY2023, 0000320193-24-000123, Sep. 30 2023 column: 29,965; 31,590; 29,508;
  6,331; 143,566; 43,715; 352,583; 62,611; 9,822; 5,985; 145,308; 95,281; 290,437;
  (214); 62,146.
- FY2024, 0000320193-25-000079, Sep. 28 2024 column: 29,943; 35,228; 33,410;
  7,286; 152,987; 45,680; 364,980; 68,960; 10,912; 9,967; 176,392; 85,750;
  308,030; (19,154); 56,950.
- FY2025, 0000320193-25-000079, Sep. 27 2025 column: 35,934; 18,763; 39,777;
  5,718; 147,957; 49,834; 359,241; 69,860; 12,350; 7,979; 165,631; 78,328;
  285,508; (14,264); 73,733. Every one of these matches. The Intangibles row is
  the exception and is not from this statement: 13,301 is the total intangibles
  in the note to the 10-Q filed 2026-07-31, accession 0000320193-26-000020, whose
  re-presented Sep. 27 2025 balance sheet shows 11,093 non-current and whose note
  splits the total into 11,093 non-current and 2,208 current.

Signs: the accumulated deficit is negative in FY2022 to FY2025 and positive
retained earnings in FY2021, exactly as the filings present them.

Blanks: Goodwill in all five years and Short-Term Borrowings in all five, each
with "Not tagged in XBRL" and the right filing index URL. Both are correct --
Apple's balance sheet carries neither caption. Intangibles is blank FY2021 to
FY2024 for the same reason and populated in FY2025 only, which is the seam logged
as breakage row 3.

Extras: Intangibles FY2025, logged. Nothing else.

Tags traced: Long-Term Debt FY2024, LongTermDebtNoncurrent,
0000320193-25-000079 -> balance sheets, Sep. 28 2024, non-current term debt
85,750. Total Equity FY2021, StockholdersEquity, 0000320193-24-000123 ->
CONSOLIDATED STATEMENTS OF SHAREHOLDERS' EQUITY (R7), "Beginning balances at Sep.
25, 2021", total 63,090; that filing's balance sheet does not carry the date, and
its three-year equity statement does, which is why the tag resolves there.
Intangibles FY2025, IntangibleAssetsNetExcludingGoodwill, 0000320193-26-000020 ->
Condensed Consolidated Financial Statement Details -- Intangible Assets, Net
(R37), Sep. 27 2025, total intangible assets net 13,301.

### Cash flow statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
| FY2021 | [x] | [x] | [x] | [x] |
| FY2022 | [x] | [x] | [x] | [x] |
| FY2023 | [x] | [x] | [x] | [x] |
| FY2024 | [x] | [x] | [x] | [x] |
| FY2025 | [x] | [x] | [x] | [x] |

Citations. Read off CONSOLIDATED STATEMENTS OF CASH FLOWS (R8).

- FY2021, 0000320193-23-000106, Sep. 25 2021 column: D&A 11,284; share-based
  compensation 7,906; cash generated by operating activities 104,038; payments for
  PP&E (11,085); cash used in investing (14,545); dividends (14,467); repurchases
  (85,971); cash used in financing (93,353).
- FY2022, same filing, Sep. 24 2022 column: 11,104; 9,038; 122,151; (10,708);
  (22,354); (14,841); (89,402); (110,749).
- FY2023, 0000320193-25-000079, Sep. 30 2023 column: 11,519; 10,833; 110,543;
  (10,959); 3,705; (15,025); (77,550); (108,488).
- FY2024, same filing, Sep. 28 2024 column: 11,445; 11,688; 118,254; (9,447);
  2,935; (15,234); (94,949); (121,983).
- FY2025, same filing, Sep. 27 2025 column: 11,698; 12,863; 111,482; (12,715);
  15,195; (15,421); (90,711); (120,686).

Signs: capex, dividends and buybacks are payments in the filing and are carried
positive in the workbook, which the row notes say and which the investing and
financing formulas subtract. The subtotals keep the filing's own sign, so investing
is negative in FY2021 and FY2022 and positive in FY2023 to FY2025, as reported.

Blanks: cash at the beginning and end of FY2021, which no column before it can
supply. The message shown is malformed and names the wrong input; breakage row 6.

Extras: none.

Tags traced: Buybacks FY2023, PaymentsForRepurchaseOfCommonStock,
0000320193-25-000079 -> statements of cash flows, Sep. 30 2023, repurchases of
common stock (77,550). D&A FY2022, DepreciationDepletionAndAmortization,
0000320193-24-000123 -> same statement, Sep. 24 2022, 11,104. Dividends Paid
FY2025, 0000320193-25-000079 -> same statement, Sep. 27 2025, payments for
dividends and dividend equivalents (15,421).

### Checks sheet

- [x] Balance check green in every historical column
      Excel's own arithmetic through the evaluator: 0 in all five columns.
- [x] Cash tie green in every historical column, or its residual is accounted
      for out of the filer's own statement and the figure is written down here
      Line widened 2026-08-06, closing breakage row 15. It asked for the residual
      to be the filer's effect of exchange rates on cash, which is what it is for
      one of these three filers and not the only thing it can be; what a checker
      can do in every case is account for it off the statement.
      FY2022 +342, FY2023 -559, FY2024 -772, FY2025 0, in millions. Apple's cash
      flow statement carries no effect-of-exchange-rates line at all. Every one of
      these is the year-on-year change in the restricted cash that the statement's
      "cash, cash equivalents and restricted cash" includes and the balance
      sheet's "cash and cash equivalents" excludes. The gap is 1,331 at the FY2022
      close (24,977 against 23,646), 772 at FY2023 (30,737 against 29,965) and nil
      thereafter, and each residual is the difference between two of those:
      1,331 - 989 = 342 at FY2022, 772 - 1,331 = -559 at FY2023, 0 - 772 = -772 at
      FY2024, and nil to nil at FY2025. Accounted for to the dollar.
- [x] Retained earnings residual is explained by buybacks and other equity
      movements, per year, with the figures written down here:
      FY2022 -93,592 = repurchases charged to retained earnings 90,186 plus common
      stock withheld for net share settlement 3,454, less 48 of dividends declared
      against dividends paid. FY2023 -79,116 = 77,046 plus 2,099 less 29. FY2024
      -97,442 = 95,846 plus 1,612 less 16. FY2025 -91,699 = 90,052 plus 1,655 less
      8. All from CONSOLIDATED STATEMENTS OF SHAREHOLDERS' EQUITY, R7 of
      0000320193-23-000106 and 0000320193-25-000079. Every residual is explained
      to the dollar.
- [x] Section coverage percentages read for all five balance sheet sections, and
      none of them is a surprise once the 10-K is open beside it. Write the
      lowest one and what sits in its plug:
      FY2025 reads 67.7, 58.8, 54.5, 85.4 and -19.3 percent for current assets,
      total assets, current liabilities, total liabilities and equity. The lowest
      of the twenty-five cells is total equity FY2024 at -33.6 percent; its plug
      is 76,104 million, which is common stock and additional paid-in capital
      83,276 less accumulated other comprehensive loss 7,172. Negative because the
      section's one component, an accumulated deficit of (19,154), is measured
      against a total those two hold up. The current-asset plug of 47,765 in
      FY2025 is vendor non-trade receivables 33,180 plus other current assets
      14,585, to the dollar; the total-asset plug is non-current marketable
      securities 77,723 plus other non-current assets 83,727, less the intangibles
      figure that breakage row 4 says should not have been subtracted whole.
- [ ] The flag list under the checks says nothing you disagree with
      The five lines listed are all true: goodwill and short-term borrowings have
      no reported history, and the three cash-flow plugs reach the shares they
      claim. Not ticked because the list is not the whole of what the workbook
      flags: the two false LARGE_YOY_CHANGE flags of breakage rows 1 and 2 sit in
      cell comments and on the Source Tags sheet and never reach this list, and
      neither do the PLUG_ABSORBS_BLANK flags on the income statement. A reader
      who reads only the Checks sheet does not learn either thing. Breakage row 5.

### Forecast mechanics

Enter dummy assumptions, then delete them.

Verified through the formula-evaluation harness rather than by typing into Excel:
the workbook was evaluated as shipped and again with one unremarkable assumption
set written into all 45 named input cells. This is the populate-then-blank pass
the two boxes below describe, run by the evaluator that computes Excel's formulas
outside Excel. A pass in real Excel with the same dummy assumptions would add
Excel's own recalculation to the evidence and is the user's to run if they want
it; nothing here depends on it.

- [x] With assumptions filled, all three statements populate and the checks stay
      green
      All 219 forecast formula cells return numbers; no cell anywhere evaluates to
      an error; the balance check, the cash tie and the retained earnings
      roll-forward are all zero in FY2026E, FY2027E and FY2028E.
- [x] With assumptions blank, all forecast cells are blank: no zeros, no
      leftovers
      All 219 return empty with the Assumptions sheet as shipped.
- [ ] Rows with no forecast say why when you hover the row label
      Reserved for the user: whether a comment renders on hover is a thing only
      Excel can show. The text is present and correct in the file -- EPS basic,
      EPS diluted and both share counts carry NO_FORECAST_DRIVER on their row
      labels, and goodwill and short-term borrowings carry NO_REPORTED_HISTORY.

### The workbook itself

- [ ] Opens in real Excel with no repair prompt, opened by hand rather than by
      automation, because automation runs with alerts suppressed and would not
      see the dialog
- [x] All seven sheets present, all comments readable, no #REF! or #VALUE!
      anywhere
      Seven sheets in the order the plan names them, 48 defined names and 402 cell
      comments. A full evaluation of every formula in the workbook produced no
      error value of any kind, blank and filled. "Readable" in Excel's own
      rendering belongs with the interactive open above.

### Sitting log

Left for the user: the interactive open above, the hover-tooltip line, and the
signature. Everything else on this copy is worked, with its evidence beside it.

| Date | Where you stopped |
| --- | --- |
| 2026-08-05 | Value comparison complete for all five years of all three statements. Six entries open in the breakage log against this copy (rows 1, 3, 4, 5, 6 and 15), so it cannot be signed. |

    Signed off:                              Date:

---

## Copy 2. Honeywell

    Company:            Honeywell International Inc.
    Ticker / CIK:       HON / 773840
    Scaffold file:      app/exports/acceptance/Honeywell_International_Inc/
                        Honeywell_International_Inc_3Statement_2026-08-05_1632.xlsx
    Generated on:       2026-08-05 16:32, from the committed fixture
    Years in workbook:  FY2021 to FY2025 historical, FY2026E to FY2028E forecast
    10-K checked:       FY2025 0000773840-26-000013 (filed 2026-02-17)
                        FY2024 0000773840-25-000010 (filed 2025-02-14)
                        FY2023 0000773840-24-000014 (filed 2024-02-16)
                        FY2022 0000773840-23-000013 (filed 2023-02-10)
                        FY2021 0000773840-22-000018 (filed 2022-02-11)
                        https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=773840&type=10-K

Honeywell tags no Liabilities element for any year, so its total liabilities row
is derived as assets less equity and its balance check is zero because it was
made zero. The Checks sheet says so and the row is left uncoloured. What to
confirm here is that the derived total matches the 10-K's own total liabilities,
which is the check the workbook cannot run for you.

- [ ] Total liabilities, derived, matches the 10-K in every historical year
      Not ticked, and the line cannot be worked as written: Honeywell's balance
      sheet carries no total liabilities line at all in any of these five years.
      It goes from the last liability caption straight to shareowners' equity. The
      honest substitute is the sum of the liability captions on the face, and
      against that the derived total is exact in FY2025 and 7,000,000 too high in
      each of FY2021 to FY2024. Worked year by year, in millions:
      FY2021 derived 45,228; captions 19,508 + 14,254 + 2,364 + 208 + 1,800 +
      7,087 = 45,221. FY2022 derived 44,956; 19,938 + 15,123 + 2,093 + 146 + 1,180
      + 6,469 = 44,949. FY2023 derived 45,091; 18,539 + 16,562 + 2,094 + 134 +
      1,490 + 6,265 = 45,084. FY2024 derived 56,042; 21,256 + 25,479 + 1,787 + 112
      + 1,325 + 6,076 = 56,035, reading the FY2024 10-K, or 21,256 + 25,440 +
      1,581 + 112 + 1,325 + 5,581 + 740 = 56,035 reading the FY2025 10-K's
      re-presented column, which agrees. FY2025 derived 58,651; 23,414 + 27,141 +
      1,577 + 111 + 0 + 6,408 = 58,651, exact. The recurring 7 is the redeemable
      noncontrolling interest, which Honeywell reports between liabilities and
      equity and which assets-less-equity sweeps into liabilities; it is nil at
      Dec. 31 2025, which is why that year agrees. Breakage row 8.

### Income statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
| FY2021 | [x] | [x] | [x] | [x] |
| FY2022 | [ ] | [x] | [x] | [x] |
| FY2023 | [ ] | [x] | [x] | [x] |
| FY2024 | [ ] | [x] | [x] | [x] |
| FY2025 | [ ] | [x] | [x] | [x] |

FY2022 to FY2025 are not ticked for a match because of one row: Operating Income.
Honeywell's consolidated statement of operations has no operating income
subtotal, and 8,022 / 7,563 / 7,667 / 8,127 are its Segment profit, taken from
the segment note's reconciliation to pretax income and tagged
us-gaap:OperatingIncomeLoss. Every other line on those columns matches. Breakage
row 7. FY2021 is ticked because that year has no operating income value at all.

Citations. Read off CONSOLIDATED STATEMENT OF OPERATIONS (R3), and off SEGMENT
FINANCIAL DATA Reconciliation of Operating Profit Loss From Segments to
Consolidated (R145 of the FY2025 10-K, R133 of the FY2023 10-K) for the operating
income row.

- FY2021, 0000773840-24-000014, Dec. 31 2021 column: net sales 34,392; cost of
  products and services sold 22,061; R&D 1,333; SG&A 4,798; interest and other
  financial charges 343; income before taxes 7,235; tax 1,625; net income
  attributable to Honeywell 5,542; EPS 8.01 basic and 7.91 diluted.
- FY2022, same filing, Dec. 31 2022 column: 35,466; 22,347; 1,478; 5,214; 414;
  6,379; 1,412; 4,966; 7.33 and 7.27. Segment profit 8,022, R133.
- FY2023, 0000773840-26-000013, Dec. 31 2023 column: 33,009; 20,637; 1,375;
  4,887; 749; 6,191; 1,262; 5,658; 8.53 and 8.47. Segment profit 7,563, R145.
- FY2024, same filing, Dec. 31 2024 column: 34,717; 21,360; 1,454; 5,235; 1,048;
  6,244; 1,249; 5,705; 8.76 and 8.71. Segment profit 7,667, R145.
- FY2025, same filing, Dec. 31 2025 column: 37,442; 23,613; 1,812; 5,450; 1,344;
  5,476; 1,008; 4,729; 7.40 and 7.36. Segment profit 8,127, R145.

Ambiguity, recorded rather than resolved. FY2023's figures above are the FY2025
10-K's re-presented column, not the FY2023 10-K as filed, which reported net
sales 36,662, cost of sales 22,995, R&D 1,456, SG&A 5,127, interest 765 and
pretax 7,159 for the same year before the Solstice spin-off moved a business to
discontinued operations. Both are Honeywell's own numbers for Dec. 31 2023; the
workbook takes the most recent annual report, which is the documented rule. The
consequence is a series that changes basis between FY2022 and FY2023: the fall
from 35,466 to 33,009 in revenue is a change of presentation and not a decline,
and nothing in the workbook says so. Breakage row 16.

Signs: costs, R&D, SG&A, interest and tax are positive deductions in the filing
and positive in the workbook. Net income is the figure attributable to Honeywell,
which is 43 million below the consolidated total in FY2025; the difference lands
in the discontinued-operations plug, whose row note says so.

Blanks: Operating Income FY2021, and with it the operating plug and EBITDA, each
carrying "Not tagged in XBRL. Check the income statement of the FY2021 10-K" and
the index URL. Honeywell tags no OperatingIncomeLoss for 2021 in any filing. The
other-income plug for that year drops the operating term from its formula rather
than treating the blank as zero and carries PLUG_ABSORBS_BLANK naming the line it
absorbed, which is the right behaviour. The pointer sends the reader to a
statement that has no such line, which is a wording matter and is noted in
breakage row 11.

Extras: Operating Income FY2022 to FY2025, in the sense that the income statement
does not carry it; the value is in the filing, in the segment note. Logged.

Tags traced: Revenue FY2023, RevenueFromContractWithCustomerExcludingAssessedTax,
0000773840-26-000013 -> statement of operations, Dec. 31 2023, net sales 33,009.
Operating Income FY2025, OperatingIncomeLoss, same filing -> R145, Segment profit
8,127. Cost of Revenue FY2021, CostOfGoodsAndServicesSold, 0000773840-24-000014
-> statement of operations, Dec. 31 2021, cost of products and services sold
22,061.

### Balance sheet, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
| FY2021 | [ ] | [x] | [x] | [x] |
| FY2022 | [ ] | [x] | [x] | [x] |
| FY2023 | [ ] | [x] | [x] | [x] |
| FY2024 | [ ] | [x] | [x] | [x] |
| FY2025 | [ ] | [x] | [x] | [x] |

No year is ticked for a match, for one row in all five and a second in four. The
Intangibles row is the finite-lived intangibles only against a balance-sheet
caption that includes indefinite-lived ones (breakage row 9), and Total
Liabilities carries the redeemable noncontrolling interest in FY2021 to FY2024
(breakage row 8). Every other row matches in every year.

Citations. Read off CONSOLIDATED BALANCE SHEET (R5), in millions.

- FY2021, 0000773840-23-000013, Dec. 31 2021 column: cash 10,959; short-term
  investments 564; receivables 6,830; inventories 5,138; other current assets
  1,881; total current assets 25,372; PP&E 5,562; goodwill 17,756; other
  intangible assets net 3,613 against the workbook's 2,599; total assets 64,470;
  accounts payable 6,484; commercial paper and other short-term borrowings 3,542;
  current maturities of long-term debt 1,803; total current liabilities 19,508;
  long-term debt 14,254; retained earnings 42,827; total shareowners' equity
  19,242.
- FY2022, same filing, Dec. 31 2022 column: 9,627; 483; 7,440; 5,538; 1,894;
  24,982; 5,471; 17,497; 3,222 against 2,269; 62,275; 6,329; 2,717; 1,730; 19,938;
  15,123; 45,093; 17,319.
- FY2023, 0000773840-24-000014, Dec. 31 2023 column: 7,925; 170; 7,530; 6,178;
  1,699; 23,502; 5,660; goodwill 18,049 against the workbook's 17,238; 3,231
  against 2,260; 61,525; 6,849; 2,085; 1,796; 18,539; 16,562; 47,979; 16,434.
- FY2024, 0000773840-26-000013, Dec. 31 2024 column: 9,906; 386; 7,247; 5,884;
  1,259 plus assets held for sale 1,365 and current assets of discontinued
  operations 1,861; 27,908; 4,457; 21,019; 6,621 against 6,207; 75,196; 6,109;
  4,273; 1,325; 21,256; 25,440; 50,835; 19,154.
- FY2025, same filing, Dec. 31 2025 column: 12,487; 443; 7,621; 6,162; 1,182 plus
  assets held for sale 2,492; 30,387; 4,629; 21,079; 6,736 against 6,342; 73,681;
  6,315; 5,893; 1,546; 23,414; 27,141; 50,964; 15,030.

Ambiguities, recorded rather than resolved. Two rows take a later filing's
re-presented figure over the one the year's own 10-K published, and both are
Honeywell's own numbers. Goodwill at Dec. 31 2023 is 18,049 on the FY2023 and
FY2024 balance sheets and 17,238 in the FY2025 10-K, where the goodwill
roll-forward opens on the post-spin basis; the workbook takes 17,238. Cash,
receivables, inventories, PP&E, goodwill, payables and current maturities at Dec.
31 2024 are all higher in the FY2024 10-K than in the FY2025 10-K's comparative,
which moves a discontinued operation out of each; the workbook takes the later
column throughout, so cash reads 9,906 rather than 10,567 and current maturities
1,325 rather than 1,347. Total assets and total equity are the same in both.

Blanks: Commercial Paper in all five years, with "Not tagged in XBRL" and the
right index URL. Correct: Honeywell reports commercial paper inside "Commercial
paper and other short-term borrowings", which the short-term borrowings row reads,
so the two terms of the short-term debt sum cannot overlap. Nothing else is blank.

Extras: none. The two mismatched rows show figures that are in the filings, just
not on the line the row sits beside.

Tags traced: Long-Term Debt FY2021, LongTermDebtAndCapitalLeaseObligations,
0000773840-23-000013 -> balance sheet, Dec. 31 2021, long-term debt 14,254.
Retained Earnings FY2025, RetainedEarningsAccumulatedDeficit,
0000773840-26-000013 -> balance sheet, Dec. 31 2025, retained earnings 50,964.
Goodwill FY2023, Goodwill, 0000773840-26-000013 -> not on that filing's balance
sheet, which carries only 2025 and 2024; the 17,238 is the restated opening of the
2024 goodwill roll-forward, confirmed against EDGAR's companyconcept record for
the element, which shows 18,049 from every filing up to the FY2024 10-K and
17,238 from the FY2025 10-K.

### Cash flow statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
| FY2021 | [x] | [x] | [x] | [x] |
| FY2022 | [x] | [x] | [x] | [x] |
| FY2023 | [x] | [x] | [x] | [x] |
| FY2024 | [x] | [x] | [x] | [x] |
| FY2025 | [x] | [x] | [x] | [x] |

FY2021 and FY2024 now tick, with one row carrying a caveat rather than a
mismatch. D&A reads 1,138 against a face total of 1,223 in FY2021, and 1,153
against 1,152 in FY2024, and in both years the workbook's figure is exactly what
Honeywell tagged. Closed 2026-08-06 as breakage row 10, a filer-side
inconsistency and not an Edgardly defect, on this evidence:

- The FY2021 and FY2022 10-Ks both present depreciation 674 and amortization 549
  for the year ended 2021-12-31, summing to 1,223, and both tag
  us-gaap:DepreciationDepletionAndAmortization for that year as 1,138.
- The FY2025 10-K presents 493 and 659 for the year ended 2024-12-31, summing to
  1,152, and tags the element as 1,153.
- Confirmed against EDGAR's companyconcept record for the element,
  `companyconcept/CIK0000773840/us-gaap/DepreciationDepletionAndAmortization.json`,
  which shows the same 1,138 and 1,153 from every filing that reports those years.
  The 85 million and the 1 million are unreconciled on the face of the filings and
  no note in any of them accounts for either.
- FY2022, FY2023 and FY2025 are internally consistent: 657 + 547 = 1,204,
  490 + 514 = 1,004, and 546 + 842 = 1,388, each equal to the tagged total.

Edgardly reports what the filer tagged, which is the rule everywhere else in the
tool, and inventing 1,223 from two components Honeywell chose not to add would be
a number no filing states. No code changed.

Citations. Read off CONSOLIDATED STATEMENT OF CASH FLOWS, R6 of the FY2022 10-K
and R7 of the later ones, in millions.

- FY2021, 0000773840-24-000014, Dec. 31 2021 column: depreciation 674 and
  amortization 549, so 1,223 against the workbook's 1,138; stock compensation 217;
  net cash provided by operating activities 6,038; capital expenditures (895); net
  cash used for investing (1,061); repurchases (3,380); dividends (2,626); net cash
  used for financing (8,254); effect of exchange rates (39).
- FY2022, same filing, Dec. 31 2022 column: 657 and 547, so 1,204; 188; 5,274;
  (766); (93); (4,200); (2,719); (6,330); exchange rates (183).
- FY2023, 0000773840-26-000013, Dec. 31 2023 column: 490 and 514, so 1,004; 197;
  5,340; (741); (1,293); (3,715); (2,855); (5,763); exchange rates 14.
- FY2024, same filing, Dec. 31 2024 column: 493 and 659, so 1,152 against the
  workbook's 1,153; 189; 6,097; (871); (10,157); (1,655); (2,902); 6,839; exchange
  rates (137).
- FY2025, same filing, Dec. 31 2025 column: 546 and 842, so 1,388; 196; 6,408;
  (986); (2,711); (3,804); (2,976); (1,953); exchange rates 176.

Signs: capex, buybacks and dividends are payments in the filing and positive in
the workbook; the three subtotals keep the filing's own sign, including the
positive 6,839 of financing in FY2024, which is the year Honeywell issued 10,408
of long-term debt.

Blanks: cash at the beginning and end of FY2021, with the same malformed message
as the other two copies. Breakage row 6.

Extras: none.

Tags traced: Buybacks FY2021, PaymentsForRepurchaseOfCommonStock,
0000773840-24-000014 -> statement of cash flows, Dec. 31 2021, repurchases of
common stock (3,380). Cash from Operations FY2025,
NetCashProvidedByUsedInOperatingActivities, 0000773840-26-000013 -> same
statement, Dec. 31 2025, 6,408. Capex FY2022,
PaymentsToAcquirePropertyPlantAndEquipment, 0000773840-25-000010 -> its statement
of cash flows, Dec. 31 2022, capital expenditures (766).

### Checks sheet

- [x] Balance check: confirmed as zero by construction, not read as evidence,
      and the flag saying so is present
      Two flags, both present and both correct: TOTAL_DERIVED on the total
      liabilities row, saying the filer tags no element for it and it is derived as
      assets less equity, and CHECK_NOT_AVAILABLE on the balance check itself,
      saying the row is zero because it was made zero. The row is uncoloured.
- [x] Cash tie green in every historical column, or its residual is accounted
      for out of the filer's own statement and the figure is written down here
      Line widened 2026-08-06, as on the Apple copy and for the same reason
      (breakage row 15): the residual is accounted for rather than assumed to be
      one particular thing.
      FY2022 +183, FY2023 -14, FY2024 +798, FY2025 -837, in millions. Two of the
      four are exactly the exchange-rate effect Honeywell reports: the (183) for
      FY2022 and the 14 for FY2023. FY2024 and FY2025 are that effect plus 661:
      the FY2025 10-K restates the Dec. 31 2024 cash balance from 10,567 to 9,906
      by moving a discontinued operation's cash out, and the workbook's balance
      sheet takes the restated figure while the cash flow statement it is measured
      against still opens on the original. So 798 = 137 + 661 and -837 = -176 -
      661. Accounted for to the dollar, and the workbook now says so on its own:
      the FY2023-to-FY2024 comparability seam flags the cash row on both cells
      with the 10,567 against 9,906 as its evidence.
- [x] Retained earnings residual is explained by buybacks and other equity
      movements, per year, with the figures written down here:
      FY2022 +19, FY2023 +83, FY2024 +53, FY2025 -1,624, in millions. The first
      three are entirely the excess of dividends paid over dividends declared:
      declared 2,700 against 2,719 paid, 2,772 against 2,855, 2,849 against 2,902.
      Honeywell charges repurchases to treasury stock, not to retained earnings,
      which is why this filer's residual is small where Apple's is enormous.
      FY2025 is the spin-off: the statement of shareowners' equity, R8 of
      0000773840-26-000013, charges 1,651 of Spin-offs and 15 of Other to retained
      earnings, and 1,651 + 15 - 42 of dividend timing is 1,624 exactly.
- [x] Section coverage percentages read for all five balance sheet sections, and
      none of them is a surprise once the 10-K is open beside it. Write the
      lowest one and what sits in its plug:
      FY2025 reads 87.9, 84.7, 58.7, 86.2 and 339.1 percent. The lowest of the
      twenty-five cells is total current liabilities FY2022 at 54.0 percent, whose
      plug of 9,162 is the accrued liabilities line, in one piece, off the face of
      the balance sheet. Honeywell reads high everywhere else because its balance
      sheet is short and the registry reaches most of it. The equity figure above
      100 is the same shape as Apple's below zero: retained earnings of 50,964
      against a total of 15,030 that 43,029 of treasury stock and 5,146 of
      accumulated other comprehensive loss pull down.
- [x] The flag list under the checks says nothing you disagree with
      Eight lines, all true. The commercial paper NO_REPORTED_HISTORY is right,
      the TOTAL_DERIVED line is the one this copy turns on, and the six
      PLUG_TOO_LARGE lines reach the shares they claim. The same scoping caveat as
      Apple's copy applies -- cell-level flags do not reach this list, breakage row
      5 -- and on this filer it hides something: nothing here says that FY2021 has
      no operating income, nor that FY2023 onward is a different basis from the two
      years before it.

### Forecast mechanics

Enter dummy assumptions, then delete them.

Verified through the formula-evaluation harness, as on the Apple copy. A pass in
real Excel is the user's to run if they want it.

- [x] With assumptions filled, all three statements populate and the checks stay
      green
      All 222 forecast formula cells return numbers, no cell evaluates to an
      error, and the balance check, cash tie and retained earnings roll-forward
      are zero in all three forecast columns.
- [x] With assumptions blank, all forecast cells are blank: no zeros, no
      leftovers
      All 222 return empty as shipped.
- [ ] Rows with no forecast say why when you hover the row label
      Reserved for the user. The text is present: the four per-share and share
      count rows carry NO_FORECAST_DRIVER and commercial paper carries
      NO_REPORTED_HISTORY.

### The workbook itself

- [ ] Opens in real Excel with no repair prompt, opened by hand
- [x] All seven sheets present, all comments readable, no #REF! or #VALUE!
      anywhere
      Seven sheets, 48 defined names, 402 comments, and no error value anywhere in
      a full evaluation, blank or filled. "Readable" belongs with the open above.

### Sitting log

Left for the user: the interactive open above, the hover-tooltip line, and the
signature. Everything else on this copy is worked, with its evidence beside it.

| Date | Where you stopped |
| --- | --- |
| 2026-08-05 | Value comparison complete for all five years of all three statements. Eight entries open in the breakage log against this copy (rows 5, 6, 7, 8, 9, 10, 11 and 16), so it cannot be signed. |

    Signed off:                              Date:

---

## Copy 3. Kroger

    Company:            The Kroger Co.
    Ticker / CIK:       KR / 56873
    Scaffold file:      app/exports/acceptance/KROGER_CO/
                        KROGER_CO_3Statement_2026-08-05_1632.xlsx
    Generated on:       2026-08-05 16:32, from the committed fixture
    Years in workbook:  FY2021 to FY2025 historical, FY2026E to FY2028E forecast
    10-K checked:       FY2025 0001104659-26-037723 (filed 2026-03-31, year ended 2026-01-31)
                        FY2024 0001558370-25-004267 (filed 2025-04-01, year ended 2025-02-01)
                        FY2023 0001558370-24-004603 (filed 2024-04-02, year ended 2024-02-03)
                        FY2022 0001558370-23-004767 (filed 2023-03-28, year ended 2023-01-28)
                        FY2021 0001558370-22-004595 (filed 2022-04-01, year ended 2022-01-29)
                        https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=56873&type=10-K

Kroger is in the set for its 52 or 53 week fiscal year ending in late January
and for its thin tagging in older years. Three things about it are known and are
not bugs: it tags no inventory element, so its inventory row is blank and its
current asset plug says it absorbed it; it tags no SG&A or R&D element, so its
whole operating cost lands in the operating plug and that plug is negative; and
its cost of revenue chain ends in an element that excludes depreciation where
the others include it, so the rows above it carry a seam flag from FY2018.

All three were confirmed against EDGAR rather than assumed. The companyconcept
API returns 404 for both SellingGeneralAndAdministrativeExpense and
ResearchAndDevelopmentExpense on this filer, meaning it has never reported
either, and its four InventoryNet facts all end in 2010, outside every column of
this workbook.

- [x] Column headings match the fiscal years the filings' own statements name
      Amended 2026-08-06, closing breakage row 14. The line asked for agreement
      with the cover pages, and read literally it cannot be ticked for this
      filer, because two of its five cover pages disagree with their own
      filings. The statements are the authority where the two part company, and
      this line now says so.
      The workbook's five columns end 2022-01-29, 2023-01-28, 2024-02-03,
      2025-02-01 and 2026-01-31, and read FY2021 to FY2025. Document Fiscal Year
      Focus on the five cover pages reads 2021, 2022, 2024, 2025 and 2025: the
      third and fourth are a year ahead of the workbook and the fourth and fifth
      collide on one name, so two columns would share a heading if the cover
      pages were followed. The statements side with the workbook. The balance
      sheet parenthetical reads "1,918 shares issued in 2021 and 2020" in the
      first, "in 2023 and 2022" in the third and "in 2025 and 2024" in the
      fifth, so the year ended 2024-02-03 is Kroger's fiscal 2023 and the year
      ended 2025-02-01 its fiscal 2024, which is what the headings say. The
      FY2024 10-K's own prose agrees: "within 120 days after the end of the
      fiscal year 2024" for the year ended 2025-02-01. The headings are right
      and two cover pages are the error, which is what PROGRESS.md open question
      8 established and what the fiscal-year offset rule of 2026-08-05 is built
      on: the filer's convention is read across all nineteen of its annual
      filings, which vote 17 to 2 for an offset of one, rather than taken at
      face value year by year.
- [x] The fiscal-2018 cost-of-revenue seam is described where this window can
      show it, and the wording is defensible
      Amended 2026-08-06, closing breakage row 13. The line asked for a
      TAG_TRANSITION flag on the seam, and no five-year window ending in FY2025
      can carry one: Kroger resolves through
      CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization in all
      five columns, so no column crosses the seam and the flag has nothing to
      mark. It would need an acceptance run over a window starting before fiscal
      2018, which is a different check from this one.
      What a checker can find, and what this line now asks for, is the Cost of
      Revenue row's own note. It names Kroger, names fiscal 2018, and quotes the
      caption -- "Merchandise costs, including advertising, warehousing, and
      transportation, excluding items shown separately below" -- which the FY2025
      10-K's statement of operations carries word for word. It says the element
      excludes depreciation and amortisation where the others include it, that a
      filer resolving through it reports a narrower cost line and a wider gross
      profit, and that the seam is flagged where a row crosses it. That is
      accurate and it is where a reader of this workbook will meet the fact.
      Two TAG_TRANSITION flags are present and both are right: accounts payable
      switching from AccountsPayableTradeCurrent to AccountsPayableCurrent after
      the period ending 2023-01-28, and interest expense switching from
      InterestExpense to InterestIncomeExpenseNonoperatingNet after the period
      ending 2024-02-03, which is the switch that turns the row negative.

### Income statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
| FY2021 | [x] | [x] | [x] | [x] |
| FY2022 | [x] | [x] | [x] | [x] |
| FY2023 | [x] | [x] | [x] | [x] |
| FY2024 | [x] | [x] | [x] | [x] |
| FY2025 | [x] | [x] | [x] | [x] |

Citations. Read off CONSOLIDATED STATEMENTS OF OPERATIONS (R4), in millions.

- FY2021, 0001558370-24-004603, Jan. 29 2022 column: sales 137,888; merchandise
  costs 107,539; operating profit 3,477; interest expense (571); net earnings
  before income tax 2,051; income tax 385; net earnings attributable to The Kroger
  Co. 1,655; EPS 2.20 basic and 2.17 diluted; 744 and 754 million shares.
- FY2022, same filing, Jan. 28 2023 column: 148,258; 116,480; 4,126; (535);
  2,902; 653; 2,244; 3.10 and 3.06; 718 and 727 million.
- FY2023, 0001104659-26-037723, Feb. 03 2024 column: 150,039; 116,675; 3,096;
  (441); 2,836; 667; 2,164; 2.99 and 2.96; 718 and 725 million.
- FY2024, same filing, Feb. 01 2025 column: 147,123; 113,720; 3,849; net interest
  expense (450); 3,342; 670; 2,665; 3.70 and 3.67; 715 and 720 million.
- FY2025, same filing, Jan. 31 2026 column: 147,642; 113,240; 1,890; net interest
  expense (639); 1,200; 176; 1,016; 1.55 and 1.54; 652 and 655 million.

Signs, and the one that changes. Kroger presents interest as a deduction in all
five years. The workbook carries it positive in FY2021 to FY2023, where the row
resolves through InterestExpense, and negative in FY2024 and FY2025, where it
resolves through InterestIncomeExpenseNonoperatingNet and takes the filer's own
sign. That is the sign flip the row note warns about and the TAG_TRANSITION flag
marks. It is correct in the sense that each cell carries what its tag holds, and
it means the row cannot be summed across the seam. The other-income plug below it
absorbs the difference and inherits the flag.

Blanks: SG&A and R&D in all five years, each with "Not tagged in XBRL" and the
right index URL, and each confirmed above against EDGAR. Kroger's operating,
general and administrative expense of 28,308 in FY2025, its rent of 872 and its
depreciation and amortization of 3,332 are therefore all inside the operating
plug, which is why that plug is -32,512 and 1,720 percent of operating income at
its worst. The plug is flagged and the flag is right.

Extras: none.

Tags traced: Cost of Revenue FY2025,
CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization,
0001104659-26-037723 -> statements of operations, Jan. 31 2026, merchandise costs
113,240. Interest Expense FY2025, InterestIncomeExpenseNonoperatingNet, same
filing -> same statement, net interest expense (639), which is the -639 the
workbook shows. Operating Income FY2021, OperatingIncomeLoss,
0001558370-24-004603 -> its statements of operations, Jan. 29 2022, operating
profit 3,477.

### Balance sheet, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
| FY2021 | [ ] | [x] | [x] | [x] |
| FY2022 | [ ] | [x] | [x] | [x] |
| FY2023 | [ ] | [x] | [x] | [x] |
| FY2024 | [ ] | [x] | [x] | [x] |
| FY2025 | [ ] | [x] | [x] | [x] |

No year is ticked for a match, for the two debt rows. Kroger presents debt and
finance leases in one caption on each side of the balance sheet and also tags the
debt-only amounts separately; the chains take the debt-only tags, so both rows
read below the caption above them in every year. Breakage row 12. Every other row
matches in every year.

Citations. Read off CONSOLIDATED BALANCE SHEETS (R2), in millions.

- FY2021, 0001558370-22-004595, Jan. 29 2022 column: cash and temporary cash
  investments 1,821; receivables 1,828; total current assets 12,174; PP&E 23,789;
  intangibles net 942; goodwill 3,076; total assets 49,086; trade accounts payable
  7,117; current portion of long-term debt including finance leases 555 against
  the workbook's 451; total current liabilities 16,323; long-term debt including
  finance leases 12,809 against 11,294; total liabilities 39,657; accumulated
  earnings 24,066; total equity 9,429.
- FY2022, 0001558370-24-004603, Jan. 28 2023 column: 1,015; 2,234; 12,670;
  24,726; 899; 2,916; 49,623; 10,179; 1,310 against 1,153; 17,238; 12,068 against
  10,139; 39,609; 25,601; 10,014.
- FY2023, same filing, Feb. 03 2024 column: 1,883; 2,136; 12,948; 25,230; 899;
  2,916; 50,505; 10,381; 198 against 25; 16,058; 12,028 against 10,162; 38,904;
  26,946; 11,601.
- FY2024, 0001104659-26-037723, Feb. 01 2025 column: 3,959; 2,195; 15,273;
  25,703; 834; 2,674; 52,616; 10,124; 272 against 104; 15,940; 17,633 against
  15,805; 44,335; 28,724; 8,281.
- FY2025, same filing, Jan. 31 2026 column: 3,334; 2,192; 14,505; 24,260; 808;
  2,595; 49,953; 10,488; 1,802 against 1,366; 18,108; 15,764 against 14,509;
  44,017; 28,850; 5,936.

Total equity is the figure including noncontrolling interests, which is what the
balance check needs and what the row note says; Kroger's total shareowners'
equity attributable to the parent is 5,927 in FY2025 against the 5,936 shown.

Blanks: Inventory, Short-Term Investments, Commercial Paper and Short-Term
Borrowings, all five years each, every one with a flag message and the right
index URL. All four are correct. Kroger presents no single inventory line -- FIFO
inventory 9,445 less a LIFO reserve of 2,553 at Jan. 31 2026 -- and carries none
of the other three captions at all. The 6,892 of net inventory sits inside the
current-asset plug, which is what the plug's note says.

Extras: none.

Tags traced: Total Liabilities FY2024, Liabilities, 0001104659-26-037723 ->
balance sheets, Feb. 01 2025, Total Liabilities 44,335. Accounts Payable FY2022,
AccountsPayableTradeCurrent, 0001558370-24-004603 -> its balance sheets, Jan. 28
2023, trade accounts payable 10,179, which is the tag the TAG_TRANSITION flag
names as the one before the switch. Intangibles FY2025,
IntangibleAssetsNetExcludingGoodwill, 0001104659-26-037723 -> balance sheets, Jan.
31 2026, Intangibles net 808.

### Cash flow statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
| FY2021 | [x] | [x] | [x] | [x] |
| FY2022 | [x] | [x] | [x] | [x] |
| FY2023 | [x] | [x] | [x] | [x] |
| FY2024 | [x] | [x] | [x] | [x] |
| FY2025 | [x] | [x] | [x] | [x] |

Citations. Read off CONSOLIDATED STATEMENTS OF CASH FLOWS (R7), in millions.

- FY2021, 0001558370-24-004603, Jan. 29 2022 column: depreciation and
  amortization 2,824; share-based employee compensation 203; net cash provided by
  operating activities 6,190; payments for property and equipment (2,614); net cash
  used by investing (2,611); dividends paid (589); treasury stock purchases
  (1,647); net cash used by financing (3,445).
- FY2022, same filing, Jan. 28 2023 column: 2,965; 190; 4,498; (3,078); (3,015);
  (682); (993); (2,289).
- FY2023, 0001104659-26-037723, Feb. 03 2024 column: 3,125; 172; 6,788; (3,904);
  (3,750); (796); (62); (2,170).
- FY2024, same filing, Feb. 01 2025 column: 3,246; 175; 5,794; (4,017); (3,228);
  (883); (4,156); (490).
- FY2025, same filing, Jan. 31 2026 column: 3,332; 157; 7,311; (3,855); (3,914);
  (885); (2,699); (4,022).

Signs: capex, dividends and buybacks are payments in the filing and positive in
the workbook; the subtotals keep the filing's sign. Kroger reports no effect of
exchange rates and no restricted cash, so the statement's own beginning and
ending balances are the balance sheet's cash line to the dollar in every year:
1,015, 1,883, 3,959 and 3,334 in the last four.

Blanks: cash at the beginning and end of FY2021, same malformed message as the
other two copies. Breakage row 6.

Extras: none.

Tags traced: Capex FY2023, PaymentsToAcquirePropertyPlantAndEquipment,
0001104659-26-037723 -> statements of cash flows, Feb. 03 2024, payments for
property and equipment including payments for lease buyouts (3,904). D&A FY2021,
DepreciationDepletionAndAmortization, 0001558370-24-004603 -> its statements of
cash flows, Jan. 29 2022, depreciation and amortization 2,824. Buybacks FY2024,
PaymentsForRepurchaseOfCommonStock, 0001104659-26-037723 -> statements of cash
flows, Feb. 01 2025, treasury stock purchases (4,156).

### Checks sheet

- [x] Balance check green in every historical column
      0 in all five columns, and unlike Honeywell's this one is evidence: Kroger
      tags Liabilities, so the row is three reported numbers meeting.
- [x] Cash tie green in every historical column, or its residual is the filer's
      effect of exchange rates on cash and the figure is written down here:
      0 in all four columns that have one. Kroger reports no exchange-rate effect
      and no restricted cash, so there is nothing for a residual to be.
- [x] Retained earnings residual is explained by buybacks and other equity
      movements, per year, with the figures written down here:
      FY2022 -27, FY2023 -23, FY2024 -4, FY2025 -5, in millions, and every one of
      them is dividends declared against dividends paid and nothing else. FY2025 is
      the worked case: the statement of changes in shareowners' equity, R8 of
      0001104659-26-037723, moves accumulated earnings from 28,724 by net earnings
      attributable of 1,016 and cash dividends declared of 890 to 28,850, and 890
      against the 885 paid is the 5. Kroger charges treasury stock purchases -- 3,154
      at cost in FY2025 against 2,699 of cash -- to treasury stock, so they never
      touch this row. This is the third of the three shapes in the acceptance set:
      Apple's residual is a buyback, Honeywell's a spin-off, Kroger's a timing
      difference of a few million.
- [x] Section coverage percentages read for all five balance sheet sections, and
      none of them is a surprise once the 10-K is open beside it. Write the
      lowest one and what sits in its plug:
      FY2025 reads 38.1, 84.4, 65.5, 74.1 and 486.0 percent. The lowest of the
      twenty-five cells is total current assets FY2022 at 25.6 percent, whose plug
      of 9,421 is store deposits in-transit 1,127, FIFO inventory 9,756 less a LIFO
      reserve of 2,196, and prepaid and other current assets 734, which is 9,421 to
      the dollar. Low because the registry's inventory row is blank for this filer
      and the section's largest component is inventory; it says the current-asset
      breakdown cannot be relied on and says nothing about the 12,670 subtotal,
      which is Kroger's own. Equity at 486 percent is retained earnings of 28,850
      against a total of 5,936 that 28,113 of treasury stock holds down.
- [x] The flag list under the checks says nothing you disagree with
      Eleven lines. The six NO_REPORTED_HISTORY rows -- SG&A, R&D, short-term
      investments, inventory, commercial paper, short-term borrowings -- are each
      listed separately, which is the Session 6 fix working: keyed on the row alone
      they would have collapsed to one. The five PLUG_TOO_LARGE lines reach the
      shares they claim, including the operating plug's 1,720 percent, which is the
      worst of its five years and is written as "reaches", not as a fact about one
      column. The same scoping caveat as the other two copies applies, breakage row
      5: the two false LARGE_YOY_CHANGE flags of breakage row 2 do not appear here,
      and neither do the two TAG_TRANSITION flags this copy turns on.

### Forecast mechanics

Enter dummy assumptions, then delete them.

Verified through the formula-evaluation harness, as on the other two copies. A
pass in real Excel is the user's to run if they want it.

- [x] With assumptions filled, all three statements populate and the checks stay
      green
      All 207 forecast formula cells return numbers, no cell evaluates to an
      error, and all three checks are zero in all three forecast columns.
- [x] With assumptions blank, all forecast cells are blank: no zeros, no
      leftovers
      All 207 return empty as shipped.
- [ ] Rows with no forecast say why when you hover the row label
      Reserved for the user. The text is present: the four per-share and share
      count rows carry NO_FORECAST_DRIVER, and the six untagged rows above carry
      NO_REPORTED_HISTORY.

### The workbook itself

- [ ] Opens in real Excel with no repair prompt, opened by hand
- [x] All seven sheets present, all comments readable, no #REF! or #VALUE!
      anywhere
      Seven sheets, 48 defined names, 403 comments, and no error value anywhere in
      a full evaluation, blank or filled. "Readable" belongs with the open above.

### Sitting log

Left for the user: the interactive open above, the hover-tooltip line, and the
signature. Everything else on this copy is worked, with its evidence beside it.

| Date | Where you stopped |
| --- | --- |
| 2026-08-05 | Value comparison complete for all five years of all three statements. Six entries open in the breakage log against this copy (rows 2, 5, 6, 12, 13 and 14), so it cannot be signed. |

    Signed off:                              Date:
