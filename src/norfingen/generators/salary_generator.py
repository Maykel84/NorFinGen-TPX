"""Monthly payroll run generator (Layer 2 + Layer 3).

Every month, three vouchers:
1. Payroll: DR 5000 (normal/gap salary) + DR 2930 (June only — feriepenger
   drawdown) / CR 2710 / CR 2740.
2. AGA: DR 5400 / CR 2700 — TWO components, both accrued in the year
   EARNED (opptjeningsprinsippet): AGA on the actual salary paid this month
   (excluding, in June, the feriepenger portion — its AGA was already
   recognized the previous year via #3) + AGA on this month's feriepenger
   provision (calc_aga(calc_feriepenger_provision(...)) — "det samme
   gjelder arbeidsgiveravgift av feriepenger").
3. Feriepenger provision (2026-09-21 correction): DR 5099 / CR 2930 — 12% of
   that month's NORMAL gross (calc_feriepenger_provision), accrued every
   month including June, funding NEXT year's payout.

June — feriepenger REPLACES the normal salary, it is not added on top of it
(see norfingen.seed.payroll.calc_june_salary; still 12% of the PRIOR year's
gross, unchanged formula — the amount actually paid to the employee is
IDENTICAL to before this correction). Normally (feriepenger >= current
salary) the normal June salary = 0, that month's entire gross amount is
untaxed feriepenger. For employees with <1 year of tenure the difference
is paid out as a regular, taxed salary.

Feriepenger bookkeeping (2026-09-21 correction — see payroll.py's module
docstring for the full rationale): the feriepenger portion of June's payout
no longer hits account 5000 a second time — it draws down the SAME
liability (2930) that voucher #3 built up over the preceding 12 months, and
its AGA is not recomputed in June either (also already accrued monthly the
year before). Recreating the "pay salary AND feriepenger, double the cost"
bug this project already fixed once (via a second, uncoordinated
mechanism — for BOTH the feriepenger amount and separately its AGA) was the
specific risk checked against before writing this.

A prior, uncommitted draft of this same correction also added a flat 2%
"employee benefits" cost (account 5900) on top — removed, it duplicated the
existing canteen cost (opex_generator.py, account 7350).

The feriepenger basis per employee = the sum of
calc_brutto_with_raises(e, year, month) for the months the employee was
active in the previous year (see brutto_earned_in_year) — critical for
merger-phase employees (E11-E16, active since 2022-09): their 2022 basis is
4 months, not 12.

Raises: +3% per year in July, the first one in the year after hiring (see
norfingen.seed.payroll.calc_brutto_with_raises) — applied both to the
current month's gross pay and to the previous year's feriepenger basis.
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
    calc_feriepenger_provision,
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
    """The total gross earned by an employee in a given calendar year —
    respects startDate (an employee not yet active before their start has a
    basis of 0 for those months). Phase 5 — compared against
    first_working_day_of_month(), NOT date(year, month, 1): since
    EMPLOYEES.start_date is now always the first working day of the month
    (which can be the 2nd or 3rd calendar day if the 1st falls on a
    weekend), comparing against a fixed calendar day 1 would wrongly
    exclude an employee from their own start month (e.g.
    start_date=2022-10-03 > date(2022,10,1))."""
    return sum(
        calc_brutto_with_raises(employee, year, month)
        for month in range(1, 13)
        if employee.start_date <= first_working_day_of_month(year, month)
    )


def generate_monthly_salary(year: int, month: int) -> tuple[SalaryTransaction, list[Voucher]]:
    # first_working_day_of_month(), not date(year, month, 1) — see the
    # brutto_earned_in_year() docstring above, same reason.
    active = active_employees(first_working_day_of_month(year, month))
    pay_date = last_working_day(year, month)
    june = is_june(month)

    payslips: list[Payslip] = []
    salary_total = feriepenger_drawdown_total = 0.0  # DR 5000 / DR 2930 (June only)
    netto_total = skattetrekk_total = aga_total = 0.0
    provision_total = 0.0  # DR 5099, every month

    transaction = SalaryTransaction(date=pay_date, year=year, month=month)

    for employee in active:
        emp_ref = TripletexRef(id=numeric_id(employee.number))
        specifications = []
        # Always the "normal" entitled gross for this month — the base for
        # the feriepenger provision (and its AGA), regardless of whether
        # June's actual payout is swapped for feriepenger. Matches exactly
        # what brutto_earned_in_year() sums, so 12 months of provisioning
        # equal calc_feriepenger()'s basis for next year.
        normal_gross = calc_brutto_with_raises(employee, year, month)
        feriepenger_provision = calc_feriepenger_provision(normal_gross)

        if june:
            basis_prev_year = brutto_earned_in_year(employee, year - 1)
            june_salary = calc_june_salary(employee, year, basis_prev_year)
            skattetrekk = june_salary.tax_on_salary
            netto = june_salary.total_brutto - skattetrekk

            salary_total += june_salary.gross_salary
            feriepenger_drawdown_total += june_salary.feriepenger
            # AGA only on the gap (regular, currently-earned salary) —
            # NOT on the feriepenger portion, whose AGA was already accrued
            # monthly the year it was earned (see voucher #2/#3 above).
            aga_this_employee = calc_aga(june_salary.gross_salary)

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
            brutto = normal_gross
            skattetrekk = calc_skattetrekk(brutto)
            netto = calc_netto(brutto, skattetrekk)
            salary_total += brutto
            aga_this_employee = calc_aga(brutto)
            specifications.append(
                SalarySpecification(wageType=WAGE_TYPE_FAST_LONN, description="Fast lønn", amount=brutto)
            )
            specifications.append(
                SalarySpecification(wageType=WAGE_TYPE_SKATTETREKK, description="Skattetrekk", amount=-skattetrekk)
            )

        # AGA on this month's feriepenger provision — accrued the same
        # month as the provision itself, per opptjeningsprinsippet
        # ("det samme gjelder arbeidsgiveravgift av feriepenger").
        aga_this_employee += calc_aga(feriepenger_provision)

        netto_total += netto
        skattetrekk_total += skattetrekk
        aga_total += aga_this_employee
        provision_total += feriepenger_provision

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

    payroll_voucher_postings = []
    if salary_total:
        payroll_voucher_postings.append(Posting(date=pay_date, account=acct(5000), amount=round(salary_total, 2)))
    if feriepenger_drawdown_total:
        payroll_voucher_postings.append(Posting(date=pay_date, account=acct(2930), amount=round(feriepenger_drawdown_total, 2)))
    payroll_voucher_postings.append(Posting(date=pay_date, account=acct(2710), amount=-round(netto_total, 2)))
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
        description=f"Arbeidsgiveravgift (lønn + avsetning feriepenger) {month_label}",
        voucherType=VoucherType.SALARY,
        postings=[
            Posting(date=pay_date, account=acct(5400), amount=round(aga_total, 2)),
            Posting(date=pay_date, account=acct(2700), amount=-round(aga_total, 2)),
        ],
    )
    assert_voucher_valid(aga_voucher)
    vouchers.append(aga_voucher)

    provision_voucher = Voucher(
        date=pay_date,
        description=f"Avsetning feriepenger {month_label}",
        voucherType=VoucherType.SALARY,
        postings=[
            Posting(date=pay_date, account=acct(5099), amount=round(provision_total, 2)),
            Posting(date=pay_date, account=acct(2930), amount=-round(provision_total, 2)),
        ],
    )
    assert_voucher_valid(provision_voucher)
    vouchers.append(provision_voucher)

    return transaction, vouchers
