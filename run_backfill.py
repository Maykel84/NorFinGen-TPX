#!/usr/bin/env python3
"""CLI: generuje historyczne dane NorFinGen (2019 -> dziś) i zapisuje do Supabase.

Użycie:
    python run_backfill.py --start 2019-01-01
    python run_backfill.py --start 2019-01-01 --end 2023-12-31

Faza 0.5b — jeden potok. Historia przechodzi przez TEN SAM kod co dzień bieżący
(`run_daily.process_day`), dzień po dniu, w kolejności chronologicznej: kapitał
zakładowy, zamówienia, faktury zakupu, COGS i koszty operacyjne, płatności,
godziny, lista płac. Dawny podział na tryb miesięczny (dokumenty) i dzienny
(płatności, godziny) zniknął: wymagał ręcznej kolejności i osobnej naprawy
(`fix_outgoing_transactions.py`), a cron miał własną, uboższą ścieżkę.
`--mode monthly|daily` zostają jako przestarzałe aliasy tego samego potoku.

Po zakończeniu ustawia watermark (`generation_state`) na ostatni przetworzony
dzień, żeby catch-up crona ruszył od właściwego miejsca. Kolejność dni daje też
rosnące `vouchers.id` zgodne z datą.

Wymagane przy pełnym resecie (robi je człowiek, nie skrypt): wyłączony cron,
TRUNCATE tabel transakcyjnych z RESTART IDENTITY, potem ten skrypt.

Uwaga wydajnościowa: ~2800 dni kalendarzowych dla 2019->dziś, commit per rekord
(jak reszta repository.py) — lokalnie kilkadziesiąt sekund, na Supabase godzina i więcej.

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

from norfingen.db.repository import ensure_schema, seed_reference_data  # noqa: E402

logger = logging.getLogger("run_backfill")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def run_backfill_pipeline(start_date: date, end_date: date) -> None:
    """Przepuszcza KAŻDY dzień kalendarzowy z [start_date, end_date] przez
    run_daily.process_day, w kolejności chronologicznej — to samo, co robi cron
    dla dnia bieżącego (faza 0.5b, zob. nagłówek pliku).

    Pętla obejmuje wszystkie dni, nie tylko robocze (faza 0.5a): płatność z
    terminem w weekend jest księgowana w poniedziałek, ale faktury klientów z
    invoice_day w weekend powstają w sam weekend; godziny i lista płac pilnują
    dni roboczych same. `end_date` jest obcinany do dziś (generator nigdy nie
    tworzy rekordów z przyszłości), a watermark ustawiany na ostatni
    przetworzony dzień — nie dalej.

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
    from norfingen.db.repository import close_connection, set_watermark, terminate_stale_sessions
    from run_daily import run_daily

    end_date = min(end_date, date.today())
    max_retries = 3
    retry_delay_seconds = 10
    current = start_date
    processed = 0
    while current <= end_date:
        for attempt in range(1, max_retries + 1):
            try:
                run_daily(target_date=current, skip_setup=True)
                break
            except Exception as exc:
                logger.warning(
                    "run_backfill_pipeline: błąd dla %s (próba %d/%d): %s — reconnect i ponów",
                    current, attempt, max_retries, exc,
                )
                close_connection()
                try:
                    killed = terminate_stale_sessions()
                    if killed:
                        logger.warning("run_backfill_pipeline: zabito %d zawieszonych sesji 'idle in transaction'", killed)
                except Exception:
                    pass  # brak połączenia/uprawnień do pg_stat_activity nie powinien zablokować retry
                if attempt == max_retries:
                    logger.error("run_backfill_pipeline: %s nie powiodło się po %d próbach — przerywam", current, max_retries)
                    raise
                time.sleep(retry_delay_seconds * attempt)
        processed += 1
        if processed % 50 == 0:
            logger.info("run_backfill_pipeline: przetworzono %d dni, ostatni %s", processed, current)
        current += timedelta(days=1)

    set_watermark(end_date)
    logger.info("run_backfill_pipeline zakończony: %d dni (%s -> %s), watermark = %s", processed, start_date, end_date, end_date)


# Przestarzała nazwa sprzed fazy 0.5b — ten sam potok.
run_backfill_daily = run_backfill_pipeline


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Backfill historycznych danych NorFinGen do Supabase Postgres.")
    parser.add_argument("--start", type=_parse_date, default=date(2019, 1, 1), help="YYYY-MM-DD, domyślnie 2019-01-01")
    parser.add_argument("--end", type=_parse_date, default=None, help="YYYY-MM-DD, domyślnie dzisiejsza data")
    parser.add_argument(
        "--mode", choices=["pipeline", "monthly", "daily"], default="pipeline",
        help="przestarzałe: monthly i daily to aliasy jedynego potoku (faza 0.5b).",
    )
    args = parser.parse_args()
    end_date = args.end or date.today()

    if args.mode != "pipeline":
        logger.warning("--mode %s jest przestarzały: od fazy 0.5b istnieje jeden potok, uruchamiam go w całości.", args.mode)

    logger.info("Inicjalizacja schematu (db/schema.sql) i danych referencyjnych...")
    ensure_schema()
    seed_reference_data()

    logger.info("Start backfillu (jeden potok, każdy dzień kalendarzowy): %s -> %s", args.start, end_date)
    run_backfill_pipeline(args.start, end_date)


if __name__ == "__main__":
    main()
