"""Pętla historyczna — generuje wszystkie dokumenty W2 + Vouchery W3 dla zakresu dat.

Domyślnie 2019-01-01 (założenie firmy) do dziś. Przed pętlą — jednorazowy MANUAL
Voucher kapitału zakładowego (2019-01-02, DR 1910 / CR 2000, 30 000 NOK).

Ten moduł NIE zapisuje jeszcze do Supabase — `persist_fn`, jeśli podana, jest
wywoływana z każdym wygenerowanym obiektem (Order, SupplierInvoice, SalaryTransaction,
Voucher) i to ona odpowiada za zapis. Domyślnie (`persist_fn=None`) backfill tylko
generuje i waliduje w pamięci, zwracając statystyki — przydatne do testów i
podglądu wolumenu przed podłączeniem warstwy bazodanowej.
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
    """Jednorazowy MANUAL Voucher otwierający bilans — kapitał zakładowy 30 000 NOK."""
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
    """Lista (year, month) od start_date do end_date włącznie, po miesiącach."""
    months: list[tuple[int, int]] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        months.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def generate_and_persist_month(year: int, month: int, persist_fn: Optional[PersistFn] = None) -> dict:
    """Generuje i (jeśli podano persist_fn) zapisuje Order/SupplierInvoice/
    SalaryTransaction + odpowiadające Vouchery dla JEDNEGO miesiąca. Wydzielone
    z run_backfill(), żeby run_daily.py (i docelowo APScheduler job na Railway)
    mogły wygenerować tylko bieżący miesiąc bez przechodzenia całej historii."""
    stats = dict(EMPTY_MONTH_STATS)

    def _emit(obj: object) -> None:
        if persist_fn is not None:
            persist_fn(obj)

    orders = generate_monthly_orders(year, month)
    for order in orders:
        _emit(order)
    stats["orders"] += len(orders)
    stats["order_lines"] += sum(len(o.orderLines) for o in orders)

    invoices = generate_monthly_supplier_invoices(year, month)
    for invoice in invoices:
        supplier_seed = supplier_by_number(invoice.invoiceNumber.split("-")[0])
        voucher = build_voucher_for_invoice(invoice, supplier_seed)
        _emit(invoice)
        _emit(voucher)
        stats["vouchers"] += 1
        stats["postings"] += len(voucher.postings)
    stats["supplier_invoices"] += len(invoices)

    transaction, vouchers = generate_monthly_salary(year, month)
    _emit(transaction)
    for voucher in vouchers:
        _emit(voucher)
    stats["salary_transactions"] += 1
    stats["payslips"] += len(transaction.payslips)
    stats["vouchers"] += len(vouchers)
    stats["postings"] += sum(len(v.postings) for v in vouchers)

    opex_vouchers = generate_monthly_opex(year, month)
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
    """Generuje Order/SupplierInvoice/SalaryTransaction + odpowiadające Vouchery
    dla każdego miesiąca w [start_date, end_date]. Zwraca statystyki wolumenu i
    loguje (logging.INFO) podsumowanie per miesiąc."""
    if end_date is None:
        end_date = date.today()

    stats = {"months": 0, **EMPTY_MONTH_STATS}

    def _emit(obj: object) -> None:
        if persist_fn is not None:
            persist_fn(obj)

    capital_voucher = founding_capital_voucher()
    _emit(capital_voucher)
    stats["vouchers"] += 1
    stats["postings"] += len(capital_voucher.postings)
    logger.info("Voucher kapitału zakładowego zapisany (%s)", FOUNDING_CAPITAL_DATE)

    for year, month in months_range(start_date, end_date):
        stats["months"] += 1
        month_stats = generate_and_persist_month(year, month, persist_fn)
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
