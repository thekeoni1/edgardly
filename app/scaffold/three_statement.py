"""three_statement.py -- the model spec: rows, periods, provenance, arithmetic.

What this module produces is a description of a three-statement model, not a
workbook. Every row knows which statement it sits on, where each historical
value came from, and what arithmetic ties it to the rows around it. Nothing
here imports openpyxl, and app/scaffold/excel.py is the only thing that turns
any of it into a file.

Four ideas carry the whole module.

**A total is reported; the components plug to it.** XBRL hands over isolated
tagged values, not a statement, so the tagged components of a subtotal almost
never sum to the subtotal a filer reports (V2_PLAN risk R1). Apple tags cash,
short-term investments, receivables and inventory, and those four are two
thirds of its current assets; the rest is vendor non-trade receivables and
other buckets the 41-item registry does not reach. So each subtotal carries an
explicit plug row -- "Other current assets (plug to reported total)" -- written
as arithmetic rather than filled in as a number. On the income statement and
the cash flow statement a plug over a tenth of the total it plugs to is
flagged; on the balance sheet the same measurement is reported as a per-section
coverage percentage instead, because there it is true nearly everywhere and a
warning shown nearly everywhere is one nobody reads. The registry stays 41
items; the gap between it and a filer's balance sheet is shown rather than
closed by guessing.

**A blank is a fact about the filing.** A row a filer does not tag is present,
missing, and explained: Kroger tags no InventoryNet, Honeywell tags no
Liabilities at all. Such a row is never quietly folded into a plug without the
plug saying so, and a plug that absorbed one names it. That is the difference
between a model that is honest about being incomplete and one that looks
complete.

**A filer's own number wins.** Some rows are both: a tag when the filer carries
it, arithmetic when it does not. Apple tags GrossProfit and Honeywell does not;
no filer in the acceptance set tags DebtCurrent, so short-term debt is the sum
of three current-liability lines for all of them; Honeywell tags no Liabilities
at all, so its liability total is assets less equity. The tag is preferred
wherever it exists, per period, and the arithmetic stands in only where it does
not, saying so.

**Every leaf is a tag.** Derived rows and plugs are arithmetic on other rows,
and the descent bottoms out at values a filer reported, with the tag, the
filing date and the accession behind each. Total Debt stands on Short-Term
Debt, which stands on three tagged current-liability lines: two levels of
formula and four reported leaves, all of them visible in the workbook. The
one-level limit the decisions log fixes governs values Edgardly computes and
ships as numbers; here nothing is shipped as a number that a reader cannot
expand in front of them, so depth costs nothing that rule was protecting.

The forecast side is plumbing only. Every forecast cell is arithmetic on an
assumption the analyst enters or on another forecast cell, and a year whose
assumption column is not complete produces nothing at all rather than zeros
pretending to be forecasts.
"""

from collections import namedtuple

import line_items
import periods
import xbrl_extractor as xbrl


# ---------------------------------------------------------------------------
# What a row is
# ---------------------------------------------------------------------------

# A registry item the filer tags. Historical cells are the filer's own numbers.
ROLE_REPORTED = "reported"
# A reported total that the rows above it plug to.
ROLE_SUBTOTAL = "subtotal"
# Arithmetic on other rows, in the historical columns as well as the forecast.
ROLE_DERIVED = "derived"
# The difference between a reported total and the components tagged for it.
ROLE_PLUG = "plug"
# Present for reference, part of no sum.
ROLE_MEMO = "memo"

# A cell is in one of the three states the data layer already uses.
CELL_REPORTED = xbrl.PROVENANCE_REPORTED
CELL_DERIVED = xbrl.PROVENANCE_DERIVED
CELL_MISSING = xbrl.PROVENANCE_MISSING

# A plug bigger than this share of the total it plugs to says the registry does
# not reach far enough into this filer's statements for the section to be
# relied on (V2_PLAN task 2.2b and the decisions log entry behind it). It is
# measured against the total the plug ties to rather than against the
# statement's headline total, which is the stricter of the two readings: a
# subtotal is never larger than the statement it sits in.
PLUG_FLAG_THRESHOLD = 0.10

# Where that warning is worth raising, and where the same measurement is worth
# reporting instead. On the income statement and the cash flow statement a plug
# over the threshold is unusual and says something: it fires on 19 of 44 income
# statement plug cells across the acceptance filers and on 31 of 45 cash flow
# ones. On the balance sheet it fires on 72 of 75, because the 41-item registry
# meets a real balance sheet with right-of-use assets, deferred tax, vendor
# non-trade receivables and a dozen other captions it has no item for. Each
# instance was true and the warning was still useless, because a reader who
# sees it on every subtotal stops reading it. So the balance sheet reports the
# measurement as a per-section coverage percentage on the Checks sheet, which
# is the same number without the sentence that overclaimed. See the decisions
# log entry of 2026-08-05 closing open question 11.
PLUG_FLAG_STATEMENTS = (line_items.STATEMENT_IS, line_items.STATEMENT_CF)
COVERAGE_STATEMENTS = (line_items.STATEMENT_BS,)

FLAG_PLUG_TOO_LARGE = "PLUG_TOO_LARGE"
FLAG_PLUG_ABSORBS_BLANK = "PLUG_ABSORBS_BLANK"
FLAG_TOTAL_DERIVED = "TOTAL_DERIVED"
FLAG_CHECK_NOT_AVAILABLE = "CHECK_NOT_AVAILABLE"
FLAG_NO_FORECAST_DRIVER = "NO_FORECAST_DRIVER"
FLAG_FORECAST_UNANCHORED = "FORECAST_UNANCHORED"
FLAG_NO_REPORTED_HISTORY = "NO_REPORTED_HISTORY"
FLAG_CAPTION_MAY_INCLUDE_LEASES = "CAPTION_MAY_INCLUDE_LEASES"

MODEL_FLAGS = (FLAG_PLUG_TOO_LARGE, FLAG_PLUG_ABSORBS_BLANK, FLAG_TOTAL_DERIVED,
               FLAG_CHECK_NOT_AVAILABLE, FLAG_NO_FORECAST_DRIVER,
               FLAG_FORECAST_UNANCHORED, FLAG_NO_REPORTED_HISTORY,
               FLAG_CAPTION_MAY_INCLUDE_LEASES,
               xbrl.FLAG_TAG_TRANSITION)


# ---------------------------------------------------------------------------
# The expression vocabulary
#
# The whole arithmetic of the model is written in these node types. The writer
# renders them into A1 formulas and never has to know what a plug is; this
# module decides what the arithmetic says and never has to know what a cell
# reference looks like. Keeping the vocabulary this small is also what task 2.5
# asks for: it is exactly the set the formula evaluator handles, so a formula
# the tests cannot check cannot be written here by accident.
# ---------------------------------------------------------------------------

def ref(row_name, offset=0):
    """A cell on another row. offset 0 is this column, -1 the one before it."""
    return ("ref", row_name, offset)


def asm(key):
    """An assumption input, by name. The writer resolves it to a named range."""
    return ("asm", key)


def const(value):
    return ("const", value)


def add(*terms):
    return ("+",) + tuple(terms)


def sub(first, *rest):
    return ("-", first) + tuple(rest)


def mul(*terms):
    return ("*",) + tuple(terms)


def div(numerator, denominator):
    return ("/", numerator, denominator)


def refs_in(expr):
    """Every ("ref", row, offset) node an expression tree reaches."""
    if not isinstance(expr, tuple):
        return []
    if expr[0] == "ref":
        return [expr]
    if expr[0] in ("asm", "const"):
        return []
    found = []
    for part in expr[1:]:
        found.extend(refs_in(part))
    return found


def assumptions_in(expr):
    """Every assumption key an expression tree reaches."""
    if not isinstance(expr, tuple):
        return []
    if expr[0] == "asm":
        return [expr[1]]
    if expr[0] in ("ref", "const"):
        return []
    found = []
    for part in expr[1:]:
        found.extend(assumptions_in(part))
    return found


# ---------------------------------------------------------------------------
# Assumptions
#
# One set per forecast year, every one blank in a generated workbook and every
# one the analyst's to fill. A forecast column whose set is not complete
# produces no forecast at all, which is what the readiness row on the
# Assumptions sheet says out loud rather than leaving a half-built column to be
# mistaken for a model.
# ---------------------------------------------------------------------------

Assumption = namedtuple("Assumption", "key label unit note")

