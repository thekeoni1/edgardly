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
    Scaffold file:
    Generated on:
    Years in workbook:
    10-K checked:                            (accession number, link)

Each historical year's own accession is on the Source Tags sheet, one line per
value, so a year sourced from a later filing's comparative column says so.

### Income statement, per historical year

| Year | Every line matches the 10-K, value and sign | Blanks the 10-K fills: listed with the flag message shown | Values Edgardly shows that the 10-K does not: listed, and logged as bugs | Source tag spot check, 3 random cells traced to the filing viewer |
| --- | --- | --- | --- | --- |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |

### Balance sheet, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |

### Cash flow statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |

### Checks sheet

- [ ] Balance check green in every historical column
- [ ] Cash tie green in every historical column, or its residual is the filer's
      effect of exchange rates on cash and the figure is written down here:
- [ ] Retained earnings residual is explained by buybacks and other equity
      movements, per year, with the figures written down here:
- [ ] Section coverage percentages read for all five balance sheet sections, and
      none of them is a surprise once the 10-K is open beside it. Write the
      lowest one and what sits in its plug:
- [ ] The flag list under the checks says nothing you disagree with

### Forecast mechanics

Enter dummy assumptions, then delete them.

- [ ] With assumptions filled, all three statements populate and the checks stay
      green
- [ ] With assumptions blank, all forecast cells are blank: no zeros, no
      leftovers
- [ ] Rows with no forecast say why when you hover the row label

### The workbook itself

- [ ] Opens in real Excel with no repair prompt, opened by hand rather than by
      automation, because automation runs with alerts suppressed and would not
      see the dialog
- [ ] All seven sheets present, all comments readable, no #REF! or #VALUE!
      anywhere

### Sitting log

| Date | Where you stopped |
| --- | --- |
|  |  |

    Signed off:                              Date:

---

## Copy 2. Honeywell

    Company:            Honeywell International Inc.
    Ticker / CIK:       HON / 773840
    Scaffold file:
    Generated on:
    Years in workbook:
    10-K checked:                            (accession number, link)

Honeywell tags no Liabilities element for any year, so its total liabilities row
is derived as assets less equity and its balance check is zero because it was
made zero. The Checks sheet says so and the row is left uncoloured. What to
confirm here is that the derived total matches the 10-K's own total liabilities,
which is the check the workbook cannot run for you.

- [ ] Total liabilities, derived, matches the 10-K in every historical year

### Income statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |

### Balance sheet, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |

### Cash flow statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |

### Checks sheet

- [ ] Balance check: confirmed as zero by construction, not read as evidence,
      and the flag saying so is present
- [ ] Cash tie green in every historical column, or its residual is the filer's
      effect of exchange rates on cash and the figure is written down here:
- [ ] Retained earnings residual is explained by buybacks and other equity
      movements, per year, with the figures written down here:
- [ ] Section coverage percentages read for all five balance sheet sections, and
      none of them is a surprise once the 10-K is open beside it. Write the
      lowest one and what sits in its plug:
- [ ] The flag list under the checks says nothing you disagree with

### Forecast mechanics

Enter dummy assumptions, then delete them.

- [ ] With assumptions filled, all three statements populate and the checks stay
      green
- [ ] With assumptions blank, all forecast cells are blank: no zeros, no
      leftovers
- [ ] Rows with no forecast say why when you hover the row label

### The workbook itself

- [ ] Opens in real Excel with no repair prompt, opened by hand
- [ ] All seven sheets present, all comments readable, no #REF! or #VALUE!
      anywhere

### Sitting log

| Date | Where you stopped |
| --- | --- |
|  |  |

    Signed off:                              Date:

---

## Copy 3. Kroger

    Company:            The Kroger Co.
    Ticker / CIK:       KR / 56873
    Scaffold file:
    Generated on:
    Years in workbook:
    10-K checked:                            (accession number, link)

Kroger is in the set for its 52 or 53 week fiscal year ending in late January
and for its thin tagging in older years. Three things about it are known and are
not bugs: it tags no inventory element, so its inventory row is blank and its
current asset plug says it absorbed it; it tags no SG&A or R&D element, so its
whole operating cost lands in the operating plug and that plug is negative; and
its cost of revenue chain ends in an element that excludes depreciation where
the others include it, so the rows above it carry a seam flag from FY2018.

- [ ] Column headings match the fiscal years the 10-K cover pages name
- [ ] The FY2018 seam flag is present and its wording is defensible

### Income statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |

### Balance sheet, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |

### Cash flow statement, per historical year

| Year | Matches | Blanks listed | Extras listed | Tags traced |
| --- | --- | --- | --- | --- |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |
|  | [ ] | [ ] | [ ] | [ ] |

### Checks sheet

- [ ] Balance check green in every historical column
- [ ] Cash tie green in every historical column, or its residual is the filer's
      effect of exchange rates on cash and the figure is written down here:
- [ ] Retained earnings residual is explained by buybacks and other equity
      movements, per year, with the figures written down here:
- [ ] Section coverage percentages read for all five balance sheet sections, and
      none of them is a surprise once the 10-K is open beside it. Write the
      lowest one and what sits in its plug:
- [ ] The flag list under the checks says nothing you disagree with

### Forecast mechanics

Enter dummy assumptions, then delete them.

- [ ] With assumptions filled, all three statements populate and the checks stay
      green
- [ ] With assumptions blank, all forecast cells are blank: no zeros, no
      leftovers
- [ ] Rows with no forecast say why when you hover the row label

### The workbook itself

- [ ] Opens in real Excel with no repair prompt, opened by hand
- [ ] All seven sheets present, all comments readable, no #REF! or #VALUE!
      anywhere

### Sitting log

| Date | Where you stopped |
| --- | --- |
|  |  |

    Signed off:                              Date:
