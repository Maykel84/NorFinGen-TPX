"""Krok 2 — dostęp read-only dla BI (Power BI). Offline (bez połączenia do
bazy, zgodnie z konwencją reszty pakietu testów) — pilnuje regresji: gdyby
ktoś w przyszłości usunął GRANT z schema.sql, `analyst`/`powerbi_reader`
wróciłyby do stanu "polityki RLS poprawne, ale funkcjonalnie bezużyteczne"
(zob. SESSION_HANDOFF.md p. 11)."""

from pathlib import Path

SCHEMA_SQL = (Path(__file__).resolve().parents[1] / "src" / "norfingen" / "db" / "schema.sql").read_text()


def test_schema_grants_select_to_analyst():
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst" in SCHEMA_SQL


def test_schema_sets_default_privileges_for_future_tables():
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analyst" in SCHEMA_SQL


def test_setup_script_never_hardcodes_a_password():
    """Skrypt generuje hasło w pamięci (secrets) — nigdy nie powinien
    zawierać literalnego hasła/sekretu wpisanego na stałe w kodzie."""
    script = (Path(__file__).resolve().parents[1] / "scripts" / "setup_powerbi_reader.py").read_text()
    assert "secrets.choice" in script
    assert "ALTER ROLE powerbi_reader WITH PASSWORD '" not in script  # literalny sekret w kodzie
