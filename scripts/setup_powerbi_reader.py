"""Krok 2 — tworzy realną, login-capable rolę read-only `powerbi_reader` dla Power BI.

Dlaczego osobna rola, a nie `analyst` z Fazy 1: `analyst` jest NOLOGIN (czysto
techniczna, do definiowania polityk RLS) — Power BI potrzebuje prawdziwych
danych logowania. `powerbi_reader` dostaje LOGIN + hasło i dziedziczy komplet
uprawnień/polityk przez `GRANT analyst TO powerbi_reader`.

BEZPIECZEŃSTWO — hasło jest generowane losowo (secrets, 32 znaki) przy każdym
uruchomieniu i wypisywane TYLKO na stdout. Nie jest zapisywane do żadnego
pliku w repo ani do .env — skopiuj je do menedżera haseł od razu po
uruchomieniu. Powtórne uruchomienie skryptu ustawia NOWE hasło (rotacja) i
unieważnia poprzednie.

Uruchomienie (wymaga DATABASE_URL z uprawnieniami superusera/właściciela):
    python scripts/setup_powerbi_reader.py
"""

import secrets
import string
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norfingen.config import settings  # noqa: E402
from norfingen.db.repository import get_connection  # noqa: E402

ROLE_NAME = "powerbi_reader"
PASSWORD_LENGTH = 32
# Limit jednoczesnych połączeń — Power BI Service przy scheduled refresh z
# kilku raportów naraz potrafi otworzyć wiele sesji; 3 wystarcza na
# desktop + service, a chroni bazę przed wysyceniem puli połączeń.
CONNECTION_LIMIT = 3

# Bez znaków, które łamią URI połączenia / wymagają escapowania w Power BI
# (@ : / ? # [ ] % &) — hasło i tak ma 32 znaki entropii z tego alfabetu.
PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!*-_=+.,;()<>{}~^"


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def setup_powerbi_reader() -> str:
    password = generate_password()
    conn = get_connection()
    with conn.cursor() as cur:
        # CREATE ROLE nie jest idempotentne — ten sam wzorzec warunkowy co dla
        # roli `analyst` w schema.sql. Przy powtórnym uruchomieniu rola już
        # istnieje i dostaje tylko nowe hasło (rotacja).
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'powerbi_reader') THEN
                    CREATE ROLE powerbi_reader WITH LOGIN;
                END IF;
            END
            $$;
            """
        )
        # Hasło osobnym ALTER-em z parametrem — NIE interpolowane do treści
        # DO $$...$$ (tam trafiłoby do logów serwera jako jawny tekst i nie
        # dałoby się go bezpiecznie sparametryzować).
        cur.execute(f"ALTER ROLE {ROLE_NAME} WITH PASSWORD %s", (password,))
        cur.execute(f"ALTER ROLE {ROLE_NAME} CONNECTION LIMIT {CONNECTION_LIMIT}")
        # Dziedziczenie uprawnień i polityk RLS roli `analyst` (Faza 1 + GRANT-y
        # z schema.sql). Polityki RLS `TO analyst` stosują się do każdej roli
        # będącej członkiem `analyst`, więc nie trzeba ich powielać.
        cur.execute(f"GRANT analyst TO {ROLE_NAME}")
        # Bez jawnego NOSUPERUSER/NOCREATEDB/NOCREATEROLE — to i tak domyślne
        # atrybuty świeżo utworzonej roli (CREATE ROLE ... WITH LOGIN nie
        # nadaje żadnych z nich), a Supabase (rola łącząca się z tego skryptu
        # nie jest prawdziwym superuserem, tylko ma CREATEROLE) odrzuca próbę
        # dotknięcia atrybutu SUPERUSER nawet w kierunku "false":
        # "Only roles with the SUPERUSER attribute may alter roles with the
        # SUPERUSER attribute" — więc ta linia jest zbędna i wywala transakcję.
    conn.commit()
    return password


def print_connection_details(password: str) -> None:
    parsed = urlparse(settings.DATABASE_URL)
    host = parsed.hostname or ""
    port = parsed.port or 5432
    dbname = (parsed.path or "/postgres").lstrip("/")

    # Supabase pooler wymaga nazwy użytkownika w formacie
    # "<rola>.<project_ref>" (routing tenantów) — sam "powerbi_reader" nie
    # zadziała przez pooler. project_ref bierzemy z istniejącego użytkownika
    # w DATABASE_URL (np. "postgres.abcdefgh" -> "abcdefgh").
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
    print("  DANE POŁĄCZENIA DLA POWER BI — skopiuj do menedżera haseł TERAZ")
    print("=" * 70)
    print(f"  Server (host:port) : {host}:{port}")
    print(f"  Database           : {dbname}")
    print(f"  Username           : {login_user} {user_note}")
    print(f"  Password           : {password}")
    print("=" * 70)
    print("  To hasło NIE jest nigdzie zapisane — ani w repo, ani w .env.")
    print("  Ponowne uruchomienie tego skryptu wygeneruje NOWE hasło")
    print("  i unieważni powyższe.")
    print("=" * 70 + "\n")
    print("Power BI Desktop: Get Data -> PostgreSQL database")
    print(f"  Server:   {host}:{port}")
    print(f"  Database: {dbname}")
    print("  Data Connectivity mode: Import (zalecane) lub DirectQuery")
    print("  W zakładce Database podaj powyższy Username/Password.")
    print("  Zaznacz 'Encrypt connection' (Supabase wymaga SSL).\n")


if __name__ == "__main__":
    pwd = setup_powerbi_reader()
    print(f"✓ Rola {ROLE_NAME} utworzona/zaktualizowana (LOGIN, CONNECTION LIMIT {CONNECTION_LIMIT}, dziedziczy analyst)")
    print_connection_details(pwd)
