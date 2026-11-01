"""Phase 4 (docs/SPEC_poprawki_ksiegowe.md): the COGS liabilities can be paid.

Before: the monthly COGS accrual (Dr 4291|4292 / Cr 2400) had no document behind it, so no payment was ever generated and
88 mln NOK sat on 2400 for good (gl_checks T8). After: every accrual has a CogsPayable (a due date, an amount, a status),
paid like a purchase invoice - Dr 2400 / Cr 1910 on the due date moved to the next working day - and the supplier
dimension on 2400 is there so accounts-payable ageing clears per supplier. 4291 is owed to L01 Microsoft Norge, 4292 to
L09 Ingram Micro.
"""

from collections import defaultdict
from datetime import date, timedelta

import pytest

from norfingen.generators.backfill import months_range
from norfingen.generators.bank_transaction_generator import build_cogs_payment, generate_daily_bank_transactions
from norfingen.generators.opex_generator import COGS_PAYMENT_TERMS_DAYS, cogs_payable_for, generate_monthly_opex
from norfingen.models.bank_transaction import BankTransactionType
from norfingen.models.cogs_payable import CogsPayableStatus
from norfingen.seed.roster import ALL_SUPPLIERS, COGS_SUPPLIER_BY_ACCOUNT, SUPPLIERS, numeric_id, supplier_by_number
from norfingen.seed.workdays import is_working_day, next_working_day

MONTHS = months_range(date(2019, 1, 1), date(2026, 12, 31))


def _accruals():
    for year, month in MONTHS:
        for voucher in generate_monthly_opex(year, month):
            payable = cogs_payable_for(voucher)
            if payable is not None:
                yield voucher, payable


def _with_id(payable, n):
    return payable.model_copy(update={"id": n})


def test_only_the_two_cogs_accounts_become_payables_and_the_cash_costs_do_not():
    kinds, other = defaultdict(int), 0
    for year, month in MONTHS:
        for voucher in generate_monthly_opex(year, month):
            payable = cogs_payable_for(voucher)
            if payable is None:
                other += 1
                assert any(p.account.number == 1910 and p.amount < 0 for p in voucher.postings), \
                    f"{voucher.description}: neither a COGS accrual nor a bank-paid cost"
            else:
                kinds[payable.account_number] += 1
    assert set(kinds) == {4291, 4292}
    assert kinds[4291] > 60 and kinds[4292] > 60 and other > 250


def test_every_payable_matches_its_accrual_voucher_to_the_cent():
    n = 0
    for voucher, payable in _accruals():
        credit = next(p for p in voucher.postings if p.account.number == 2400)
        assert payable.amount_currency == -credit.amount > 0
        assert payable.accrual_date == voucher.date
        assert payable.payment_due_date == voucher.date + timedelta(days=COGS_PAYMENT_TERMS_DAYS)
        assert payable.description == voucher.description
        assert payable.status == CogsPayableStatus.UNPAID
        # 4291 -> L01 Microsoft Norge, 4292 -> L09 Ingram Micro; the same supplier sits on the 2400 posting (ageing)
        assert payable.supplier_id == numeric_id(COGS_SUPPLIER_BY_ACCOUNT[payable.account_number])
        assert credit.supplier.id == payable.supplier_id
        n += 1
    assert n > 120


def test_the_payment_clears_the_liability_to_the_cent_per_supplier():
    cleared = defaultdict(float)
    for i, (voucher, payable) in enumerate(_accruals(), start=1):
        transaction, bank_voucher = build_cogs_payment(_with_id(payable, i))
        assert transaction.transaction_type == BankTransactionType.OUTGOING
        assert transaction.cogs_payable_id == i and transaction.supplier_invoice_id is None
        assert (transaction.account_from, transaction.account_to) == (1910, 2400)
        assert transaction.date == next_working_day(payable.payment_due_date) >= payable.payment_due_date
        assert is_working_day(transaction.date)
        by_account = {p.account.number: p.amount for p in bank_voucher.postings}
        assert by_account == {2400: payable.amount_currency, 1910: -payable.amount_currency}
        assert bank_voucher.validate_balance() and bank_voucher.date == transaction.date
        for p in (*voucher.postings, *bank_voucher.postings):
            if p.account.number == 2400:
                cleared[payable.supplier_id] += p.amount
    assert all(abs(total) < 0.005 for total in cleared.values()), dict(cleared)


def test_a_payment_without_a_stored_payable_is_refused():
    _, payable = next(_accruals())
    with pytest.raises(AssertionError):
        build_cogs_payment(payable)  # id None: the link to the bank transaction would be lost


def test_the_daily_generator_pays_a_payable_on_its_shifted_due_day_and_only_then():
    voucher, payable = next((v, p) for v, p in _accruals() if not is_working_day(p.payment_due_date))
    payable = _with_id(payable, 7)
    pay_day = next_working_day(payable.payment_due_date)
    assert pay_day > payable.payment_due_date                       # a weekend due date moves to Monday

    def paid_on(day):
        return generate_daily_bank_transactions(day.year, day.month, day.day, [], [], [payable])

    assert len(paid_on(pay_day)) == 1
    assert paid_on(payable.payment_due_date) == []                  # not on the weekend itself
    assert paid_on(pay_day - timedelta(days=1)) == [] and paid_on(pay_day + timedelta(days=1)) == []


def test_two_payables_falling_due_the_same_day_are_both_paid():
    by_due = defaultdict(list)
    for _, payable in _accruals():
        by_due[payable.payment_due_date].append(payable)
    due, group = next((d, g) for d, g in by_due.items() if len(g) == 2)  # 4291 and 4292 accrue on the same day
    group = [_with_id(p, i) for i, p in enumerate(group, start=1)]
    day = next_working_day(due)
    results = generate_daily_bank_transactions(day.year, day.month, day.day, [], [], group)
    assert {t.cogs_payable_id for t, _ in results} == {1, 2}


def test_what_is_left_on_2400_after_the_payments_is_exactly_the_unpaid_payables():
    """gl_checks T8, COGS part, at the source: accruals credited minus payments debited, up to a given day, equals the payables
    not yet paid - so the test can add them to the expected balance (variant B)."""
    today = date(2026, 11, 1)  # a Sunday: the Oct-1 accrual falls due on Saturday 31 Oct and is paid Monday 2 Nov
    accrued = paid = unpaid = 0.0
    open_accruals = set()
    for voucher, payable in _accruals():
        if voucher.date > today:
            continue
        accrued += payable.amount_currency
        if next_working_day(payable.payment_due_date) <= today:
            paid += payable.amount_currency
        else:
            unpaid += payable.amount_currency
            open_accruals.add(payable.accrual_date)
    assert round(accrued - paid - unpaid, 2) == 0
    assert open_accruals == {date(2026, 10, 1), date(2026, 11, 1)}   # exactly the two latest months are still open


def test_l09_is_a_cogs_only_supplier_kept_out_of_the_invoice_and_renegotiation_lists():
    """L09 must NOT join SUPPLIERS: company_events draws the SUPPLIER_RENEGOTIATION victim with rng.choice over that
    list, so a ninth entry would move the draw - and with it the price history."""
    assert len(SUPPLIERS) == 8 and all(s.number != "L09" for s in SUPPLIERS)
    assert [s.number for s in ALL_SUPPLIERS] == [f"L0{i}" for i in range(1, 10)]
    l09 = supplier_by_number("L09")
    assert l09.name == "Ingram Micro AS" and l09.real_org_number == "961425905"
    assert numeric_id("L09") == 9
    assert COGS_SUPPLIER_BY_ACCOUNT == {4291: "L01", 4292: "L09"}
