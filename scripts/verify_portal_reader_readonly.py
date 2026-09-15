"""Ręczna weryfikacja `portal_reader` (Zadanie 1b promptu Portal-DB-Access) —
NIE część pakietu pytest offline (zob. `tests/test_api_keys_export.py`,
sekcja "Portal, ścieżka 3"), bo z definicji wymaga prawdziwego połączenia do
bazy jako ta rola. Uruchom RĘCZNIE po `scripts/setup_portal_reader.py`,
zanim zaufasz że GRANT/RLS faktycznie ogranicza rolę do SELECT.

Sprawdza:
1. SELECT działa (dziedziczy `analyst`).
2. DELETE/UPDATE/DROP TABLE są odrzucone — wypisuje DOKŁADNY komunikat błędu
   Postgresa (do wklejenia w docs/SESSION_HANDOFF.md).
3. `statement_timeout` (15s) faktycznie przerywa długie zapytanie
   (`pg_sleep(20)`).

Uruchomienie (hasło z ostatniego `setup_portal_reader.py`, NIGDY w repo):
    PORTAL_READER_DATABASE_URL="postgresql://portal_reader.<ref>:<hasło>@<pooler-host>:5432/postgres" \\
        python scripts/verify_portal_reader_readonly.py
"""

import os
import sys
import time

import psycopg2


def main() -> None:
    dsn = os.environ.get("PORTAL_READER_DATABASE_URL")
    if not dsn:
        print("Brak PORTAL_READER_DATABASE_URL w środowisku.", file=sys.stderr)
        sys.exit(1)

    print("=== 1. SELECT (oczekiwane: działa) ===")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM customers")
        print(f"  OK — SELECT COUNT(*) FROM customers = {cur.fetchone()[0]}")

    print("\n=== 2a. DELETE (oczekiwane: permission denied) ===")
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM customers WHERE id = 1")
        print("  ✗ NIEOCZEKIWANE — DELETE się wykonał!")
    except Exception as exc:  # noqa: BLE001 - chcemy dokładny tekst błędu
        print(f"  OK — odrzucone: {exc}".strip())

    print("\n=== 2b. UPDATE (oczekiwane: permission denied) ===")
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE orders SET invoice_date = invoice_date WHERE id = 1")
        print("  ✗ NIEOCZEKIWANE — UPDATE się wykonał!")
    except Exception as exc:  # noqa: BLE001
        print(f"  OK — odrzucone: {exc}".strip())

    print("\n=== 2c. DROP TABLE (oczekiwane: must be owner of table) ===")
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE customers")
        print("  ✗ NIEOCZEKIWANE — DROP TABLE się wykonał!")
    except Exception as exc:  # noqa: BLE001
        print(f"  OK — odrzucone: {exc}".strip())

    conn.close()

    print("\n=== 3. statement_timeout (15s, oczekiwane: przerwane ok. 15s) ===")
    conn2 = psycopg2.connect(dsn)
    conn2.autocommit = True
    t0 = time.time()
    try:
        with conn2.cursor() as cur:
            cur.execute("SELECT pg_sleep(20)")
        print("  ✗ NIEOCZEKIWANE — zapytanie 20s nie zostało przerwane!")
    except Exception as exc:  # noqa: BLE001
        elapsed = time.time() - t0
        print(f"  OK — przerwane po {elapsed:.1f}s: {exc}".strip())
    conn2.close()


if __name__ == "__main__":
    main()
