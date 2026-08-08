"""line_items.py -- the canonical line-item registry.

Single home for the facts that describe what a line item IS, independent of how
any one view renders it: which statement it belongs to, whether it is a flow or
an instant, which unit class it carries, which XBRL tags report it, and how it is
derived when no tag reports it at all.

The registry is a superset of what the UI shows. TAG_MAP, the extraction set the
single-company table and the peer table have always driven off, stays at the same
14 tag-reported items it has always held. UI_LINE_ITEMS is what those views
display and fixes the display order: those 14 plus Total Debt, which no filer
reports and Edgardly derives, for 15 in all. Everything else in the registry is
available to callers that ask for it by name (the scaffold engine will) without
appearing in any existing view.

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
#
# every_input_required says what a missing input means. True is the ordinary
# case and the safe one: Gross Profit without a cost of revenue is unknown, not
# equal to revenue. False is for a total whose components a filer picks from,
# where the components present are the whole of the balance and the ones absent
# are lines the filer does not have. Only a sum may set it, only where every
# term is a distinct balance-sheet line, and even then at least one term must be
# present -- a total of nothing stays missing rather than becoming zero.
Derivation = namedtuple(
    "Derivation", "name statement kind unit inputs formula note every_input_required")
Derivation.__new__.__defaults__ = (True,)


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
    ], note="Some filers tag this element only in the segment note, not on the face of "
            "the income statement, and the row's position between gross profit and "
            "pretax income then implies a subtotal the statement does not carry. "
            "Honeywell (CIK 773840) is such a filer: its consolidated statement of "
            "operations runs from total costs, expenses and other straight to income "
            "before taxes, and the 8,127 million shown for FY2025 is the \"Segment "
            "profit\" line of the segment note's reconciliation to pretax income, R145 "
            "of 0000773840-26-000013. The value is the filer's own and is genuinely "
            "this element; what it is not is a figure from the statement this row sits "
            "on, and three rows stand on it -- the operating plug, EBITDA and the "
            "other-income plug -- and inherit the question (breakage log row 7)."),

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
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
    ], note="Excludes goodwill. The fallback also excludes indefinite-lived intangibles, "
            "which the first tag includes, so it is narrower than the caption a filer "
            "carrying both kinds reports and is second for that reason. It led until "
            "2026-08-05 and Honeywell's row read 2,599 million at 2021-12-31 against an "
            "\"Other intangible assets -- net\" caption of 3,613, short by the "
            "indefinite-lived half in all five years, with the difference falling into "
            "the non-current asset plug (breakage log row 9). "
            "IntangibleAssetsNetExcludingGoodwill is a "
            "filer's whole intangibles balance and not the non-current half of it, and "
            "this row sits among non-current assets. A filer that splits the caption "
            "reports the current portion inside total current assets as well, so "
            "subtracting the whole of this row from a non-current total counts that "
            "portion twice: Apple's 10-Q of 2026-07-31 splits 13,301 million into 11,093 "
            "non-current and 2,208 current, and the 2,208 is already inside total current "
            "assets. No committed fixture resolves this row from an annual report of a "
            "filer that splits it, so the caveat is a warning about the element rather "
            "than a description of a value on show (breakage log row 4)."),

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
    ], note="One tag, because only one tag means this row. DebtCurrent is a filer's whole "
            "current debt balance; every other candidate is a component of it, and a "
            "chain picks one component where the row needs them all added. Not one of the "
            "five committed fixtures tags DebtCurrent, so for all of them this row is the "
            "sum of its parts: see DERIVATIONS['Short-Term Debt']."),

    # The three components of Short-Term Debt. Registry items in their own right
    # so each carries its own tag, filed date and accession into the derived
    # value's provenance, rather than the sum being arithmetic on raw tags a
    # reader cannot trace.
    _item("Current Maturities of Long-Term Debt", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "LongTermDebtCurrent",
    ], note="The current half of the long-term debt balance, and the mirror of the "
            "Long-Term Debt chain: a filer presenting debt and finance leases as one "
            "caption splits it across the first tag of each. Honeywell and Kroger both "
            "do, and the combined tag leads for that reason. Where a filer tags both, "
            "the row equals the caption on the face of the balance sheet and so "
            "includes obligations under finance leases: Kroger's is 1,802 million at "
            "2026-01-31, against 1,366 of debt alone, and the 436 of finance leases is "
            "the difference. Before the 2026-08-05 decisions-log entry the debt-only "
            "tag led and the row sat 436 below the line it appears beside, matching no "
            "figure on the statement. A filer tagging only LongTermDebtCurrent is "
            "unaffected, which is Apple (breakage log row 12)."),

    _item("Commercial Paper", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "CommercialPaper",
    ], note="OtherShortTermBorrowings is deliberately not a fallback here or under "
            "Short-Term Borrowings. Apple tags both for 2019-09-28 and both hold the same "
            "5,980 million, so it is an alias for this line rather than a second balance, "
            "and reading it as a separate term would double-count the whole of it."),

    _item("Short-Term Borrowings", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "ShortTermBorrowings",
    ], note="Borrowings that are short-term by origin rather than by maturity: bank "
            "lines, overdrafts, and for some filers the commercial paper too. Honeywell "
            "puts both in it and says so on the face of the balance sheet, where the line "
            "reads \"Commercial paper and other short-term borrowings\"; it tags no "
            "CommercialPaper instant, so the two terms cannot overlap for that filer."),

    _item("Long-Term Debt", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ], note="Strictly the non-current balance, through either of the first two tags. "
            "LongTermDebtAndCapitalLeaseObligations is the non-current line of a filer "
            "that presents debt and finance leases as one caption; its current half is "
            "LongTermDebtAndCapitalLeaseObligationsCurrent, a different tag, which is why "
            "it belongs here and its name does not mean it includes current maturities. "
            "It leads because where a filer tags both it is the caption on the face of "
            "the balance sheet, so the row equals the line it sits beside: Kroger's "
            "long-term debt including obligations under finance leases is 15,764 million "
            "at 2026-01-31 against 14,509 of debt alone, and the 1,255 of finance leases "
            "is the difference the debt-only tag left out of a row nobody could tie to "
            "the statement (decisions log, 2026-08-05; breakage log row 12). A filer "
            "tagging only LongTermDebtNoncurrent is unaffected, which is Apple. "
            "The last fallback is broader still: LongTermDebt covers the whole long-term "
            "balance "
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

    # The two halves of the finance lease obligation. Part of no sum in the
    # model: they are here so a reader can tie a debt row to the caption beside
    # it on a balance sheet that presents debt and finance leases as one line.
    # The combined caption is a presentation subtotal a filer need not tag, and
    # Kroger does not: its "long-term debt including obligations under finance
    # leases" of 15,764 million at 2026-01-31 appears in no taxonomy of its
    # companyfacts payload, and is LongTermDebtNoncurrent 14,509 plus
    # FinanceLeaseLiabilityNoncurrent 1,255. Composing that sum for the reader
    # would mean deciding, with nothing in the data to decide it from, that this
    # filer's balance sheet combines them, so the two terms are shown instead
    # and the debt row's flag says what to do with them (breakage log row 12).
    _item("Finance Lease Liability, Current", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "FinanceLeaseLiabilityCurrent",
    ], note="The current portion of the finance lease obligation, which some filers "
            "present inside the current debt caption and some on a line of their own. "
            "Apple, Honeywell and Kroger all tag it; only Kroger's balance sheet folds "
            "it into the debt caption."),

    _item("Finance Lease Liability, Non-current", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "FinanceLeaseLiabilityNoncurrent",
    ], note="The non-current portion, and the mirror of the current one above. Where a "
            "filer presents it inside the long-term debt caption, that caption is this "
            "row plus the Long-Term Debt row and neither one alone."),

    _item("Total Liabilities", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "Liabilities",
    ]),

    # Temporary equity: the mezzanine section, between liabilities and equity on
    # the face of a balance sheet and inside neither. It is a registry item for
    # one reason, which is that a filer tagging no Liabilities element has its
    # total derived as assets less equity, and that identity sweeps the whole of
    # the mezzanine into liabilities unless it is taken out. Honeywell carries 7
    # million of it at four of its five year ends and nil at the fifth, which is
    # exactly the error the derived total made, and is small enough to be
    # harmless and shaped like something that would not be (breakage log row 8).
    _item("Temporary Equity", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR, [
        "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrolling"
        "Interest",
        "RedeemableNoncontrollingInterestEquityCarryingAmount",
        "RedeemableNoncontrollingInterestEquityCommonCarryingAmount",
    ], note="Redeemable noncontrolling interests and other redeemable equity, which a "
            "filer presents on its own line between total liabilities and total equity "
            "and which belongs to neither. The first two tags are whole-balance "
            "elements and lead for that reason; the third is the common portion alone, "
            "and is the only one Honeywell (CIK 773840) tags -- its 7 million at "
            "2021-12-31 through 2024-12-31 is the whole of its mezzanine section, nil "
            "at 2025-12-31. A filer splitting the balance across the common, preferred "
            "and other partial elements while tagging neither whole-balance element "
            "would be captured only in part, because a chain takes one tag; no fixture "
            "does that and the limitation is recorded rather than guessed around."),

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
             "not zero. JPMorgan is the case, and gets no row. Long-Term Debt is strictly "
             "non-current except through its last fallback, and Short-Term Debt is the "
             "current side, so the two do not overlap; the exception is named in the "
             "Long-Term Debt note and no committed fixture reaches it.",
    ),
    "Short-Term Debt": Derivation(
        "Short-Term Debt", STATEMENT_BS, KIND_INSTANT, UNIT_DOLLAR,
        inputs=(("Current Maturities of Long-Term Debt", 1),
                ("Commercial Paper", 1),
                ("Short-Term Borrowings", 1)),
        formula=("Current Maturities of Long-Term Debt + Commercial Paper "
                 "+ Short-Term Borrowings"),
        every_input_required=False,
        note="Three separate lines of a current-liabilities section, added. A filer "
             "carries the ones it has: Apple's FY2023 balance sheet shows term debt and "
             "commercial paper and no other short-term borrowings, Honeywell shows "
             "current maturities and one combined borrowings line, Kroger shows current "
             "maturities alone. So the terms are optional, and the formula that ships "
             "with each value names only the ones that were there. At least one must be, "
             "or the row stays missing. This is what a chain could not do: a chain picks "
             "one component and calls it the total, which understated Apple by exactly "
             "the 5,985 million of commercial paper it left out.",
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

# The debt elements that already include obligations under finance leases. A row
# resolving through one of these is the caption on the face of the balance sheet
# and needs no lease added to it; a row resolving through anything else may not
# be, and cannot be told apart from one that is. See the Finance Lease Liability
# entries above and PROGRESS.md's decisions log entry of 2026-08-05.
COMBINED_DEBT_AND_LEASE_TAGS = frozenset({
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligationsCurrent",
})


def inputs_used(name, values):
    """Which of a rule's inputs are present in *values*, in formula order.

    Empty when the rule cannot be applied at all: any input missing from a rule
    that requires them all, or every input missing from a rule that does not.
    """
    rule = DERIVATIONS[name]
    used = []
    for input_name, _sign in rule.inputs:
        if values.get(input_name) is None:
            if rule.every_input_required:
                return []
        else:
            used.append(input_name)
    return used


def derive(name, values):
    """Apply a derivation rule to a dict of already-resolved input values.

    values maps input name to a number or None. Returns the derived number, or
    None when the rule cannot be applied. Missing inputs never become zero: a
    value Edgardly cannot compute is reported as absent, never guessed. For the
    one rule whose terms are optional, an absent term is a line the filer's
    balance sheet does not carry rather than a number nobody knows, which is
    why it may be left out of the sum instead of stopping it.

    Raises KeyError for a name with no derivation rule.
    """
    rule = DERIVATIONS[name]
    used = inputs_used(name, values)
    if not used:
        return None
    signs = dict(rule.inputs)
    return sum(signs[input_name] * values[input_name] for input_name in used)


def formula_for(name, values):
    """The formula string to ship with a derived value, naming the terms used.

    Identical to the rule's own formula whenever every term was present, which
    is every rule but one. Where terms are optional, the string has to describe
    the arithmetic that actually happened: "Current Maturities of Long-Term Debt
    + Commercial Paper" is checkable, and the full three-term formula would be a
    claim about a line the filer does not report.
    """
    rule = DERIVATIONS[name]
    used = inputs_used(name, values)
    if not used or len(used) == len(rule.inputs):
        return rule.formula
    signs = dict(rule.inputs)
    parts = []
    for input_name in used:
        joiner = "" if not parts else (" + " if signs[input_name] > 0 else " - ")
        parts.append("{}{}".format(joiner, input_name))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Extraction set
#
# The items the single-company table, the CSV, and both Excel exports show, in
# the order they are displayed. TAG_MAP is the subset of them that a tag
# reports, built from the registry so the chains cannot drift apart, and keeps
# the shape callers expect: a plain dict of canonical name to an ordered list of
# us-gaap tags. Total Debt is displayed and is in no chain, because no filer
# reports it; it is arithmetic, and the only row here that always is.
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
    "Total Debt",
)

TAG_MAP = {name: list(REGISTRY[name].tags) for name in UI_LINE_ITEMS if name in REGISTRY}

# Reported items a displayed derivation needs and no view shows. Both tables
# extract these alongside the displayed ones, compute with them, and drop them
# before rendering, so Total Debt can be built from reported values without
# putting four more rows on a screen that asked for fifteen.
DERIVATION_INPUT_ITEMS = (
    "Short-Term Debt",
    "Current Maturities of Long-Term Debt",
    "Commercial Paper",
    "Short-Term Borrowings",
)

# Displayed rows a table may fill by arithmetic, in the order they must be
# computed: Short-Term Debt is one of Total Debt's inputs, so it has to exist
# before Total Debt is attempted.
DERIVED_UI_ITEMS = ("Gross Profit", "Short-Term Debt", "Total Debt")


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


# Where a missing value's pointer should send a reader, for the items whose
# statement is not the only place a filer may present them. Naming the statement
# the registry assigns the row to is right in general and useless for a filer
# whose statement has no such line: Honeywell tags no OperatingIncomeLoss for
# FY2021 and its income statement carries no operating income line in that year
# or any other, so "check the income statement" cannot resolve the blank however
# carefully it is followed (breakage log row 11). The item's statement is
# unchanged -- this widens where to look, not where the row belongs.
MISSING_POINTER_LABELS = {
    "Operating Income": "income statement or the segment note",
}


def missing_pointer_label(name):
    """Where to tell a reader to look for an item a filer did not tag."""
    return MISSING_POINTER_LABELS.get(name) or statement_label_of(name)


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
