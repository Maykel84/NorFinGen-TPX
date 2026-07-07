from datetime import date

from norfingen.generators.salary_generator import brutto_earned_in_year, generate_monthly_salary
from norfingen.seed.payroll import (
    active_employees,
    calc_aga,
    calc_brutto_with_raises,
    calc_june_salary,
    calc_skattetrekk,
)
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

    # Feriepenger ZASTĘPUJE pensję, nie dodaje się do niej -> tylko 2 vouchery
    # (lista płac + AGA), tak jak w każdym innym miesiącu — bez podwajania kosztu.
    assert len(vouchers) == 2
    for v in vouchers:
        assert v.validate_balance(), f"Voucher niezbalansowany: {v.description}"

    payroll_voucher, aga_voucher = vouchers

    expected_total_brutto = sum(
        calc_june_salary(e, 2022, brutto_earned_in_year(e, 2021)).total_brutto for e in active
    )
    expected_aga_total = sum(
        calc_aga(calc_june_salary(e, 2022, brutto_earned_in_year(e, 2021)).total_brutto) for e in active
    )

    assert _posting(payroll_voucher, 5000).amount == round(expected_total_brutto, 2)
    assert _posting(aga_voucher, 5400).amount == round(expected_aga_total, 2)
    assert _posting(aga_voucher, 2700).amount == -round(expected_aga_total, 2)

    # E09/E10 startowali 2021-06-01 -> aktywni 7 miesięcy w 2021 (cze-gru), nie 12.
    # Bez podwyżki (pierwsza dopiero w lipcu 2022 — rok po zatrudnieniu).
    e09 = employee_by_number("E09")
    expected_e09_2021 = sum(calc_brutto_with_raises(e09, 2021, m) for m in range(6, 13))
    assert brutto_earned_in_year(e09, 2021) == expected_e09_2021

    # E01-E06 (założenie 2019) aktywni cały 2021 -> 12 miesięcy, z jedną podwyżką
    # w lipcu 2020 (już aktywna cały 2021) i drugą w lipcu 2021 (od H2).
    e01 = employee_by_number("E01")
    expected_e01_2021 = sum(calc_brutto_with_raises(e01, 2021, m) for m in range(1, 13))
    assert brutto_earned_in_year(e01, 2021) == expected_e01_2021
    # H2 2021 wyższe brutto niż H1 -> podwyżka lipcowa faktycznie zadziałała.
    assert calc_brutto_with_raises(e01, 2021, 7) > calc_brutto_with_raises(e01, 2021, 6)


def test_june_2023():
    on_date = date(2023, 6, 1)
    active = active_employees(on_date)
    # 16 od fuzji (2022-09) + E17 (2022-10-15) + E18 (2022-12-14) + E19
    # (2023-02-12) + E20 (2023-04-13) = 20.
    assert {e.number for e in active} == {f"E{i:02d}" for i in range(1, 17)} | {"E17", "E18", "E19", "E20"}

    transaction, vouchers = generate_monthly_salary(2023, 6)
    assert len(transaction.payslips) == 20
    assert len(vouchers) == 2

    for v in vouchers:
        assert v.validate_balance(), f"Voucher niezbalansowany: {v.description}"

    # E11-E16 (merger 2022-09-01) aktywni tylko 4 miesiące w 2022 (wrz-gru), nie 12.
    # Bez podwyżki (pierwsza dopiero w lipcu 2023).
    e11 = employee_by_number("E11")
    expected_e11_2022 = sum(calc_brutto_with_raises(e11, 2022, m) for m in range(9, 13))
    assert brutto_earned_in_year(e11, 2022) == expected_e11_2022

    # E01-E06 aktywni cały 2022 -> 12 miesięcy, z podwyżkami skumulowanymi od 2020/2021.
    e01 = employee_by_number("E01")
    expected_e01_2022 = sum(calc_brutto_with_raises(e01, 2022, m) for m in range(1, 13))
    assert brutto_earned_in_year(e01, 2022) == expected_e01_2022

    payroll_voucher, aga_voucher = vouchers
    expected_total_brutto = sum(
        calc_june_salary(e, 2023, brutto_earned_in_year(e, 2022)).total_brutto for e in active
    )
    assert _posting(payroll_voucher, 5000).amount == round(expected_total_brutto, 2)
    assert round(sum(p.amount for p in payroll_voucher.postings), 2) == 0
    assert round(sum(p.amount for p in aga_voucher.postings), 2) == 0


def test_june_salary_replaces_not_doubles_regular_pay():
    # Pracownik z długim stażem (feriepenger z pełnego roku poprzedniego >=
    # bieżąca pensja) -> normalna pensja czerwcowa = 0, brak podwojenia kosztu.
    e01 = employee_by_number("E01")
    basis_2021 = brutto_earned_in_year(e01, 2021)
    result = calc_june_salary(e01, 2022, basis_2021)

    normal_gross = calc_brutto_with_raises(e01, 2022, 6)
    assert result.feriepenger >= normal_gross
    assert result.gross_salary == 0.0
    assert result.total_brutto == result.feriepenger
    assert result.tax_on_salary == 0.0
    # Koszt czerwca (total_brutto) NIE jest sumą pensja+feriepenger — to feriepenger
    # SAMO w sobie, bliskie (nie znacznie wyższe od) normalnej pensji.
    assert result.total_brutto < normal_gross + result.feriepenger


def test_june_salary_gap_for_short_tenure_employee():
    # E09 wystartował 2021-06-01 -> podstawa feriepenger za 2021 to tylko 7
    # miesięcy (cze-gru), więc feriepenger < pełna bieżąca pensja -> dopłata.
    e09 = employee_by_number("E09")
    basis_2021 = brutto_earned_in_year(e09, 2021)
    result = calc_june_salary(e09, 2022, basis_2021)

    normal_gross = calc_brutto_with_raises(e09, 2022, 6)
    assert result.feriepenger < normal_gross
    assert result.gross_salary == round(normal_gross - result.feriepenger, 2)
    assert result.total_brutto == round(result.feriepenger + result.gross_salary, 2)
    assert result.tax_on_salary == calc_skattetrekk(result.gross_salary)
    assert result.tax_on_salary > 0


def test_june_no_double_cost():
    # Koszt czerwca (konto 5000, ex-AGA) nie powinien przekraczać 150% średniej
    # z sąsiednich miesięcy — przed naprawą feriepenger był to koszt narastający
    # bez ograniczenia (pełna pensja + pełne feriepenger).
    for year in (2021, 2022, 2023, 2024, 2025, 2026):
        _, may_v = generate_monthly_salary(year, 5)
        _, jun_v = generate_monthly_salary(year, 6)
        _, jul_v = generate_monthly_salary(year, 7)
        may_cost = _posting(may_v[0], 5000).amount
        jun_cost = _posting(jun_v[0], 5000).amount
        jul_cost = _posting(jul_v[0], 5000).amount
        neighbor_avg = (may_cost + jul_cost) / 2
        assert jun_cost <= neighbor_avg * 1.5, f"{year}: czerwiec={jun_cost} > 150% sąsiadów={neighbor_avg}"
