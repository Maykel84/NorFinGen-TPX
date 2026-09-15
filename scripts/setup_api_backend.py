"""Tworzy infrastrukturę bazodanową dla usługi REST API (`api/`) — tabelę
`api_keys` (własny system kluczy, niezależny od Supabase Auth/anon/authenticated)
oraz rolę `api_key_manager`, jedyną z prawem odczytu/aktualizacji tej tabeli.

Dlaczego OSOBNA rola od `demo_reader`/`powerbi_reader`: `api_keys` musi być
NIEwidoczna dla read-only konsumentów danych (żeby nikt z dostępem SQL nie
mógł odczytać hashy/rate-limitów innych posiadaczy kluczy) — stąd RLS bez
polityki dla `analyst`. Ale usługa API (`api/auth.py`) i tak potrzebuje
odczytu i aktualizacji (`last_used_at`, licznik rate-limit) tej jednej
tabeli — stąd trzecia, wąsko uprawniona rola, analogiczny wzorzec do
`scripts/setup_demo_reader.py`/`setup_powerbi_reader.py` (osobna rola =
niezależna rotacja, minimalny zakres uprawnień, nic nie dziedziczy z
`analyst` bo nie potrzebuje dostępu do żadnej innej tabeli).

Idempotentne: bezpieczne do wielokrotnego uruchomienia. Powtórne uruchomienie
= rotacja hasła `api_key_manager` (poprzednie przestaje działać).

Uruchomienie (wymaga DATABASE_URL z uprawnieniami właściciela/superusera):
    python scripts/setup_api_backend.py
"""

import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norfingen.db.repository import get_connection  # noqa: E402

ROLE_NAME = "api_key_manager"
PASSWORD_LENGTH = 28
CONNECTION_LIMIT = 5
STATEMENT_TIMEOUT = "10s"
PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!*-_=+.,;()<>{}~^"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    owner_label TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    rate_limit_per_hour INT DEFAULT 100,
    revoked BOOLEAN DEFAULT false,
    last_used_at TIMESTAMPTZ,
    -- Rozszerzenie ponad szkic z promptu: licznik rate-limit trzymany w
    -- samej tabeli (nie w pamięci procesu) - przetrwa restart usługi i
    -- (gdyby kiedyś było > 1 instancja API) jest współdzielony, bo liczy
    -- się w bazie, nie per-proces. Aktualizowany atomowo w auth.py.
    request_count_this_window INT NOT NULL DEFAULT 0,
    window_start TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Samoobsługowe generowanie kluczy (portal /portal, Zadanie 1) - kolumny
# dodane w tej sesji. `requester_label` duplikuje `owner_label` celowo:
# `owner_label` jest ogólnym polem używanym też przez klucze wydawane
# ręcznie (api/scripts/generate_api_key.py), `requester_label` to to samo
# co user wpisał w formularzu, trzymane osobno żeby móc kiedyś odróżnić
# self-service od ręcznych bez zgadywania po treści etykiety.
ALTER_TABLE_SELF_SERVICE_SQL = """
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS requester_label TEXT;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS self_service BOOLEAN DEFAULT false;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS created_from_ip TEXT;
"""

# Licznik dla /api/v1/export/{format} (Zadanie 3b) - osobna, celowo bardzo
# wąska tabela (tylko IP + znacznik czasu), żeby nie przeciążać semantyki
# api_keys (eksport nie wymaga klucza API wcale). Ta sama rola
# `api_key_manager` ją obsługuje - już jest jedyną rolą usługi z prawem
# zapisu do stanu rate-limitingu, więc nie ma powodu tworzyć czwartej roli.
CREATE_EXPORT_REQUESTS_SQL = """
CREATE TABLE IF NOT EXISTS export_requests (
    id SERIAL PRIMARY KEY,
    ip TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def setup_api_backend() -> str:
    password = generate_password()
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
        cur.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;")
        cur.execute(ALTER_TABLE_SELF_SERVICE_SQL)
        cur.execute(CREATE_EXPORT_REQUESTS_SQL)
        cur.execute("ALTER TABLE export_requests ENABLE ROW LEVEL SECURITY;")

        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_key_manager') THEN
                    CREATE ROLE api_key_manager WITH LOGIN;
                END IF;
            END
            $$;
            """
        )
        cur.execute(f"ALTER ROLE {ROLE_NAME} WITH PASSWORD %s", (password,))
        cur.execute(f"ALTER ROLE {ROLE_NAME} CONNECTION LIMIT {CONNECTION_LIMIT};")
        cur.execute(f"ALTER ROLE {ROLE_NAME} SET statement_timeout = '{STATEMENT_TIMEOUT}';")

        # Wąski zakres: SELECT/UPDATE (klucze istniejące, walidacja+licznik w
        # auth.py) + INSERT (nowe klucze self-service, Zadanie 1b) na
        # api_keys, nic więcej (nie dziedziczy analyst - nie ma powodu
        # widzieć żadnej innej tabeli). INSERT dodany w tej sesji - do teraz
        # nowe klucze powstawały wyłącznie przez api/scripts/generate_api_key.py
        # z uprawnieniami właściciela, bez potrzeby prawa zapisu dla tej roli.
        cur.execute("GRANT SELECT, INSERT, UPDATE ON api_keys TO api_key_manager;")
        cur.execute("GRANT USAGE, SELECT ON SEQUENCE api_keys_id_seq TO api_key_manager;")
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT FROM pg_policies
                    WHERE tablename = 'api_keys' AND policyname = 'api_key_manager_access'
                ) THEN
                    CREATE POLICY api_key_manager_access ON api_keys
                        FOR ALL TO api_key_manager USING (true) WITH CHECK (true);
                END IF;
            END
            $$;
            """
        )
        # Świadomie ŻADNEJ polityki dla analyst/demo_reader/powerbi_reader -
        # api_keys musi zostac niewidoczna dla konsumentow danych read-only.

        cur.execute("GRANT SELECT, INSERT ON export_requests TO api_key_manager;")
        cur.execute("GRANT USAGE, SELECT ON SEQUENCE export_requests_id_seq TO api_key_manager;")
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT FROM pg_policies
                    WHERE tablename = 'export_requests' AND policyname = 'api_key_manager_access'
                ) THEN
                    CREATE POLICY api_key_manager_access ON export_requests
                        FOR ALL TO api_key_manager USING (true) WITH CHECK (true);
                END IF;
            END
            $$;
            """
        )
    conn.commit()
    conn.close()

    print(f"Rola '{ROLE_NAME}' gotowa (hasło zrotowane, zapisz teraz - nie pokaże się ponownie):")
    print(f"  password: {password}")
    print()
    print("Ustaw jako zmienną środowiskową dla usługi api/ (nigdy w repo):")
    print(f"  API_KEY_MANAGER_DATABASE_URL=postgresql://api_key_manager.<project_ref>:{password}@<pooler-host>:5432/postgres")
    return password


if __name__ == "__main__":
    setup_api_backend()
