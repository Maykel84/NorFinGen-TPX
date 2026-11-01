"""Everything the generators produce that is dated on ONE calendar day (phase 0.5b).

History and the current day used to come from two different code paths:

* the monthly backfill built orders, supplier invoices, payroll and operating costs
  from the `generate_monthly_*` functions;
* the daily cron (`run_daily`) built orders with a separate, poorer function
  (`generate_daily_orders`) and did not produce supplier invoices, COGS or
  operating costs at all - which is why October 2026 had no costs, no extra
  consulting orders and none of the customer-event effects (bankruptcy,
  large project, raised bad-debt probability, macro shock).

Now there is one source. A month is generated WHOLE by the very same
`generate_monthly_*` functions that built the history, once (cached), and a day takes
the slice dated on it. Generating the whole month first and filtering afterwards is not
a style choice, it is what keeps the numbers identical:

* supplier invoices draw from ONE random stream per month shared by all suppliers
  (`supplier-invoices-{year}-{month}`), consumed in supplier order - generating
  per supplier or per day would move every amount;
* the same holds for the customer events and the per-order bad-debt draws.

tests/test_golden_hash.py pins the monthly output; tests/test_day_events.py pins that
the union of all days of a month equals the monthly output, exactly.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from norfingen.generators.opex_generator import generate_monthly_opex
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.supplier_invoice_generator import generate_monthly_supplier_invoices
from norfingen.generators.voucher import Voucher
from norfingen.models.order import Order
from norfingen.models.supplier_invoice import SupplierInvoice


@lru_cache(maxsize=4)
def _month(year: int, month: int) -> tuple[tuple[Order, ...], tuple[SupplierInvoice, ...], tuple[Voucher, ...]]:
    """The whole month, generated once. Tuples so no caller can mutate the cached lists."""
    return (
        tuple(generate_monthly_orders(year, month)),
        tuple(generate_monthly_supplier_invoices(year, month)),
        tuple(generate_monthly_opex(year, month)),
    )


def orders_dated(day: date) -> list[Order]:
    """Customer invoices dated `day` - weekends included (an invoice keeps its own date)."""
    return [o for o in _month(day.year, day.month)[0] if o.orderDate == day]


def supplier_invoices_dated(day: date) -> list[SupplierInvoice]:
    return [i for i in _month(day.year, day.month)[1] if i.invoiceDate == day]


def operating_vouchers_dated(day: date) -> list[Voucher]:
    """Operating costs and COGS accruals (accounts 4290-4292, 6xxx-7xxx) dated `day`."""
    return [v for v in _month(day.year, day.month)[2] if v.date == day]
