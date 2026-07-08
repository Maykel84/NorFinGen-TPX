from datetime import date

from norfingen.generators.salary_generator import brutto_earned_in_year, calc_june_salary, generate_monthly_salary
from norfingen.seed.payroll import first_working_day_of_month
from norfingen.seed.roster import EMPLOYEES, employee_by_number, numeric_id


def test_all_employees_start_on_first_working_day_of_month():
    """Zadanie 1b — żaden pracownik nie zaczyna w środku/na końcu miesiąca."""
    for e in EMPLOYEES:
        expected = first_working_day_of_month(e.start_date.year, e.start_date.month)
        assert e.start_date == expected, f"{e.number}: start_date={e.start_date} != pierwszy dzień roboczy {expected}"


def test_first_working_day_of_month_skips_weekend():
    assert first_working_day_of_month(2022, 10) == date(2022, 10, 3)  # 1-2 października 2022 to weekend
    assert first_working_day_of_month(2025, 6) == date(2025, 6, 2)  # 1 czerwca 2025 to niedziela
    assert first_working_day_of_month(2019, 1) == date(2019, 1, 1)  # 1 stycznia 2019 to wtorek — bez zmian


def test_feriepengegrunnlag_prorated_for_partial_previous_year():
    """Zadanie 1a/2b — E17 zatrudniony 2022-10-03: podstawa feriepenger za
    2022 to tylko październik-grudzień (3 miesiące), nie pełny rok."""
    e17 = employee_by_number("E17")
    assert e17.start_date == date(2022, 10, 3)

    basis_2022 = brutto_earned_in_year(e17, 2022)
    monthly = e17.annual_salary / 12
    assert abs(basis_2022 - 3 * monthly) < 0.02  # październik, listopad, grudzień — bez podwyżki (pierwsza dopiero VII/2023)

    june_2023 = calc_june_salary(e17, 2023, basis_2022)
    assert abs(june_2023.feriepenger - round(basis_2022 * 0.12)) < 0.02
    # Feriepenger (z 3 miesięcy) < normalna pensja czerwcowa -> dopłata do pełnej pensji.
    assert june_2023.gross_salary > 0
    assert abs(june_2023.total_brutto - monthly) < 0.02


def test_no_feriepenger_in_employees_own_hire_year():
    """Zadanie 2c — pracownik zatrudniony w TRAKCIE roku nie dostaje
    feriepenger w czerwcu TEGO SAMEGO roku (brak podstawy z roku poprzedniego,
    bo jeszcze nie pracował) — dostaje tylko normalną pensję czerwcową.
    E06 (Faza 6 — zastępuje usuniętego E20 z rozwiązanego zespołu skalowania):
    start 2019-04-01, więc rok firmy jeszcze nie istniał w 2018."""
    e06 = employee_by_number("E06")
    assert e06.start_date == date(2019, 4, 1)

    basis_2018 = brutto_earned_in_year(e06, 2018)
    assert basis_2018 == 0

    june_2019 = calc_june_salary(e06, 2019, basis_2018)
    assert june_2019.feriepenger == 0
    assert june_2019.gross_salary > 0
    assert june_2019.total_brutto == june_2019.gross_salary


def test_no_feriepenger_specification_line_when_amount_is_zero():
    """Zadanie 2c — brak wiersza salary_specifications typu FERIEPENGER, gdy
    kwota wynosi 0 (nie tylko kwota=0, ale brak samego rekordu — czystość
    audytu: 'nie generuje się żadne feriepenger' rozumiane dosłownie)."""
    from norfingen.models.salary import WAGE_TYPE_FERIEPENGER

    transaction, _ = generate_monthly_salary(2019, 6)
    e06_payslip = next(p for p in transaction.payslips if p.employee.id == numeric_id("E06"))
    feriepenger_specs = [s for s in e06_payslip.specifications if s.wageType.id == WAGE_TYPE_FERIEPENGER.id]
    assert feriepenger_specs == []


def test_new_hire_day_two_or_three_paid_in_own_start_month():
    """Zadanie 1a/1b — bugfix Fazy 5: pracownik którego pierwszy dzień
    roboczy wypada 2./3. dnia miesiąca (bo 1. to weekend) musi dostać
    wypłatę za SWÓJ miesiąc startu, nie dopiero za kolejny."""
    e17 = employee_by_number("E17")
    transaction, _ = generate_monthly_salary(2022, 10)
    assert any(p.employee.id == numeric_id("E17") for p in transaction.payslips)

    # E07 (Faza 6 — zastępuje usuniętego E38): start 2020-03-02 (1 marca 2020
    # to niedziela) — ten sam wzorzec "dzień 2", inny miesiąc/rok.
    e07 = employee_by_number("E07")
    assert e07.start_date == date(2020, 3, 2)
    transaction_mar, _ = generate_monthly_salary(2020, 3)
    assert any(p.employee.id == numeric_id("E07") for p in transaction_mar.payslips)


def test_feriepenger_accounts_for_july_raise_in_prior_year():
    """Zadanie 2b — pracownik z pełnym rokiem poprzednim, obejmującym
    podwyżkę lipcową: podstawa musi uwzględniać wyższą stawkę H2, nie tylko
    stawkę ze stycznia x12."""
    e01 = employee_by_number("E01")  # start 2019-01-01 -> pełne lata poprzednie od 2020
    basis_2020 = brutto_earned_in_year(e01, 2020)
    monthly_h1 = e01.annual_salary / 12  # brak podwyżki w 2019 (rok zatrudnienia)
    monthly_h2 = round(monthly_h1 * 1.03, 2)  # pierwsza podwyżka lipiec 2020
    expected = round(monthly_h1 * 6 + monthly_h2 * 6, 2)
    assert abs(basis_2020 - expected) < 0.05
    assert basis_2020 > monthly_h1 * 12  # podstawa wyższa niż "stara stawka x 12"