ASSUMPTIONS = (
    Assumption("rev_growth", "Revenue growth", "percent",
               "Applied to the prior year's revenue."),
    Assumption("gross_margin", "Gross margin", "percent",
               "Gross profit as a percent of revenue. Cost of revenue is the "
               "remainder, so the two cannot disagree."),
    Assumption("sga_pct_rev", "SG&A percent of revenue", "percent", ""),
    Assumption("rnd_pct_rev", "R&D percent of revenue", "percent", ""),
    Assumption("da_pct_rev", "D&A percent of revenue", "percent",
               "Drives the add-back on the cash flow statement and the "
               "depreciation leg of the PP&E roll-forward: one number used "
               "twice rather than two that can drift apart."),
    Assumption("capex_pct_rev", "Capex percent of revenue", "percent",
               "A payment, so it is subtracted in investing and added to PP&E."),
    Assumption("sbc_pct_rev", "Stock-based compensation percent of revenue",
               "percent",
               "A non-cash add-back that also builds paid-in capital, so it "
               "appears in both places and nets to nothing in the balance check."),
    Assumption("dso", "Days sales outstanding", "days",
               "Receivables as a share of a 365-day year of revenue."),
    Assumption("dio", "Days inventory outstanding", "days",
               "Inventory as a share of a 365-day year of cost of revenue."),
    Assumption("dpo", "Days payable outstanding", "days",
               "Payables as a share of a 365-day year of cost of revenue."),
    Assumption("interest_rate", "Interest rate on average total debt", "percent",
               "Applied to the average of opening and closing total debt, so an "
               "issuance during the year is charged for half of it."),
    Assumption("tax_rate", "Effective tax rate", "percent",
               "Applied to pretax income."),
    Assumption("dividend_payout", "Dividend payout percent of net income", "percent",
               "A payment, so it is subtracted in financing and out of retained "
               "earnings."),
    Assumption("buyback_pct_ni", "Buybacks percent of net income", "percent",
               "A payment, so it is subtracted in financing and out of equity."),
    Assumption("net_debt_issuance", "Net long-term debt issuance", "currency",
               "In the same units as the statements, negative for a net "
               "repayment. Drives the financing line and the debt balance from "
               "one cell, so the two cannot disagree."),
)

ASSUMPTION_KEYS = tuple(a.key for a in ASSUMPTIONS)
ASSUMPTIONS_BY_KEY = {a.key: a for a in ASSUMPTIONS}

# The sentinel that says a forecast year can be modeled at all: true only when
# every assumption for that year, and every year before it, has been filled in.
READY_KEY = "ready"


# ---------------------------------------------------------------------------
# Row layout
# ---------------------------------------------------------------------------

RowSpec = namedtuple(
    "RowSpec",
    "name item role statement label note components total terms optional_terms "
    "forecast forecast_note")
RowSpec.__new__.__defaults__ = (None, ROLE_REPORTED, None, None, "", (), None, None,
                                False, None, "")


def _registry_note(item):
    entry = line_items.REGISTRY.get(item)
    if entry is None:
        return ""
    parts = [part for part in (entry.sign, entry.note) if part]
    return " ".join(parts)


def _reported(item, role=ROLE_REPORTED, label=None, terms=None, optional_terms=False,
              forecast=None, forecast_note="", note=None):
    """A registry item. Historical cells are the filer's own numbers.

    terms, when given, is the arithmetic that stands in for a period the filer
    did not tag. It never overrides a tag; it only fills what a tag left empty.
    """
    entry = line_items.REGISTRY[item]
    return RowSpec(name=item, item=item, role=role, statement=entry.statement,
                   label=label or item,
                   note=_registry_note(item) if note is None else note,
                   components=(), total=None, terms=terms,
                   optional_terms=optional_terms, forecast=forecast,
                   forecast_note=forecast_note)


def _subtotal(item, components, terms=None, forecast=None, forecast_note="",
              note=None):
    """A reported total that the rows above it are measured against."""
    return _reported(item, role=ROLE_SUBTOTAL, terms=terms, forecast=forecast,
                     forecast_note=forecast_note,
                     note=note)._replace(components=tuple(components))


def _plug(name, total, components, statement, note, forecast=None, forecast_note=""):
    """The difference between a reported total and the components tagged for it."""
    return RowSpec(name=name, item=None, role=ROLE_PLUG, statement=statement,
                   label=name, note=note, components=tuple(components), total=total,
                   terms=None, optional_terms=False, forecast=forecast,
                   forecast_note=forecast_note)


def _derived(name, statement, terms, note, label=None, role=ROLE_DERIVED,
             forecast=None, forecast_note=""):
    """Arithmetic on other rows, with no tag of its own anywhere.

    terms are (row, sign) pairs in this column, or (row, sign, offset) triples
    where the arithmetic reaches back a period. Opening cash is the only row
    that needs the third form, and it needs it exactly because opening cash is
    last period's closing balance.
    """
    return RowSpec(name=name, item=None, role=role, statement=statement,
                   label=label or name, note=note, components=(), total=None,
                   terms=tuple(terms), optional_terms=False, forecast=forecast,
                   forecast_note=forecast_note)


def _memo(item, forecast=None, forecast_note=""):
    return _reported(item, role=ROLE_MEMO, forecast=forecast,
                     forecast_note=forecast_note)


# Reasons a row has no forecast, spelled out where the row is defined so the
# workbook can say them rather than leaving a blank column to be guessed at.
_NO_DRIVER = ("No assumption drives this row, so its forecast columns are left "
              "empty rather than carried forward. A share count needs a "
              "repurchase price and the per-share figures need the count; "
              "neither is something this tool should invent.")

_HELD_FLAT = ("Held at the last reported balance. Nothing in the assumption set "
              "moves it, and a balance that does not move contributes nothing to "
              "the cash flow statement, which is what keeps the forecast balance "
              "sheet tying.")

_HELD_FLAT_IS = ("Held at the last reported amount. It is a residual of what the "
                 "registry reaches rather than a line any filer reports, so there "
                 "is no honest driver for it; the analyst overwrites it or accepts "
                 "it as a run rate.")

_FORECAST_ZERO = ("Zero in the forecast, deliberately. No balance sheet row moves "
                  "with it, so any other figure would push cash with nothing on "
                  "the other side and the balance check would break. The "
                  "historical columns show what it has actually been.")

_PLUG_NAME_OTHER_OPEX = "Other operating items, net (plug to reported total)"
_PLUG_NAME_OTHER_INCOME = "Other income (expense), net (plug to reported total)"
_PLUG_NAME_BELOW_TAX = ("Discontinued operations and noncontrolling interests "
                        "(plug to reported total)")
_PLUG_NAME_OTHER_CA = "Other current assets (plug to reported total)"
_PLUG_NAME_OTHER_NCA = "Other non-current assets (plug to reported total)"
_PLUG_NAME_OTHER_CL = "Other current liabilities (plug to reported total)"
_PLUG_NAME_OTHER_NCL = "Other non-current liabilities (plug to reported total)"
_PLUG_NAME_OTHER_EQUITY = "Other equity components (plug to reported total)"
_PLUG_NAME_WORKING_CAPITAL = ("Working capital and other operating items "
                              "(plug to reported total)")
_PLUG_NAME_OTHER_INVESTING = "Other investing activities (plug to reported total)"
_PLUG_NAME_OTHER_FINANCING = "Other financing activities (plug to reported total)"

_ROW_NET_INCOME_CF = "Net income (from the income statement)"
_ROW_NET_CHANGE = "Net change in cash"
_ROW_CASH_OPEN = "Cash, beginning of period"
_ROW_CASH_CLOSE = "Cash, end of period"


# -- Income statement --------------------------------------------------------

