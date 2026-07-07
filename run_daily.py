#!/usr/bin/env python3
"""Generuje dane NorFinGen za konkretny dzień i zapisuje je do Supabase.

CLI:
    python run_daily.py

Importowalny jako funkcja — docelowo wywoływany z APScheduler job na Railway
(zamiast GitHub Actions):
    from run_daily import run_daily
    run_daily()

Etap 4 — rytm dzienny (nie miesięczny jak poprzednio). Generuje dla
target_date (domyślnie dzisiaj):
1. Zamówienia klientów, których invoice_day wypada dzisiaj (generate_daily_orders)
2. Płatności bankowe, których termin przypada dzisiaj — dopasowywane wśród
   zamówień/faktur zakupu z ostatnich max. 45 dni (generate_daily_bank_transactions)
3. Godziny pracy konsultantów, jeśli to dzień roboczy (generate_daily_hours)
4. Lista płac, jeśli target_date to ostatni dzień roboczy miesiąca (generate_monthly_salary)

Idempotentny: ON CONFLICT DO NOTHING na naturalnych kluczach biznesowych we
wszystkich tabelach + status supplier_invoices przełączany na PAID po
zaksięgowaniu płatności (save_bank_transactions) — powtórne uruchomienie dla
tego samego dnia nie tworzy duplikatów i nie generuje drugi raz tej samej
płatności.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from norfingen.db.repository import (  # noqa: E402
    ensure_schema,
    get_orders_for_payment_window,
    get_unpaid_supplier_invoices,
    save_bank_transactions,
    save_hour_entries,
    save_orders,
    save_salary,
    seed_reference_data,
)
from norfingen.generators.bank_transaction_generator import generate_daily_bank_transactions  # noqa: E402
from norfingen.generators.hours_generator import generate_daily_hours  # noqa: E402
from norfingen.generators.order_generator import generate_daily_orders  # noqa: E402
from norfingen.generators.salary_generator import generate_monthly_salary  # noqa: E402
from norfingen.seed.payroll import active_employees, last_working_day, should_generate_monthly_salary  # noqa: E402
from norfingen.seed.roster import numeric_id  # noqa: E402

logger = logging.getLogger("run_daily")


def run_daily(target_date: Optional[date] = None, skip_setup: bool = False) -> dict:
    """Generuje dane dla konkretnego dnia (domyślnie: dzisiaj). Importowalna
    jako funkcja dla APScheduler na Railway — nie wymaga subprocesu CLI.

    skip_setup=True pomija ensure_schema()/seed_reference_data() — używane
    przez run_backfill.py::run_backfill_daily(), który woła run_daily() setki
    razy w pętli i sam wykonuje setup raz na starcie; bez tego każde z ~1800
    wywołań powtarzałoby ~50 idempotentnych, ale niepotrzebnych round-tripów
    do bazy."""
    if target_date is None:
        target_date = date.today()

    # Faza 5a — generator NIGDY nie tworzy rekordów z datą późniejszą niż
    # dzisiaj; bezpiecznik na wypadek wywołania run_daily() z przyszłą datą
    # (np. pomyłka wywołującego kodu, nie tylko backfill).
    if target_date > date.today():
        logger.warning("run_daily: target_date %s jest w przyszłości — pomijam.", target_date)
        return {"orders": 0, "bank_transactions": 0, "hour_entries": 0, "salary": 0, "skipped": True}

    year, month, day = target_date.year, target_date.month, target_date.day

    if not skip_setup:
        ensure_schema()
        seed_reference_data()

    stats = {"orders": 0, "bank_transactions": 0, "hour_entries": 0, "salary": 0}

    # 1. Zamówienia klientów, których invoice_day wypada dzisiaj
    orders = generate_daily_orders(year, month, day)
    if orders:
        save_orders(orders)
        stats["orders"] = len(orders)

    # 2. Płatności bankowe — potrzebujemy zamówień/faktur z bazy (nie tylko
    #    dzisiejszych), żeby dopasować payment_terms/payment_due_date == dzisiaj
    pending_orders = get_orders_for_payment_window(target_date)
    pending_invoices = get_unpaid_supplier_invoices(target_date)
    bank_txns = generate_daily_bank_transactions(year, month, day, pending_orders, pending_invoices)
    if bank_txns:
        save_bank_transactions(bank_txns)
        stats["bank_transactions"] = len(bank_txns)

    # 3. Godziny pracy konsultantów (generate_daily_hours sama filtruje dni robocze)
    active_ids = [numeric_id(e.number) for e in active_employees(target_date)]
    hour_entries = generate_daily_hours(year, month, day, active_ids)
    if hour_entries:
        save_hour_entries(hour_entries)
        stats["hour_entries"] = len(hour_entries)

    # 4. Lista płac — tylko w ostatni dzień roboczy miesiąca, i tylko jeśli
    # ten dzień faktycznie już minął (should_generate_monthly_salary — Faza 5a).
    if target_date == last_working_day(year, month) and should_generate_monthly_salary(year, month):
        salary_txn, vouchers = generate_monthly_salary(year, month)
        save_salary(salary_txn, vouchers)
        stats["salary"] = 1

    logger.info("run_daily %s: %s", target_date.isoformat(), stats)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_daily()


if __name__ == "__main__":
    main()
