"""line_items.py -- the canonical line-item registry.

Single home for the facts that describe what a line item IS, independent of how
any one view renders it: which statement it belongs to, whether it is a flow or
an instant, which unit class it carries, which XBRL tags report it, and how it is
derived when no tag reports it at all.

The registry is a superset of what the UI shows. TAG_MAP, the extraction set the
single-company table and the peer table have always driven off, stays at the same
14 items it has always held; UI_LINE_ITEMS names them and fixes their display
order. Everything else in the registry is available to callers that ask for it by
name (the scaffold engine will) without appearing in any existing view.

Nothing here reads EDGAR. Tag resolution lives in xbrl_extractor, which imports
TAG_MAP and tags_for from this module.
"""

from collections import namedtuple


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# Statement the item belongs to.
STATEMENT_IS = "IS"   # income statement
STATEMENT_BS = "BS"   # balance sheet
STATEMENT_CF = "CF"   # cash flow statement

# How to name a statement to a reader. A missing value's pointer says which
# statement of the filing to go look at, so the code needs prose, not a code.
STATEMENT_LABELS = {
    STATEMENT_IS: "income statement",
    STATEMENT_BS: "balance sheet",
    STATEMENT_CF: "cash flow statement",
}

# Flow items cover a span of time and carry both a start and an end date.
# Instants are measured at one date and carry an end only.
KIND_FLOW = "flow"
KIND_INSTANT = "instant"

# Unit class. Drives number formats, scale factors, and the column headers that
# name the units. Every item is in exactly one class.
UNIT_DOLLAR = "dollar"
UNIT_EPS = "eps"
UNIT_SHARES = "shares"


# sign records the convention a reader needs to use the number correctly (an
# expense reported positive, a payment that is really an outflow). note records
# what the chain does not say: which fallback is broader than its label, why a
# source was chosen. Both are empty when there is nothing worth saying.
LineItem = namedtuple("LineItem", "name statement kind unit tags sign note")

# inputs is a tuple of (line-item name, sign) pairs; formula is the human-readable
# string that ships with the value as its provenance.
Derivation = namedtuple("Derivation", "name statement kind unit inputs formula note")


def _item(name, statement, kind, unit, tags, sign="", note=""):
    return LineItem(name, statement, kind, unit, tuple(tags), sign, note)


# ---------------------------------------------------------------------------
# Reported items
#
# Each entry's tag list is a fallback chain in preference order. Resolution is
# per period, not per series: for any one period the earliest tag in the chain
# that reports that period wins, so a company that switched tags mid-history
# keeps both eras. Correcting a chain is a one-line edit here.
#
# Chains are validated against the committed fixtures in
# app/tests/test_real_filings.py. A chain that has not yet met a fixture is a
# proposal, not a verified fact.
# ---------------------------------------------------------------------------

