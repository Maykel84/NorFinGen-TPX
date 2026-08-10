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


def test_v_pl_monthly_computes_revenue_from_orders_not_postings():
    """Zadanie 2 — regresja krytycznego błędu ze szkicu w prompcie: postings
    NIGDY nie zawiera przychodu (account_number 3000-3999), więc widok P&L
    musi liczyć revenue z orders/order_lines, nie z postings — inaczej
    revenue zawsze wychodzi 0/NULL. Zob. nagłówek DATA_DICTIONARY.md."""
    view_start = SCHEMA_SQL.index("CREATE OR REPLACE VIEW v_pl_monthly")
    view_end = SCHEMA_SQL.index(";", SCHEMA_SQL.index("v_headcount_monthly", view_start))
    view_sql = SCHEMA_SQL[view_start:view_end]
    assert "order_lines" in view_sql
    assert "BETWEEN 3000 AND 3999" not in view_sql


def test_bi_views_use_security_invoker():
    """Bez security_invoker=true widok czyta tabele źródłowe z uprawnieniami
    WŁAŚCICIELA widoku (postgres, omija RLS), nie roli faktycznie
    odpytującej — RLS byłoby po cichu omijane przy odpytywaniu przez widok."""
    for view in ("v_sales_flat", "v_pl_monthly", "v_headcount_monthly"):
        assert f"CREATE OR REPLACE VIEW {view} WITH (security_invoker = true)" in SCHEMA_SQL


def test_bi_views_granted_to_analyst():
    assert "GRANT SELECT ON v_sales_flat, v_pl_monthly, v_headcount_monthly TO analyst" in SCHEMA_SQL
