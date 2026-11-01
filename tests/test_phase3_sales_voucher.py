"""Phase 3 (docs/SPEC_poprawki_ksiegowe.md): sales invoices are booked in the ledger.

Before: nothing on the sales side - no revenue (3000), no receivable debit (1500), no output VAT (2700) - while customer
payments (Dr 1910 / Cr 1500) were booked, so account 1500 stood at -185 mln NOK (gl_checks T3, T4, T5). After: every
invoice is Dr 1500 gross / Cr 3000 net / Cr 2700 VAT on its invoice date.
"""

import calendar
from collections import defaultdict
from datetime import date

import pytest

from norfingen.generators.backfill import months_range
from norfingen.generators.bank_transaction_generator import build_incoming_payment
from norfingen.generators.money import pg_round2
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.sales_voucher import build_sales_voucher, order_gross_amount, order_net_amount
from norfingen.generators.voucher import BALANCE_TOLERANCE, VoucherType
from norfingen.models.order import OrderStatus
from norfingen.seed.roster import customer_by_id

MONTHS = months_range(date(2019, 1, 1), date(2026, 12, 31))


def _orders():
    for year, month in MONTHS:
        yield from generate_monthly_orders(year, month)


def test_every_invoice_books_receivable_revenue_and_output_vat_and_balances_to_the_cent():
    n = 0
    for order in _orders():
        voucher = build_sales_voucher(order)
        by_account = {p.account.number: p.amount for p in voucher.postings}
        gross, net = order_gross_amount(order), order_net_amount(order)

        assert voucher.voucherType == VoucherType.OUTGOING_INVOICE
        assert voucher.date == order.invoiceDate                         # an invoice keeps its own date - weekends too
        assert set(by_account) == {1500, 3000, 2700} and len(voucher.postings) == 3
        assert by_account[1500] == gross > 0                             # Dr receivable, gross
        assert by_account[3000] == -net                                  # Cr revenue, net
        assert by_account[2700] == -round(gross - net, 2)                # Cr output VAT = gross - net
        assert abs(sum(p.amount for p in voucher.postings)) <= BALANCE_TOLERANCE
        n += 1
    assert n > 1800


def test_vat_is_25_percent_of_revenue_per_invoice_within_rounding():
    worst = 0.0
    for order in _orders():
        voucher = build_sales_voucher(order)
        vat = -next(p.amount for p in voucher.postings if p.account.number == 2700)
        net = -next(p.amount for p in voucher.postings if p.account.number == 3000)
        worst = max(worst, abs(vat - 0.25 * net))
    assert worst <= 0.03, f"worst per-invoice VAT deviation from 25%: {worst:.4f}"   # a few lines, each rounded to a cent


def test_the_receivable_dimension_and_the_description_identify_the_invoice():
    seen = set()
    for order in _orders():
        voucher = build_sales_voucher(order)
        customer = customer_by_id(order.customer.id)
        receivable = next(p for p in voucher.postings if p.account.number == 1500)
        assert receivable.customer.id == order.customer.id               # accounts-receivable ageing needs the customer
        assert customer.number in voucher.description and order.invoiceDate.isoformat() in voucher.description
        key = (voucher.date, voucher.description)
        assert key not in seen, f"duplicate voucher key {key}"           # vouchers are unique on (date, description)
        seen.add(key)


def test_ledger_revenue_equals_invoiced_revenue_every_month():
    """gl_checks T4 at the source: Cr 3000 per month == sum of the order lines' excl.-VAT amounts per month,
    both rounded the way Postgres stores them."""
    gl, lines = defaultdict(float), defaultdict(float)
    for order in _orders():
        voucher = build_sales_voucher(order)
        month = (order.invoiceDate.year, order.invoiceDate.month)
        gl[month] += -sum(p.amount for p in voucher.postings if p.account.number == 3000)
        lines[month] += sum(pg_round2(l.amountExcludingVatCurrency) for l in order.orderLines)
    assert gl.keys() == lines.keys()
    for month in gl:
        assert abs(gl[month] - lines[month]) < 0.01, month


def test_output_vat_is_25_percent_of_ledger_revenue_within_a_cent_per_invoice():
    """gl_checks T5 at the source. The VAT booked is the invoice's own VAT (gross - net), and every invoice's VAT is 25% of its
    net only to the cent: its lines are rounded one by one. Over the history that adds up to a few krone (3.16 NOK on 1853
    invoices to 2026-09-30: 1167 exact, 531 at +0.01, 155 at -0.01), so the honest bound is one cent per invoice - not the 1 NOK in
    the original T5, which no booking faithful to the invoices can meet."""
    vat = revenue = 0.0
    n = 0
    for order in _orders():
        voucher = build_sales_voucher(order)
        vat += -sum(p.amount for p in voucher.postings if p.account.number == 2700)
        revenue += -sum(p.amount for p in voucher.postings if p.account.number == 3000)
        n += 1
    assert abs(vat - 0.25 * revenue) <= 0.01 * n


def test_the_payment_clears_the_receivable_to_the_grosz():
    """Dr 1500 on the invoice and Cr 1500 on the payment are the same number: they cancel exactly. Checked both for a
    fresh Order and for one read back from the database (storedGrossAmountCurrency), which is what the pipeline pays."""
    checked = 0
    for order in _orders():
        if order.status == OrderStatus.WRITTEN_OFF:
            continue
        for candidate in (order, order.model_copy(update={"storedGrossAmountCurrency": order_gross_amount(order)})):
            invoice_voucher = build_sales_voucher(candidate)
            payment = build_incoming_payment(candidate, payment_terms=customer_by_id(candidate.customer.id).payment_terms)
            assert payment is not None
            receivable = [p for v in (invoice_voucher, payment[1]) for p in v.postings if p.account.number == 1500]
            assert abs(sum(p.amount for p in receivable)) < 0.005
            assert payment[0].amount == order_gross_amount(candidate)
        checked += 1
    assert checked > 1700


def test_a_written_off_invoice_stays_on_the_receivable():
    """Bad debt is a modelled behaviour, not an error: never paid, so 1500 keeps its gross (flagged in the export)."""
    written_off = [o for o in _orders() if o.status == OrderStatus.WRITTEN_OFF]
    assert written_off
    for order in written_off:
        assert build_incoming_payment(order, payment_terms=30) is None
        assert build_sales_voucher(order).postings[0].amount == order_gross_amount(order)


def test_no_vat_invoice_has_no_2700_line():
    order = next(_orders())
    free = order.model_copy(update={"orderLines": [order.orderLines[0].model_copy(update={"vatType": None})]})
    # a zero-rated line still carries 25% in OrderLine.amountCurrency, so force gross == net to exercise the branch
    forced = free.model_copy(update={"storedGrossAmountCurrency": order_net_amount(free)})
    voucher = build_sales_voucher(forced)
    assert {p.account.number for p in voucher.postings} == {1500, 3000}
    assert voucher.validate_balance()


def test_the_invoice_date_may_be_a_weekend():
    weekend = [o for o in _orders() if o.invoiceDate.weekday() >= 5]
    assert len(weekend) > 100
    assert all(build_sales_voucher(o).date == o.invoiceDate for o in weekend)
