"""Phase 5 (docs/SPEC_poprawki_ksiegowe.md): operating costs on realistic days, and the bi-monthly VAT settlement.

The amounts did not move (tests/test_golden_hash.py pins `opex_amounts` / `cogs_payable_amounts` as computed BEFORE the
change); only the day of each entry did. The VAT settlement moves the term's 2700 / 2710 balances to 2740 on the last day of
the term and pays (or refunds) the difference on the due date.
"""

import pytest
from datetime import date

from norfingen.generators.backfill import months_range
from norfingen.generators.bank_transaction_generator import generate_daily_bank_transactions
from norfingen.generators.opex_generator import generate_monthly_opex
from norfingen.generators.vat_settlement import (
    build_vat_payment,
    build_vat_settlement,
    payment_date_for,
    term_bounds,
    term_ending_on,
)
from norfingen.generators.voucher import BALANCE_TOLERANCE
from norfingen.models.bank_transaction import BankTransactionType
from norfingen.models.vat_settlement import VatSettlementStatus
from norfingen.seed.payroll import last_working_day
from norfingen.seed.workdays import is_working_day, previous_working_day

MONTHS = months_range(date(2019, 1, 1), date(2026, 12, 31))


def _opex():
    for year, month in MONTHS:
        for voucher in generate_monthly_opex(year, month):
            yield year, month, voucher


# --- cost dates ---------------------------------------------------------------------------------

def test_no_operating_cost_is_booked_on_a_weekend_or_outside_its_month():
    n = 0
    for year, month, v in _opex():
        assert is_working_day(v.date), (v.description, v.date)
        assert (v.date.year, v.date.month) == (year, month), (v.description, v.date)
        assert all(p.date == v.date for p in v.postings)
        n += 1
    assert n > 450


def test_each_kind_of_cost_lands_on_its_agreed_day():
    seen = set()
    for year, month, v in _opex():
        account = next(p.account.number for p in v.postings if p.amount > 0)
        if v.description.startswith(("Kantinetilskudd", "Kjøregodtgjørelse")) or account in (4291, 4292):
            assert v.date == last_working_day(year, month), v.description     # month end, with payroll
            seen.add("month_end")
        elif v.description.startswith("Representasjon"):
            assert 5 <= v.date.day <= 25, v.date
            seen.add("representation")
        elif v.description.startswith("Konferansereise"):
            assert 8 <= v.date.day <= 25, v.date
            seen.add("conference")
    assert seen == {"month_end", "representation", "conference"}


def test_representation_day_varies_between_months_but_is_reproducible():
    days = {}
    for year, month in MONTHS:
        for v in generate_monthly_opex(year, month):
            if v.description.startswith("Representasjon"):
                days[(year, month)] = v.date.day
    assert len(set(days.values())) > 8                       # not a fixed day in disguise
    again = {(y, m): next(v.date.day for v in generate_monthly_opex(y, m) if v.description.startswith("Representasjon"))
             for (y, m) in list(days)[:12]}
    assert all(again[k] == days[k] for k in again)


def test_previous_working_day():
    assert previous_working_day(date(2026, 10, 31)) == date(2026, 10, 30)   # Saturday -> Friday
    assert previous_working_day(date(2026, 11, 1)) == date(2026, 10, 30)    # Sunday -> Friday
    assert previous_working_day(date(2026, 10, 30)) == date(2026, 10, 30)


# --- terms and dates ----------------------------------------------------------------------------

def test_term_bounds_and_term_end_detection():
    assert term_bounds(2026, 2) == (date(2026, 3, 1), date(2026, 4, 30))
    assert term_bounds(2024, 1) == (date(2024, 1, 1), date(2024, 2, 29))      # leap year
    assert term_ending_on(date(2026, 4, 30)) == (2026, 2)
    assert term_ending_on(date(2026, 12, 31)) == (2026, 6)
    for not_end in (date(2026, 4, 29), date(2026, 5, 31), date(2026, 3, 31), date(2026, 1, 31)):
        assert term_ending_on(not_end) is None