_INCOME_STATEMENT = (
    _reported("Revenue",
              forecast=mul(ref("Revenue", -1), add(const(1), asm("rev_growth")))),
    _reported("Cost of Revenue",
              forecast=sub(ref("Revenue"), ref("Gross Profit"))),
    _reported("Gross Profit", terms=(("Revenue", 1), ("Cost of Revenue", -1)),
              forecast=mul(ref("Revenue"), asm("gross_margin")),
              note="Apple tags GrossProfit and its row is the filer's own number. "
                   "Honeywell and Kroger tag no such element, so theirs is revenue "
                   "less cost of revenue, and the seam in the cost row reaches this "
                   "row with it."),
    _reported("SG&A", forecast=mul(ref("Revenue"), asm("sga_pct_rev"))),
    _reported("R&D", forecast=mul(ref("Revenue"), asm("rnd_pct_rev"))),
    _plug(_PLUG_NAME_OTHER_OPEX, total="Operating Income",
          components=(("Gross Profit", 1), ("SG&A", -1), ("R&D", -1)),
          statement=line_items.STATEMENT_IS,
          note="The operating income the filer reports, less gross profit and plus "
               "the operating expenses the registry reaches. It is a net residual "
               "and goes either way: negative for Kroger, which tags no SG&A "
               "element at all so the whole of its operating cost lands here, and "
               "positive for Honeywell, whose operating income includes items the "
               "three rows above do not. A positive figure adds to operating "
               "income and a negative one subtracts.",
          forecast=ref(_PLUG_NAME_OTHER_OPEX, -1), forecast_note=_HELD_FLAT_IS),
    _subtotal("Operating Income",
              components=(("Gross Profit", 1), ("SG&A", -1), ("R&D", -1),
                          (_PLUG_NAME_OTHER_OPEX, 1)),
              forecast=add(sub(ref("Gross Profit"), ref("SG&A"), ref("R&D")),
                           ref(_PLUG_NAME_OTHER_OPEX))),
    _reported("Interest Expense",
              forecast=mul(asm("interest_rate"),
                           div(add(ref("Total Debt", -1), ref("Total Debt")),
                               const(2)))),
    _plug(_PLUG_NAME_OTHER_INCOME, total="Pretax Income",
          components=(("Operating Income", 1), ("Interest Expense", -1)),
          statement=line_items.STATEMENT_IS,
          note="Operating income less interest, less the pretax income the filer "
               "reports. Interest income, equity method results and everything "
               "else between the two subtotals lands here.",
          forecast=ref(_PLUG_NAME_OTHER_INCOME, -1), forecast_note=_HELD_FLAT_IS),
    _subtotal("Pretax Income",
              components=(("Operating Income", 1), ("Interest Expense", -1),
                          (_PLUG_NAME_OTHER_INCOME, 1)),
              forecast=add(sub(ref("Operating Income"), ref("Interest Expense")),
                           ref(_PLUG_NAME_OTHER_INCOME))),
    _reported("Income Tax Expense",
              forecast=mul(ref("Pretax Income"), asm("tax_rate"))),
    _plug(_PLUG_NAME_BELOW_TAX, total="Net Income",
          components=(("Pretax Income", 1), ("Income Tax Expense", -1)),
          statement=line_items.STATEMENT_IS,
          note="Pretax income less tax, less the net income the filer reports. "
               "Discontinued operations and the share of profit belonging to "
               "noncontrolling interests are what sit between the two.",
          forecast=ref(_PLUG_NAME_BELOW_TAX, -1), forecast_note=_HELD_FLAT_IS),
    _subtotal("Net Income",
              components=(("Pretax Income", 1), ("Income Tax Expense", -1),
                          (_PLUG_NAME_BELOW_TAX, 1)),
              forecast=add(sub(ref("Pretax Income"), ref("Income Tax Expense")),
                           ref(_PLUG_NAME_BELOW_TAX))),
    _derived("EBITDA", line_items.STATEMENT_IS,
             terms=(("Operating Income", 1), ("D&A", 1)), role=ROLE_MEMO,
             note=line_items.DERIVATIONS["EBITDA"].note,
             forecast=add(ref("Operating Income"), ref("D&A"))),
    _memo("EPS Basic", forecast_note=_NO_DRIVER),
    _memo("EPS Diluted", forecast_note=_NO_DRIVER),
    _memo("Shares Outstanding (Basic)", forecast_note=_NO_DRIVER),
    _memo("Shares Outstanding (Diluted)", forecast_note=_NO_DRIVER),
)


# -- Balance sheet -----------------------------------------------------------

_BALANCE_SHEET = (
    _reported("Cash and Equivalents", forecast=ref(_ROW_CASH_CLOSE),
              forecast_note="Read off the cash flow statement, which is the "
                            "linkage the whole model exists to make."),
    _reported("Short-Term Investments", forecast=ref("Short-Term Investments", -1),
              forecast_note=_HELD_FLAT),
    _reported("Accounts Receivable",
              forecast=div(mul(asm("dso"), ref("Revenue")), const(365))),
    _reported("Inventory",
              forecast=div(mul(asm("dio"), ref("Cost of Revenue")), const(365))),
    _plug(_PLUG_NAME_OTHER_CA, total="Total Current Assets",
          components=(("Cash and Equivalents", 1), ("Short-Term Investments", 1),
                      ("Accounts Receivable", 1), ("Inventory", 1)),
          statement=line_items.STATEMENT_BS,
          note="Total current assets the filer reports, less the four current "
               "asset lines the registry reads. Prepaid expenses, deferred costs "
               "and, for some filers, a very large non-trade receivable are here.",
          forecast=ref(_PLUG_NAME_OTHER_CA, -1), forecast_note=_HELD_FLAT),
    _subtotal("Total Current Assets",
              components=(("Cash and Equivalents", 1), ("Short-Term Investments", 1),
                          ("Accounts Receivable", 1), ("Inventory", 1),
                          (_PLUG_NAME_OTHER_CA, 1)),
              forecast=add(ref("Cash and Equivalents"), ref("Short-Term Investments"),
                           ref("Accounts Receivable"), ref("Inventory"),
                           ref(_PLUG_NAME_OTHER_CA))),
    _reported("PP&E Net",
              forecast=add(sub(ref("PP&E Net", -1), ref("D&A")), ref("Capex")),
              forecast_note="The PP&E roll-forward: opening balance, less "
                            "depreciation and amortisation, plus capex."),
    _reported("Goodwill", forecast=ref("Goodwill", -1), forecast_note=_HELD_FLAT),
    _reported("Intangibles", forecast=ref("Intangibles", -1),
              forecast_note=_HELD_FLAT),
    _plug(_PLUG_NAME_OTHER_NCA, total="Total Assets",
          components=(("Total Current Assets", 1), ("PP&E Net", 1), ("Goodwill", 1),
                      ("Intangibles", 1)),
          statement=line_items.STATEMENT_BS,
          note="Total assets the filer reports, less current assets and the three "
               "non-current lines the registry reads. Right-of-use assets, "
               "deferred tax assets and long-term investments are here.",
          forecast=ref(_PLUG_NAME_OTHER_NCA, -1), forecast_note=_HELD_FLAT),
    _subtotal("Total Assets",
              components=(("Total Current Assets", 1), ("PP&E Net", 1),
                          ("Goodwill", 1), ("Intangibles", 1),
                          (_PLUG_NAME_OTHER_NCA, 1)),
              forecast=add(ref("Total Current Assets"), ref("PP&E Net"),
                           ref("Goodwill"), ref("Intangibles"),
                           ref(_PLUG_NAME_OTHER_NCA))),
    _reported("Accounts Payable",
              forecast=div(mul(asm("dpo"), ref("Cost of Revenue")), const(365))),
    _memo("Current Maturities of Long-Term Debt",
          forecast=ref("Current Maturities of Long-Term Debt", -1),
          forecast_note=_HELD_FLAT),
    _memo("Commercial Paper", forecast=ref("Commercial Paper", -1),
          forecast_note=_HELD_FLAT),
    _memo("Short-Term Borrowings", forecast=ref("Short-Term Borrowings", -1),
          forecast_note=_HELD_FLAT),
    _memo("Finance Lease Liability, Current",
          forecast=ref("Finance Lease Liability, Current", -1),
          forecast_note=_HELD_FLAT),
    _reported("Short-Term Debt",
              terms=(("Current Maturities of Long-Term Debt", 1),
                     ("Commercial Paper", 1), ("Short-Term Borrowings", 1)),
              optional_terms=True,
              forecast=ref("Short-Term Debt", -1), forecast_note=_HELD_FLAT),
    _plug(_PLUG_NAME_OTHER_CL, total="Total Current Liabilities",
          components=(("Accounts Payable", 1), ("Short-Term Debt", 1)),
          statement=line_items.STATEMENT_BS,
          note="Total current liabilities the filer reports, less payables and "
               "the current debt balance. Accrued compensation, deferred revenue "
               "and current tax sit here.",
          forecast=ref(_PLUG_NAME_OTHER_CL, -1), forecast_note=_HELD_FLAT),
    _subtotal("Total Current Liabilities",
              components=(("Accounts Payable", 1), ("Short-Term Debt", 1),
                          (_PLUG_NAME_OTHER_CL, 1)),
              forecast=add(ref("Accounts Payable"), ref("Short-Term Debt"),
                           ref(_PLUG_NAME_OTHER_CL))),
    _reported("Long-Term Debt",
              forecast=add(ref("Long-Term Debt", -1), asm("net_debt_issuance")),
              forecast_note="The debt roll-forward: opening balance plus net "
                            "issuance, which is the same cell the financing "
                            "section uses, so the two cannot disagree."),
    _memo("Finance Lease Liability, Non-current",
          forecast=ref("Finance Lease Liability, Non-current", -1),
          forecast_note=_HELD_FLAT),
    _plug(_PLUG_NAME_OTHER_NCL, total="Total Liabilities",
          components=(("Total Current Liabilities", 1), ("Long-Term Debt", 1)),
          statement=line_items.STATEMENT_BS,
          note="Total liabilities the filer reports, less current liabilities and "
               "non-current debt. Pension obligations, deferred tax and long-term "
               "lease liabilities sit here.",
          forecast=ref(_PLUG_NAME_OTHER_NCL, -1), forecast_note=_HELD_FLAT),
    _subtotal("Total Liabilities",
              components=(("Total Current Liabilities", 1), ("Long-Term Debt", 1),
                          (_PLUG_NAME_OTHER_NCL, 1)),
              terms=(("Total Assets", 1), ("Total Equity", -1)),
              forecast=add(ref("Total Current Liabilities"), ref("Long-Term Debt"),
                           ref(_PLUG_NAME_OTHER_NCL)),
              note="Honeywell tags no Liabilities element for any year, so its "
                   "total is assets less equity: the balance sheet equation solved "
                   "for the one term the filer left untagged. That is exact rather "
                   "than approximate, and what it costs is the balance check, "
                   "which then holds by construction rather than by evidence. The "
                   "Checks sheet says so instead of showing a green zero."),
    _reported("Retained Earnings",
              forecast=sub(add(ref("Retained Earnings", -1), ref("Net Income")),
                           ref("Dividends Paid")),
              forecast_note="The retained earnings roll-forward: opening balance, "
                            "plus net income, less dividends."),
    _plug(_PLUG_NAME_OTHER_EQUITY, total="Total Equity",
          components=(("Retained Earnings", 1),),
          statement=line_items.STATEMENT_BS,
          note="Total equity the filer reports, less retained earnings. Common "
               "stock, paid-in capital, treasury stock, accumulated other "
               "comprehensive income and any noncontrolling interest are here.",
          forecast=sub(add(ref(_PLUG_NAME_OTHER_EQUITY, -1),
                           ref("Stock-Based Compensation")),
                       ref("Buybacks")),
          forecast_note="The one plug that is not held flat, because two rows of "
                        "the cash flow statement move it: stock compensation "
                        "builds paid-in capital and a buyback consumes equity. "
                        "Holding it flat would leave the forecast balance check "
                        "short by exactly those two."),
    _subtotal("Total Equity",
              components=(("Retained Earnings", 1), (_PLUG_NAME_OTHER_EQUITY, 1)),
              forecast=add(ref("Retained Earnings"), ref(_PLUG_NAME_OTHER_EQUITY))),
    _derived("Total Debt", line_items.STATEMENT_BS,
             terms=(("Short-Term Debt", 1), ("Long-Term Debt", 1)), role=ROLE_MEMO,
             note=line_items.DERIVATIONS["Total Debt"].note,
             forecast=add(ref("Short-Term Debt"), ref("Long-Term Debt"))),
)


