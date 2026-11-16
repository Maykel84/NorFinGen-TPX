"""Audit 2026-11-16, phase 4: written-off receivables leave account 1500 and reach the result.

9 orders (1.75 mln NOK gross) have a WRITTEN_OFF status - customers who never pay - and nothing was ever booked for them:
the receivable stayed on 1500 for ever and no loss appeared. Now, 120 days after the due date, one voucher per order:
Dr 7830 (net) + Dr 2700 (VAT) / Cr 1500 (gross, with the customer)."""
from datetime import date

from norfingen.generators.sales_voucher import build_sales_voucher, order_gross_amount, order_net_amount
from norfingen.generators.write_off import WRITE_OFF_AFTER_DAYS, build_write_off_voucher, write_off_date
from norfingen.models.base import TripletexRef
from norfingen.models.order import Order, OrderLine, OrderStatus
from norfingen.seed.workdays import is_working_day


def _order(status, invoice_date=date(2024, 11, 12), due_in=30):
    return Order(
        id=955, customer=TripletexRef(id=12), orderDate=invoice_date, deliveryDate=invoice_date, invoiceDate=invoice_date,
        invoicesDueIn=due_in, status=status,
        orderLines=[OrderLine(product=TripletexRef(id=1), count=1.0, unitPriceExcludingVatCurrency=57_821.23,
                              vatType=TripletexRef(id=3))],
    )


def test_write_off_is_120_days_after_the_due_date_on_a_working_day():
    assert WRITE_OFF_AFTER_DAYS == 120
    d = write_off_date(date(2024, 11, 12), 30)  # due 2024-12-12 + 120 = 2025-04-11 (Friday)
    assert d == date(2025, 4, 11) and is_working_day(d)
    assert is_working_day(write_off_date(date(2020, 3, 3), 30))
    for day in range(1, 29):  # never a weekend or holiday, whatever the invoice date
        assert is_working_day(write_off_date(date(2023, 6, day), 45))


def test_voucher_clears_exactly_what_the_sales_voucher_booked():
    order = _order(OrderStatus.WRITTEN_OFF)
    sale, off = build_sales_voucher(order), build_write_off_voucher(order)
    assert sale.postings[0].amount == -off.postings[-1].amount == order_gross_amount(order)  # 1500 clears to the cent
    posts = {p.account.number: p.amount for p in off.postings}
    assert posts[7830] == order_net_amount(order)
    assert posts[2700] == round(order_gross_amount(order) - order_net_amount(order), 2)  # the output VAT is reclaimed
    assert round(sum(posts.values()), 2) == 0.0
    assert off.postings[-1].customer.id == 12  # the ageing of that customer clears
    assert off.date == write_off_date(order.invoiceDate, order.invoicesDueIn)
    assert "ordre 955" in off.description  # unique per order, so a re-run books nothing twice


def test_only_written_off_orders_get_a_voucher():
    assert build_write_off_voucher(_order(OrderStatus.PAID)) is None
    assert build_write_off_voucher(_order(OrderStatus.OVERDUE)) is None


def test_run_daily_books_the_write_off_and_links_it_to_the_order():
    """The pipeline saves the voucher AND the order link (phase 5 derives the invoice status from it), before the VAT
    settlement of the day is built."""
    from unittest.mock import patch

    import run_daily as run_daily_module
    from tests.test_run_daily import _patch_repository

    order = _order(OrderStatus.WRITTEN_OFF)
    mocks = _patch_repository()
    mocks["get_orders_to_write_off"].return_value = [order]
    with patch.multiple(run_daily_module, **mocks):
        stats = run_daily_module.run_daily(date(2025, 4, 11))
    voucher, order_id = mocks["save_write_off"].call_args.args
    assert order_id == 955 and voucher.date == date(2025, 4, 11)
    assert stats["write_offs"] == 1
