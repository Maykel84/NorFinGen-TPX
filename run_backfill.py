#!/usr/bin/env python3
"""CLI: generuje historyczne dane NorFinGen (2019 -> dziś) i zapisuje do Supabase.

Użycie (tryb miesięczny — domyślny, orders/supplier_invoices/salary):
    python run_backfill.py --start 2019-01-01
    python run_backfill.py --start 2019-01-01 --end 2023-12-31

Użycie (tryb dzienny — opcjonalny, DOPIERO PO backfillu miesięcznym: bank_transactions,
hour_entries; wymaga, żeby orders/supplier_invoices już istniały w bazie, bo
generate_daily_bank_transactions dopasowuje płatności do istniejących dokumentów):
    python run_backfill.py --mode daily --start 2019-01-01

Uwaga wydajnościowa: tryb daily woła run_daily() raz per dzień roboczy w całym
zakresie (~1800 dni dla 2019->dziś) — znacznie wolniejsze niż tryb monthly
(commit per rekord, jak reszta repository.py). Licz się z czasem rzędu godzin
dla pełnej historii od 2019.

Wymaga DATABASE_URL w .env (zob. .env.example).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from norfingen.db.repository import ensure_schema, save_all, seed_reference_data  # noqa: E402
from norfingen.generators.backfill import run_backfill  # noqa: E402
from norfingen.generators.hours_generator import is_working_day  # noqa: E402

logger = logging.getLogger("run_backfill")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def run_backfill_daily(start_date: date, end_date: date) -> None:
    """Backfill dla nowych encji dziennych (bank_transactions, hour_entries) —
    uzupełnia historię, która nie mogła powstać w backfillu miesięcznym, bo te
    generatory nie istniały wcześniej. Uruchom PO standardowym backfillu
    miesięcznym (orders/supplier_invoices muszą już być w bazie — bank
    transactions dopasowują się do nich po dacie płatności).

    Importuje run_daily() leniwie (dopiero przy wywołaniu), żeby uniknąć
    cyklu importu na poziomie modułu: run_daily.py sam wykonuje
    `sys.path.insert(..., "src")` identycznie jak ten plik.

    Retry z reconnectem per dzień: pojedyncze długożyjące połączenie psycopg2
    potrafi paść w trakcie wielogodzinnego backfillu (obserwowane wielokrotnie
    w tej sesji — zerwania sieci/DNS po uśpieniu maszyny). Zerwane połączenie
    zostawia po sobie sesję "idle in transaction" po stronie serwera (martwy
    peer nie jest wykrywany od razu przez TCP keepalive) — taka sesja blokuje
    kolejne insercje do tej samej tabeli/indeksu, więc samo zamknięcie
    lokalnego uchwytu połączenia nie wystarczy. Dlatego przy każdym błędzie:
    zamykamy lokalne połączenie, aktywnie zabijamy zawieszone sesje przez
    terminate_stale_sessions(), czekamy chwilę (rosnące opóźnienie — sieć/DNS
    po uśpieniu potrzebuje kilku-kilkunastu sekund) i próbujemy ten sam dzień
    ponownie (max 3 próby), zanim odpuścimy."""
    from norfingen.db.repository import close_connection, terminate_stale_sessions
    from run_daily import run_daily

    max_retries = 3
    retry_delay_seconds = 10
    current = start_date
    processed = 0
    while current <= end_date:
        if is_working_day(current):
            for attempt in range(1, max_retries + 1):
                try:
                    run_daily(target_date=current, skip_setup=True)
                    break
                except Exception as exc:
                    logger.warning(
                        "run_backfill_daily: błąd dla %s (próba %d/%d): %s — reconnect i ponów",
                        current, attempt, max_retries, exc,
                    )
                    close_connection()
                    try:
                        killed = terminate_stale_sessions()
                        if killed:
                            logger.warning("run_backfill_daily: zabito %d zawieszonych sesji 'idle in transaction'", killed)
                    except Exception:
                        pass  # brak połączenia/uprawnień do pg_stat_activity nie powinien zablokować retry
                    if attempt == max_retries:
                        logger.error("run_backfill_daily: %s nie powiodło się po %d próbach — przerywam", current, max_retries)
                        raise
                    time.sleep(retry_delay_seconds * attempt)
            processed += 1
            if processed % 50 == 0:
                logger.info("run_backfill_daily: przetworzono %d dni roboczych, ostatni %s", processed, current)
        current += timedelta(days=1)

    logger.info("run_backfill_daily zakończony: %d dni roboczych (%s -> %s)", processed, start_date, end_date)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Backfill historycznych danych NorFinGen do Supabase Postgres.")
    parser.add_argument("--start", type=_parse_date, default=date(2019, 1, 1), help="YYYY-MM-DD, domyślnie 2019-01-01")
    parser.add_argument("--end", type=_parse_date, default=None, help="YYYY-MM-DD, domyślnie dzisiejsza data")
    parser.add_argument(
        "--mode", choices=["monthly", "daily"], default="monthly",
        help="monthly (domyślnie): orders/supplier_invoices/salary. "
             "daily: bank_transactions/hour_entries — uruchom PO trybie monthly.",
    )
    args = parser.parse_args()
    end_date = args.end or date.today()

    logger.info("Inicjalizacja schematu (db/schema.sql) i danych referencyjnych...")
    ensure_schema()
    seed_reference_data()

    if args.mode == "daily":
        logger.info("Start backfillu dziennego: %s -> %s", args.start, end_date)
        run_backfill_daily(args.start, end_date)
        return

    logger.info("Start backfillu miesięcznego: %s -> %s", args.start, end_date)
    stats = run_backfill(start_date=args.start, end_date=end_date, persist_fn=save_all)

    logger.info(
        "Backfill zakończony: %d miesięcy | orders=%d order_lines=%d supplier_invoices=%d "
        "salary_transactions=%d payslips=%d vouchers=%d postings=%d",
        stats["months"], stats["orders"], stats["order_lines"], stats["supplier_invoices"],
        stats["salary_transactions"], stats["payslips"], stats["vouchers"], stats["postings"],
    )


if __name__ == "__main__":
    main()
