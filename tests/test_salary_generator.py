from datetime import date

from norfingen.generators.salary_generator import brutto_earned_in_year, generate_monthly_salary
from norfingen.seed.payroll import active_employees, calc_aga, calc_brutto, calc_feriepenger
from norfingen.seed.roster import employee_by_number


def _posting(voucher, account_number):
    return next(p for p in voucher.postings if p.account.number == account_number)


def test_june_2022():
    on_date = date(2022, 6, 1)
    active = active_employees(on_date)
    # Bucket "2021-06 – 2022-08" z docs/norfingen_warstwa2_schemas.html (Zmienność
    # historyczna rosteru): E01-E10 (10 os.) — E09/E10 wystartowali 2021-06-01,
    # więc są już aktywni rok później w czerwcu 2022 (NIE E01-E08/8, jak można by
    # błędnie założyć patrząc tylko na fazę "growth1").
    assert {e.number for e in active} == {f"E{i:02d}" for i in range(1, 11)}

    transaction, vouchers = generate_monthly_salary(2022, 6)
    assert transaction.year == 2022
    assert transaction.month == 6
    assert len(transaction.payslips) == 10

    assert len(vouchers) == 4
    for v in vouchers:
        assert v.validate_balance(), f"Voucher niezbalansowany: {v.description}"

    feriepenger_voucher, aga_feriepenger_voucher = vouchers[2], vouchers[3]

    expected_feriepenger_total = sum(
        calc_feriepenger(brutto_earned_in_year(e, 2021)) for e in active
    )
    expected_aga_feriepenger_total = sum(
        calc_aga(calc_feriepenger(brutto_earned_in_year(e, 2021))) for e in active
    )

    assert _posting(feriepenger_voucher, 5000).amount == round(expected_feriepenger_total, 2)
    assert _posting(feriepenger_voucher, 2710).amount == -round(expected_feriepenger_total, 2)
    assert _posting(aga_feriepenger_voucher, 5400).amount == round(expected_aga_feriepenger_total, 2)
    assert _posting(aga_feriepenger_voucher, 2700).amount == -round(expected_aga_feriepenger_total, 2)

    # E09/E10 startowali 2021-06-01 -> aktywni 7 miesięcy w 2021 (cze-gru), nie 12.
    e09 = employee_by_number("E09")
    assert brutto_earned_in_year(e09, 2021) == calc_brutto(e09) * 7

    # E01-E06 (założenie 2019) aktywni cały 2021 -> 12 miesięcy.
    e01 = employee_by_number("E01")
    assert brutto_earned_in_year(e01, 2021) == calc_brutto(e01) * 12


def test_june_2023():
    on_date = date(2023, 6, 1)
    active = active_employees(on_date)
    # Bucket "2022-09 – dziś": pełny roster 16 osób.
    assert {e.number for e in active} == {f"E{i:02d}" for i in range(1, 17)}

    transaction, vouchers = generate_monthly_salary(2023, 6)
    assert len(transaction.payslips) == 16
    assert len(vouchers) == 4

    for v in vouchers:
        assert v.validate_balance(), f"Voucher niezbalansowany: {v.description}"

    # E11-E16 (merger 2022-09-01) aktywni tylko 4 miesiące w 2022 (wrz-gru), nie 12.
    e11 = employee_by_number("E11")
    assert brutto_earned_in_year(e11, 2022) == calc_brutto(e11) * 4

    # E01-E06 aktywni cały 2022 -> 12 miesięcy.
    e01 = employee_by_number("E01")
    assert brutto_earned_in_year(e01, 2022) == calc_brutto(e01) * 12

    feriepenger_voucher, aga_feriepenger_voucher = vouchers[2], vouchers[3]
    expected_feriepenger_total = sum(
        calc_feriepenger(brutto_earned_in_year(e, 2022)) for e in active
    )
    assert _posting(feriepenger_voucher, 5000).amount == round(expected_feriepenger_total, 2)
    assert round(sum(p.amount for p in feriepenger_voucher.postings), 2) == 0
    assert round(sum(p.amount for p in aga_feriepenger_voucher.postings), 2) == 0
