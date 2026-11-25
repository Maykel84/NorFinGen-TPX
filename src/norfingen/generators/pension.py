"""Mandatory occupational pension, OTP (obligatorisk tjenestepensjon) - round 4, step 2 (2026-11-25).

Every Norwegian employer must pay at least 2 % of the pay into a pension scheme for its employees. The generator booked salary, holiday
pay and employer's tax but no pension, a hidden cost of about 0.6-0.8 % of revenue. Now:

    on the payroll day (last working day of the month), a voucher right after the payroll:
        Dr 5420 Innskuddspensjon (OTP)        2 % of the gross pay of the month (wage types 100 Fast lønn + 260 Feriepenger, the same
        Cr 2950 Skyldig pensjonspremie (OTP)  gross as the payroll_gross of the golden fingerprint)
    quarterly, on the 15th (moved to a working day) of January, April, July and October, the quarter that has just ended is paid:
        Dr 2950 / Cr 1910                     what was ACCRUED in that quarter (the credit turnover of 2950 in the quarter)

5420 lies in 5000-5999, so it is in `labor_cost` and in the operating result. A pure function of the payroll and the calendar (no RNG).
The payment is the accrual of the quarter, not the balance of the account, so re-running the payment day gives the same amount.
Simplifications, on purpose: the 2 % is the legal minimum (no scheme above it), there is no cap at 12 G and no floor at 1 G (every
salary here is far above 1 G and the cap bites only above ~1.5 mln NOK a year), and employer's tax (AGA) on the pension premium is
not modelled (it would add ~14 % on top of 5420: ~0.1 % of revenue).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.seed.workdays import next_working_day

ACCOUNT_OTP_EXPENSE = 5420
ACCOUNT_PENSION_LIABILITY = 2950
ACCOUNT_BANK = 1910
OTP_RATE = 0.02
GROSS_WAGE_TYPES = (100, 260)  # Fast lønn + Feriepenger
PAYMENT_MONTHS = (1, 4, 7, 10)


def otp_base(salary_txn) -> float:
    """The pay the 2 % is calculated on: gross fixed pay plus holiday pay of the month, summed over all payslips."""
    return round(sum(
        spec.amount
        for payslip in salary_txn.payslips
        for spec in payslip.specifications
        if spec.wageType.id in GROSS_WAGE_TYPES
    ), 2)


def otp_voucher(on_date: date, base: float) -> Optional[Voucher]:
    amount = round(base * OTP_RATE, 2)
    if amount <= 0:
        return None
    voucher = Voucher(
        date=on_date,
        description=f"Obligatorisk tjenestepensjon (OTP) {on_date.year}-{on_date.month:02d}",
        voucherType=VoucherType.ADJUSTMENT,
        postings=[
            Posting(date=on_date, account=acct(ACCOUNT_OTP_EXPENSE), amount=amount),
            Posting(date=on_date, account=acct(ACCOUNT_PENSION_LIABILITY), amount=-amount),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher


def payment_date(year: int, month: int) -> date:
    """The 15th of January / April / July / October, moved to the next working day (never leaves the month)."""
    return next_working_day(date(year, month, 15))


def quarter_paid_on(on_date: date) -> Optional[tuple[date, date, str]]:
    """(first day, last day, label) of the quarter that is paid on `on_date`, or None when it is not a payment day."""
    if on_date.month not in PAYMENT_MONTHS or on_date != payment_date(on_date.year, on_date.month):
        return None
    end = date(on_date.year, on_date.month, 1) - timedelta(days=1)  # last day of the previous month = end of the quarter
    start = date(end.year, end.month - 2, 1)
    return start, end, f"{start.year}-Q{(start.month - 1) // 3 + 1}"


def otp_payment_voucher(on_date: date, accrued_in_quarter: float) -> Optional[Voucher]:
    quarter = quarter_paid_on(on_date)
    if quarter is None or accrued_in_quarter <= 0:
        return None
    amount = round(accrued_in_quarter, 2)
    voucher = Voucher(
        date=on_date,
        description=f"Innbetaling pensjonspremie OTP {quarter[2]}",
        voucherType=VoucherType.BANK,
        postings=[
            Posting(date=on_date, account=acct(ACCOUNT_PENSION_LIABILITY), amount=amount),
            Posting(date=on_date, account=acct(ACCOUNT_BANK), amount=-amount),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher
