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
from norfingen.generators.opex_generator import cogs_payable_for, cogs_payment_due_date, generate_monthly_opex, split_cogs
from norfingen.models.bank_transaction import BankTransactionType
from norfingen.models.cogs_payable import CogsPayableStatus
from norfingen.seed.roster import (ALL_SUPPLIERS, COGS_SUPPLIER_BY_ACCOUNT, COGS_SUPPLIER_SHARES, SUPPLIER_ADDRESSES, SUPPLIERS,
                                   numeric_id, supplier_by_number)
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
        assert payable.payment_due_date == cogs_payment_due_date(voucher.date)
        assert payable.description == voucher.description
        assert payable.status == CogsPayableStatus.UNPAID
        # round 2, point 3: each account is owed to several suppliers (COGS_SUPPLIER_SHARES); the same supplier sits on the
        # 2400 posting (ageing) and on the 4291/4292 and 2710 postings
        assert payable.supplier_id in {numeric_id(n) for n, _, _ in COGS_SUPPLIER_SHARES[payable.account_number]}
        assert {p.supplier.id for p in voucher.postings} == {payable.supplier_id}
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


def test_the_due_date_is_the_last_working_day_of_the_month_after_the_accrual():
    """Round 2, point 1: no month skipped, no month doubled. Always a working day, so the payment never shifts."""
    for voucher, payable in _accruals():
        due = payable.payment_due_date
        assert is_working_day(due) and next_working_day(due) == due
        assert (due.year, due.month) == ((voucher.date.year + (voucher.date.month == 12)), voucher.date.month % 12 + 1)
        later = due + timedelta(days=1)
        while later.month == due.month:                       # nothing after it in that month is a working day
            assert not is_working_day(later)
            later += timedelta(days=1)
    assert cogs_payment_due_date(date(2026, 1, 30)) == date(2026, 2, 27)    # old rule: 1 Mar -> February had no payment
    assert cogs_payment_due_date(date(2026, 10, 30)) == date(2026, 11, 30)  # Monday
    assert cogs_payment_due_date(date(2026, 12, 31)) == date(2027, 1, 29)   # Friday (31 Jan 2027 is a Sunday)


def test_exactly_one_cogs_payment_per_supplier_per_month():
    per_month = defaultdict(int)
    for _, payable in _accruals():
        pay_day = next_working_day(payable.payment_due_date)
        per_month[(payable.supplier_id, pay_day.year, pay_day.month)] += 1
    assert set(per_month.values()) == {1}, {k: v for k, v in per_month.items() if v != 1}


def test_the_daily_generator_pays_a_payable_on_its_due_day_and_only_then():
    voucher, payable = next(_accruals())
    payable = _with_id(payable, 7)
    pay_day = payable.payment_due_date

    def paid_on(day):
        return generate_daily_bank_transactions(day.year, day.month, day.day, [], [], [payable])

    assert len(paid_on(pay_day)) == 1
    assert paid_on(pay_day - timedelta(days=1)) == [] and paid_on(pay_day + timedelta(days=1)) == []


def test_two_payables_falling_due_the_same_day_are_both_paid():
    by_due = defaultdict(list)
    for _, payable in _accruals():
        by_due[payable.payment_due_date].append(payable)
    due, group = next((d, g) for d, g in by_due.items() if len(g) == 6)  # 3 suppliers x 2 accounts accrue on the same day
    group = [_with_id(p, i) for i, p in enumerate(group, start=1)]
    day = next_working_day(due)
    results = generate_daily_bank_transactions(day.year, day.month, day.day, [], [], group)
    assert {t.cogs_payable_id for t, _ in results} == {1, 2, 3, 4, 5, 6}


def test_what_is_left_on_2400_after_the_payments_is_exactly_the_unpaid_payables():
    """gl_checks T8, COGS part, at the source: accruals credited minus payments debited, up to a given day, equals the payables
    not yet paid - so the test can add them to the expected balance (variant B)."""
    today = date(2026, 11, 1)  # a Sunday; accruals are booked on the last working day: Sep-30 fell due Fri 30 Oct and is paid
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
    assert open_accruals == {date(2026, 10, 30)}   # only October is open: due Mon 30 Nov (the November accrual is also 30 Nov, due 31 Dec)


def test_the_cogs_suppliers_are_kept_out_of_the_invoice_and_renegotiation_lists():
    """L09-L13 must NOT join SUPPLIERS: company_events draws the SUPPLIER_RENEGOTIATION victim with rng.choice over that
    list, so a ninth entry would move the draw - and with it the price history."""
    assert len(SUPPLIERS) == 8 and all(int(s.number[1:]) <= 8 for s in SUPPLIERS)
    assert [s.number for s in ALL_SUPPLIERS] == [f"L{i:02d}" for i in range(1, 14)]
    l09 = supplier_by_number("L09")
    assert l09.name == "Ingram Micro AS" and l09.real_org_number == "961425905"
    assert numeric_id("L09") == 9 and numeric_id("L13") == 13
    assert COGS_SUPPLIER_BY_ACCOUNT == {4291: "L01", 4292: "L09"}          # the main supplier of each account
    for number in ("L10", "L11", "L12", "L13"):                            # checked against data.brreg.no on 2026-11-17
        supplier = supplier_by_number(number)
        assert supplier.real_org_number and len(supplier.real_org_number) == 9
        assert SUPPLIER_ADDRESSES[number][2] == "brreg"


def test_the_shares_of_each_account_add_up_to_one_and_every_supplier_is_listed():
    for account, shares in COGS_SUPPLIER_SHARES.items():
        assert abs(sum(share for _, share, _ in shares) - 1.0) < 1e-9
        assert len(shares) >= 3 and shares[0][2] is None            # the main supplier keeps the pre-split description
        for number, _, _ in shares:
            assert supplier_by_number(number)


def test_the_split_adds_up_to_the_cent_and_no_supplier_dominates():
    """Round 2, point 3: who is owed changes, how much does not. (The frozen proof is golden cogs_month_net_totals.)"""
    per_month_account = defaultdict(float)
    per_supplier = defaultdict(float)
    for _, payable in _accruals():
        per_month_account[(payable.accrual_date.strftime("%Y-%m"), payable.account_number)] += payable.amount_excluding_vat_currency
        per_supplier[payable.supplier_id] += payable.amount_excluding_vat_currency
    assert len(per_month_account) == 2 * len({month for month, _ in per_month_account})   # both accounts, every month with COGS
    total = sum(per_supplier.values())
    assert len(per_supplier) == 6
    assert max(per_supplier.values()) / total < 0.40, {k: round(v / total, 3) for k, v in per_supplier.items()}
    assert min(per_supplier.values()) / total > 0.03


def test_split_cogs_is_exact_deterministic_and_positive():
    for account in (4291, 4292):
        for net in (1_234_567.89, 605_098.00, 0.07):
            parts = split_cogs(account, 2026, 10, net)
            assert round(sum(p for _, _, p in parts), 2) == round(net, 2)
            assert all(p >= 0 for _, _, p in parts) and parts == split_cogs(account, 2026, 10, net)
    a, b = split_cogs(4292, 2026, 9, 1_728_219.0), split_cogs(4292, 2026, 10, 1_728_219.0)
    assert [p for _, _, p in a] != [p for _, _, p in b]               # the shares move a little from month to month


def test_vat_on_every_split_voucher_is_25_percent_of_its_own_net():
    for voucher, payable in _accruals():
        net = round(next(p.amount for p in voucher.postings if p.account.number in (4291, 4292)), 2)
        vat = round(next(p.amount for p in voucher.postings if p.account.number == 2710), 2)
        assert abs(vat - round(net * 0.25, 2)) <= 0.011
