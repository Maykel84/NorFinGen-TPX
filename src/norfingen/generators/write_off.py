"""Write-off of uncollectible receivables (audit 2026-11-16, phase 4).

The generator models a small share of customers who never pay (Order.status WRITTEN_OFF, the deliberate bad-debt trap).
Until the audit nothing was ever booked for them: their receivable (account 1500) stayed on the books for ever and the
loss never reached the result. Now, WRITE_OFF_AFTER_DAYS days after the invoice's due date - after the 90 days a late
payer (OVERDUE) needs, so a customer who would still pay is never written off - the receivable is cleared:

    Dr 7830 Tap på krav     net      (the loss; an operating cost, so it reaches the result)
    Dr 2700 Utgående mva    VAT      (the output VAT of the invoice is reclaimed: a realised loss reduces it)
    Cr 1500 Kundefordringer gross    (customer dimension: the ageing of that customer clears)

One voucher per ORDER (not per invoice line). The amounts are the very ones the sales voucher booked
(`order_net_amount` / `order_gross_amount`), so the receivable clears to the cent. The VAT correction lands in the VAT
term of the write-off date, because the term settlement reads the ledger.

NS 4102: losses on receivables are 7830 "Tap på krav" (7770 is bank and card fees), hence 7830.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from norfingen.generators.sales_voucher import (
    ACCOUNT_OUTPUT_VAT,
    ACCOUNT_RECEIVABLES,
    order_gross_amount,
    order_net_amount,
)
from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.models.order import Order, OrderStatus
from norfingen.models.supplier_invoice import PURCHASE_VAT_TYPE_REF  # noqa: F401  (kept next to the VAT accounts)
from norfingen.seed.roster import customer_by_id
from norfingen.seed.workdays import next_working_day

ACCOUNT_BAD_DEBT = 7830  # Tap på krav
WRITE_OFF_AFTER_DAYS = 120  # after the due date: well past the 90-day delay of a customer who does pay


def write_off_date(invoice_date: date, invoices_due_in: int) -> date:
    """The due date + 120 days, moved to the next working day (the books are closed on weekends and holidays)."""
    return next_working_day(invoice_date + timedelta(days=invoices_due_in + WRITE_OFF_AFTER_DAYS))


def build_write_off_voucher(order: Order) -> Optional[Voucher]:
    """The write-off voucher of one WRITTEN_OFF order, dated on its write-off date; None for any other order."""
    if order.status != OrderStatus.WRITTEN_OFF or order.invoiceDate is None:
        return None
    on_date = write_off_date(order.invoiceDate, order.invoicesDueIn)
    customer = customer_by_id(order.customer.id)
    net = order_net_amount(order)
    gross = order_gross_amount(order)
    vat = round(gross - net, 2)
    postings = [Posting(date=on_date, account=acct(ACCOUNT_BAD_DEBT), amount=net)]
    if vat:
        postings.append(Posting(date=on_date, account=acct(ACCOUNT_OUTPUT_VAT), amount=vat))
    postings.append(Posting(date=on_date, account=acct(ACCOUNT_RECEIVABLES), amount=-gross, customer=order.customer))
    voucher = Voucher(
        date=on_date,
        description=f"Tap på krav — faktura {customer.number} {order.invoiceDate.isoformat()} (ordre {order.id}) — {customer.name}",
        voucherType=VoucherType.MANUAL,
        postings=postings,
    )
    assert_voucher_valid(voucher)
    return voucher
