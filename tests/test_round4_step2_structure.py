"""Round 4, step 2: depreciation, mandatory pension (OTP) and corporate income tax. Pure functions, no database."""

from datetime import date, timedelta

import pytest

from norfingen.generators import depreciation as dep
from norfingen.generators import income_tax as tax
from norfingen.generators import pension
from norfingen.generators.salary_generator import generate_monthly_salary
from norfingen.generators.voucher import VoucherType
from norfingen.seed.payroll import last_working_day
from norfingen.seed.workdays import is_working_day


def _by_account(voucher):
    return {p.account.number: p.amount for p in voucher.postings}


# ------------------------------------------------------------------ depreciation
def test_a_purchase_after_the_last_working_day_of_its_month_starts_one_month_later():
    assert dep.first_depreciation_month(date(2024, 8, 12)) == (2024, 8)
    assert dep.first_depreciation_month(date(2024, 8, 30)) == (2024, 8)      # Friday = the last working day
    assert dep.first_depreciation_month(date(2024, 8, 31)) == (2024, 9)      # Saturday, after it
    assert dep.first_depreciation_month(date(2024, 12, 31)) == (2024, 12)    # a Tuesday: the last working day itself


@pytest.mark.parametrize("cost,added", [(150_000.0, date(2024, 8, 12)), (89_999.99, date(2021, 3, 31)), (30_000.01, date(2023, 12, 30))])
def test_an_asset_is_written_down_to_exactly_zero_over_60_months(cost, added):
    start_year, start_month = dep.first_depreciation_month(added)
    total, months = 0.0, 0
    for k in range(80):                                                       # far beyond the useful life
        year, month = start_year + (start_month - 1 + k) // 12, (start_month - 1 + k) % 12 + 1
        charge = dep.monthly_charge(cost, added, year, month)
        total = round(total + charge, 2)
        months += charge > 0
    assert months == 60 and total == round(cost, 2)
    assert dep.monthly_charge(cost, added, start_year, start_month) > 0
    before = (start_year, start_month - 1) if start_month > 1 else (start_year - 1, 12)
    assert dep.monthly_charge(cost, added, *before) == 0                      # nothing before the first month


def test_the_depreciation_voucher_is_booked_on_the_last_working_day_only():
    additions = [(date(2024, 1, 10), 120_000.0)]
    on = last_working_day(2024, 3)
    voucher = dep.depreciation_voucher(on, additions)
    assert voucher.voucherType == VoucherType.ADJUSTMENT and voucher.date == on
    assert _by_account(voucher) == {6015: 2000.0, 1209: -2000.0}
    assert voucher.description == "Avskrivning maskiner og anlegg 2024-03"
    assert dep.depreciation_voucher(date(2024, 3, 15), additions) is None
    assert dep.depreciation_voucher(last_working_day(2023, 12), additions) is None   # before the purchase: nothing to write down


def test_an_asset_dated_after_the_vouchers_own_date_is_not_in_that_voucher():
    on = last_working_day(2024, 8)                                            # Friday 2024-08-30
    assert dep.depreciation_for_month([(date(2024, 8, 31), 60_000.0)], 2024, 8, on) == 0.0
    assert dep.depreciation_for_month([(date(2024, 8, 29), 60_000.0)], 2024, 8, on) == 1000.0


def test_five_years_of_depreciation_of_several_assets_reconciles_to_their_cost():
    additions = [(date(2020, 2, 3), 45_000.0), (date(2020, 2, 28), 99_999.99), (date(2021, 11, 30), 31_234.56)]
    booked = 0.0
    for year in range(2020, 2028):
        for month in range(1, 13):
            voucher = dep.depreciation_voucher(last_working_day(year, month), additions)
            booked = round(booked + (voucher.postings[0].amount if voucher else 0.0), 2)
    assert booked == round(sum(c for _, c in additions), 2)


# ------------------------------------------------------------------ pension (OTP)
def test_otp_is_two_percent_of_the_gross_pay_of_the_month():
    txn, _ = generate_monthly_salary(2024, 1)
    base = pension.otp_base(txn)
    assert base > 0
    voucher = pension.otp_voucher(txn.date, base)
    assert voucher.voucherType == VoucherType.ADJUSTMENT
    assert _by_account(voucher) == {5420: round(base * 0.02, 2), 2950: -round(base * 0.02, 2)}
    assert voucher.description == "Obligatorisk tjenestepensjon (OTP) 2024-01"
    assert pension.otp_voucher(txn.date, 0.0) is None


def test_june_otp_includes_the_holiday_pay_paid_out():
    june, _ = generate_monthly_salary(2024, 6)
    may, _ = generate_monthly_salary(2024, 5)
    assert pension.otp_base(june) > pension.otp_base(may)                      # feriepenger (260) are part of the gross


@pytest.mark.parametrize("on,label", [(date(2026, 1, 15), "2025-Q4"), (date(2026, 4, 15), "2026-Q1"),
                                      (date(2026, 7, 15), "2026-Q2"), (date(2026, 10, 15), "2026-Q3"),
                                      (date(2023, 7, 17), "2023-Q2")])          # 15 July 2023 is a Saturday
def test_the_quarter_is_paid_on_the_15th_moved_to_a_working_day(on, label):
    start, end, got = pension.quarter_paid_on(on)
    assert got == label and is_working_day(on) and (end + timedelta(days=1)).month == on.month and (end - start).days >= 89


