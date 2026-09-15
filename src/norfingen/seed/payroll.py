"""Norwegian payroll calculation functions — operate on data from norfingen.seed.roster.

Rates: skattetrekk (tax withholding) ~33% (approximation of the advance tax
payment), AGA (employer's social security contribution) 14.1% (Oslo Zone 1),
feriepenger (holiday pay) 12% (IT industry standard, statutory minimum 10.2%).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from norfingen.seed.roster import EMPLOYEES, EmployeeSeed

SKATTETREKK_RATE = 0.33
AGA_RATE = 0.141
FERIEPENGER_RATE = 0.12


def first_working_day_of_month(year: int, month: int) -> date:
    """Returns the first working day (Mon-Fri) of the given month. Phase 5 —
    all employees start on this day (see EMPLOYEES in roster.py) — this
    eliminates the need to prorate "how many days in a partial month", since
    the first month of employment is always a full month of work."""
    d = date(year, month, 1)
    while d.weekday() >= 5:  # Saturday=5, Sunday=6
        d += timedelta(days=1)
    return d


def active_employees(on_date: date) -> list[EmployeeSeed]:
    """Employees whose startDate <= on_date — respects historical hiring
    phases (founding 2019-01, growth1 2020-03, growth2 2021-06, merger 2022-09).
    The backfill generator MUST call this function separately for each
    historical month — never apply the current full roster retroactively.
    """
    return [e for e in EMPLOYEES if e.start_date <= on_date]


def calc_brutto(employee: EmployeeSeed) -> float:
    return employee.annual_salary / 12


def calc_brutto_with_raises(employee: EmployeeSeed, year: int, month: int,
                             raise_rate: float = 0.03, raise_month: int = 7) -> float:
    """Calculates gross salary including annual raises.

    A +raise_rate raise happens every year in raise_month (default July),
    the first one in the year following hiring."""
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
    gross_salary: float  # regular June salary — 0 in the standard case
    feriepenger: float
    total_brutto: float  # gross_salary + feriepenger — this is what posts to account 5000/AGA
    tax_on_salary: float  # skattetrekk applies only to gross_salary; feriepenger is always untaxed


def calc_june_salary(employee: EmployeeSeed, year: int, basis_prev_year: float) -> JuneSalary:
    """June: feriepenger REPLACES the normal salary, it is not added on top of
    it (a previous bug: the company paid both the full salary AND the full
    feriepenger — a double cost compounding year over year).

    Normally (feriepenger >= current year's normal salary) the normal June
    salary = 0, the entire gross amount is feriepenger (untaxed). For
    employees with <1 year of tenure (feriepenger calculated from a partial
    prior year may be lower than the current salary) the difference is paid
    out as a regular, taxed salary."""
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
    """Last working day of the month (payment date) — the last calendar day
    of the month, shifted to Friday if it falls on a Saturday/Sunday."""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    if d.weekday() == 5:  # Saturday
        d -= timedelta(days=1)
    elif d.weekday() == 6:  # Sunday
        d -= timedelta(days=2)
    return d


# Phase 5a — fix for a critical bug: the monthly backfill (generators/backfill.py
# generate_and_persist_month) processed the ENTIRE current calendar month based
# solely on (year, month) from months_range(), without checking whether the
# individual days of that month had actually already passed relative to the
# system date — result: orders/invoices/payroll with dates up to a dozen-plus
# days in the future (e.g. the entire July 2026 payroll posted on July 31,
# even though the backfill was run on July 7). The generator must NEVER create
# a record dated later than today — the functions below are a hard, reusable
# safeguard applied in generate_and_persist_month/run_daily.
def get_generation_cutoff_date() -> date:
    """The generator NEVER creates records dated later than today."""
    return date.today()


def is_date_generatable(target_date: date, cutoff: Optional[date] = None) -> bool:
    """Whether target_date is allowed to be generated — no later than cutoff (default: today)."""
    return target_date <= (cutoff if cutoff is not None else get_generation_cutoff_date())


def should_generate_monthly_salary(year: int, month: int, cutoff: Optional[date] = None) -> bool:
    """Payroll for a given month is only generated once that month has
    actually ended (payment day <= today), never ahead of time."""
    return is_date_generatable(last_working_day(year, month), cutoff)


def is_june(month: int) -> bool:
    return month == 6
