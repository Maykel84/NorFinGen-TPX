"""Phase 1 (docs/SPEC_poprawki_ksiegowe.md): payroll liabilities leave the VAT accounts.

Before: net pay on 2710, withheld tax on 2740, AGA on 2700 - the NS 4102 VAT accounts - and the feriepenger
provision on 2930. After: 2930 Skyldig lønn, 2600 Forskuddstrekk, 2770 Skyldig AGA, 2940 Skyldige feriepenger,
leaving 2700/2710/2740 free for VAT (phases 2-3 and 5). These tests are the generator-level version of
gl_checks.sql T7 (no SALARY posting on a VAT account) and T9 (feriepenger paid out of 2940 every June).
"""

from collections import defaultdict

import pytest

from norfingen.db.repository import ACCOUNTS_SEED
from norfingen.generators.backfill import months_range
from norfingen.generators.bank_transaction_generator import PAYROLL_LIABILITY_ACCOUNTS, generate_payroll_bank_transaction
from norfingen.generators.salary_generator import generate_monthly_salary
from datetime import date

VAT_ACCOUNTS = {2700, 2710, 2740}
MONTHS = months_range(date(2019, 1, 1), date(2026, 9, 30))


def _vouchers(year, month):
    transaction, vouchers = generate_monthly_salary(year, month)
    return transaction, {v.description.split(" ")[0]: v for v in vouchers}, vouchers


def _accounts(voucher, sign):
    return {p.account.number for p in voucher.postings if (p.amount > 0) == (sign > 0) and p.amount != 0}


@pytest.mark.parametrize("year,month", [(2019, 1), (2020, 6), (2022, 9), (2024, 6), (2026, 9)])
def test_each_payroll_voucher_uses_exactly_its_phase1_accounts(year, month):
    _, _, vouchers = _vouchers(year, month)
    payroll, aga, provision = vouchers  # order of generate_monthly_salary()

    assert _accounts(payroll, +1) <= {5000, 2940}          # salary expense, June feriepenger drawdown
    assert _accounts(payroll, -1) <= {2930, 2600}          # net pay owed, tax withheld
    assert _accounts(aga, +1) == {5400} and _accounts(aga, -1) == {2770}
    assert _accounts(provision, +1) == {5099} and _accounts(provision, -1) == {2940}
    for voucher in vouchers:
        assert abs(sum(p.amount for p in voucher.postings)) < 0.01


def test_no_payroll_posting_ever_touches_a_vat_account():
    """gl_checks T7, at the source: 93 months of payroll, zero postings on 2700/2710/2740."""
    for year, month in MONTHS:
        for voucher in _vouchers(year, month)[2]:
            used = {p.account.number for p in voucher.postings}
            assert not (used & VAT_ACCOUNTS), f"{year}-{month:02d}: {used & VAT_ACCOUNTS}"


def test_feriepenger_is_drawn_down_from_2940_every_june_from_2020():
    """gl_checks T9, at the source. June 2019 has no prior-year basis, so no payout; from 2020 every June pays out."""
    for year in range(2020, 2027):
        payroll = _vouchers(year, 6)[2][0]
        drawdown = [p.amount for p in payroll.postings if p.account.number == 2940 and p.amount > 0]
        assert drawdown and sum(drawdown) > 0, f"June {year}: no feriepenger drawdown on 2940"


def test_2940_never_goes_negative():
    """The provision is built up before it is drawn down: the 2940 balance (credit-positive) stays >= 0."""
    balance = 0.0
    for year, month in MONTHS:
        for voucher in _vouchers(year, month)[2]:
            for p in voucher.postings:
                if p.account.number == 2940:
                    balance -= p.amount  # credits are negative amounts
        assert balance >= -0.01, f"{year}-{month:02d}: 2940 balance {balance:.2f}"


def test_payroll_liabilities_are_cleared_by_the_payroll_payment():
    """Per month, booking (salary vouchers) + paying (bank voucher) leaves 2930, 2600 and 2770 at zero;
    2940 is deliberately not part of the payment - the provision is paid out in June as part of the salary
    run itself (drawdown), never as a separate bank transfer."""
    for year, month in MONTHS:
        transaction, _, vouchers = _vouchers(year, month)
        transaction.id = 1
        paid = generate_payroll_bank_transaction(transaction, vouchers)
        assert paid is not None
        net = defaultdict(float)
        for voucher in (*vouchers, paid[1]):
            for p in voucher.postings:
                net[p.account.number] += p.amount
        for account in PAYROLL_LIABILITY_ACCOUNTS:
            assert abs(net[account]) < 0.05, f"{year}-{month:02d}: account {account} left {net[account]:.2f}"
        assert 2940 not in {p.account.number for p in paid[1].postings}  # the payment never touches the provision


def test_chart_of_accounts_follows_ns4102_for_the_27xx_29xx_liabilities():
    names = {number: name for number, name, _type, _vat in ACCOUNTS_SEED}
    assert names[2600] == "Forskuddstrekk"
    assert names[2700] == "Utgående merverdiavgift"
    assert names[2710] == "Inngående merverdiavgift"
    assert names[2740] == "Oppgjørskonto merverdiavgift"
    assert names[2770] == "Skyldig arbeidsgiveravgift"
    assert names[2930] == "Skyldig lønn"
    assert names[2940] == "Skyldige feriepenger"
    assert 2780 not in names  # AGA on the provision stays on 2770 - a deliberate simplification (README)
    assert len({number for number, *_ in ACCOUNTS_SEED}) == len(ACCOUNTS_SEED)  # no duplicates
