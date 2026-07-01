#!/usr/bin/env python3
"""Generuje dane NorFinGen za bieżący miesiąc i zapisuje je do Supabase.

CLI:
    python run_daily.py

Importowalny jako funkcja — docelowo wywoływany z APScheduler job na Railway
(zamiast GitHub Actions):
    from run_daily import run_daily
    run_daily()

Idempotentny: bezpieczny do wielokrotnego uruchomienia tego samego dnia/miesiąca
— repository.save_all() używa ON CONFLICT DO NOTHING na naturalnych kluczach
biznesowych (invoice_number, (customer_id, order_date), (year, month), itd.),
więc powtórne odpalenie nie tworzy duplikatów.
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
    month_already_generated,
    save_all,
    seed_reference_data,
)
from norfingen.generators.backfill import EMPTY_MONTH_STATS, generate_and_persist_month  # noqa: E402

logger = logging.getLogger("run_daily")


def run_daily(today: Optional[date] = None) -> dict:
    """Generuje i zapisuje Order/SupplierInvoice/SalaryTransaction + Vouchery
    dla miesiąca zawierającego `today` (domyślnie data bieżąca). Wołana
    bezpośrednio jako funkcja z APScheduler — nie wymaga subprocessu CLI.

    Pomija generację (zamiast polegać wyłącznie na ON CONFLICT DO NOTHING),
    jeśli orders dla tego miesiąca już istnieją w bazie — oszczędza generowanie
    i odrzucanie całego miesiąca przy każdym uruchomieniu w danym miesiącu."""
    today = today or date.today()

    ensure_schema()
    seed_reference_data()

    if month_already_generated(today.year, today.month):
        logger.info("run_daily: dane za %04d-%02d już istnieją — pomijam", today.year, today.month)
        return dict(EMPTY_MONTH_STATS)

    logger.info("run_daily: generowanie danych za %04d-%02d", today.year, today.month)
    stats = generate_and_persist_month(today.year, today.month, persist_fn=save_all)
    logger.info(
        "run_daily zakończony: orders=%d order_lines=%d supplier_invoices=%d "
        "salary_transactions=%d payslips=%d vouchers=%d postings=%d",
        stats["orders"], stats["order_lines"], stats["supplier_invoices"],
        stats["salary_transactions"], stats["payslips"], stats["vouchers"], stats["postings"],
    )
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_daily()


if __name__ == "__main__":
    main()
