"""Generator miesięcznej listy płac (Warstwa 2 + Warstwa 3).

Każdy miesiąc (w tym czerwiec): Voucher 1 (lista płac: DR 5000 / CR 2710 /
CR 2740) + Voucher 2 (AGA: DR 5400 / CR 2700).

Czerwiec — feriepenger ZASTĘPUJE normalną pensję, nie dodaje się do niej (zob.
norfingen.seed.payroll.calc_june_salary). Standardowo (feriepenger >= bieżąca
pensja) normalna pensja czerwcowa = 0, cały brutto tego miesiąca to
nieopodatkowane feriepenger. Dla pracowników z <1 rok stażu różnica dopłacana
jest jako zwykła, opodatkowana pensja. AGA liczone jednolicie od total_brutto
(pensja + feriepenger) — bez osobnego, podwajającego wolucheru.

Podstawa feriepenger per pracownik = suma calc_brutto_with_raises(e, rok, miesiąc)
za miesiące, w których pracownik był aktywny w roku poprzednim (zob.
brutto_earned_in_year) — kluczowe dla pracowników z fazy merger (E11-E16,
aktywni od 2022-09): ich podstawa za 2022 to 4 miesiące, nie 12.

Podwyżki: +3% rocznie w lipcu, pierwsza w roku po zatrudnieniu (zob.
norfingen.seed.payroll.calc_brutto_with_raises) — stosowane zarówno do brutto
bieżącego miesiąca, jak i do podstawy feriepenger za rok poprzedni.
"""

from __future__ import annotations

from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.models.base import TripletexRef
from norfingen.models.salary import (
    WAGE_TYPE_FAST_LONN,
    WAGE_TYPE_FERIEPENGER,
    WAGE_TYPE_SKATTETREKK,
    Payslip,
    SalarySpecification,
    SalaryTransaction,
)
from norfingen.seed.payroll import (
    active_employees,
    calc_aga,
    calc_brutto_with_raises,
    calc_june_salary,
    calc_netto,
    calc_skattetrekk,
    first_working_day_of_month,
    is_june,
    last_working_day,
)
from norfingen.seed.roster import EmployeeSeed, numeric_id

MONTH_NAMES_NO = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]


def brutto_earned_in_year(employee: EmployeeSeed, year: int) -> float:
    """Suma brutto zarobionego przez pracownika w danym roku kalendarzowym —
    respektuje startDate (pracownik nieaktywny przed startem ma podstawę 0
    za te miesiące). Faza 5 — porównanie do first_working_day_of_month(),
    NIE date(year, month, 1): skoro EMPLOYEES.start_date jest teraz zawsze
    pierwszym dniem roboczym miesiąca (może to być 2. lub 3. dzień
    kalendarzowy, jeśli 1. wypada w weekend), porównanie do sztywnego
    kalendarzowego dnia 1 błędnie wykluczałoby pracownika z jego własnego
    miesiąca startu (np. start_date=2022-10-03 > date(2022,10,1))."""
    return sum(
        calc_brutto_with_raises(employee, year, month)
        for month in range(1, 13)
        if employee.start_date <= first_working_day_of_month(year, month)
    )


def generate_monthly_salary(year: int, month: int) -> tuple[SalaryTransaction, list[Voucher]]:
    # first_working_day_of_month(), nie date(year, month, 1) — zob. docstring
    # brutto_earned_in_year() wyżej, ten sam powód.
    active = active_employees(first_working_day_of_month(year, month))
    pay_date = last_working_day(year, month)
    june = is_june(month)

    payslips: list[Payslip] = []
    brutto_total = netto_total = skattetrekk_total = aga_total = 0.0

    transaction = SalaryTransaction(date=pay_date, year=year, month=month)

    for employee in active:
        emp_ref = TripletexRef(id=numeric_id(employee.number))
        specifications = []

        if june:
            basis_prev_year = brutto_earned_in_year(employee, year - 1)
            june_salary = calc_june_salary(employee, year, basis_prev_year)
            brutto = june_salary.total_brutto
            skattetrekk = june_salary.tax_on_salary
            netto = brutto - skattetrekk

            if june_salary.gross_salary > 0:
                specifications.append(
                    SalarySpecification(wageType=WAGE_TYPE_FAST_LONN, description="Fast lønn", amount=june_salary.gross_salary)
                )
            if june_salary.feriepenger > 0:
                specifications.append(
                    SalarySpecification(wageType=WAGE_TYPE_FERIEPENGER, description="Feriepenger", amount=june_salary.feriepenger)
                )
            if skattetrekk:
                specifications.append(
                    SalarySpecification(wageType=WAGE_TYPE_SKATTETREKK, description="Skattetrekk", amount=-skattetrekk)
                )
        else:
            brutto = calc_brutto_with_raises(employee, year, month)
            skattetrekk = calc_skattetrekk(brutto)
            netto = calc_netto(brutto, skattetrekk)
            specifications.append(
                SalarySpecification(wageType=WAGE_TYPE_FAST_LONN, description="Fast lønn", amount=brutto)
            )
            specifications.append(
                SalarySpecification(wageType=WAGE_TYPE_SKATTETREKK, description="Skattetrekk", amount=-skattetrekk)
            )

        aga = calc_aga(brutto)

        brutto_total += brutto
        netto_total += netto
        skattetrekk_total += skattetrekk
        aga_total += aga

        payslips.append(
            Payslip(
                employee=emp_ref,
                date=pay_date,
                specifications=specifications,
            )
        )

    transaction.payslips = payslips

    month_label = f"{MONTH_NAMES_NO[month - 1]} {year}"
    vouchers: list[Voucher] = []

    payroll_voucher_postings = [
        Posting(date=pay_date, account=acct(5000), amount=round(brutto_total, 2), department=None),
        Posting(date=pay_date, account=acct(2710), amount=-round(netto_total, 2)),
    ]
    if skattetrekk_total:
        payroll_voucher_postings.append(
            Posting(date=pay_date, account=acct(2740), amount=-round(skattetrekk_total, 2))
        )
    payroll_voucher = Voucher(
        date=pay_date,
        description=f"Lønnskjøring {month_label}",
        voucherType=VoucherType.SALARY,
        postings=payroll_voucher_postings,
    )
    assert_voucher_valid(payroll_voucher)
    vouchers.append(payroll_voucher)

    aga_voucher = Voucher(
        date=pay_date,
        description=f"Arbeidsgiveravgift {month_label}",
        voucherType=VoucherType.SALARY,
        postings=[
            Posting(date=pay_date, account=acct(5400), amount=round(aga_total, 2)),
            Posting(date=pay_date, account=acct(2700), amount=-round(aga_total, 2)),
        ],
    )
    assert_voucher_valid(aga_voucher)
    vouchers.append(aga_voucher)

    return transaction, vouchers