# -- Cash flow statement -----------------------------------------------------

_CASH_FLOW = (
    _derived(_ROW_NET_INCOME_CF, line_items.STATEMENT_CF,
             terms=(("Net Income", 1),),
             note="The same cell as the income statement's bottom line, "
                  "referenced rather than repeated, so the two cannot disagree.",
             forecast=ref("Net Income")),
    _reported("D&A", forecast=mul(ref("Revenue"), asm("da_pct_rev"))),
    _reported("Stock-Based Compensation",
              forecast=mul(ref("Revenue"), asm("sbc_pct_rev"))),
    _plug(_PLUG_NAME_WORKING_CAPITAL, total="Cash from Operations",
          components=((_ROW_NET_INCOME_CF, 1), ("D&A", 1),
                      ("Stock-Based Compensation", 1)),
          statement=line_items.STATEMENT_CF,
          note="Cash from operations the filer reports, less net income and the "
               "two add-backs the registry reads. The working capital movement, "
               "deferred tax and every other operating adjustment are here.",
          forecast=sub(sub(ref("Accounts Payable"), ref("Accounts Payable", -1)),
                       sub(ref("Accounts Receivable"), ref("Accounts Receivable", -1)),
                       sub(ref("Inventory"), ref("Inventory", -1))),
          forecast_note="In the forecast this stops being a plug and becomes the "
                        "working capital movement itself: the change in payables "
                        "less the changes in receivables and inventory, read off "
                        "the balance sheet rows the days assumptions drive. That "
                        "identity is what makes the forecast cash flow statement "
                        "and balance sheet agree."),
    _subtotal("Cash from Operations",
              components=((_ROW_NET_INCOME_CF, 1), ("D&A", 1),
                          ("Stock-Based Compensation", 1),
                          (_PLUG_NAME_WORKING_CAPITAL, 1)),
              forecast=add(ref(_ROW_NET_INCOME_CF), ref("D&A"),
                           ref("Stock-Based Compensation"),
                           ref(_PLUG_NAME_WORKING_CAPITAL))),
    _reported("Capex", forecast=mul(ref("Revenue"), asm("capex_pct_rev"))),
    _plug(_PLUG_NAME_OTHER_INVESTING, total="Cash from Investing",
          components=(("Capex", -1),),
          statement=line_items.STATEMENT_CF,
          note="Cash from investing the filer reports, plus capex, which is "
               "reported as a positive payment and is therefore subtracted "
               "everywhere it appears. Purchases and maturities of securities and "
               "acquisitions are here, and for a filer with a large securities "
               "portfolio this is the biggest number on the statement.",
          forecast=const(0), forecast_note=_FORECAST_ZERO),
    _subtotal("Cash from Investing",
              components=(("Capex", -1), (_PLUG_NAME_OTHER_INVESTING, 1)),
              forecast=add(mul(const(-1), ref("Capex")),
                           ref(_PLUG_NAME_OTHER_INVESTING))),
    _reported("Dividends Paid",
              forecast=mul(ref("Net Income"), asm("dividend_payout"))),
    _reported("Buybacks", forecast=mul(ref("Net Income"), asm("buyback_pct_ni"))),
    _plug(_PLUG_NAME_OTHER_FINANCING, total="Cash from Financing",
          components=(("Dividends Paid", -1), ("Buybacks", -1)),
          statement=line_items.STATEMENT_CF,
          note="Cash from financing the filer reports, plus dividends and "
               "buybacks, both reported as positive payments and therefore "
               "subtracted. Debt issued and repaid is here.",
          forecast=asm("net_debt_issuance"),
          forecast_note="In the forecast this is the net debt issuance "
                        "assumption, the same cell the debt balance moves by, so "
                        "the financing section and the balance sheet cannot "
                        "disagree."),
    _subtotal("Cash from Financing",
              components=(("Dividends Paid", -1), ("Buybacks", -1),
                          (_PLUG_NAME_OTHER_FINANCING, 1)),
              forecast=add(mul(const(-1), ref("Dividends Paid")),
                           mul(const(-1), ref("Buybacks")),
                           ref(_PLUG_NAME_OTHER_FINANCING))),
    _derived(_ROW_NET_CHANGE, line_items.STATEMENT_CF,
             terms=(("Cash from Operations", 1), ("Cash from Investing", 1),
                    ("Cash from Financing", 1)),
             note="The three sections added. A filer's own statement also carries "
                  "the effect of exchange rate changes on cash, which no registry "
                  "item reads, so for a filer with foreign operations this and the "
                  "movement in the balance sheet's cash line differ by that "
                  "amount. The cash tie on the Checks sheet is where it shows.",
             forecast=add(ref("Cash from Operations"), ref("Cash from Investing"),
                          ref("Cash from Financing"))),
    _derived(_ROW_CASH_OPEN, line_items.STATEMENT_CF,
             terms=(("Cash and Equivalents", 1, -1),),
             note="The prior column's closing balance sheet cash. The first "
                  "historical column has no prior column, so it has no opening "
                  "balance and the cash tie cannot be run for it.",
             forecast=ref("Cash and Equivalents", -1)),
    _derived(_ROW_CASH_CLOSE, line_items.STATEMENT_CF,
             terms=((_ROW_CASH_OPEN, 1), (_ROW_NET_CHANGE, 1)),
             note="Opening cash plus the net change. In the forecast the balance "
                  "sheet reads its cash line from here, which is the linkage that "
                  "makes the model a model rather than three tables.",
             forecast=add(ref(_ROW_CASH_OPEN), ref(_ROW_NET_CHANGE))),
)


STATEMENT_BLOCKS = (
    (line_items.STATEMENT_IS, "Income Statement", _INCOME_STATEMENT),
    (line_items.STATEMENT_BS, "Balance Sheet", _BALANCE_SHEET),
    (line_items.STATEMENT_CF, "Cash Flow", _CASH_FLOW),
)

ALL_ROW_SPECS = tuple(row for _code, _title, block in STATEMENT_BLOCKS
                      for row in block)

# Rows whose arithmetic fallback is the same identity a check tests. Falling
# back to one disarms that check, which the Checks sheet has to say rather than
# show a zero that was made rather than found.
_IDENTITY_FALLBACKS = {"Total Liabilities": "Balance check"}


# -- Checks ------------------------------------------------------------------

CheckSpec = namedtuple("CheckSpec", "name terms tie note")