_REGISTRY_ITEMS = [

    # -- Income statement -------------------------------------------------
    _item("Revenue", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ], note="ASC 606 moved most filers off Revenues to the "
            "RevenueFromContractWithCustomer tags around FY2018. Both eras are kept."),

    _item("Cost of Revenue", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfServices",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
    ], note="The last tag excludes depreciation and amortization, which the others "
            "include, so a filer resolving through it reports a narrower cost line and a "
            "correspondingly wider gross profit. It is last for that reason and the seam "
            "is flagged where a row crosses it. Kroger (CIK 56873) is such a filer from "
            "fiscal 2018 on, and its income statement says so on the face of the "
            "statement: \"Merchandise costs, including advertising, warehousing, and "
            "transportation, excluding items shown separately below\"."),

    _item("Gross Profit", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "GrossProfit",
    ], note="Filers that report no GrossProfit tag can be derived: see "
            "DERIVATIONS['Gross Profit']."),

    _item("SG&A", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
    ], sign="Positive as an expense.",
       note="The second tag excludes selling costs, so a filer resolving through it "
            "reports a narrower figure than the label promises."),

    _item("R&D", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "ResearchAndDevelopmentExpense",
    ], sign="Positive as an expense."),

    _item("Operating Income", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "OperatingIncomeLoss",
    ]),

    _item("Interest Expense", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
        "InterestIncomeExpenseNet",
        "InterestIncomeExpenseNonoperatingNet",
    ], sign="Positive as an expense through the first three tags. The last two are net "
            "figures and carry the filer's own sign: Kroger tags its \"Net interest "
            "expense\" of 639 million as -639, so a row that crosses into them can change "
            "sign without the underlying expense changing direction. The seam is flagged.",
       note="InterestAndDebtExpense bundles other financing charges in with interest, "
            "which is how Honeywell (CIK 773840) presents the line: \"Interest and other "
            "financial charges\", 1,344 million for FY2025. It is the filer's own interest "
            "line and the only one it tags."),

    _item("Pretax Income", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ], note="Continuing operations only. A filer with discontinued operations reports a "
            "different total on the face of the income statement."),

    _item("Income Tax Expense", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "IncomeTaxExpenseBenefit",
    ], sign="Positive as an expense; negative when the period records a net benefit."),

    _item("Net Income", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR, [
        "NetIncomeLoss",
        "ProfitLoss",
    ], note="NetIncomeLoss is attributable to the parent; ProfitLoss includes "
            "noncontrolling interests."),

    _item("EPS Basic", STATEMENT_IS, KIND_FLOW, UNIT_EPS, [
        "EarningsPerShareBasic",
    ]),

    _item("EPS Diluted", STATEMENT_IS, KIND_FLOW, UNIT_EPS, [
        "EarningsPerShareDiluted",
    ]),

    _item("Shares Outstanding (Basic)", STATEMENT_IS, KIND_FLOW, UNIT_SHARES, [
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ], note="Weighted average over the period, not the count on the balance sheet date."),

    _item("Shares Outstanding (Diluted)", STATEMENT_IS, KIND_FLOW, UNIT_SHARES, [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ], note="Weighted average over the period, not the count on the balance sheet date."),

    # -- Balance sheet ----------------------------------------------------
    _item("Cash and Equivalents", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ], note="The fallback includes restricted cash, so a filer resolving through it "
            "reports more than unrestricted cash."),

    _item("Short-Term Investments", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
    ]),

    _item("Accounts Receivable", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "AccountsReceivableNetCurrent",
        "ReceivablesNetCurrent",
    ], note="Net of allowance. The fallback covers receivables beyond trade accounts."),

    _item("Inventory", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "InventoryNet",
    ]),

    _item("Total Current Assets", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "AssetsCurrent",
    ], note="Absent for filers using an unclassified balance sheet."),

    _item("PP&E Net", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "PropertyPlantAndEquipmentNet",
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulated"
        "DepreciationAndAmortization",
    ], note="The second tag is the successor element filers moved to after ASC 842 put "
            "finance-lease right-of-use assets inside the same balance-sheet caption. It "
            "is the same line, not a broader one: Honeywell and Kroger each tag both in "
            "their transition year and the two agree to the dollar (5,471 million for "
            "Honeywell at 2022-12-31, 21,871 for Kroger at 2020-02-01). Without it both "
            "filers' rows stop dead at the transition."),

    _item("Goodwill", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "Goodwill",
    ]),

    _item("Intangibles", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "FiniteLivedIntangibleAssetsNet",
        "IntangibleAssetsNetExcludingGoodwill",
    ], note="Excludes goodwill. The first tag also excludes indefinite-lived intangibles, "
            "which the second one includes."),

    _item("Total Assets", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "Assets",
    ]),

    _item("Accounts Payable", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "AccountsPayableCurrent",
        "AccountsPayableTradeCurrent",
        "AccountsPayableAndAccruedLiabilitiesCurrent",
    ], note="AccountsPayableTradeCurrent is the narrower trade-only element; Kroger "
            "(CIK 56873) used it until fiscal 2023 and the two agree to the dollar in the "
            "year it tags both (10,381 million at 2024-02-03). The last fallback goes the "
            "other way and bundles accrued liabilities in with payables."),

    _item("Total Current Liabilities", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "LiabilitiesCurrent",
    ], note="Absent for filers using an unclassified balance sheet."),

    _item("Short-Term Debt", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "DebtCurrent",
        "LongTermDebtCurrent",
        "ShortTermBorrowings",
    ], note="DebtCurrent is the whole current debt balance. The fallbacks are components "
            "of it: current maturities of long-term debt, and short-term borrowings. A "
            "filer resolving through either fallback reports less than all current debt. "
            "Apple is such a filer. It tags no DebtCurrent, so this row falls through to "
            "LongTermDebtCurrent and misses the commercial paper it carries alongside "
            "(5,985 million in FY2023). Closing that gap needs a summed derivation rather "
            "than a chain edit, which is a Session 4 decision."),

    _item("Long-Term Debt", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
    ], note="Strictly the non-current balance, through either of the first two tags. "
            "LongTermDebtAndCapitalLeaseObligations is the non-current line of a filer "
            "that presents debt and finance leases as one caption; its current half is "
            "LongTermDebtAndCapitalLeaseObligationsCurrent, a different tag, which is why "
            "it belongs here and its name does not mean it includes current maturities. "
            "The last fallback does: LongTermDebt covers the whole long-term balance "
            "including current maturities, so a filer resolving through it reports a row "
            "broader than its label, and Total Debt double-counts for exactly those "
            "periods. It is last because it is the one tag here whose meaning does not "
            "match the row. Apple reaches it only for FY2012 and FY2013, before Apple "
            "tagged LongTermDebtNoncurrent and while it carried no current maturities at "
            "all, so the two happen to agree; JPMorgan reaches it throughout, and no "
            "scaffold is generated for a bank. Honeywell was the filer this caveat was "
            "written about and no longer reaches it: its LongTermDebt is neither its "
            "non-current line nor its balance-sheet total, reading 27,265 million at "
            "2024-12-31 where the balance sheet shows 25,479 of non-current debt and "
            "1,347 of current maturities. PROGRESS.md open question 1."),

    _item("Total Liabilities", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "Liabilities",
    ]),

    _item("Total Equity", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ], note="The first tag includes noncontrolling interests and so balances against "
            "Assets minus Liabilities; the fallback excludes them."),

    _item("Retained Earnings", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "RetainedEarningsAccumulatedDeficit",
    ], sign="Negative when the filer carries an accumulated deficit."),

    # -- Cash flow statement ----------------------------------------------
    _item("Cash from Operations", STATEMENT_CF, KIND_FLOW, UNIT_DOLLAR, [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ], sign="Positive when operations provided cash."),

    _item("D&A", STATEMENT_CF, KIND_FLOW, UNIT_DOLLAR, [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
    ], sign="Positive as an add-back to net income.",
       note="Taken from the cash flow statement rather than the income statement: for "
            "most filers D&A is buried inside cost of revenue and operating expenses and "
            "is never tagged separately on the income statement. Filers that report only "
            "the components can be derived: see DERIVATIONS['D&A']."),

    _item("Stock-Based Compensation", STATEMENT_CF, KIND_FLOW, UNIT_DOLLAR, [
        "ShareBasedCompensation",
    ], sign="Positive as an add-back to net income."),

    _item("Capex", STATEMENT_CF, KIND_FLOW, UNIT_DOLLAR, [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ], sign="Reported positive as a payment, which is a cash outflow. Subtract it, never "
            "add it."),

    _item("Cash from Investing", STATEMENT_CF, KIND_FLOW, UNIT_DOLLAR, [
        "NetCashProvidedByUsedInInvestingActivities",
    ], sign="Negative in the ordinary case, where investing consumed cash."),

    _item("Cash from Financing", STATEMENT_CF, KIND_FLOW, UNIT_DOLLAR, [
        "NetCashProvidedByUsedInFinancingActivities",
    ], sign="Negative in the ordinary case, where financing consumed cash."),

    _item("Dividends Paid", STATEMENT_CF, KIND_FLOW, UNIT_DOLLAR, [
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
    ], sign="Reported positive as a payment, which is a cash outflow.",
       note="The fallback covers common dividends only, excluding preferred."),

    _item("Buybacks", STATEMENT_CF, KIND_FLOW, UNIT_DOLLAR, [
        "PaymentsForRepurchaseOfCommonStock",
    ], sign="Reported positive as a payment, which is a cash outflow."),
]

