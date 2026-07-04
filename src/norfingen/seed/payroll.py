"""Funkcje obliczeniowe payrollu norweskiego — operują na danych z norfingen.seed.roster.

Stawki: skattetrekk ~33% (przybliżenie zaliczki podatkowej), AGA 14,1% (Oslo Zone 1),
feriepenger 12% (standard branżowy IT, min. ustawowe 10,2%).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from norfingen.seed.roster import EMPLOYEES, EmployeeSeed

SKATTETREKK_RATE = 0.33
AGA_RATE = 0.141
FERIEPENGER_RATE = 0.12


def active_employees(on_date: date) -> list[EmployeeSeed]:
    """Pracownicy, których startDate <= on_date — respektuje historyczne fazy
    zatrudnienia (founding 2019-01, growth1 2020-03, growth2 2021-06, merger 2022-09).
    Generator backfillu MUSI wywołać tę funkcję dla każdego miesiąca historycznego
    z osobna — nie używać aktualnego pełnego rosteru wstecznie.
    """
    return [e for e in EMPLOYEES if e.start_date <= on_date]


def calc_brutto(employee: EmployeeSeed) -> float:
    return employee.annual_salary / 12


def calc_brutto_with_raises(employee: EmployeeSeed, year: int, month: int,
                             raise_rate: float = 0.03, raise_month: int = 7) -> float:
    """Oblicza brutto z uwzględnieniem corocznych podwyżek.

    Podwyżka +raise_rate co roku w raise_month (domyślnie lipiec), pierwsza w
    roku następującym po zatrudnieniu."""
    base = employee.annual_salary / 12
    start_year = employee.start_date.year
    raises = 0
    for y in range(start_year + 1, year + 1):
        if y < year or (y == year and month >= raise_month):
            raises += 1
    return round(base * ((1 + raise_rate) ** raises), 2)


def calc_skattetrekk(brutto: float) -> float:
    return round(brutto * SKATTETREKK_RATE)


def calc_netto(brutto: float, skattetrekk: float) -> float:
    return brutto - skattetrekk


def calc_aga(brutto: float) -> float:
    return round(brutto * AGA_RATE)


def calc_feriepenger(brutto_prev_year: float) -> float:
    return round(brutto_prev_year * FERIEPENGER_RATE)


@dataclass(frozen=True)
class JuneSalary:
    gross_salary: float  # zwykła pensja czerwcowa — 0 w standardowym przypadku
    feriepenger: float
    total_brutto: float  # gross_salary + feriepenger — to trafia na konto 5000/AGA
    tax_on_salary: float  # skattetrekk tylko od gross_salary; feriepenger zawsze nieopodatkowane


def calc_june_salary(employee: EmployeeSeed, year: int, basis_prev_year: float) -> JuneSalary:
    """Czerwiec: feriepenger ZASTĘPUJE normalną pensję, nie dodaje się do niej
    (poprzedni błąd: firma płaciła i pełną pensję, i pełne feriepenger — podwójny
    koszt narastający z roku na rok).

    Standardowo (feriepenger >= normalna pensja bieżącego roku) normalna pensja
    czerwcowa = 0, cały brutto to feriepenger (nieopodatkowane). Dla pracowników
    z <1 rok stażu (feriepenger liczone z niepełnego roku poprzedniego może być
    niższe niż bieżąca pensja) różnica dopłacana jest jako zwykła, opodatkowana
    pensja."""
    normal_gross = calc_brutto_with_raises(employee, year, 6)
    feriepenger = calc_feriepenger(basis_prev_year)

    if feriepenger >= normal_gross:
        return JuneSalary(gross_salary=0.0, feriepenger=feriepenger, total_brutto=feriepenger, tax_on_salary=0.0)

    gap = round(normal_gross - feriepenger, 2)
    return JuneSalary(
        gross_salary=gap,
        feriepenger=feriepenger,
        total_brutto=round(feriepenger + gap, 2),
        tax_on_salary=calc_skattetrekk(gap),
    )


def last_working_day(year: int, month: int) -> date:
    """Ostatni dzień roboczy miesiąca (data wypłaty) — ostatni kalendarzowy dzień
    miesiąca, przesunięty na piątek jeśli wypada w sobotę/niedzielę."""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    if d.weekday() == 5:  # sobota
        d -= timedelta(days=1)
    elif d.weekday() == 6:  # niedziela
        d -= timedelta(days=2)
    return d


def is_june(month: int) -> bool:
    return month == 6
