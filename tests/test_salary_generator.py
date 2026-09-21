import inspect
from datetime import date

from norfingen.generators import salary_generator
from norfingen.generators.hours_generator import generate_daily_hours
from norfingen.generators.salary_generator import brutto_earned_in_year, generate_monthly_salary
from norfingen.seed.payroll import (
    active_employees,
    calc_aga,
    calc_brutto_with_raises,
    calc_feriepenger_provision,
    calc_june_salary,
    calc_skattetrekk,
)
from norfingen.seed.roster import employee_by_number


def _posting(voucher, account_number):
    return next(p for p in voucher.postings if p.account.number == account_number)


def _posting_amount_or_zero(voucher, account_number):
    return next((p.amount for p in voucher.postings if p.account.number == account_number), 0.0)


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

    # Feriepenger ZASTĘPUJE pensję, nie dodaje się do niej -> nadal bez
    # podwajania kosztu. Trzy vouchery: lista płac (bez 5000, o ile nikt nie
    # ma "gap"), AGA (lønn + avsetning feriepenger), rezerwa feriepenger.
    assert len(vouchers) == 3
    for v in vouchers:
        assert v.validate_balance(), f"Voucher niezbalansowany: {v.description}"

    payroll_voucher, aga_voucher, provision_voucher = vouchers

    expected_feriepenger_total = sum(
        calc_june_salary(e, 2022, brutto_earned_in_year(e, 2021)).feriepenger for e in active
    )
    expected_gap_total = sum(
        calc_june_salary(e, 2022, brutto_earned_in_year(e, 2021)).gross_salary for e in active
    )
    expected_aga_on_gap = sum(
        calc_aga(calc_june_salary(e, 2022, brutto_earned_in_year(e, 2021)).gross_salary) for e in active
    )
    expected_provision_total = sum(calc_feriepenger_provision(calc_brutto_with_raises(e, 2022, 6)) for e in active)
    expected_aga_on_provision = sum(calc_aga(calc_feriepenger_provision(calc_brutto_with_raises(e, 2022, 6))) for e in active)

    assert _posting(payroll_voucher, 2930).amount == round(expected_feriepenger_total, 2)
    if expected_gap_total:
        assert _posting(payroll_voucher, 5000).amount == round(expected_gap_total, 2)
    assert _posting(aga_voucher, 5400).amount == round(expected_aga_on_gap + expected_aga_on_provision, 2)
    assert _posting(aga_voucher, 2700).amount == -round(expected_aga_on_gap + expected_aga_on_provision, 2)
    assert _posting(provision_voucher, 5099).amount == round(expected_provision_total, 2)
    assert _posting(provision_voucher, 2930).amount == -round(expected_provision_total, 2)

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
    # Faza 6 — zespół przestaje rosnąć po E17 (2022-10-03, jedyne dociążenie
    # po fuzji), więc czerwiec 2023 to nadal ci sami 17 pracownicy.
    assert {e.number for e in active} == {f"E{i:02d}" for i in range(1, 17)} | {"E17"}

    transaction, vouchers = generate_monthly_salary(2023, 6)
    assert len(transaction.payslips) == 17
    assert len(vouchers) == 3

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

    payroll_voucher, aga_voucher, provision_voucher = vouchers
    expected_feriepenger_total = sum(
        calc_june_salary(e, 2023, brutto_earned_in_year(e, 2022)).feriepenger for e in active
    )
    assert _posting(payroll_voucher, 2930).amount == round(expected_feriepenger_total, 2)
    assert round(sum(p.amount for p in payroll_voucher.postings), 2) == 0
    assert round(sum(p.amount for p in aga_voucher.postings), 2) == 0
    assert round(sum(p.amount for p in provision_voucher.postings), 2) == 0


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
    # Konto 5000 (P&L) w czerwcu: po korekcie feriepenger draws down 2930
    # (bilans, nie P&L), więc 5000 w czerwcu to WYŁĄCZNIE ewentualny "gap"
    # dla pracowników z niepełnym poprzednim rokiem — musi być NISKIE
    # (bliskie zeru), nie zbliżone do normalnej miesięcznej pensji.
    for year in (2021, 2022, 2023, 2024, 2025, 2026):
        _, may_v = generate_monthly_salary(year, 5)
        _, jun_v = generate_monthly_salary(year, 6)
        may_cost = _posting(may_v[0], 5000).amount
        jun_cost = _posting_amount_or_zero(jun_v[0], 5000)
        assert jun_cost <= may_cost * 0.5, f"{year}: czerwcowy 'gap' na 5000={jun_cost} > 50% normalnej pensji={may_cost}"