REGISTRY = {item.name: item for item in _REGISTRY_ITEMS}


# ---------------------------------------------------------------------------
# Derivation rules
#
# A derived value is never a reported tag and never a guess. It is arithmetic on
# reported inputs, and it carries its formula so a reader can check the work.
# Every input is required: one missing input makes the result missing, not zero.
# ---------------------------------------------------------------------------

DERIVATIONS = {
    "Total Debt": Derivation(
        "Total Debt", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR,
        inputs=(("Short-Term Debt", 1), ("Long-Term Debt", 1)),
        formula="Short-Term Debt + Long-Term Debt",
        note="The row the old extractor labeled Total Debt was one of these two, never "
             "the sum. Both components are required: a filer reporting only long-term "
             "debt gets no Total Debt, because a missing short-term balance is unknown, "
             "not zero. Watch the Long-Term Debt note: a filer resolving that row "
             "through LongTermDebt may already include its current maturities here.",
    ),
    "EBITDA": Derivation(
        "EBITDA", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR,
        inputs=(("Operating Income", 1), ("D&A", 1)),
        formula="Operating Income + D&A",
        note="D&A comes off the cash flow statement, so this is the standard "
             "approximation, not a figure any filer reports. It differs from a filer's "
             "own adjusted EBITDA, which usually adds back more.",
    ),
    "Gross Profit": Derivation(
        "Gross Profit", STATEMENT_IS, KIND_FLOW, UNIT_DOLLAR,
        inputs=(("Revenue", 1), ("Cost of Revenue", -1)),
        formula="Revenue - Cost of Revenue",
        note="A fallback, not the primary source. Used only for periods where the filer "
             "reports no GrossProfit tag.",
    ),
    "D&A": Derivation(
        "D&A", STATEMENT_CF, KIND_FLOW, UNIT_DOLLAR,
        inputs=(("Depreciation", 1), ("Amortization of Intangibles", 1)),
        formula="Depreciation + Amortization of Intangibles",
        note="A fallback for filers that tag only the components. Its inputs are the raw "
             "tags Depreciation and AmortizationOfIntangibleAssets, which are not "
             "registry items of their own; the resolver reads them directly.",
    ),
}

