"""Start-up financing: the founding share capital and a loan from the owner (audit 2026-11-16, phase 3).

Why it exists. Until the audit the books opened with 30 000 NOK of share capital and nothing else, so the bank account
(1910) was negative on 176 days (to -2.8 mln NOK on 2019-10-01): a company cannot spend money it does not have. The
company now starts with

    capital   500 000 NOK  Dr 1910 / Cr 2000 Aksjekapital                  (2019-01-02, the founding voucher)
    loan    3 500 000 NOK  Dr 1910 / Cr 2290 Annen langsiktig gjeld          (2019-01-02, from the owner)

The loan costs 5 % a year and is serviced on the last working day of every month, by one BANK voucher:

    Dr 2290   principal  (nothing in 2019-2020, then 60 equal instalments 2021-01 .. 2025-12)
    Dr 8150   interest   (monthly: balance at the start of the month x 5 % / 12)
    Cr 1910   principal + interest

Interest is a FINANCIAL cost (8xxx): it is not in `PL_miesiecznie` (which sums 4000-7999), so the operating result and the
margin are unchanged - the audit's margin figures stay valid. Everything is a pure function of the calendar (no RNG), so
history and the daily cron produce the same vouchers. Simplifications, on purpose: the loan is not split into a
short-term and a long-term part, and the first month's interest is a full month although the money arrives on the 2nd.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.seed.payroll import last_working_day

ACCOUNT_BANK = 1910
ACCOUNT_SHARE_CAPITAL = 2000
ACCOUNT_OWNER_LOAN = 2290  # Annen langsiktig gjeld (loan from the shareholder)
ACCOUNT_INTEREST = 8150  # Annen rentekostnad

FOUNDING_DATE = date(2019, 1, 2)
SHARE_CAPITAL = 500_000.0
LOAN_PRINCIPAL = 3_500_000.0
LOAN_ANNUAL_RATE = 0.05
LOAN_FIRST_INSTALMENT = (2021, 1)  # 2019-2020: interest only
LOAN_INSTALMENTS = 60  # 2021-01 .. 2025-12


def _months_since_first_instalment(year: int, month: int) -> int:
    return (year - LOAN_FIRST_INSTALMENT[0]) * 12 + (month - LOAN_FIRST_INSTALMENT[1])


def principal_due(year: int, month: int) -> float:
    """Principal repaid on the last working day of (year, month): 1/60 of the loan, the last instalment takes the cent
    remainder so that the balance ends at exactly zero."""
    k = _months_since_first_instalment(year, month)
    if k < 0 or k >= LOAN_INSTALMENTS:
        return 0.0
    regular = round(LOAN_PRINCIPAL / LOAN_INSTALMENTS, 2)
    if k < LOAN_INSTALMENTS - 1:
        return regular
    return round(LOAN_PRINCIPAL - regular * (LOAN_INSTALMENTS - 1), 2)


def balance_at_month_start(year: int, month: int) -> float:
    """The loan balance on the first day of (year, month), before that month's instalment."""
    if (year, month) < (FOUNDING_DATE.year, FOUNDING_DATE.month):
        return 0.0
    repaid = 0.0
    y, m = LOAN_FIRST_INSTALMENT
    while (y, m) < (year, month) and _months_since_first_instalment(y, m) < LOAN_INSTALMENTS:
        repaid += principal_due(y, m)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return round(LOAN_PRINCIPAL - repaid, 2)


def interest_due(year: int, month: int) -> float:
    return round(balance_at_month_start(year, month) * LOAN_ANNUAL_RATE / 12, 2)


def loan_drawdown_voucher() -> Voucher:
    """The owner lends the company 3.5 mln NOK on the founding day (MANUAL, like the capital voucher)."""
    voucher = Voucher(
        date=FOUNDING_DATE,
        description="Lån fra eier — oppstartslån 3 500 000 NOK",
        voucherType=VoucherType.MANUAL,
        postings=[
            Posting(date=FOUNDING_DATE, account=acct(ACCOUNT_BANK), amount=LOAN_PRINCIPAL),
            Posting(date=FOUNDING_DATE, account=acct(ACCOUNT_OWNER_LOAN), amount=-LOAN_PRINCIPAL),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher


def loan_service_voucher(on_date: date) -> Optional[Voucher]:
    """The month's interest and principal, paid from the bank on the last working day of the month; None on any other day
    and after the loan is repaid."""
    if on_date != last_working_day(on_date.year, on_date.month) or on_date < FOUNDING_DATE:
        return None
    interest = interest_due(on_date.year, on_date.month)
    principal = principal_due(on_date.year, on_date.month)
    if interest <= 0 and principal <= 0:
        return None
    postings = []
    if principal:
        postings.append(Posting(date=on_date, account=acct(ACCOUNT_OWNER_LOAN), amount=principal))
    if interest:
        postings.append(Posting(date=on_date, account=acct(ACCOUNT_INTEREST), amount=interest))
    postings.append(Posting(date=on_date, account=acct(ACCOUNT_BANK), amount=-round(principal + interest, 2)))
    label = f"{on_date.year}-{on_date.month:02d}"
    voucher = Voucher(
        date=on_date,
        description=f"Lån fra eier — renter og avdrag {label}" if principal else f"Lån fra eier — renter {label}",
        voucherType=VoucherType.BANK,
        postings=postings,
    )
    assert_voucher_valid(voucher)
    return voucher
