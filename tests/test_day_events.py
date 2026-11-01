"""day_events: slicing a generated month by day must lose nothing and invent nothing (phase 0.5b).

The pipeline generates each month WHOLE (the shared random streams demand it) and a day takes the
objects dated on it. That is only correct if every object is dated INSIDE the month it was generated
for. A voucher, order or invoice dated outside its month would silently never be saved.
"""

import calendar
from datetime import date

import pytest

from norfingen.generators.day_events import operating_vouchers_dated, orders_dated, supplier_invoices_dated
from norfingen.generators.opex_generator import generate_monthly_opex
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.supplier_invoice_generator import generate_monthly_supplier_invoices

MONTHS = [(y, m) for y in range(2019, 2028) for m in range(1, 13)]


def _days(year, month):
    return [date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)]


@pytest.mark.parametrize("year,month", MONTHS)
def test_every_object_is_dated_inside_its_own_month(year, month):
    for o in generate_monthly_orders(year, month):
        assert (o.orderDate.year, o.orderDate.month) == (year, month)
    for i in generate_monthly_supplier_invoices(year, month):
        assert (i.invoiceDate.year, i.invoiceDate.month) == (year, month)
    for v in generate_monthly_opex(year, month):
        assert (v.date.year, v.date.month) == (year, month)


@pytest.mark.parametrize("year,month", [(2019, 3), (2020, 4), (2022, 9), (2023, 6), (2024, 11), (2026, 10)])
def test_days_of_a_month_add_up_to_the_monthly_output_exactly(year, month):
    days = _days(year, month)
    assert sorted((o.customer.id, o.orderDate) for d in days for o in orders_dated(d)) == sorted(
        (o.customer.id, o.orderDate) for o in generate_monthly_orders(year, month))

    assert sorted(i.invoiceNumber for d in days for i in supplier_invoices_dated(d)) == sorted(
        i.invoiceNumber for i in generate_monthly_supplier_invoices(year, month))
    assert sorted((v.date, v.description) for d in days for v in operating_vouchers_dated(d)) == sorted(
        (v.date, v.description) for v in generate_monthly_opex(year, month))


def test_a_days_slice_contains_only_objects_dated_on_that_day():
    for d in (date(2026, 10, 3), date(2026, 10, 25), date(2024, 11, 1)):
        assert all(o.orderDate == d for o in orders_dated(d))
        assert all(i.invoiceDate == d for i in supplier_invoices_dated(d))
        assert all(v.date == d for v in operating_vouchers_dated(d))


def test_cache_does_not_let_a_caller_mutate_the_month():
    first = orders_dated(date(2026, 10, 3))
    first.clear()  # callers get lists, but the cached month is a tuple
    assert orders_dated(date(2026, 10, 3)), "clearing the returned list must not affect the cached month"
