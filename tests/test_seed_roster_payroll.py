from datetime import date

from norfingen.seed.payroll import (
    active_employees,
    calc_aga,
    calc_brutto,
    calc_feriepenger,
    calc_netto,
    calc_skattetrekk,
    is_june,
    last_working_day,
)
from norfingen.seed.roster import CUSTOMERS, DEPARTMENTS, EMPLOYEES, PRODUCTS, SUPPLIERS


def test_roster_counts_match_docs():
    assert len(DEPARTMENTS) == 4
    assert len(EMPLOYEES) == 16
    assert len(CUSTOMERS) == 12
    assert len(SUPPLIERS) == 8
    assert len(PRODUCTS) == 6


def test_active_employees_respects_historical_phases():
    assert len(active_employees(date(2019, 6, 1))) == 6
    assert len(active_employees(date(2020, 6, 1))) == 8
    assert len(active_employees(date(2021, 12, 1))) == 10
    assert len(active_employees(date(2023, 1, 1))) == 16


def test_active_employees_brutto_aggregate_matches_docs():
    # Łączne brutto/mies. dla okresu 2022-09 - dziś: 16 os. ≈ 955 000 NOK (docs W2,
    # wartość zaokrąglona w dokumentacji — dopuszczamy tolerancję wynikającą z sumy
    # rzeczywistych stawek rocznych w roster.py).
    active = active_employees(date(2023, 1, 1))
    total_brutto = sum(calc_brutto(e) for e in active)
    assert abs(total_brutto - 955_000) < 20_000


def test_payroll_calculations():
    brutto = 73_333
    skattetrekk = calc_skattetrekk(brutto)
    assert skattetrekk == round(brutto * 0.33)
    netto = calc_netto(brutto, skattetrekk)
    assert netto == brutto - skattetrekk
    aga = calc_aga(brutto)
    assert aga == round(brutto * 0.141)


def test_calc_feriepenger():
    assert calc_feriepenger(955_000) == round(955_000 * 0.12)


def test_last_working_day_rolls_back_from_weekend():
    # Czerwiec 2024 -> 30.06.2024 to niedziela -> powinno przesunąć na piątek 28.06
    assert last_working_day(2024, 6) == date(2024, 6, 28)
    # Styczeń 2024 -> 31.01.2024 to środa -> bez zmian
    assert last_working_day(2024, 1) == date(2024, 1, 31)


def test_is_june():
    assert is_june(6) is True
    assert is_june(5) is False
