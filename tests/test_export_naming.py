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