CHECKS = (
    CheckSpec(
        "Balance check (assets less liabilities and equity)",
        terms=(("Total Assets", 1, 0), ("Total Liabilities", -1, 0),
               ("Total Equity", -1, 0)),
        tie=True,
        note="Zero when the balance sheet holds. A filer that tags no Liabilities "
             "element has its total derived from this very identity, and the row "
             "is then zero because it was made zero; that case is flagged and says "
             "so rather than showing a green zero that means nothing."),
    CheckSpec(
        "Cash tie (cash flow close less balance sheet cash)",
        terms=((_ROW_CASH_CLOSE, 1, 0), ("Cash and Equivalents", -1, 0)),
        tie=True,
        note="Zero when the cash flow statement closes on the balance sheet's cash "
             "line. A filer with foreign operations reports an exchange rate "
             "effect on cash that no registry item reads, and that is what a "
             "non-zero residual here usually is."),
    CheckSpec(
        "Retained earnings roll-forward residual",
        terms=(("Retained Earnings", 1, 0), ("Retained Earnings", -1, -1),
               ("Net Income", -1, 0), ("Dividends Paid", 1, 0)),
        tie=False,
        note="Closing retained earnings, less opening, less net income, plus "
             "dividends. A residual and not a tie: filers charge share "
             "retirements, treasury stock and other equity movements to retained "
             "earnings and none of those is a registry item, so a non-zero figure "
             "here is ordinary rather than wrong. It is zero by construction in "
             "the forecast columns, where that roll-forward is the definition of "
             "the row."),
)


def _check_terms(check):
    """A check's terms as (row, sign, offset), tolerating a two-part shorthand."""
    return tuple(term if len(term) == 3 else (term[0], term[1], 0)
                 for term in check.terms)


# ---------------------------------------------------------------------------
# Building the model
# ---------------------------------------------------------------------------

Cell = namedtuple("Cell", "value state provenance flags terms")
Cell.__new__.__defaults__ = (None, CELL_MISSING, None, (), None)

Row = namedtuple("Row", "name item role statement label note components total terms "
                        "optional_terms forecast forecast_note cells unit flags")

Period = namedtuple("Period", "key label kind index")

PERIOD_HISTORICAL = "historical"
PERIOD_FORECAST = "forecast"

ModelSpec = namedtuple(
    "ModelSpec",
    "cik entity scope periods rows checks assumptions flags fiscal_year_offset "
    "coverage")
ModelSpec.__new__.__defaults__ = ((),)


def _triples(terms):
    """Normalise terms to (row, sign, offset), defaulting to this column."""
    return tuple(term if len(term) == 3 else (term[0], term[1], 0)
                 for term in terms)


def _plug_terms(spec):
    """A plug's arithmetic: the reported total, less every component."""
    return _triples(((spec.total, 1),) + tuple((name, -sign)
                                               for name, sign in spec.components))


def _cell_value(cells, row_name, key):
    cell = (cells.get(row_name) or {}).get(key)
    return cell.value if cell is not None else None


def _evaluate(cells, terms, key, period_keys, optional=False):
    """Evaluate (row, sign, offset) terms for one column.

    Absent means absent: one missing input makes the result missing rather than
    smaller, which is the rule the data layer applies and for the same reason.
    A hole is never read as a zero.

    optional is the one exception the decisions log already carries, for a total
    whose components a filer picks from. At least one term must be present or
    the result is still missing, so a total of nothing never becomes zero.
    """
    index = period_keys.index(key)
    total = 0.0
    used = []
    for row_name, sign, offset in terms:
        position = index + offset
        value = (None if position < 0 or position >= len(period_keys)
                 else _cell_value(cells, row_name, period_keys[position]))
        if value is None:
            if not optional:
                return None, ()
            continue
        total += sign * value
        used.append((row_name, sign, offset))
    if not used:
        return None, ()
    return total, tuple(used)


def _missing_terms(cells, terms, key, period_keys):
    """Which of a row's inputs had no value, so an absence can be explained."""
    index = period_keys.index(key)
    absent = []
    for row_name, _sign, offset in terms:
        position = index + offset
        if (position < 0 or position >= len(period_keys)
                or _cell_value(cells, row_name, period_keys[position]) is None):
            absent.append(row_name)
    return absent


_PLUG_TOO_LARGE_TAIL = (
    "This filer's XBRL is too sparse for this section of the scaffold to be "
    "relied on: most of the subtotal sits in elements the registry does not "
    "read, so the components above do not describe it.")


def _plug_too_large_message(share, total_row, reaches=False):
    """One sentence, written once, so a cell and a summary cannot disagree.

    The summary form says "reaches" and carries the worst year's share, because
    a row flagged in five years with five different percentages has to report
    one of them and the smallest would be the wrong one to pick.
    """
    return "This plug {} {:.0f} percent of {}. {}".format(
        "reaches" if reaches else "is", 100.0 * share, total_row,
        _PLUG_TOO_LARGE_TAIL)


def _flag(flag_type, message, period_end=None, details=None):
    return {"flag_type": flag_type, "message": message, "period_end": period_end,
            "details": details or {}}


def _formula_text(terms):
    """The arithmetic a derived cell carries, in words a reader can check."""
    parts = []
    for row_name, sign, offset in terms:
        name = row_name if not offset else "{} (prior period)".format(row_name)
        if not parts:
            parts.append(name if sign > 0 else "-{}".format(name))
        else:
            parts.append("{} {}".format("+" if sign > 0 else "-", name))
    return " ".join(parts)


def _derivation_input(row_name, cell):
    """One entry of a derived cell's provenance, describing where it came from.

    A reported input names its tag and its filing. A derived input carries its
    own formula and its own inputs instead, so a total standing on a subtotal
    can still be followed all the way down to values a filer tagged.
    """
    entry = {"name": row_name, "value": cell.value}
    prov = cell.provenance or {}
    if prov.get("state") == CELL_REPORTED:
        entry.update({"tag": prov.get("tag"), "filed": prov.get("filed"),
                      "accession": prov.get("accession")})
    elif prov.get("state") == CELL_DERIVED:
        entry.update({"formula": prov.get("formula"),
                      "inputs": prov.get("inputs", [])})
    return entry


def _provenance_inputs(cells, terms, key, period_keys):
    index = period_keys.index(key)
    return [_derivation_input(name, cells[name][period_keys[index + offset]])
            for name, _sign, offset in terms]


# -- Ordering ----------------------------------------------------------------

def _dependencies(spec):
    """Which rows a row's historical arithmetic stands on."""
    if spec.role == ROLE_PLUG:
        return {term[0] for term in _plug_terms(spec)}
    if spec.terms:
        return {term[0] for term in spec.terms}
    return set()


def _computation_order(spec_rows):
    """Layout order is for reading; this is the order the arithmetic needs.

    A plug needs the total it plugs to, and a total a filer never tagged needs
    the rows its identity is built from, which sit below it on the page. Sorting
    by dependency rather than by layout is what lets Honeywell's liability plug
    stand on a total that is itself derived, without the two being written in
    the order they happen to be printed in.
    """
    by_name = {spec.name: spec for spec in spec_rows}
    ordered = []
    placed = set()
    visiting = set()

    def visit(name):
        if name in placed or name not in by_name:
            return
        if name in visiting:
            raise ValueError("circular row dependency at {}".format(name))
        visiting.add(name)
        for dependency in sorted(_dependencies(by_name[name])):
            visit(dependency)
        visiting.discard(name)
        placed.add(name)
        ordered.append(by_name[name])

    for spec in spec_rows:
        visit(spec.name)
    return ordered


# -- Cells -------------------------------------------------------------------

def _reported_cells(deduped, item, period_keys, all_flags):
    """One cell per period for a registry item, from the filer's own numbers.

    A historical column of this model is a fiscal year of a filed annual
    report, so a value only an interim filing carries is not one of the filer's
    own numbers for this column. Ranking already hands the period to the 10-K
    wherever a 10-K reports the item; where none does, a 10-Q comparative used
    to win by default, and the row took a figure no annual report presents.
    Apple's FY2025 Intangibles was the case: 13,301 million off the re-presented
    balance sheet of the 10-Q filed 2026-07-31, on a row Apple's 10-K does not
    carry, and the whole intangibles balance where the row is the non-current
    half (breakage log rows 3 and 4).

    Such a period is returned separately rather than dropped, so the hole can
    name the figure it declined and the filing behind it. See the decisions log
    entry of 2026-08-05.

    Returns (cells, interim), the second keyed by period end.
    """
    info = deduped.get(item) or {"data": []}
    chosen = periods.points_by_end(info["data"], set(period_keys), periods.ANNUAL)
    item_flags = all_flags.get(item, [])
    cells = {}
    interim = {}
    for key in period_keys:
        dp = chosen.get(key)
        if dp is None:
            continue
        if not xbrl.is_annual_report_form(dp.get("form")):
            interim[key] = dp
            continue
        flags = tuple(_flag(f["flag_type"], f["message"], key, f.get("details"))
                      for f in item_flags if f.get("period_end") == key)
        cells[key] = Cell(dp["value"], CELL_REPORTED, xbrl.reported_provenance(dp),
                          flags, None)
    return cells, interim


