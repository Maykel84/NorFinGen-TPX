"""Portal self-service, ścieżka 3 — tworzy realną, login-capable rolę
read-only `portal_reader`, hasło WSPÓLNE dla wszystkich, którzy o nie poproszą
przez `POST /api/v1/db-access/request` (`api/routers/db_access.py`).

Decyzja bezpieczeństwa (dwuetapowa, ustalona z użytkownikiem): jedno wspólne
hasło zamiast osobnej roli per-osoba — akceptowalne, bo dane syntetyczne,
dostęp wyłącznie SELECT (dziedziczy `analyst`, ten sam wzorzec co
`demo_reader`/`powerbi_reader`), a `CONNECTION LIMIT`/`statement_timeout`
ograniczają nadużycie niezależnie od tego ilu osobom hasło zostanie wydane.
Endpoint decyduje KOMU wydać hasło (limit 3 żądania/IP/dobę + log audytowy
`db_access_requests`) - ta rola tylko definiuje, co hasło pozwala zrobić.

BEZPIECZEŃSTWO — hasło generowane losowo (32 znaki) przy KAŻDYM uruchomieniu,
wypisywane TYLKO na stdout. Nigdy do pliku w repo/.env. Ustaw jako
`PORTAL_READER_PASSWORD` (+ `PORTAL_READER_USERNAME`, `PORTAL_DB_HOST`) w
sekretach usługi `api/` (`fly secrets set`) - stamtąd endpoint je czyta i
zwraca w odpowiedzi. Powtórne uruchomienie = rotacja, unieważnia poprzednie
hasło - wymaga aktualizacji sekretu + redeployu, inaczej endpoint zwraca
nieaktualne hasło aż do następnego deployu.

Uruchomienie (wymaga DATABASE_URL z uprawnieniami superusera/właściciela):
    python scripts/setup_portal_reader.py
"""

import secrets
import string
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norfingen.config import settings  # noqa: E402
from norfingen.db.repository import get_connection  # noqa: E402

ROLE_NAME = "portal_reader"
PASSWORD_LENGTH = 32
# Wyzsze niz demo_reader (2)/powerbi_reader (3) - haslo jest swiadomie
# wspolne, wiec wielu odbiorcow moze polaczyc sie rownoczesnie (Power BI
# scheduled refresh + kilka sesji SQL/Python naraz).
CONNECTION_LIMIT = 10
STATEMENT_TIMEOUT = "15s"

PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!*-_=+.,;()<>{}~^"


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def setup_portal_reader() -> str:
    password = generate_password()
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'portal_reader') THEN
                    CREATE ROLE portal_reader WITH LOGIN;
                END IF;
            END
            $$;
            """
        )
        cur.execute(f"ALTER ROLE {ROLE_NAME} WITH PASSWORD %s", (password,))
        cur.execute(f"ALTER ROLE {ROLE_NAME} CONNECTION LIMIT {CONNECTION_LIMIT};")
        cur.execute(f"ALTER ROLE {ROLE_NAME} SET statement_timeout = '{STATEMENT_TIMEOUT}';")
        # Dziedziczenie uprawnień/polityk RLS `analyst` (SELECT-only, 20/20
        # tabel z polityką `USING (true)`) - identyczny wzorzec co
        # demo_reader/powerbi_reader, zero duplikowania polityk.
        cur.execute(f"GRANT analyst TO {ROLE_NAME}")
    conn.commit()
    return password


def print_connection_details(password: str) -> None:
    parsed = urlparse(settings.DATABASE_URL)
    host = parsed.hostname or ""
    port = parsed.port or 5432
    dbname = (parsed.path or "/postgres").lstrip("/")

    admin_user = parsed.username or ""
    project_ref = admin_user.split(".", 1)[1] if "." in admin_user else None
    is_pooler = "pooler" in host

    if is_pooler and project_ref:
        login_user = f"{ROLE_NAME}.{project_ref}"
        user_note = "(format poolera Supabase: <rola>.<project_ref>)"
    else:
        login_user = ROLE_NAME
        user_note = ""

    print("\n" + "=" * 70)
    print("  DANE POŁĄCZENIA PORTAL_READER — skopiuj do menedżera haseł TERAZ")
    print("=" * 70)
    print(f"  Server (host:port) : {host}:{port}")
    print(f"  Database           : {dbname}")
    print(f"  Username           : {login_user} {user_note}")
    print(f"  Password           : {password}")
    print("=" * 70)
    print("  To hasło NIE jest nigdzie zapisane — ani w repo, ani w .env.")
    print("  Ustaw jako sekrety usługi api/ (fly secrets set), NIGDY w repo:")
    print(f"    PORTAL_DB_HOST={host}")
    print(f"    PORTAL_READER_USERNAME={login_user}")
    print(f"    PORTAL_READER_PASSWORD={password}")
    print("  Ponowne uruchomienie tego skryptu wygeneruje NOWE hasło i")
    print("  unieważni powyższe — wymaga aktualizacji sekretu + redeployu.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    pwd = setup_portal_reader()
    print(
        f"✓ Rola {ROLE_NAME} utworzona/zaktualizowana "
        f"(LOGIN, CONNECTION LIMIT {CONNECTION_LIMIT}, statement_timeout={STATEMENT_TIMEOUT}, dziedziczy analyst)"
    )
    print_connection_details(pwd)
