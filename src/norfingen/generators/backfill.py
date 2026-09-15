"""The historical loop — generates all Layer 2 documents + Layer 3 Vouchers for a date range.

Defaults to 2019-01-01 (company founding) through today. Before the loop —
a one-off MANUAL Voucher for the founding capital (2019-01-02, DR 1910 /
CR 2000, 30,000 NOK).

This module does NOT write to Supabase itself — `persist_fn`, if given, is
called with each generated object (Order, SupplierInvoice,
SalaryTransaction, Voucher) and it's responsible for the actual save. By
default (`persist_fn=None`) the backfill only generates and validates
in-memory, returning statistics — useful for tests and previewing volume
before wiring up the database layer.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable, Optional

from norfingen.generators.opex_generator import generate_monthly_opex
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.salary_generator import generate_monthly_salary
from norfingen.generators.supplier_invoice_generator import build_voucher_for_invoice, generate_monthly_supplier_invoices
from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.seed.payroll import get_generation_cutoff_date, is_date_generatable, should_generate_monthly_salary
from norfingen.seed.roster import supplier_by_number

logger = logging.getLogger("norfingen.backfill")

DEFAULT_START_DATE = date(2019, 1, 1)
FOUNDING_CAPITAL_DATE = date(2019, 1, 2)
FOUNDING_CAPITAL_AMOUNT = 30_000.0

PersistFn = Callable[[object], None]

EMPTY_MONTH_STATS = {
    "orders": 0,
    "order_lines": 0,
    "supplier_invoices": 0,
    "salary_transactions": 0,
    "payslips": 0,
    "vouchers": 0,
    "postings": 0,
}


def founding_capital_voucher() -> Voucher:
    """A one-off MANUAL Voucher opening the balance sheet — 30,000 NOK founding capital."""
    voucher = Voucher(
        date=FOUNDING_CAPITAL_DATE,
        description="Stiftelse — aksjekapital 30 000 NOK",
        voucherType=VoucherType.MANUAL,
        postings=[
            Posting(date=FOUNDING_CAPITAL_DATE, account=acct(1910), amount=FOUNDING_CAPITAL_AMOUNT),
            Posting(date=FOUNDING_CAPITAL_DATE, account=acct(2000), amount=-FOUNDING_CAPITAL_AMOUNT),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher


def months_range(start_date: date, end_date: date) -> list[tuple[int, int]]:
    """A list of (year, month) from start_date to end_date inclusive, by month."""
    months: list[tuple[int, int]] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        months.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def generate_and_persist_month(year: int, month: int, persist_fn: Optional[PersistFn] = None,
                                cutoff: Optional[date] = None) -> dict:
    """Generates and (if persist_fn is given) saves Order/SupplierInvoice/
    SalaryTransaction + matching Vouchers for ONE month. Factored out of
    run_backfill() so that run_daily.py (and eventually an APScheduler job
    on Railway) can generate just the current month without walking the
    entire history.

    Phase 5a — `cutoff` (defaults to today, see
    seed.payroll.get_generation_cutoff_date): for the CURRENT (not yet
    finished) month, this function is still called once for the whole
    (year, month) — but every generated record with a date LATER than
    cutoff is discarded before saving (not just before persist_fn, but also
    before it's counted into stats), instead of assuming that since we're
    processing this month, the whole month has already passed. Without
    this, e.g. a customer order with invoice_day=27 would be created dated
    the 27th of the CURRENT month, even if the backfill was run on the 7th
    of that month."""
    if cutoff is None:
        cutoff = get_generation_cutoff_date()
    stats = dict(EMPTY_MONTH_STATS)

    def _emit(obj: object) -> None:
        if persist_fn is not None:
            persist_fn(obj)

    orders = [o for o in generate_monthly_orders(year, month) if is_date_generatable(o.orderDate, cutoff)]
    for order in orders:
        _emit(order)
    stats["orders"] += len(orders)
    stats["order_lines"] += sum(len(o.orderLines) for o in orders)

    invoices = [i for i in generate_monthly_supplier_invoices(year, month) if is_date_generatable(i.invoiceDate, cutoff)]
    for invoice in invoices:
        supplier_seed = supplier_by_number(invoice.invoiceNumber.split("-")[0])
        voucher = build_voucher_for_invoice(invoice, supplier_seed)
        _emit(invoice)
        _emit(voucher)
        stats["vouchers"] += 1
        stats["postings"] += len(voucher.postings)
    stats["supplier_invoices"] += len(invoices)

    if should_generate_monthly_salary(year, month, cutoff):
        transaction, vouchers = generate_monthly_salary(year, month)
        _emit(transaction)
        for voucher in vouchers:
            _emit(voucher)
        stats["salary_transactions"] += 1
        stats["payslips"] += len(transaction.payslips)
        stats["vouchers"] += len(vouchers)
        stats["postings"] += sum(len(v.postings) for v in vouchers)

    opex_vouchers = [v for v in generate_monthly_opex(year, month) if is_date_generatable(v.date, cutoff)]
    for voucher in opex_vouchers:
        _emit(voucher)
    stats["vouchers"] += len(opex_vouchers)
    stats["postings"] += sum(len(v.postings) for v in opex_vouchers)

    return stats


def run_backfill(
    start_date: date = DEFAULT_START_DATE,
    end_date: Optional[date] = None,
    persist_fn: Optional[PersistFn] = None,
) -> dict:
    """Generates Order/SupplierInvoice/SalaryTransaction + matching Vouchers
    for every month in [start_date, end_date]. Returns volume statistics and
    logs (logging.INFO) a per-month summary.

    Phase 5a — `end_date` (explicit or the default `date.today()`) is
    always additionally clamped to `get_generation_cutoff_date()` (also
    today) — the generator NEVER creates records dated later than the
    actual system date, regardless of what `end_date` the caller passes.
    The cutoff itself is also passed into `generate_and_persist_month()`,
    so the CURRENT (not yet finished) month within this range isn't
    generated in full (see that function)."""
    cutoff = get_generation_cutoff_date()
    if end_date is None:
        end_date = cutoff
    end_date = min(end_date, cutoff)

    stats = {"months": 0, **EMPTY_MONTH_STATS}

    def _emit(obj: object) -> None:
        if persist_fn is not None:
            persist_fn(obj)

    capital_voucher = founding_capital_voucher()
    _emit(capital_voucher)
    stats["vouchers"] += 1
    stats["postings"] += len(capital_voucher.postings)
    logger.info("Founding capital Voucher saved (%s)", FOUNDING_CAPITAL_DATE)

    for year, month in months_range(start_date, end_date):
        stats["months"] += 1
        month_stats = generate_and_persist_month(year, month, persist_fn, cutoff=cutoff)
        for key, value in month_stats.items():
            stats[key] += value
        logger.info(
            "%04d-%02d: orders=%d order_lines=%d supplier_invoices=%d salary_transactions=%d "
            "payslips=%d vouchers=%d postings=%d",
            year, month,
            month_stats["orders"], month_stats["order_lines"], month_stats["supplier_invoices"],
            month_stats["salary_transactions"], month_stats["payslips"],
            month_stats["vouchers"], month_stats["postings"],
        )

    return stats