def _fill_plug(spec, cells, period_keys):
    """The difference between a reported total and the components tagged for it.

    Computed only where the total is there to plug to. Where a component is
    absent the plug still computes and records which component it swallowed: a
    filer that tags no inventory has its inventory inside the current-asset
    plug, and saying so is the difference between a plug and a place to hide
    things.
    """
    built = cells[spec.name]
    for key in period_keys:
        total = _cell_value(cells, spec.total, key)
        if total is None:
            continue
        present = [(name, sign) for name, sign in spec.components
                   if _cell_value(cells, name, key) is not None]
        absorbed = [name for name, _sign in spec.components
                    if _cell_value(cells, name, key) is None]
        value = total - sum(sign * _cell_value(cells, name, key)
                            for name, sign in present)
        used = _triples(((spec.total, 1),)
                        + tuple((name, -sign) for name, sign in present))
        flags = []
        if absorbed:
            flags.append(_flag(
                FLAG_PLUG_ABSORBS_BLANK,
                "This plug absorbs {}, which the filer does not tag for this "
                "period. It is larger than it would otherwise be by whatever that "
                "line holds, and the line itself is shown blank above rather than "
                "quietly folded in here.".format(", ".join(absorbed)),
                key, {"absorbed": absorbed}))
        if (spec.statement in PLUG_FLAG_STATEMENTS and total
                and abs(value) > PLUG_FLAG_THRESHOLD * abs(total)):
            flags.append(_flag(
                FLAG_PLUG_TOO_LARGE,
                _plug_too_large_message(abs(value) / abs(total), spec.total),
                key, {"share_of_total": abs(value) / abs(total),
                      "total_row": spec.total, "plug": value, "total": total}))
        built[key] = Cell(value, CELL_DERIVED,
                          xbrl.derived_provenance(
                              _formula_text(used),
                              _provenance_inputs(cells, used, key, period_keys)),
                          tuple(flags), used)


def _fill_terms(spec, cells, period_keys):
    """Fill what a tag left empty, from the arithmetic the row carries.

    Never over a reported value: a filer's own number wins wherever it exists,
    which is why this runs over the holes rather than over the row.
    """
    built = cells[spec.name]
    terms = _triples(spec.terms)
    identity = spec.name in _IDENTITY_FALLBACKS
    for key in period_keys:
        if built.get(key) is not None:
            continue
        value, used = _evaluate(cells, terms, key, period_keys, spec.optional_terms)
        if value is None:
            continue
        flags = ()
        if identity:
            flags = (_flag(
                FLAG_TOTAL_DERIVED,
                "This filer tags no element for this row, so it is derived as {}. "
                "That is the balance sheet equation solved for the one term the "
                "filer left untagged, which is exact; what it costs is the {}, "
                "which then holds by construction rather than by "
                "evidence.".format(_formula_text(used),
                                   _IDENTITY_FALLBACKS[spec.name].lower()),
                key),)
        built[key] = Cell(value, CELL_DERIVED,
                          xbrl.derived_provenance(
                              _formula_text(used),
                              _provenance_inputs(cells, used, key, period_keys)),
                          flags, used)


def _row_terms(spec):
    """The arithmetic a row is filled by, or None if it has none at all."""
    if spec.role == ROLE_PLUG:
        return _plug_terms(spec)
    if spec.terms:
        return _triples(spec.terms)
    return None


def _no_prior_column_sentence(formula, first_label, inherited_from=None):
    """The sentence for a blank the model's own window caused.

    Neither of the two things the other flags say is true here. The filer did
    tag the input: Apple's FY2021 cash of 34,940 million is on the same
    workbook's balance sheet. And there is nothing to go and look up, because
    what is absent is a column of this model rather than a line of the filing.
    The old message said both at once -- "Edgardly computes it as ." with an
    empty formula, then "Cash and Equivalents is not reported for this period"
    about a figure two sheets away (breakage log row 6).
    """
    if inherited_from is None:
        return ("Computed as {}, which reaches back to the period before {}. "
                "That column is outside the model's window, so there is no "
                "opening balance for it to read. The filer does report one; what "
                "is missing here is a column of this model, not a line of the "
                "filing".format(formula, first_label))
    return ("Computed as {}. {} is blank for the same reason, and the reason is "
            "the model rather than the filer: there is no column before {} to "
            "read an opening balance from".format(formula, inherited_from,
                                                  first_label))


def _missing_reason(spec, cells, key, index, period_keys, tagged_ends, interim,
                    first_label, no_prior):
    """Which kind of absence this is, and the sentence it needs.

    Returns the keyword arguments missing_provenance takes, so the decision
    about what an absence means is made once, here, rather than split between
    this module and the message.
    """
    if key in interim:
        return {"flag": xbrl.FLAG_NOT_IN_ANNUAL_REPORT, "interim": interim[key]}

    terms = _row_terms(spec)
    if terms is None:
        return {"flag": (xbrl.FLAG_PERIOD_UNRESOLVED if key in tagged_ends
                         else xbrl.FLAG_NOT_TAGGED)}

    short_of = tuple(_missing_terms(cells, terms, key, period_keys))
    # A row that is a registry derivation carries the registry's own formula, so
    # a reader sees the rule rather than this model's rendering of it. Everything
    # else -- every plug, and the four cash flow links -- is a construct of the
    # scaffold with no registry entry to look up, which is where the empty
    # formula came from.
    formula = (None if (spec.name in line_items.DERIVATIONS
                        or spec.item in line_items.DERIVATIONS)
               else _formula_text(terms))

    off_edge = any(index + offset < 0 for _name, _sign, offset in terms)
    inherited = next((name for name, _sign, offset in terms
                      if (name, period_keys[index + offset]) in no_prior
                      and 0 <= index + offset < len(period_keys)), None)
    if off_edge or inherited is not None:
        return {"flag": xbrl.FLAG_NO_PRIOR_COLUMN,
                "opening": _no_prior_column_sentence(
                    formula or _formula_text(terms), first_label,
                    None if off_edge else inherited)}

    return {"flag": xbrl.FLAG_DERIVATION_UNAVAILABLE, "missing_inputs": short_of,
            "formula": formula}


def _build_rows(spec_rows, deduped, cik, period_keys, labels, all_flags, pointers):
    """Every row's historical cells: reported first, then arithmetic, then holes."""
    cells = {spec.name: {} for spec in spec_rows}
    interim_cells = {spec.name: {} for spec in spec_rows}

    for spec in spec_rows:
        if spec.item is not None:
            cells[spec.name], interim_cells[spec.name] = _reported_cells(
                deduped, spec.item, period_keys, all_flags)

    for spec in _computation_order(spec_rows):
        if spec.role == ROLE_PLUG:
            _fill_plug(spec, cells, period_keys)
        elif spec.terms:
            _fill_terms(spec, cells, period_keys)

    # The holes, in the order the arithmetic ran rather than the order the page
    # prints, so a row whose input is blank for the model's own reason can say
    # so instead of repeating the reason as if it were its own.
    no_prior = set()
    for spec in _computation_order(spec_rows):
        built = cells[spec.name]
        interim = interim_cells[spec.name]
        tagged = set()
        if spec.item:
            info = deduped.get(spec.item) or {"data": []}
            tagged = {dp.get("end") for dp in info["data"]
                      if dp.get("value") is not None}
        for index, key in enumerate(period_keys):
            if built.get(key) is not None:
                continue
            reason = _missing_reason(spec, cells, key, index, period_keys, tagged,
                                     interim, labels[0], no_prior)
            if reason["flag"] == xbrl.FLAG_NO_PRIOR_COLUMN:
                no_prior.add((spec.name, key))
            built[key] = Cell(
                None, CELL_MISSING,
                xbrl.missing_provenance(
                    spec.item or spec.name, labels[index], cik,
                    pointers.get(key),
                    statement_label=(None if spec.item else
                                     line_items.STATEMENT_LABELS.get(spec.statement, "")),
                    **reason),
                (), None)

    rows = []
    for spec in spec_rows:
        entry = line_items.REGISTRY.get(spec.item) if spec.item else None
        unit = entry.unit if entry is not None else line_items.UNIT_DOLLAR
        rows.append(Row(spec.name, spec.item, spec.role, spec.statement, spec.label,
                        spec.note, spec.components, spec.total, spec.terms,
                        spec.optional_terms, spec.forecast, spec.forecast_note,
                        cells[spec.name], unit, ()))
    return rows, cells