# Raw tags behind the D&A component fallback, in the order the formula sums them.
DA_COMPONENT_TAGS = ("Depreciation", "AmortizationOfIntangibleAssets")


def derive(name, values):
    """Apply a derivation rule to a dict of already-resolved input values.

    values maps input name to a number or None. Returns the derived number, or
    None when any input is missing. Missing inputs never become zero: a value
    Edgardly cannot compute is reported as absent, never guessed.

    Raises KeyError for a name with no derivation rule.
    """
    rule = DERIVATIONS[name]
    total = 0
    for input_name, sign in rule.inputs:
        value = values.get(input_name)
        if value is None:
            return None
        total += sign * value
    return total


# ---------------------------------------------------------------------------
# Extraction set
#
# The 14 items the single-company table, the CSV, and both Excel exports have
# always shown, in the order they are displayed. TAG_MAP is built from the
# registry so the chains cannot drift apart, and keeps the shape callers expect:
# a plain dict of canonical name to an ordered list of us-gaap tags.
# ---------------------------------------------------------------------------

UI_LINE_ITEMS = (
    "Revenue",
    "Cost of Revenue",
    "Gross Profit",
    "Operating Income",
    "Net Income",
    "EPS Basic",
    "EPS Diluted",
    "Shares Outstanding (Basic)",
    "Shares Outstanding (Diluted)",
    "Total Assets",
    "Total Liabilities",
    "Total Equity",
    "Cash and Equivalents",
    "Long-Term Debt",
)

TAG_MAP = {name: list(REGISTRY[name].tags) for name in UI_LINE_ITEMS}


def tags_for(name):
    """Return the fallback tag chain for a line item, or an empty tuple.

    Accepts any registry name, not just the ones in TAG_MAP, so callers can ask
    for a line item the UI does not show. Derived-only names have no chain and
    come back empty.
    """
    item = REGISTRY.get(name)
    return item.tags if item else ()


def statement_of(name):
    """Return the statement code an item belongs to, or None.

    Derived-only names are covered too: they are on whichever statement their
    result belongs to, which is not always where their inputs live (EBITDA is
    an income statement figure built partly from a cash flow item).
    """
    item = REGISTRY.get(name)
    if item is not None:
        return item.statement
    rule = DERIVATIONS.get(name)
    return rule.statement if rule is not None else None


def statement_label_of(name):
    """Return the prose name of an item's statement, or an empty string."""
    return STATEMENT_LABELS.get(statement_of(name), "")


# ---------------------------------------------------------------------------
# Unit classification
#
# Derived from the registry, so a new item is classified by the unit field on
# its own entry and nowhere else. Derived items are classified too: a consumer
# asking about Total Debt needs to know it is dollars.
# ---------------------------------------------------------------------------

