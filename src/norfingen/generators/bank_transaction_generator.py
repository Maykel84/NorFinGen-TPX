"""BankTransaction + Voucher (type BANK) — Layer 3, Tier 4.

Models the actual cash in/outflow, time-shifted relative to the issuance of
the source document (Order/SupplierInvoice) by payment_terms /
payment_due_date — unlike the INVOICE/INCOMING_INVOICE Voucher, which is
booked on the day the invoice is issued.

DR/CR patterns:
  Incoming payment (customer pays an Order):
    DR 1910 Bankinnskudd driftskonto  +amount
    CR 1500 Kundefordringer          -amount
    date = invoice_date + payment_terms days (+90 days if Order.status ==
           OVERDUE; no payment at all if Order.status == WRITTEN_OFF — bad
           debt, see order_generator.determine_order_status)

  Outgoing payment (company pays a SupplierInvoice):
    DR 2400 Leverandørgjeld           +amount
    CR 1910 Bankinnskudd driftskonto -amount
    date = payment_due_date

  Payroll payout (Step 2 — gap fix: payroll never generated a bank
  transaction, since Tier 2, not a Phase 6 regression):
    DR 2930 Skyldig lønn               +employees' net pay
    DR 2600 Forskuddstrekk             +tax withholding (if >0, not always —
                                          e.g. long-tenured employees have 0 in June)
    DR 2770 Skyldig arbeidsgiveravgift +AGA
    CR 1910 Bankinnskudd driftskonto   -total
    date = salary_transaction.date (payout day = the day cash leaves the
           bank, unlike invoices there's no separate payment term here)

    A deliberate simplification (as allowed by the Step 2 prompt): ONE
    aggregated transaction/month (net pay+tax withholding+AGA together),
    not three separate ones to three different recipients (employees /
    Skatteetaten x2) — a fully accurate accounting would also need to model
    the time-shifted deadline for remitting tax withholding/AGA to the tax
    authority (in Norway typically the 15th of the month FOLLOWING the
    payout, not the same day), which is beyond the scope of this fix (which
    addresses the fact that the transaction didn't exist at all, not a
    precise time-based breakdown).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from norfingen.generators.sales_voucher import order_gross_amount
from norfingen.generators.salary_generator import ACCOUNT_FORSKUDDSTREKK, ACCOUNT_SKYLDIG_AGA, ACCOUNT_SKYLDIG_LONN
from norfingen.generators.vat_settlement import build_vat_payment
from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.models.bank_transaction import BankTransaction, BankTransactionType
from norfingen.models.base import TripletexRef
from norfingen.models.cogs_payable import CogsPayable
from norfingen.models.order import Order, OrderStatus
from norfingen.models.salary import SalaryTransaction
from norfingen.models.supplier_invoice import SupplierInvoice
from norfingen.models.vat_settlement import VatSettlement
from norfingen.seed.roster import customer_by_id
from norfingen.seed.workdays import next_working_day

ACCOUNT_BANK = 1910  # Bankinnskudd, driftskonto
ACCOUNT_KUNDEFORDRINGER = 1500
ACCOUNT_LEVERANDORGJELD = 2400
# Phase 1: the payroll liabilities have their own NS 4102 accounts (2930/2600/2770), defined once in
# salary_generator, so the voucher that books the liability and the one that pays it cannot disagree.
# The feriepenger liability (2940) is deliberately NOT here: it is not paid with the payroll.
ACCOUNT_SKYLDIG_SKATTETREKK = ACCOUNT_FORSKUDDSTREKK
PAYROLL_LIABILITY_ACCOUNTS = (ACCOUNT_SKYLDIG_LONN, ACCOUNT_FORSKUDDSTREKK, ACCOUNT_SKYLDIG_AGA)

OVERDUE_PAYMENT_DELAY_DAYS = 90  # OVERDUE pays payment_terms + 90 days, not on time


def _order_gross_amount(order: Order) -> float:
    """The invoice's gross amount - the single definition lives in sales_voucher.order_gross_amount, because the sales
    voucher (Dr 1500) and this payment (Cr 1500) must carry the very same number for the receivable to clear to the
    grosz. For an Order rebuilt from the database it is SUM(order_lines.amount_currency) as stored; for a fresh one the
    per-line sum rounded as Postgres will round it. (Before phase 0.5a this was round(sum(unrounded lines), 2), which
    differed from the stored sum by 0.01-0.02 NOK on 445 orders.)"""
    return order_gross_amount(order)


def _incoming_payment_date(order: Order, payment_terms: int) -> Optional[date]:
    """None if WRITTEN_OFF — bad debt, never paid. OVERDUE pays with a delay
    of OVERDUE_PAYMENT_DELAY_DAYS relative to the normal due date.

    The bank books on working days only: a due date falling on Saturday or
    Sunday is booked on the following Monday. (Before phase 0.5a such payments
    were never generated at all - the daily loop only visited working days and
    matched on the exact date - which silently dropped 525 invoices, 74.3 mln
    NOK gross.)"""
    if order.status == OrderStatus.WRITTEN_OFF:
        return None
    base = order.invoiceDate + timedelta(days=payment_terms)
    if order.status == OrderStatus.OVERDUE:
        base = base + timedelta(days=OVERDUE_PAYMENT_DELAY_DAYS)
    return next_working_day(base)


def build_incoming_payment(order: Order, payment_terms: int) -> Optional[tuple[BankTransaction, Voucher]]:
    """A customer pays a sales invoice (Order) — a bank account inflow.
    date = order.invoiceDate + payment_terms days (net 14/30/45 per
    customer, see roster.CustomerSeed.payment_terms), adjusted for
    Order.status (see _incoming_payment_date). Returns None for
    WRITTEN_OFF — no payment."""
    assert order.invoiceDate is not None, "An Order without invoiceDate does not generate a payment"
    payment_date = _incoming_payment_date(order, payment_terms)
    if payment_date is None:
        return None
    amount = _order_gross_amount(order)

    transaction = BankTransaction(
        date=payment_date,
        amount=amount,
        transaction_type=BankTransactionType.INCOMING,
        description=f"Innbetaling faktura K{order.customer.id:02d} — {order.invoiceDate.isoformat()}",
        customer_id=order.customer.id,
        order_id=order.id,
        account_from=ACCOUNT_KUNDEFORDRINGER,
        account_to=ACCOUNT_BANK,
    )

    voucher = Voucher(
        date=payment_date,
        description=f"Innbetaling — faktura K{order.customer.id:02d} {order.invoiceDate.isoformat()}",
        voucherType=VoucherType.BANK,
        postings=[
            Posting(date=payment_date, account=acct(ACCOUNT_BANK), amount=amount, customer=order.customer),
            Posting(date=payment_date, account=acct(ACCOUNT_KUNDEFORDRINGER), amount=-amount, customer=order.customer),
        ],
    )
    assert_voucher_valid(voucher)
    return transaction, voucher


def generate_daily_bank_transactions(
    year: int,
    month: int,
    day: int,
    orders: list[Order],
    supplier_invoices: list[SupplierInvoice],
    cogs_payables: list[CogsPayable] = (),
    vat_settlements: list[VatSettlement] = (),
) -> list[tuple[BankTransaction, Voucher]]:
    """Generates bank payments falling exactly on a given day — matches
    among the `orders`/`supplier_invoices` from previous months (payment
    arrives delayed by payment_terms/payment_due_date, not in the month the
    invoice was issued), so the caller must pass in documents from a
    sufficiently long history back (max payment_terms = 45 days + a buffer
    for months of different lengths).

    Returns (BankTransaction, Voucher) pairs — unlike
    generate_monthly_orders()/generate_monthly_supplier_invoices() (which
    return only the documents, with the Voucher built separately by the
    caller), here the pair is inseparable: a BankTransaction without its
    matching Voucher makes no accounting sense, and computing the Voucher
    without recomputing payment_date would be an unnecessary duplication of
    the logic already in build_incoming_payment/build_outgoing_payment."""
    today = date(year, month, day)
    results: list[tuple[BankTransaction, Voucher]] = []

    for order in orders:
        customer = customer_by_id(order.customer.id)
        payment_date = _incoming_payment_date(order, customer.payment_terms)
        if payment_date == today:
            payment = build_incoming_payment(order, customer.payment_terms)
            if payment is not None:
                results.append(payment)

    for invoice in supplier_invoices:
        if invoice.paymentDueDate is not None and next_working_day(invoice.paymentDueDate) == today:
            results.append(build_outgoing_payment(invoice))

    # Phase 4: the COGS pass-through liabilities are paid like purchase invoices - on the due date, moved to the
    # next working day.
    for payable in cogs_payables:
        if next_working_day(payable.payment_due_date) == today:
            results.append(build_cogs_payment(payable))

    # Phase 5: the VAT return of a term is paid (or refunded) on its payment date (already a working day).
    for settlement in vat_settlements:
        if settlement.payment_date == today and settlement.balance != 0:
            results.append(build_vat_payment(settlement))

    return results


def build_outgoing_payment(invoice: SupplierInvoice) -> tuple[BankTransaction, Voucher]:
    """The company pays a purchase invoice (SupplierInvoice) — a bank
    account outflow. date = invoice.paymentDueDate, moved to the next working
    day when it falls on a weekend (the bank books on business days only)."""
    assert invoice.paymentDueDate is not None, "A SupplierInvoice without paymentDueDate does not generate a payment"
    amount = round(invoice.amountCurrency, 2)
    payment_date = next_working_day(invoice.paymentDueDate)

    transaction = BankTransaction(
        date=payment_date,
        amount=amount,
        transaction_type=BankTransactionType.OUTGOING,
        description=f"Utbetaling {invoice.invoiceNumber}",
        supplier_id=invoice.supplier.id,
        supplier_invoice_id=invoice.id,
        account_from=ACCOUNT_BANK,
        account_to=ACCOUNT_LEVERANDORGJELD,
    )

    voucher = Voucher(
        date=payment_date,
        description=f"Utbetaling {invoice.invoiceNumber}",
        voucherType=VoucherType.BANK,
        postings=[
            Posting(date=payment_date, account=acct(ACCOUNT_LEVERANDORGJELD), amount=amount, supplier=invoice.supplier),
            Posting(date=payment_date, account=acct(ACCOUNT_BANK), amount=-amount, supplier=invoice.supplier),
        ],
    )
    assert_voucher_valid(voucher)
    return transaction, voucher


def build_cogs_payment(payable: CogsPayable) -> tuple[BankTransaction, Voucher]:
    """The company pays a COGS pass-through liability (phase 4): Dr 2400 Leverandorgjeld / Cr 1910 Bankinnskudd, on the
    due date moved to the next working day. Same shape as build_outgoing_payment for a purchase invoice; the supplier
    dimension on 2400 is the one the accrual put there, so the ageing clears per supplier."""
    assert payable.id is not None, "build_cogs_payment: payable.id must be a real ID from the database"
    amount = round(payable.amount_currency, 2)
    payment_date = next_working_day(payable.payment_due_date)
    supplier = TripletexRef(id=payable.supplier_id)

    transaction = BankTransaction(
        date=payment_date,
        amount=amount,
        transaction_type=BankTransactionType.OUTGOING,
        description=f"Utbetaling {payable.description}",
        supplier_id=payable.supplier_id,
        cogs_payable_id=payable.id,
        account_from=ACCOUNT_BANK,
        account_to=ACCOUNT_LEVERANDORGJELD,
    )
    voucher = Voucher(
        date=payment_date,
        description=f"Utbetaling {payable.description}",
        voucherType=VoucherType.BANK,
        postings=[
            Posting(date=payment_date, account=acct(ACCOUNT_LEVERANDORGJELD), amount=amount, supplier=supplier),
            Posting(date=payment_date, account=acct(ACCOUNT_BANK), amount=-amount, supplier=supplier),
        ],
    )
    assert_voucher_valid(voucher)
    return transaction, voucher


def generate_payroll_bank_transaction(
    transaction: SalaryTransaction, vouchers: list[Voucher]
) -> Optional[tuple[BankTransaction, Voucher]]:
    """The company pays out payroll — a bank account outflow (Step 2, gap
    fix: payroll never generated a BankTransaction, see the module-level
    docstring). Amounts are NOT recomputed from scratch — they're pulled
    from the liability postings (2930/2600/2770) of the `vouchers` returned
    by `salary_generator.generate_monthly_salary()` (the same two vouchers
    as always: payroll + AGA), so the payout is guaranteed to match, down
    to the øre, what was actually booked as a liability — no risk of drift
    from duplicating the calculation logic.

    `transaction.id` MUST already be a real ID from the database (not
    None) — the caller sets it after `save_salary()` (see `run_daily.py`)
    or after manually pulling it from the database (see
    `scripts/archive/fix_missing_payroll_transactions.py`).

    Returns None if `vouchers` contains no liability posting at all
    (shouldn't happen for a real payroll run — a safeguard for an
    empty/zero month)."""
    assert transaction.id is not None, "generate_payroll_bank_transaction: transaction.id must be set (a real ID from the database)"

    owed_by_account: dict[int, float] = {}
    for voucher in vouchers:
        for posting in voucher.postings:
            account_number = posting.account.number
            if account_number in PAYROLL_LIABILITY_ACCOUNTS and posting.amount < 0:
                owed_by_account[account_number] = owed_by_account.get(account_number, 0.0) - posting.amount

    total = round(sum(owed_by_account.values()), 2)
    if total <= 0:
        return None

    payment_date = transaction.date
    month_label = payment_date.strftime("%B %Y")

    bank_transaction = BankTransaction(
        date=payment_date,
        amount=total,
        transaction_type=BankTransactionType.OUTGOING,
        description=f"Lønnsutbetaling {month_label}",
        salary_transaction_id=transaction.id,
        account_from=ACCOUNT_SKYLDIG_LONN,
        account_to=ACCOUNT_BANK,
    )

    postings = [
        Posting(date=payment_date, account=acct(account_number), amount=round(owed, 2))
        for account_number, owed in sorted(owed_by_account.items())
    ]
    postings.append(Posting(date=payment_date, account=acct(ACCOUNT_BANK), amount=-total))

    voucher = Voucher(
        date=payment_date,
        description=f"Lønnsutbetaling {month_label}",
        voucherType=VoucherType.BANK,
        postings=postings,
    )
    assert_voucher_valid(voucher)
    return bank_transaction, voucher
