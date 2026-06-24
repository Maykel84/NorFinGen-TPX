#!/usr/bin/env python3
"""CLI: generuje historyczne dane NorFinGen (2019 -> dziś) i zapisuje do Supabase.

Użycie:
    python run_backfill.py --start 2019-01-01
    python run_backfill.py --start 2019-01-01 --end 2023-12-31

Wymaga DATABASE_URL w .env (zob. .env.example).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from norfingen.db.repository import ensure_schema, save_all, seed_reference_data  # noqa: E402
from norfingen.generators.backfill import run_backfill  # noqa: E402

logger = logging.getLogger("run_backfill")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Backfill historycznych danych NorFinGen do Supabase Postgres.")
    parser.add_argument("--start", type=_parse_date, default=date(2019, 1, 1), help="YYYY-MM-DD, domyślnie 2019-01-01")
    parser.add_argument("--end", type=_parse_date, default=None, help="YYYY-MM-DD, domyślnie dzisiejsza data")
    args = parser.parse_args()

    logger.info("Inicjalizacja schematu (db/schema.sql) i danych referencyjnych...")
    ensure_schema()
    seed_reference_data()

    logger.info("Start backfillu: %s -> %s", args.start, args.end or "dziś")
    stats = run_backfill(start_date=args.start, end_date=args.end, persist_fn=save_all)

    logger.info(
        "Backfill zakończony: %d miesięcy | orders=%d order_lines=%d supplier_invoices=%d "
        "salary_transactions=%d payslips=%d vouchers=%d postings=%d",
        stats["months"], stats["orders"], stats["order_lines"], stats["supplier_invoices"],
        stats["salary_transactions"], stats["payslips"], stats["vouchers"], stats["postings"],
    )


if __name__ == "__main__":
    main()