def _names_with_unit(unit):
    names = {name for name, item in REGISTRY.items() if item.unit == unit}
    names |= {name for name, rule in DERIVATIONS.items() if rule.unit == unit}
    return frozenset(names)


DOLLAR_LINE_ITEMS = _names_with_unit(UNIT_DOLLAR)
EPS_LINE_ITEMS = _names_with_unit(UNIT_EPS)
SHARE_LINE_ITEMS = _names_with_unit(UNIT_SHARES)


def classification_for_client():
    """Return the line-item classification the browser needs, JSON-ready.

    The peer-comparison UI builds its checkbox grid and picks its per-row scale
    factors from these lists. They used to be typed out a second time in
    index.html, where nothing kept them in step with the Python. Sorted lists,
    not sets, so the payload is stable between requests; ui_line_items keeps
    registry order because it drives display order.
    """
    return {
        "ui_line_items": list(UI_LINE_ITEMS),
        "dollar": sorted(DOLLAR_LINE_ITEMS),
        "eps": sorted(EPS_LINE_ITEMS),
        "shares": sorted(SHARE_LINE_ITEMS),
    }


# ---------------------------------------------------------------------------
# Display scaling
#
# A scale is a (factor, label) pair: divide raw values by factor, and print
# label in the header so the reader knows the units. EPS is never scaled.
# ---------------------------------------------------------------------------

# Above this, dollars are shown in millions; above the next one, in thousands.
DOLLAR_MILLIONS_THRESHOLD = 1_000_000_000
DOLLAR_THOUSANDS_THRESHOLD = 10_000_000

# Above this, share counts are shown in millions rather than thousands.
SHARE_MILLIONS_THRESHOLD = 1_000_000_000

# Used when no value is available to size the table from.
DEFAULT_DOLLAR_SCALE = (1, "$")
DEFAULT_SHARE_SCALE = (1_000, "000s")


def dollar_scale_for(value):
    """Return the (factor, label) dollar scale appropriate for *value*.

    Sign is irrelevant to scale, so the magnitude is what gets compared.
    """
    magnitude = abs(value)
    if magnitude > DOLLAR_MILLIONS_THRESHOLD:
        return 1_000_000, "$mm"
    if magnitude > DOLLAR_THOUSANDS_THRESHOLD:
        return 1_000, "$000s"
    return 1, "$"


def share_scale_for(value):
    """Return the (factor, label) share-count scale appropriate for *value*."""
    if abs(value) > SHARE_MILLIONS_THRESHOLD:
        return 1_000_000, "mm"
    return 1_000, "000s"


# ---------------------------------------------------------------------------
# Scope gate
#
# Some filers do not fit the three-statement template, and the honest response
# is to say so rather than to emit a scaffold that quietly means nothing. The
# gate governs scaffold generation only. The puller and the peer comparison
# read whatever these companies tag, exactly as before: a bank's revenue and
# net income are perfectly good numbers, they just do not roll up into a
# standard model.
# ---------------------------------------------------------------------------

# Banks and credit institutions, then insurance carriers and agents. Both
# ranges are inclusive, and both come from the SEC's own SIC list.
SIC_BANK_RANGE = (6020, 6199)
SIC_INSURANCE_RANGE = (6311, 6411)

# Reasons a verdict can carry. in_scope is the only one that permits a scaffold.
SCOPE_IN = "in_scope"
SCOPE_FINANCIAL_SIC = "financial_sic"
SCOPE_FINANCIAL_SHAPE = "financial_shape"
SCOPE_IFRS_ONLY = "ifrs_only"

# The refusal text for financial filers, fixed by V2_PLAN 1.4. The heuristic
# case appends its evidence to this sentence rather than replacing it, so the
# reason for a refusal is always visible and a misclassification is arguable.
REFUSAL_FINANCIAL = (
    "Bank and insurance financial statements do not fit the standard "
    "three-statement template; Edgardly will not generate a scaffold for "
    "this company"
)

REFUSAL_IFRS_ONLY = (
    "This company reports under IFRS, not US GAAP. Edgardly reads the us-gaap "
    "XBRL taxonomy, so it can extract no line items for this filer and will "
    "not generate a scaffold. The blank table is a limit of this tool, not a "
    "gap in the company's filings"
)