@pytest.mark.parametrize("year,term,expected", [
    (2026, 1, date(2026, 4, 10)),    # Friday
    (2026, 2, date(2026, 6, 10)),    # Wednesday
    (2026, 3, date(2026, 8, 31)),    # Monday
    (2026, 4, date(2026, 10, 12)),   # 10 Oct is a Saturday -> Monday 12
    (2026, 5, date(2026, 12, 10)),   # Thursday
    (2026, 6, date(2027, 2, 10)),    # NEXT year, Wednesday
    (2024, 3, date(2024, 9, 2)),     # 31 Aug 2024 is a Saturday -> Monday 2 Sep
])
def test_payment_dates(year, term, expected):
    assert payment_date_for(year, term) == expected


# --- the settlement voucher ---------------------------------------------------------------------

def test_settlement_of_a_payable_term_zeroes_the_vat_accounts_and_credits_2740():
    voucher, settlement = build_vat_settlement(2026, 2, output_vat=1_989_194.06, input_vat=85_669.97)
    by_account = {p.account.number: p.amount for p in voucher.postings}
    assert by_account == {2700: 1_989_194.06, 2710: -85_669.97, 2740: -1_903_524.09}   # Dr 2700 / Cr 2710 / Cr 2740
    assert voucher.date == date(2026, 4, 30) and voucher.voucherType.value == "MANUAL"
    assert abs(sum(by_account.values())) <= BALANCE_TOLERANCE
    assert settlement.balance == 1_903_524.09 and settlement.status == VatSettlementStatus.UNPAID
    assert settlement.payment_date == date(2026, 6, 10) and settlement.period_end == date(2026, 4, 30)


def test_a_refund_term_debits_2740():
    voucher, settlement = build_vat_settlement(2019, 1, output_vat=0.0, input_vat=87_412.11)   # the company's first term: costs only
    by_account = {p.account.number: p.amount for p in voucher.postings}
    assert by_account == {2710: -87_412.11, 2740: 87_412.11}                                  # no 2700 line at all
    assert settlement.balance == -87_412.11


def test_a_term_with_no_vat_has_no_settlement_and_a_zero_balance_is_not_left_open():
    assert build_vat_settlement(2026, 3, 0.0, 0.0) is None
    voucher, settlement = build_vat_settlement(2026, 3, 100.0, 100.0)
    assert {p.account.number for p in voucher.postings} == {2700, 2710}                      # nothing on 2740
    assert settlement.status == VatSettlementStatus.PAID


# --- the payment --------------------------------------------------------------------------------

def _settlement(balance_output, balance_input, year=2026, term=2, sid=7):
    _, settlement = build_vat_settlement(year, term, balance_output, balance_input)
    return settlement.model_copy(update={"id": sid})


def test_payment_clears_2740_and_leaves_through_the_bank():
    settlement = _settlement(1_989_194.06, 85_669.97)
    transaction, voucher = build_vat_payment(settlement)
    assert transaction.transaction_type == BankTransactionType.OUTGOING
    assert transaction.amount == 1_903_524.09 and transaction.vat_settlement_id == 7
    assert (transaction.account_from, transaction.account_to) == (1910, 2740)
    assert {p.account.number: p.amount for p in voucher.postings} == {2740: 1_903_524.09, 1910: -1_903_524.09}
    assert transaction.date == voucher.date == date(2026, 6, 10)


def test_refund_comes_into_the_bank():
    settlement = _settlement(0.0, 87_412.11, year=2019, term=1)
    transaction, voucher = build_vat_payment(settlement)
    assert transaction.transaction_type == BankTransactionType.INCOMING and transaction.amount == 87_412.11
    assert {p.account.number: p.amount for p in voucher.postings} == {2740: -87_412.11, 1910: 87_412.11}
    assert transaction.date == date(2019, 4, 10)


def test_the_payment_is_generated_on_the_payment_date_and_only_then():
    settlement = _settlement(1_989_194.06, 85_669.97)
    on_day = generate_daily_bank_transactions(2026, 6, 10, [], [], [], [settlement])
    assert [t.vat_settlement_id for t, _ in on_day] == [7]
    for day in (9, 11):
        assert generate_daily_bank_transactions(2026, 6, day, [], [], [], [settlement]) == []


def test_every_vat_payment_date_is_a_working_day():
    for year in range(2019, 2028):
        for term in range(1, 7):
            assert is_working_day(payment_date_for(year, term)), (year, term)