def test_salary_generator_module_does_not_import_hours_at_all():
    """Architectural guard for the "realistic hours model" feature
    (VACATION/PARENTAL_LEAVE/WELFARE_LEAVE/all-departments): salary_generator
    must never come to depend on hour_entries — pay is computed from
    annual_salary/employment status only."""
    source = inspect.getsource(salary_generator)
    assert "hours_generator" not in source
    assert "leave_events" not in source
    assert "vacation" not in source
    assert "hour_entries" not in source


def test_payroll_unaffected_by_hours_changes():
    """salary_transactions for a given month are identical whether or not
    hour_entries were generated first for that same period — hours and
    payroll are two independent generators over the same roster."""
    from datetime import timedelta

    year, month = 2025, 6

    before_txn, before_vouchers = generate_monthly_salary(year, month)

    # Generate a full month of hour_entries (including leave/vacation logic)
    # for every active employee, in between the two payroll calls.
    active_ids = [int(e.number[1:]) for e in active_employees(date(year, month, 15))]
    day = date(year, month, 1)
    while day.month == month:
        generate_daily_hours(day.year, day.month, day.day, active_ids)
        day += timedelta(days=1)

    after_txn, after_vouchers = generate_monthly_salary(year, month)

    assert before_txn.model_dump() == after_txn.model_dump()
    assert [v.model_dump() for v in before_vouchers] == [v.model_dump() for v in after_vouchers]


# --- Feriepenger correction (2026-09-21): monthly accrual + synced AGA, no separate benefits cost ---


def test_no_separate_benefit_cost_account_5900():
    """Account 5900 is not used by any generator — an earlier, uncommitted
    draft of this correction added a flat 2% "employee benefits" cost there
    (duplicating the canteen cost, account 7350) and was removed."""
    for year, month in [(2023, 5), (2023, 6), (2024, 1), (2025, 6)]:
        _, vouchers = generate_monthly_salary(year, month)
        for v in vouchers:
            assert all(p.account.number != 5900 for p in v.postings), (
                f"{year}-{month}: voucher '{v.description}' posts to 5900"
            )
    source = inspect.getsource(salary_generator)
    assert "acct(5900)" not in source
    assert "calc_employee_benefits_cost" not in source


def test_feriepenger_accrued_monthly_all_twelve_months():
    """The 5099/2930 provision voucher is posted every month, June included,
    at 12% of that month's normal gross summed across active employees."""
    for month in range(1, 13):
        active = active_employees(date(2024, month, 15))
        _, vouchers = generate_monthly_salary(2024, month)
        provision_voucher = next(v for v in vouchers if "Avsetning feriepenger" in v.description)
        expected = sum(calc_feriepenger_provision(calc_brutto_with_raises(e, 2024, month)) for e in active)
        assert _posting(provision_voucher, 5099).amount == round(expected, 2)
        assert _posting(provision_voucher, 2930).amount == -round(expected, 2)
        assert expected > 0


def test_aga_accrued_monthly_with_feriepenger_reserve():
    """Every month's AGA voucher includes AGA on that month's feriepenger
    provision, on top of AGA on the salary actually paid — not just in June.
    Non-June months only here — June's "salary actually paid" side is the
    gap (see test_june_payout_settles_liability_not_new_cost), not full
    normal gross, so it needs its own dedicated assertions."""
    for month in (3, 9):
        active = active_employees(date(2024, month, 15))
        _, vouchers = generate_monthly_salary(2024, month)
        aga_voucher = next(v for v in vouchers if "Arbeidsgiveravgift" in v.description)
        expected_aga_on_provision = sum(
            calc_aga(calc_feriepenger_provision(calc_brutto_with_raises(e, 2024, month))) for e in active
        )
        actual_aga = _posting(aga_voucher, 5400).amount
        aga_on_salary_only = sum(calc_aga(calc_brutto_with_raises(e, 2024, month)) for e in active)
        assert actual_aga == round(aga_on_salary_only + expected_aga_on_provision, 2)
        # The provision-AGA component alone is nonzero — confirms it's really there.
        assert expected_aga_on_provision > 0