# Tags that betray a financial institution the SIC code failed to catch. A
# company reporting interest and dividend income as its operating revenue, and
# tagging no revenue or cost of revenue at all, is running a bank's income
# statement whatever its SIC says. make_fixture.py keeps these alongside the
# registry's own tags so the heuristic can be tested offline.
SCOPE_HEURISTIC_TAGS = ("InterestAndDividendIncomeOperating",)

# in_scope answers the only question the caller has to act on; reason and
# message explain it, and detail carries the evidence so a wrong verdict can be
# argued with rather than just worked around.
ScopeVerdict = namedtuple("ScopeVerdict", "in_scope reason message detail")


def _sic_in(sic, low_high):
    low, high = low_high
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return False
    return low <= code <= high


def _taxonomies(facts):
    """Return the taxonomies a companyfacts payload actually reports facts in.

    A taxonomy present but empty counts as absent. What matters is whether the
    filer tagged anything in it, not whether the key exists.
    """
    if not isinstance(facts, dict):
        return set()
    blocks = facts.get("facts", {}) or {}
    return {name for name, tags in blocks.items() if tags}


def _has_financial_shape(facts):
    """True when the tagged statements look like a bank's, whatever the SIC says.

    The signal is a company that reports interest and dividend income as an
    operating line while tagging neither revenue nor cost of revenue. An
    operating company always has at least one of those two.
    """
    us_gaap = (facts or {}).get("facts", {}).get("us-gaap", {}) if isinstance(facts, dict) else {}
    if not us_gaap:
        return False
    if not any(tag in us_gaap for tag in SCOPE_HEURISTIC_TAGS):
        return False
    for name in ("Revenue", "Cost of Revenue"):
        if any(tag in us_gaap for tag in tags_for(name)):
            return False
    return True


def is_in_scope(sic, facts):
    """Decide whether a filer can be given a three-statement scaffold.

    Three ways to fall out of scope, checked in this order:

    1. SIC code inside the bank or insurance ranges. Deterministic and the
       reason the ranges are in the plan.
    2. Only an ifrs-full taxonomy, no us-gaap. Nothing to extract at all, so
       this filer needs its own message rather than the financial one.
    3. The statement-shape heuristic, for financials the SIC missed.

    Every check that fired is recorded in detail["reasons"], even the ones that
    did not decide the verdict, so a company refused for two reasons does not
    look like it was refused for one.

    sic may be None or unparseable; the gate then rests on the facts alone.
    Returns a ScopeVerdict. in_scope is True only when nothing fired.
    """
    taxonomies = _taxonomies(facts)
    is_bank_sic = _sic_in(sic, SIC_BANK_RANGE)
    is_insurance_sic = _sic_in(sic, SIC_INSURANCE_RANGE)
    ifrs_only = "ifrs-full" in taxonomies and "us-gaap" not in taxonomies
    financial_shape = _has_financial_shape(facts)

    reasons = []
    if is_bank_sic or is_insurance_sic:
        reasons.append(SCOPE_FINANCIAL_SIC)
    if ifrs_only:
        reasons.append(SCOPE_IFRS_ONLY)
    if financial_shape:
        reasons.append(SCOPE_FINANCIAL_SHAPE)

    detail = {
        "sic": str(sic) if sic not in (None, "") else None,
        "sic_range": ("bank" if is_bank_sic else "insurance" if is_insurance_sic else None),
        "taxonomies": sorted(taxonomies),
        "heuristic_matched": financial_shape,
        "reasons": reasons,
    }

    if not reasons:
        return ScopeVerdict(True, SCOPE_IN, "", detail)

    reason = reasons[0]
    if reason == SCOPE_IFRS_ONLY:
        message = REFUSAL_IFRS_ONLY + "."
    elif reason == SCOPE_FINANCIAL_SIC:
        message = "{}. SIC code {} is in the {} range.".format(
            REFUSAL_FINANCIAL, detail["sic"], detail["sic_range"])
    else:
        message = (
            "{}. This company's SIC code ({}) is not a financial one, but it tags "
            "{} and no revenue or cost of revenue at all, which is a financial "
            "institution's income statement.".format(
                REFUSAL_FINANCIAL,
                detail["sic"] or "not reported",
                ", ".join(SCOPE_HEURISTIC_TAGS))
        )
    return ScopeVerdict(False, reason, message, detail)
