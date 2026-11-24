"""Poprawki eksportu — spójne, angielskie/Tripletex-zgodne nazewnictwo kolumn
(Zadanie 0) i kody pocztowe (Zadanie 2). Testy działają offline (bez
połączenia do bazy) — sprawdzają tekst zapytań SQL (export_queries.QUERIES)
i dane roster.py bezpośrednio, zgodnie z konwencją reszty tego pakietu
testów (żadna inna tabela testów nie łączy się z prawdziwym Supabase, zob.
tests/test_repository.py). Ręczna weryfikacja wygenerowanego
norfingen_export.xlsx (nagłówki arkuszy) jest osobnym krokiem opisanym w
SESSION_HANDOFF.md, nie automatycznym testem — wymagałby żywej bazy."""

import re

from norfingen.seed.roster import CUSTOMERS, NORWEGIAN_POSTAL_CODES

from export_queries import QUERIES

POLISH_INDICATORS = [
    "klient", "dostawca", "wartosc", "ilosc", "przychody", "koszty_",
    "wynik_", "liczba_", "laczne_", "opis", "konto", "miesiac",
]

AS_ALIAS_RE = re.compile(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def test_all_customers_have_postal_code():
    used_cities = {c.city for c in CUSTOMERS}
    missing = used_cities - set(NORWEGIAN_POSTAL_CODES.keys())
    assert not missing, f"Brak kodów pocztowych dla: {missing}"
    for customer in CUSTOMERS:
        assert NORWEGIAN_POSTAL_CODES[customer.city]  # niepuste


def test_postal_codes_are_four_digit_strings():
    for city, code in NORWEGIAN_POSTAL_CODES.items():
        assert code.isdigit() and len(code) == 4, f"{city}: {code!r} nie wygląda jak realny norweski postnummer"


def test_export_queries_use_consistent_naming():
    """Żadne AS-aliasy w zapytaniach export_queries.QUERIES nie używają
    polskich nazw opisowych (heurystyka z Zadania 4) — sprawdza tekst
    zapytań SQL wprost, nie wymaga wygenerowanego pliku/żywej bazy."""
    for sheet, sql in QUERIES.items():
        aliases = AS_ALIAS_RE.findall(sql)
        for alias in aliases:
            assert not any(p in alias.lower() for p in POLISH_INDICATORS), \
                f"{sheet}: alias {alias!r} wygląda na polską nazwę kolumny"


def test_new_employee_payroll_sheet_registered():
    """Zadanie 3 — Payroll_per_pracownik musi istnieć obok istniejących arkuszy
    (nazwa arkusza zostaje po polsku — Zadanie 0 dotyczy tylko kolumn)."""
    assert "Payroll_per_pracownik" in QUERIES
    for expected_alias in ("employee_id", "employee_name", "net_amount", "gross_amount", "tax_amount"):
        assert expected_alias in QUERIES["Payroll_per_pracownik"]


def test_sales_invoice_export_flags_the_deliberate_test_traps():
    """Accounting phase 3: late and written-off invoices are modelled on purpose, so the export says so - a reconciliation
    that finds them has found a feature, not an error. Same four columns in the local export and in the REST API's copy."""
    from api.export_data import _COLUMNS

    flags = ("invoice_status", "is_overdue", "payment_due_date", "paid_date", "paid_late")
    for column in flags:
        assert column in QUERIES["Faktury_sprzedazy"], column
        assert column in _COLUMNS["Faktury_sprzedazy"], column
    # round 2, point 1: the status is derived in ONE place, the view v_invoice_status; the export joins it per order
    assert "v_invoice_status" in QUERIES["Faktury_sprzedazy"]
    from pathlib import Path
    view_sql = Path("src/norfingen/db/schema.sql").read_text(encoding="utf-8")
    view_sql = view_sql[view_sql.index("CREATE OR REPLACE VIEW v_invoice_status"):]
    view_sql = view_sql[:view_sql.index("v_headcount_monthly counts")]
    assert "bank_transactions" in view_sql                               # paid_date comes from the real payment
    assert "LEFT JOIN bank_transactions" in view_sql                     # an unpaid invoice must not vanish
    # the REST API copy lists exactly the columns of the local query
    for column in _COLUMNS["Faktury_sprzedazy"]:
        assert column in QUERIES["Faktury_sprzedazy"], column


def test_cogs_liabilities_have_their_own_export_sheet():
    """Accounting phase 4 (variant B): the COGS pass-through liabilities sit on 2400 beside the purchase invoices but have no
    invoice, so they get a sheet of their own - otherwise the supplier ledger cannot be reconciled (gl_checks T8). Same columns
    in the local export and in the REST API's copy; `status` is the open/paid flag, `paid_date` the bank payment."""
    from api.export_data import _COLUMNS

    assert "Zobowiazania_COGS" in QUERIES
    columns = ("payable_id", "accrual_date", "payment_due_date", "account_number", "supplier_id", "supplier_name",
               "description", "amount_excluding_vat_currency", "vat_amount_currency", "amount_currency",
               "status", "paid_date")  # amount_currency is GROSS since the audit of 2026-11-16 (phase 2)
    assert list(_COLUMNS["Zobowiazania_COGS"]) == list(columns)
    for column in columns:
        assert column in QUERIES["Zobowiazania_COGS"], column
    assert "LEFT JOIN" in QUERIES["Zobowiazania_COGS"].upper()   # an unpaid payable must not vanish from the sheet


def test_vat_settlements_have_their_own_export_sheet():
    """Accounting phase 5: one row per settled VAT term - term, output VAT, input VAT, balance, payment date, status. The same
    columns in the local export and in the REST API's copy; an unpaid term must not vanish (LEFT JOIN to the bank)."""
    from api.export_data import _COLUMNS

    columns = ("term", "period_start", "period_end", "output_vat", "input_vat", "balance",
               "payment_date", "status", "paid_date")
    assert list(_COLUMNS["Rozliczenia_MVA"]) == list(columns)
    for column in columns:
        assert column.split(".")[-1] in QUERIES["Rozliczenia_MVA"], column
    assert "LEFT JOIN" in QUERIES["Rozliczenia_MVA"].upper()