def test_no_other_day_pays_the_pension():
    assert all(pension.quarter_paid_on(date(2026, m, d)) is None
               for m in range(1, 13) for d in (1, 14, 16, 20, 28) if not (m == 1 and d == 16))
    assert pension.quarter_paid_on(date(2026, 2, 15)) is None and pension.quarter_paid_on(date(2026, 5, 15)) is None


def test_the_payment_clears_the_liability():
    voucher = pension.otp_payment_voucher(date(2026, 7, 15), 123_456.78)
    assert voucher.voucherType == VoucherType.BANK
    assert _by_account(voucher) == {2950: 123_456.78, 1910: -123_456.78}
    assert voucher.description == "Innbetaling pensjonspremie OTP 2026-Q2"
    assert pension.otp_payment_voucher(date(2026, 7, 16), 100.0) is None and pension.otp_payment_voucher(date(2026, 7, 15), 0.0) is None


# ------------------------------------------------------------------ income tax
RESULTS = {2019: -3_000_000.0, 2020: 2_000_000.0, 2021: 2_500_000.0, 2022: 1_000_000.0}


def test_a_loss_is_carried_forward_and_used_up_by_the_next_profits():
    assert tax.loss_carried_forward(2019, RESULTS) == 0.0
    assert tax.loss_carried_forward(2020, RESULTS) == 3_000_000.0
    assert tax.loss_carried_forward(2021, RESULTS) == 1_000_000.0             # 2020's profit used 2 mln of the 3 mln
    assert tax.loss_carried_forward(2022, RESULTS) == 0.0
    assert tax.tax_for_year(2019, RESULTS) == 0.0 and tax.tax_for_year(2020, RESULTS) == 0.0
    assert tax.tax_for_year(2021, RESULTS) == round(0.22 * 1_500_000.0, 2)    # 2.5 mln - the remaining 1 mln
    assert tax.tax_for_year(2022, RESULTS) == round(0.22 * 1_000_000.0, 2)


def test_tax_is_never_negative_and_a_later_loss_does_not_refund_an_earlier_tax():
    results = {2020: 1_000_000.0, 2021: -5_000_000.0, 2022: 2_000_000.0}
    assert tax.tax_for_year(2020, results) == 220_000.0
    assert tax.tax_for_year(2021, results) == 0.0
    assert tax.tax_for_year(2022, results) == 0.0                              # 2021's 5 mln loss covers 2022's 2 mln profit
    assert tax.loss_carried_forward(2023, results) == 3_000_000.0
    assert all(tax.tax_for_year(y, results) >= 0 for y in range(2019, 2025))


def test_the_tax_voucher_is_booked_on_31_december_only():
    voucher = tax.tax_voucher(date(2021, 12, 31), RESULTS)
    assert voucher.voucherType == VoucherType.ADJUSTMENT
    assert _by_account(voucher) == {8300: 330_000.0, 2500: -330_000.0}
    assert voucher.description == "Skattekostnad 2021 (22 % av skattbart resultat)"
    assert tax.tax_voucher(date(2021, 12, 30), RESULTS) is None and tax.tax_voucher(date(2021, 11, 30), RESULTS) is None
    assert tax.tax_voucher(date(2020, 12, 31), RESULTS) is None and tax.tax_voucher(date(2019, 12, 31), RESULTS) is None


def test_the_advance_tax_is_two_equal_instalments_that_add_up_to_the_cent():
    results = {2025: 100_000.05}                                              # tax 22 000.01, an odd cent: the halves differ by 1 cent
    total = tax.tax_for_year(2025, results)
    first_day, second_day = tax.instalment_dates(2026)
    assert first_day == date(2026, 2, 16) and second_day == date(2026, 4, 15)   # 15 Feb 2026 is a Sunday
    first = tax.advance_tax_payment_voucher(first_day, results)
    second = tax.advance_tax_payment_voucher(second_day, results)
    assert first.voucherType == VoucherType.BANK and first.description == "Forskuddsskatt 2025 termin 1"
    assert second.description == "Forskuddsskatt 2025 termin 2"
    assert round(_by_account(first)[2500] + _by_account(second)[2500], 2) == total
    assert total == 22_000.01 and round(_by_account(second)[2500] - _by_account(first)[2500], 2) == 0.01
    assert _by_account(first)[1910] == -_by_account(first)[2500]
    assert tax.advance_tax_payment_voucher(date(2026, 3, 16), results) is None


def test_the_instalment_does_not_change_when_the_day_is_run_again():
    """The instalment comes from the year's tax, not from the balance of 2500: the first run has already paid half."""
    results = {2025: 4_000_000.0}
    a = tax.advance_tax_payment_voucher(tax.instalment_dates(2026)[0], results)
    b = tax.advance_tax_payment_voucher(tax.instalment_dates(2026)[0], dict(results))
    assert _by_account(a) == _by_account(b) == {2500: 440_000.0, 1910: -440_000.0}


def test_a_year_without_taxable_profit_has_no_payment():
    assert tax.advance_tax_payment_voucher(tax.instalment_dates(2021)[0], RESULTS) is None   # 2020: no tax
    assert tax.advance_tax_payment_voucher(tax.instalment_dates(2020)[1], RESULTS) is None   # 2019: a loss
