"""Weryfikuje, że rola powerbi_reader ma poprawne, ograniczone uprawnienia —
SELECT działa na widokach BI i tabelach źródłowych, INSERT/UPDATE/DELETE są
poprawnie zablokowane (RLS + brak GRANT-ów zapisu).

Uruchomienie:
    python scripts/test_powerbi_connection.py <username>
    # hasło z POWERBI_READER_PASSWORD w env, albo interaktywny prompt

Świadome odstępstwo od promptu — hasło NIE jest przyjmowane jako argument
CLI (sys.argv), tylko ze zmiennej środowiskowej lub interaktywnie
(getpass, bez echo) — hasło w argv trafiłoby do historii powłoki i byłoby
widoczne w liście procesów (`ps aux`) innym użytkownikom tej samej maszyny,
co kłóciłoby się z zasadą tego projektu "hasło nigdy nie ląduje nigdzie
poza stdout jednorazowo" (zob. scripts/setup_powerbi_reader.py).
Host/port/dbname brane z DATABASE_URL (.env), nie trzeba ich podawać ręcznie.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

load_dotenv()

VIEWS_TO_CHECK = ["v_sales_flat", "v_pl_monthly", "v_headcount_monthly"]
TABLES_TO_CHECK = ["orders", "customers", "accounts"]  # 1 tabela RLS + 1 RLS + 1 referencyjna bez RLS


def _connect(username: str, password: str) -> psycopg2.extensions.connection:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("Brak DATABASE_URL w .env — potrzebny do wyciągnięcia host/port/dbname.")
    parsed = urlparse(database_url)
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port,
        dbname=parsed.path.lstrip("/"),
        user=username,
        password=password,
        sslmode="require",  # Supabase wymaga SSL
    )


def test_read_access(username: str, password: str) -> bool:
    """Zwraca True jeśli wszystkie testy przeszły, False jeśli którykolwiek
    zawiódł (odczyt nie działa ALBO zapis nieoczekiwanie się powiódł)."""
    conn = _connect(username, password)
    conn.autocommit = False
    ok = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT current_user")
        print(f"Połączono jako: {cur.fetchone()[0]}")

        print("\n--- SELECT (powinno działać) ---")
        for view in VIEWS_TO_CHECK:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {view}")
                print(f"  OK  {view}: {cur.fetchone()[0]} wierszy")
            except Exception as exc:  # noqa: BLE001
                print(f"  BŁĄD  {view}: SELECT nie zadziałał — {exc}")
                ok = False
                conn.rollback()

        for table in TABLES_TO_CHECK:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"  OK  {table}: {cur.fetchone()[0]} wierszy")
            except Exception as exc:  # noqa: BLE001
                print(f"  BŁĄD  {table}: SELECT nie zadziałał — {exc}")
                ok = False
                conn.rollback()

        print("\n--- INSERT/UPDATE/DELETE (powinny być zablokowane) ---")
        write_statements = {
            "INSERT": "INSERT INTO customers (id, name) VALUES (999999, 'powerbi_reader_test')",
            "UPDATE": "UPDATE customers SET name = 'x' WHERE id = 1",
            "DELETE": "DELETE FROM customers WHERE id = 1",
        }
        for label, sql in write_statements.items():
            try:
                cur.execute(sql)
                conn.commit()
                print(f"  BŁĄD BEZPIECZEŃSTWA: {label} się powiódł, nie powinien!")
                ok = False
            except psycopg2.errors.InsufficientPrivilege:
                print(f"  OK  {label} poprawnie zablokowany (InsufficientPrivilege)")
            finally:
                conn.rollback()
    finally:
        conn.close()

    return ok


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Użycie: python scripts/test_powerbi_connection.py <username powerbi_reader.<project_ref>>")
    username = sys.argv[1]
    password = os.environ.get("POWERBI_READER_PASSWORD") or getpass.getpass("Hasło powerbi_reader: ")

    ok = test_read_access(username, password)
    print("\n" + ("✓ Wszystkie testy przeszły." if ok else "✗ Niektóre testy zawiodły — zobacz wyżej."))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
