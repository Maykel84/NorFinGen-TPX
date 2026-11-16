"""Audit 2026-11-16, phase 3: share capital 500 000 + an owner loan of 3 500 000 NOK, serviced monthly.

Before, the books opened with 30 000 NOK and the bank (1910) was negative on 176 days, down to -2.8 mln NOK. The
loan is a pure function of the calendar, so history and the daily cron book identical vouchers."""
from datetime import date, timedelta

from norfingen.generators.backfill import FOUNDING_CAPITAL_AMOUNT, founding_capital_voucher
from norfingen.generators.owner_loan import (
    LOAN_FIRST_INSTALMENT,
    LOAN_INSTALMENTS,
    LOAN_PRINCIPAL,
    balance_at_month_start,
    interest_due,
    loan_drawdown_voucher,
    loan_service_voucher,
    principal_due,
)
from norfingen.seed.payroll import last_working_day


def _months(start=(2019, 1), end=(2027, 12)):
    y, m = start
    while (y, m) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def test_capital_and_loan_open_the_books_with_4_mln_in_the_bank():
    capital, loan = founding_capital_voucher(), loan_drawdown_voucher()
    assert FOUNDING_CAPITAL_AMOUNT == 500_000.0 and LOAN_PRINCIPAL == 3_500_000.0
    assert {p.account.number: p.amount for p in capital.postings} == {1910: 500_000.0, 2000: -500_000.0}
    assert {p.account.number: p.amount for p in loan.postings} == {1910: 3_500_000.0, 2290: -3_500_000.0}
    assert capital.date == loan.date == date(2019, 1, 2)


def test_interest_only_until_2020_then_60_equal_instalments_ending_at_exactly_zero():
    assert all(principal_due(2019, m) == 0.0 and principal_due(2020, m) == 0.0 for m in range(1, 13))
    assert LOAN_FIRST_INSTALMENT == (2021, 1) and LOAN_INSTALMENTS == 60
    paid = [principal_due(y, m) for y, m in _months()]
    assert sum(1 for x in paid if x) == 60 and round(sum(paid), 2) == LOAN_PRINCIPAL
    assert principal_due(2021, 1) == 58_333.33 and principal_due(2025, 12) == 58_333.53  # the cent remainder
    assert balance_at_month_start(2025, 12) == 58_333.53 and balance_at_month_start(2026, 1) == 0.0


def test_interest_is_5_percent_a_year_on_the_balance_at_the_start_of_the_month():
    assert interest_due(2019, 1) == round(3_500_000 * 0.05 / 12, 2) == 14_583.33
    assert interest_due(2021, 2) == round((3_500_000 - 58_333.33) * 0.05 / 12, 2)
    assert interest_due(2026, 1) == 0.0


def test_service_voucher_is_booked_on_the_last_working_day_and_balances():
    first = loan_service_voucher(last_working_day(2019, 1))
    assert {p.account.number: p.amount for p in first.postings} == {8150: 14_583.33, 1910: -14_583.33}
    with_principal = loan_service_voucher(last_working_day(2021, 1))
    posts = {p.account.number: p.amount for p in with_principal.postings}
    assert posts[2290] == 58_333.33 and posts[8150] == interest_due(2021, 1)
    assert round(sum(posts.values()), 2) == 0.0
    # any other day, before the founding and after the loan is repaid: nothing
    assert loan_service_voucher(date(2019, 1, 2)) is None
    assert loan_service_voucher(last_working_day(2026, 1)) is None


def test_exactly_one_service_voucher_per_month_over_the_whole_life_of_the_loan():
    days = [d for y, m in _months((2019, 1), (2025, 12))
            for d in [loan_service_voucher(last_working_day(y, m))] if d is not None]
    assert len(days) == 84  # 2019-01 .. 2025-12
    d, end, booked = date(2019, 1, 1), date(2026, 12, 31), 0
    while d <= end:
        booked += loan_service_voucher(d) is not None
        d += timedelta(days=1)
    assert booked == 84  # no other calendar day books one
    assert sum(p.amount for v in days for p in v.postings if p.account.number == 2290) == LOAN_PRINCIPAL
