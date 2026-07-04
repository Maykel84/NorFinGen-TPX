from datetime import date

from norfingen.seed.payroll import (
    active_employees,
    calc_aga,
    calc_brutto,
    calc_brutto_with_raises,
    calc_feriepenger,
    calc_netto,
    calc_skattetrekk,
    is_june,
    last_working_day,
)
from norfingen.seed.roster import (
    CUSTOMERS,
    DEPARTMENTS,
    EMPLOYEES,
    PRODUCTS,
    PROJECTS,
    SUPPLIERS,
    employee_by_number,
    numeric_id,
    project_by_number,
)


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


def test_founding_cohort_staggered_over_four_months():
    # Kohorta założycielska rozłożona 2019-01 -> 2019-04, nie jednego dnia.
    assert len(active_employees(date(2019, 1, 1))) == 1  # tylko E01 (CEO)
    assert len(active_employees(date(2019, 1, 31))) == 1
    assert len(active_employees(date(2019, 2, 1))) == 2  # +E02
    assert len(active_employees(date(2019, 2, 15))) == 3  # +E03
    assert len(active_employees(date(2019, 3, 1))) == 4  # +E04
    assert len(active_employees(date(2019, 3, 15))) == 5  # +E05
    assert len(active_employees(date(2019, 4, 1))) == 6  # +E06 -> zespół kompletny


def test_customer_count_grows_with_headcount():
    """Liczba aktywnych klientów rośnie wraz z zatrudnieniem, nie wyprzedza go —
    na koniec 2019 (6 pracowników) liczba onboardowanych klientów nie przekracza
    liczby pracowników w tym momencie."""
    headcount_end_2019 = len(active_employees(date(2019, 12, 31)))
    active_customers_end_2019 = [c for c in CUSTOMERS if c.onboarding_date <= date(2019, 12, 31)]
    assert headcount_end_2019 == 6
    assert len(active_customers_end_2019) <= headcount_end_2019


def test_founding_hires_not_paid_before_their_start_month():
    # E03 startuje 2019-02-15 -> nieaktywny na 1. dzień lutego (brak wypłaty za luty),
    # aktywny od marca (active_employees sprawdza start_date <= 1. dzień miesiąca).
    e03 = employee_by_number("E03")
    assert e03.start_date == date(2019, 2, 15)
    active_february = active_employees(date(2019, 2, 1))
    active_march = active_employees(date(2019, 3, 1))
    assert e03 not in active_february
    assert e03 in active_march


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


def test_calc_brutto_with_raises_no_raise_in_founding_year():
    e01 = employee_by_number("E01")  # start 2019-01-01
    assert calc_brutto_with_raises(e01, 2019, 1) == round(calc_brutto(e01), 2)
    assert calc_brutto_with_raises(e01, 2019, 12) == round(calc_brutto(e01), 2)


def test_calc_brutto_with_raises_first_raise_next_july():
    e01 = employee_by_number("E01")  # start 2019-01-01 -> pierwsza podwyżka lipiec 2020
    assert calc_brutto_with_raises(e01, 2020, 6) == round(calc_brutto(e01), 2)
    assert calc_brutto_with_raises(e01, 2020, 7) == round(calc_brutto(e01) * 1.03, 2)


def test_calc_brutto_with_raises_compounds_annually():
    e01 = employee_by_number("E01")
    # 880 000 NOK/rok w 2019 -> ~1 081 000 NOK/rok (brutto x12) w 2026 po H2 (7 podwyżek).
    monthly_2026_h2 = calc_brutto_with_raises(e01, 2026, 7)
    assert abs(monthly_2026_h2 * 12 - 1_081_000) < 5_000


def test_projects_seed_data():
    assert len(PROJECTS) == 8
    prj005 = project_by_number("PRJ005")
    assert prj005.customer_id == 6
    assert prj005.name == "Digitalisering — Telemark"
    assert prj005.start_date == date(2026, 3, 1)


def test_numeric_id_handles_single_and_multi_letter_prefixes():
    assert numeric_id("E07") == 7
    assert numeric_id("K03") == 3
    assert numeric_id("L05") == 5
    assert numeric_id("P02") == 2
    assert numeric_id("PRJ001") == 1
    assert numeric_id("PRJ008") == 8


def test_last_working_day_rolls_back_from_weekend():
    # Czerwiec 2024 -> 30.06.2024 to niedziela -> powinno przesunąć na piątek 28.06
    assert last_working_day(2024, 6) == date(2024, 6, 28)
    # Styczeń 2024 -> 31.01.2024 to środa -> bez zmian
    assert last_working_day(2024, 1) == date(2024, 1, 31)


def test_is_june():
    assert is_june(6) is True
    assert is_june(5) is False