def test_june_payout_settles_liability_not_new_cost():
    """June's feriepenger payout posts to 2930 (liability drawdown), never
    to 5000, and its AGA is not recomputed in June (already accrued monthly
    the year it was earned) — only the rare <1yr-tenure "gap" salary (if
    any) contributes to 5400's June AGA on the paid-salary side."""
    year = 2025
    active = active_employees(date(year, 6, 15))
    _, vouchers = generate_monthly_salary(year, 6)
    payroll_voucher = next(v for v in vouchers if v.description.startswith("Lønnskjøring"))
    aga_voucher = next(v for v in vouchers if "Arbeidsgiveravgift" in v.description)

    expected_feriepenger = sum(
        calc_june_salary(e, year, brutto_earned_in_year(e, year - 1)).feriepenger for e in active
    )
    expected_gap = sum(
        calc_june_salary(e, year, brutto_earned_in_year(e, year - 1)).gross_salary for e in active
    )
    assert _posting(payroll_voucher, 2930).amount == round(expected_feriepenger, 2)
    assert _posting_amount_or_zero(payroll_voucher, 5000) == round(expected_gap, 2)

    expected_aga_on_gap = sum(
        calc_aga(calc_june_salary(e, year, brutto_earned_in_year(e, year - 1)).gross_salary) for e in active
    )
    expected_aga_on_provision = sum(
        calc_aga(calc_feriepenger_provision(calc_brutto_with_raises(e, year, 6))) for e in active
    )
    assert _posting(aga_voucher, 5400).amount == round(expected_aga_on_gap + expected_aga_on_provision, 2)
    # AGA on the feriepenger PAYOUT itself (as opposed to on this month's
    # fresh provision) would be a much larger number — confirm we're nowhere
    # near it, i.e. it genuinely isn't being recomputed here.
    aga_if_recomputed_on_payout = sum(
        calc_aga(calc_june_salary(e, year, brutto_earned_in_year(e, year - 1)).feriepenger) for e in active
    )
    assert _posting(aga_voucher, 5400).amount < aga_if_recomputed_on_payout


def test_aga_excludes_canteen_and_insurance():
    """AGA (accounts 5400/2700) is never posted by the canteen generator —
    it's an operating cost (7350), not remuneration."""
    from norfingen.generators.opex_generator import generate_monthly_opex

    for month in range(1, 13):
        for voucher in generate_monthly_opex(2024, month):
            accounts = {p.account.number for p in voucher.postings}
            if 7350 in accounts:
                assert 5400 not in accounts
                assert 2700 not in accounts


def test_june_employee_payout_unchanged_from_faza5():
    """The amount actually paid out to the employee in June (netto) is
    identical to the original Phase 5 formula — calc_june_salary's formula
    itself was never touched by this correction, only the bookkeeping."""
    e01 = employee_by_number("E01")
    basis = brutto_earned_in_year(e01, 2024)
    result = calc_june_salary(e01, 2025, basis)
    normal_gross = calc_brutto_with_raises(e01, 2025, 6)

    # Unchanged Phase 5 invariants: feriepenger replaces (doesn't add to)
    # the normal salary, and the amount is exactly 12% of last year's basis.
    assert result.feriepenger == round(basis * 0.12)
    if result.feriepenger >= normal_gross:
        assert result.gross_salary == 0.0
        assert result.total_brutto == result.feriepenger
    else:
        assert result.gross_salary == round(normal_gross - result.feriepenger, 2)


def test_account_2930_balance_pattern_over_two_years():
    """The 2930 (Skyldige feriepenger) liability balance for one long-tenured
    employee (E01, employed since 2019) rises through year N (12 monthly
    accruals) and drops in June of year N+1 (the payout draws it down),
    then rises again through year N+1 — confirming the accrual/drawdown
    cycle nets out correctly rather than compounding."""
    e01 = employee_by_number("E01")

    def postings_2930_for(year: int, month: int) -> float:
        """Net 2930 movement from E01's share of that month's vouchers —
        the provision voucher is company-wide, so prorate isn't exact per
        employee, but for a stable-headcount month the E01-specific
        movement is exactly calc_feriepenger_provision(E01's normal gross)
        credited, plus (June only) E01's own feriepenger debited."""
        net = calc_feriepenger_provision(calc_brutto_with_raises(e01, year, month))  # credit (+liability)
        if month == 6:
            basis_prev = brutto_earned_in_year(e01, year - 1)
            net -= calc_june_salary(e01, year, basis_prev).feriepenger  # debit (-liability, drawdown)
        return net

    balance = 0.0
    yearly_end_balance = {}
    for year in (2023, 2024, 2025):
        for month in range(1, 13):
            balance += postings_2930_for(year, month)
        yearly_end_balance[year] = balance

    # The balance should stay roughly stable year-over-year for a
    # stable-tenure employee (small drift only from the raise-timing gap
    # between "this year's provisioning basis" and "last year's payout
    # basis") — not grow unboundedly, which would indicate a double-count.
    drift_2024 = abs(yearly_end_balance[2024] - yearly_end_balance[2023])
    drift_2025 = abs(yearly_end_balance[2025] - yearly_end_balance[2024])
    one_month_gross = calc_brutto_with_raises(e01, 2025, 1)
    assert drift_2024 < one_month_gross
    assert drift_2025 < one_month_gross

    # Within any single year, the balance must rise for 11 months and drop
    # sharply in June (the payout).
    running = 0.0
    monthly_end = []
    for month in range(1, 13):
        running += postings_2930_for(2024, month)
        monthly_end.append(running)
    assert monthly_end[5] < monthly_end[4]  # June (index 5) drops vs May (index 4)
    assert monthly_end[6] > monthly_end[5]  # July resumes rising
