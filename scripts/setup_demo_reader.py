"""Tworzy/rotuje realną, login-capable rolę read-only `demo_reader` — publicznie
udostępniany dostęp testowy do bazy (rekruterzy, testerzy, docs/API_ACCESS.md).

Dlaczego OSOBNA rola od `powerbi_reader` (Krok 2), nie ta sama: `powerbi_reader`
nie ma `statement_timeout` — publiczny odbiorca mógłby odpalić kosztowne
zapytanie i zająć część limitu połączeń, a rotacja/unieważnienie hasła demo
(spodziewane, bo hasło trafia do osób trzecich) zerwałoby przy okazji
prawdziwe połączenie Power BI właściciela. Osobna rola = niezależna rotacja,
własny (niższy) limit połączeń, własny timeout zapytań.

Ten sam wzorzec co scripts/setup_powerbi_reader.py: rola dziedziczy `analyst`
(polityki RLS z Fazy 1, GRANT SELECT z Kroku 2 — read-only, zweryfikowane
end-to-end), hasło generowane losowo i wypisywane TYLKO na stdout (nigdy do
pliku/repo). Powtórne uruchomienie = rotacja (poprzednie hasło przestaje
działać) — to jest jednocześnie mechanizm "rotate_demo_password" z promptu,
bez osobnego duplikującego skryptu.

Uruchomienie (wymaga DATABASE_URL z uprawnieniami superusera/właściciela):
    python scripts/setup_demo_reader.py
"""

import secrets
import string
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norfingen.config import settings  # noqa: E402
from norfingen.db.repository import get_connection  # noqa: E402

ROLE_NAME = "demo_reader"
PASSWORD_LENGTH = 28
CONNECTION_LIMIT = 2  # nizej niz powerbi_reader (3) — to jest wielu anonimowych odwiedzajacych, nie jeden BI tool
STATEMENT_TIMEOUT = "10s"  # chroni przed przypadkowym/celowym drogim zapytaniem od nieznanego odbiorcy

PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!*-_=+.,;()<>{}~^"


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def setup_demo_reader() -> str:
    password = generate_password()
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_reader') THEN
                    CREATE ROLE demo_reader WITH LOGIN;
                END IF;
            END
            $$;
            """
        )
        cur.execute(f"ALTER ROLE {ROLE_NAME} WITH PASSWORD %s", (password,))
        cur.execute(f"ALTER ROLE {ROLE_NAME} CONNECTION LIMIT {CONNECTION_LIMIT}")
        cur.execute(f"ALTER ROLE {ROLE_NAME} SET statement_timeout = '{STATEMENT_TIMEOUT}'")
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
    print("  DANE DOSTĘPU DEMO — zapisz bezpiecznie, NIGDY do pliku w repo")
    print("=" * 70)
    print(f"  Server (host:port) : {host}:{port}")
    print(f"  Database           : {dbname}")
    print(f"  Username           : {login_user} {user_note}")
    print(f"  Password           : {password}")
    print("=" * 70)
    print("  To hasło NIE jest nigdzie zapisane — ani w repo, ani w .env.")
    print("  Przekaż je bezpiecznym kanałem (nie e-mail w czystym tekście,")
    print("  nie commit). Ponowne uruchomienie tego skryptu wygeneruje NOWE")
    print("  hasło i unieważni powyższe — to jest zamierzony mechanizm rotacji.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    pwd = setup_demo_reader()
    print(
        f"✓ Rola {ROLE_NAME} utworzona/zaktualizowana "
        f"(LOGIN, CONNECTION LIMIT {CONNECTION_LIMIT}, statement_timeout={STATEMENT_TIMEOUT}, dziedziczy analyst)"
    )
    print_connection_details(pwd)
