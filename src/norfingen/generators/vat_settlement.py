"""VAT settlement (mva-oppgjør), phase 5 - docs/SPEC_poprawki_ksiegowe.md.

Before this phase 2700 collected 53 mln NOK of output VAT and 2710 3.8 mln of input VAT forever; nothing was ever settled
with the tax authority. Now, as in Tripletex, every two-month term is closed in two steps:

1. LAST DAY OF THE TERM (30 Apr for mar-apr): a voucher moves the term's balances to the settlement account 2740

       Dr 2700   output VAT of the term
       Cr 2710   input VAT of the term
       Cr 2740   output - input         (Dr 2740 when input exceeds output: a refund is due)

   so 2700 and 2710 are back to zero for that term and 2740 holds exactly what is owed (or owed to us);
2. DUE DATE (10 Jun for mar-apr), moved to the next working day: the bank transaction settles 2740

       Dr 2740 / Cr 1910   (refund: Dr 1910 / Cr 2740)

Due dates: term 1 -> 10 Apr, 2 -> 10 Jun, 3 -> 31 Aug, 4 -> 10 Oct, 5 -> 10 Dec, 6 -> 10 Feb of the NEXT year.

The two VAT totals are read from the ledger (postings on 2700 / 2710 dated in the term, the settlement vouchers
themselves excluded), never recomputed from invoices: the books say what the books say, whatever rounding went into them.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.models.bank_transaction import BankTransaction, BankTransactionType
from norfingen.models.vat_settlement import VatSettlement, VatSettlementStatus
from norfingen.seed.workdays import next_working_day

ACCOUNT_BANK = 1910
ACCOUNT_OUTPUT_VAT = 2700
ACCOUNT_INPUT_VAT = 2710
ACCOUNT_VAT_SETTLEMENT = 2740

# term -> (month, day, years after the term's year) of the payment due date
VAT_DUE_DATES = {1: (4, 10, 0), 2: (6, 10, 0), 3: (8, 31, 0), 4: (10, 10, 0), 5: (12, 10, 0), 6: (2, 10, 1)}

MONTH_NAMES_NO = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]


def term_bounds(year: int, term: int) -> tuple[date, date]:
    """(first day, last day) of VAT term 1..6 of `year`."""
    last_month = term * 2
    return date(year, last_month - 1, 1), date(year, last_month, calendar.monthrange(year, last_month)[1])


def payment_date_for(year: int, term: int) -> date:
    month, day, year_offset = VAT_DUE_DATES[term]
    return next_working_day(date(year + year_offset, month, day))


def term_ending_on(day: date) -> Optional[tuple[int, int]]:
    """(year, term) when `day` is the last calendar day of a VAT term, else None."""
    if day.month % 2 == 0 and day.day == calendar.monthrange(day.year, day.month)[1]:
        return day.year, day.month // 2
    return None


def term_label(year: int, term: int) -> str:
    start, end = term_bounds(year, term)
    return f"termin {term} {year} ({MONTH_NAMES_NO[start.month - 1]}–{MONTH_NAMES_NO[end.month - 1]})"


def build_vat_settlement(year: int, term: int, output_vat: float, input_vat: float) -> Optional[tuple[Voucher, VatSettlement]]:
    """The settlement voucher and its document, or None for a term with no VAT at all."""
    output_vat, input_vat = round(output_vat, 2), round(input_vat, 2)
    if output_vat == 0 and input_vat == 0:
        return None
    start, end = term_bounds(year, term)
    balance = round(output_vat - input_vat, 2)

    postings = []
    if output_vat:
        postings.append(Posting(date=end, account=acct(ACCOUNT_OUTPUT_VAT), amount=output_vat))
    if input_vat:
        postings.append(Posting(date=end, account=acct(ACCOUNT_INPUT_VAT), amount=-input_vat))
    if balance:
        postings.append(Posting(date=end, account=acct(ACCOUNT_VAT_SETTLEMENT), amount=-balance))
    voucher = Voucher(
        date=end,
        description=f"MVA-oppgjør {term_label(year, term)}",
        voucherType=VoucherType.MANUAL,
        postings=postings,
    )
    assert_voucher_valid(voucher)

    settlement = VatSettlement(
        period_year=year, term=term, period_start=start, period_end=end,
        payment_date=payment_date_for(year, term),
        output_vat=output_vat, input_vat=input_vat, balance=balance,
        status=VatSettlementStatus.UNPAID if balance else VatSettlementStatus.PAID,  # nothing to pay -> nothing open
    )
    return voucher, settlement


def build_vat_payment(settlement: VatSettlement) -> tuple[BankTransaction, Voucher]:
    """Pays the tax authority (balance > 0: Dr 2740 / Cr 1910) or books the refund (balance < 0: Dr 1910 / Cr 2740)
    on the settlement's payment date."""
    assert settlement.id is not None, "build_vat_payment: settlement.id must be a real ID from the database"
    assert settlement.balance != 0, "a zero balance has nothing to pay"
    day = settlement.payment_date
    amount = round(abs(settlement.balance), 2)
    label = term_label(settlement.period_year, settlement.term)
    pays = settlement.balance > 0

    description = f"MVA-betaling {label}" if pays else f"MVA-tilbakebetaling {label}"
    transaction = BankTransaction(
        date=day,
        amount=amount,
        transaction_type=BankTransactionType.OUTGOING if pays else BankTransactionType.INCOMING,
        description=description,
        vat_settlement_id=settlement.id,
        account_from=ACCOUNT_BANK if pays else ACCOUNT_VAT_SETTLEMENT,
        account_to=ACCOUNT_VAT_SETTLEMENT if pays else ACCOUNT_BANK,
    )
    voucher = Voucher(
        date=day,
        description=description,
        voucherType=VoucherType.BANK,
        postings=[
            Posting(date=day, account=acct(ACCOUNT_VAT_SETTLEMENT), amount=amount if pays else -amount),
            Posting(date=day, account=acct(ACCOUNT_BANK), amount=-amount if pays else amount),
        ],
    )
    assert_voucher_valid(voucher)
    return transaction, voucher