# A debt row, the finance lease row that may or may not sit inside the caption
# beside it, and the word for which half of the balance sheet they are on.
_LEASE_BESIDE_DEBT = (
    ("Current Maturities of Long-Term Debt", "Finance Lease Liability, Current",
     "current"),
    ("Long-Term Debt", "Finance Lease Liability, Non-current", "non-current"),
)


def _flag_lease_captions(cells, period_keys):
    """Say what a debt row does not include, where the filer reports it.

    A balance sheet that presents debt and finance leases as one caption shows
    the two added, and the combined total is a presentation subtotal a filer
    need not tag. Kroger does not tag it: its "long-term debt including
    obligations under finance leases" of 15,764 million at 2026-01-31 is in no
    taxonomy of its companyfacts payload, so no chain can reach it and the row
    reads 14,509, which is the line above nothing on the statement.

    Composing the sum would mean deciding that this filer's caption combines
    them with nothing in the data to decide it from, and Apple is the
    counter-example: it tags a finance lease liability too and its "Term debt"
    caption excludes it, so an unconditional sum would take Apple's row off its
    own caption to put Kroger's on its. So the arithmetic goes in front of the
    reader instead, on the row that is short of it, with both terms on the page
    (decisions log and breakage log row 12).

    Raised only where the row resolved through a debt-only element. A row that
    resolved through the combined element already is the caption, and telling
    its reader to add the leases again would be worse than silence.
    """
    for debt_row, lease_row, half in _LEASE_BESIDE_DEBT:
        for key in period_keys:
            debt = (cells.get(debt_row) or {}).get(key)
            lease = _cell_value(cells, lease_row, key)
            if debt is None or debt.value is None or not lease:
                continue
            tag = (debt.provenance or {}).get("tag")
            if tag in line_items.COMBINED_DEBT_AND_LEASE_TAGS:
                continue
            cells[debt_row][key] = debt._replace(flags=debt.flags + (_flag(
                FLAG_CAPTION_MAY_INCLUDE_LEASES,
                "This row is debt alone: it comes from {}, which excludes finance "
                "leases. The filer also reports a {} finance lease obligation of "
                "{:,.0f} at this date, on its own row beside this one. Some balance "
                "sheets present the two as one caption and show them added, in "
                "which case the caption is {:,.0f} and this row sits below the line "
                "it appears beside by exactly the lease amount; others present them "
                "separately, in which case this row is the caption and nothing "
                "needs adding. The combined caption is a presentation subtotal a "
                "filer need not tag, and where it is untagged Edgardly cannot tell "
                "the two presentations apart, so it puts both terms in front of "
                "you rather than guessing which shape this filer used.".format(
                    tag, half, lease, debt.value + lease),
                key, {"debt_row": debt_row, "lease_row": lease_row,
                      "lease": lease, "debt": debt.value,
                      "caption_if_combined": debt.value + lease}),))


def _propagate_flags(rows, cells, period_keys, kinds=(xbrl.FLAG_TAG_TRANSITION,)):
    """A row standing on a flagged cell carries the flag too.

    Cost of Revenue is the reason. Its chain ends in an element that excludes
    depreciation where the others include it, so a row crossing that seam
    changes meaning and so does everything computed from it: gross profit, the
    operating expense plug, EBITDA. The seam is flagged on the reported row
    already; carrying it up the arithmetic means a reader looking at gross
    profit sees it without having to know what gross profit is made of.
    """
    changed = True
    while changed:
        changed = False
        for row in rows:
            for index, key in enumerate(period_keys):
                cell = cells[row.name][key]
                if cell.terms is None:
                    continue
                seen = {(f["flag_type"], (f.get("details") or {}).get("inherited_from"))
                        for f in cell.flags}
                inherited = []
                for source, _sign, offset in cell.terms:
                    position = index + offset
                    if position < 0 or position >= len(period_keys):
                        continue
                    parent = cells[source][period_keys[position]]
                    for flag in parent.flags:
                        if flag["flag_type"] not in kinds:
                            continue
                        origin = ((flag.get("details") or {}).get("inherited_from")
                                  or source)
                        if (flag["flag_type"], origin) in seen:
                            continue
                        seen.add((flag["flag_type"], origin))
                        inherited.append(_flag(
                            flag["flag_type"],
                            "{} stands on {}, which is flagged for this period. "
                            "{}".format(row.name, source, flag["message"]),
                            key, dict(flag.get("details") or {},
                                      inherited_from=origin)))
                if inherited:
                    cells[row.name][key] = cell._replace(
                        flags=cell.flags + tuple(inherited))
                    changed = True
    return [row._replace(cells=cells[row.name]) for row in rows]


# -- Periods -----------------------------------------------------------------

def _historical_periods(deduped, names, start_year, end_year, history_years,
                        fy_offset):
    """The fiscal years the model covers, oldest first.

    Judged by dates through the same period engine both existing views run on,
    so a scaffold cannot disagree about which years exist with the table the
    user just looked at.
    """
    confirmed = periods.period_ends(deduped, names, periods.ANNUAL)
    ends = sorted(end for end in confirmed if start_year <= int(end[:4]) <= end_year)
    if history_years:
        ends = ends[-history_years:]
    annual_ends = sorted(confirmed)
    return tuple(
        Period(end, xbrl.period_label(end, "FY", "annual", fy_offset, annual_ends),
               PERIOD_HISTORICAL, index)
        for index, end in enumerate(ends))


def _forecast_periods(historical, forecast_years, fy_offset):
    """Forecast columns, named for the years after the last one reported.

    The label carries an E so a model is never mistaken for a filing. It counts
    on from the last historical label rather than off a date, because that label
    is what the filer's own fiscal-year convention already produced.
    """
    if not historical or not forecast_years:
        return ()
    try:
        last = int(historical[-1].label[2:])
    except (ValueError, IndexError):
        return ()
    return tuple(
        Period("FC{}".format(index + 1), "FY{}E".format(last + index + 1),
               PERIOD_FORECAST, len(historical) + index)
        for index in range(forecast_years))


def _never_reported(cells, name):
    """True when no historical column holds a value for this row at all."""
    built = cells.get(name) or {}
    return not any(cell.value is not None for cell in built.values())


def _unanchored(row, cells, last_key, never_reported):
    """Which prior-period cells a row's first forecast column would stand on.

    A forecast that opens on a hole is not a forecast. Where the last reported
    column has no value for something the first forecast column needs, the row
    gets none and says why, rather than reading the hole as a zero and
    modelling forward from a number nobody reported.

    A row that is blank in every column is a different thing and not a hole:
    the filer carries no such line for this whole window, whatever it holds is
    already inside a plug, and referring to it is referring to nothing. Those
    references are left alone, because an empty Excel cell contributes zero to
    a sum and zero is the right contribution from a line that is not there. It
    is also the only answer that keeps the forecast balance sheet tying: the
    working capital movement has to see the same change in inventory the
    balance sheet does, and for a filer that tags none, both are nothing.
    """
    if row.forecast is None:
        return ()
    missing = []
    for _kind, name, offset in refs_in(row.forecast):
        if offset != -1 or name in never_reported:
            continue
        cell = (cells.get(name) or {}).get(last_key)
        if cell is None or cell.value is None:
            missing.append(name)
    return tuple(sorted(set(missing)))


# -- Checks ------------------------------------------------------------------

def _build_checks(cells, period_keys, disarmed):
    """The tie-outs, and an honest word about the one that cannot be a tie."""
    built = []
    for check in CHECKS:
        terms = _check_terms(check)
        flags = tuple(_flag(FLAG_CHECK_NOT_AVAILABLE,
                            "This is not a check for this filer. {} is derived "
                            "from the same identity this row tests, so the row is "
                            "zero because it was made zero. What can still be read "
                            "off it is that the derived total is what the "
                            "components above were measured against.".format(name))
                      for name in sorted(disarmed)
                      if any(row == name for row, _sign, _offset in terms))
        cells_out = {}
        for key in period_keys:
            value, _used = _evaluate(cells, terms, key, period_keys)
            cells_out[key] = Cell(value, CELL_DERIVED if value is not None
                                  else CELL_MISSING, None, (), terms)
        built.append({"name": check.name, "terms": terms, "note": check.note,
                      "tie": check.tie and not flags, "cells": cells_out,
                      "flags": flags})
    return tuple(built)


# -- Coverage ----------------------------------------------------------------

COVERAGE_NOTE = (
    "The share of this reported subtotal that the line items the registry reads "
    "actually account for. The remainder is the plug row beside them, so a "
    "section at 68 percent is one where roughly a third of the subtotal sits in "
    "elements Edgardly does not read.\n\n"
    "Above 100 percent means the components sum to more than the subtotal, and "
    "below zero that they sum against it. Both are ordinary on the equity "
    "section, where retained earnings is measured against a total that treasury "
    "stock and accumulated other comprehensive income pull down: three of the "
    "acceptance filers land between minus 34 and plus 486 percent there and none "
    "of them is wrong.\n\n"
    "What a figure far from 100 limits is the breakdown above it, never the "
    "subtotal itself, which is the filer's own reported number either way. This "
    "is a measurement rather than a warning, because on a balance sheet it is "
    "low almost everywhere and a warning shown almost everywhere is one nobody "
    "reads."
)


def _build_coverage(spec_rows, cells, period_keys):
    """Per-section coverage on the statements that report it rather than warn.

    One entry per plug on a covered statement, carrying the fraction of each
    period's subtotal that its components reached. A section whose components
    sum to more than the reported total comes out above 100 percent, which is
    the honest reading of a negative plug rather than something to hide behind
    an absolute value.
    """
    built = []
    for spec in spec_rows:
        if spec.role != ROLE_PLUG or spec.statement not in COVERAGE_STATEMENTS:
            continue
        cells_out = {}
        for key in period_keys:
            total = _cell_value(cells, spec.total, key)
            plug = _cell_value(cells, spec.name, key)
            cells_out[key] = (None if not total or plug is None
                              else (total - plug) / total)
        built.append({"name": spec.total, "total_row": spec.total,
                      "plug_row": spec.name, "statement": spec.statement,
                      "cells": cells_out})
    return tuple(built)


# -- Entry point -------------------------------------------------------------

def build_model(cik, facts, sic=None, start_year=1990, end_year=2100,
                history_years=5, forecast_years=3):
    """Assemble the three-statement model spec for one filer.

    facts is a companyfacts payload; sic is the code from the submissions API,
    which the scope gate needs and companyfacts does not carry. Nothing here
    reaches the network.

    A filer the gate refuses gets a spec carrying the refusal and no rows at
    all. That is the whole of the refusal: the caller shows the message, and no
    half-built model is left lying around for something else to pick up by
    mistake.
    """
    scope = line_items.is_in_scope(sic, facts)
    entity = (facts or {}).get("entityName", str(cik))
    fy_offset = xbrl.fiscal_year_offset(facts)

    if not scope.in_scope:
        return ModelSpec(cik, entity, scope, (), (), (), ASSUMPTIONS, (), fy_offset)

    names = sorted({spec.item for spec in ALL_ROW_SPECS if spec.item})
    raw = xbrl.extract_all_line_items(facts, names)
    deduped = xbrl.deduplicate_all_line_items(raw)
    all_flags = xbrl.validate_financials(deduped)
    pointers = xbrl.filing_pointers(facts)

    historical = _historical_periods(deduped, names, start_year, end_year,
                                     history_years, fy_offset)
    if not historical:
        return ModelSpec(
            cik, entity, scope, (), (), (), ASSUMPTIONS,
            (_flag(xbrl.FLAG_NOT_TAGGED,
                   "This filer reports no fiscal year Edgardly can confirm, so "
                   "there is nothing to build a model on."),),
            fy_offset)

    period_keys = [p.key for p in historical]
    labels = [p.label for p in historical]

    rows, cells = _build_rows(ALL_ROW_SPECS, deduped, cik, period_keys, labels,
                              all_flags, pointers)
    _flag_lease_captions(cells, period_keys)
    rows = _propagate_flags(rows, cells, period_keys)

    disarmed = {name for name in _IDENTITY_FALLBACKS
                if any(cell.state == CELL_DERIVED
                       and any(f["flag_type"] == FLAG_TOTAL_DERIVED
                               for f in cell.flags)
                       for cell in cells[name].values())}

    forecast = _forecast_periods(historical, forecast_years, fy_offset)
    never_reported = {row.name for row in rows if _never_reported(cells, row.name)}
    model_flags = []
    final_rows = []
    for row in rows:
        row_flags = []
        if row.forecast is not None and forecast and row.name in never_reported:
            # Not a hole to model around: the filer carries no such line in any
            # of these years, so whatever it holds is already inside a plug that
            # is held flat, and forecasting it separately would count it twice.
            flag = _flag(
                FLAG_NO_REPORTED_HISTORY,
                "{} has no forecast: this filer tags no value for it in any year "
                "the model covers. Whatever the line holds is already inside the "
                "plug beside it, which is carried forward, so modelling it "
                "separately would count it twice.".format(row.name))
            row_flags.append(flag)
            model_flags.append(flag)
            row = row._replace(forecast=None)
        elif row.forecast is None and row.forecast_note:
            row_flags.append(_flag(FLAG_NO_FORECAST_DRIVER, row.forecast_note))
        elif row.forecast is not None and forecast:
            unanchored = _unanchored(row, cells, period_keys[-1], never_reported)
            if unanchored:
                flag = _flag(
                    FLAG_FORECAST_UNANCHORED,
                    "{} has no forecast: it would have to start from {} in {}, "
                    "which this filer does not report. A forecast built on a hole "
                    "is a guess with a formula in front of it.".format(
                        row.name, ", ".join(unanchored), labels[-1]))
                row_flags.append(flag)
                model_flags.append(flag)
                row = row._replace(forecast=None)
        final_rows.append(row._replace(flags=tuple(row_flags)))

    for row in final_rows:
        for key in period_keys:
            for flag in row.cells[key].flags:
                if flag["flag_type"] in (FLAG_PLUG_TOO_LARGE, FLAG_TOTAL_DERIVED):
                    model_flags.append(
                        dict(flag, details=dict(flag.get("details") or {},
                                                row=row.name)))

    checks = _build_checks(cells, period_keys, disarmed)
    for check in checks:
        model_flags.extend(check["flags"])
    coverage = _build_coverage(ALL_ROW_SPECS, cells, period_keys)

    return ModelSpec(cik, entity, scope, historical + forecast, tuple(final_rows),
                     checks, ASSUMPTIONS, tuple(model_flags), fy_offset, coverage)


# ---------------------------------------------------------------------------
# Reading a spec
# ---------------------------------------------------------------------------

def historical_periods(spec):
    return tuple(p for p in spec.periods if p.kind == PERIOD_HISTORICAL)


def forecast_periods(spec):
    return tuple(p for p in spec.periods if p.kind == PERIOD_FORECAST)


def rows_for(spec, statement):
    return tuple(row for row in spec.rows if row.statement == statement)


def row_named(spec, name):
    for row in spec.rows:
        if row.name == name:
            return row
    return None


def plug_flags(spec):
    """Every flagged plug, which is an income statement or cash flow one.

    A balance-sheet plug over the threshold is reported as coverage instead and
    never appears here; see PLUG_FLAG_STATEMENTS for why.
    """
    return tuple(f for f in spec.flags if f["flag_type"] == FLAG_PLUG_TOO_LARGE)


def summarised_flags(spec):
    """One line per flagged row, not one per flagged cell.

    A plug that is too large is usually too large in every year, and thirty
    copies of the same sentence is a way of not being read. So a flag that
    names a row is collapsed to that row, keeping the worst share it reached
    and counting the periods it covered; anything else is collapsed by its own
    message, which is what keeps six rows that each say "this filer tags no
    value for it" from collapsing into one row's worth of news.
    """
    summary = {}
    order = []
    for flag in spec.flags:
        details = flag.get("details") or {}
        key = (flag["flag_type"], details.get("row") or flag["message"])
        if key not in summary:
            summary[key] = {"flag_type": flag["flag_type"],
                            "message": flag["message"],
                            "details": dict(details), "periods": []}
            order.append(key)
        entry = summary[key]
        if flag.get("period_end"):
            entry["periods"].append(flag["period_end"])
        share = details.get("share_of_total")
        if share is not None:
            entry["details"]["share_of_total"] = max(
                share, entry["details"].get("share_of_total", 0))
    total = len(historical_periods(spec))
    out = []
    for key in order:
        entry = summary[key]
        message = entry["message"]
        row = entry["details"].get("row")
        periods_seen = len(set(entry["periods"]))
        if entry["flag_type"] == FLAG_PLUG_TOO_LARGE:
            message = _plug_too_large_message(entry["details"]["share_of_total"],
                                              entry["details"]["total_row"],
                                              reaches=periods_seen > 1)
        if row:
            message = "{}: {}".format(row, message)
        if entry["periods"]:
            message = "{} ({} of {} historical periods)".format(
                message, periods_seen, total)
        out.append({"flag_type": entry["flag_type"], "message": message,
                    "details": entry["details"]})
    return tuple(out)


def coverage_for(spec, total_row):
    """One section's coverage entry, by the subtotal it measures."""
    for entry in spec.coverage:
        if entry["total_row"] == total_row:
            return entry
    return None
