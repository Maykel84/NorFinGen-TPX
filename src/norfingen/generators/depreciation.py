"""Depreciation of the fixed assets (round 4, step 2, 2026-11-25).

Until now account 1200 "Maskiner og anlegg" only grew: the capitalised purchase invoices of supplier L05 (net amount >= 30 000
NOK) were never written down, so 1.6 mln NOK of equipment sat on the balance sheet at cost for ever and EBIT was too high.

The rule is the ordinary one: straight line over 5 years (60 months), a full month from the month of purchase, one
voucher a month on the last working day (like payroll and the COGS accruals):

    Dr 6015 Avskrivning på maskiner og anlegg      the month's charge   (inside 6000-7999, so it IS in the operating result: EBIT)
    Cr 1209 Akkumulerte avskrivninger               the same             (net book value = 1200 + 1209)

An asset bought AFTER the last working day of its month (a weekend invoice date at the month's end) starts one month later - the
voucher of the month cannot see an invoice that does not exist yet, and the rule has to give the same answer when a day is re-run.
The 60th charge takes the cent remainder, so an asset ends at exactly zero net book value. A pure function of the ledger: the list
of additions (repository.get_asset_additions) and the month, no RNG - history and the daily cron produce the same vouchers.
Simplification, on purpose: no disposals, no impairment.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.seed.payroll import last_working_day

ACCOUNT_FIXED_ASSETS = 1200
ACCOUNT_ACCUMULATED_DEPRECIATION = 1209
ACCOUNT_DEPRECIATION = 6015
USEFUL_LIFE_MONTHS = 60


def first_depreciation_month(added: date) -> tuple[int, int]:
    """(year, month) of the first charge: the month of purchase, or the next one when the purchase falls after that month's last
    working day."""
    if added <= last_working_day(added.year, added.month):
        return added.year, added.month
    return (added.year + 1, 1) if added.month == 12 else (added.year, added.month + 1)


def monthly_charge(cost: float, added: date, year: int, month: int) -> float:
    """The charge of one asset in (year, month): cost / 60 rounded to the cent, the last of the 60 charges takes the remainder."""
    first_year, first_month = first_depreciation_month(added)
    k = (year - first_year) * 12 + (month - first_month)
    if k < 0 or k >= USEFUL_LIFE_MONTHS:
        return 0.0
    regular = round(cost / USEFUL_LIFE_MONTHS, 2)
    if k < USEFUL_LIFE_MONTHS - 1:
        return regular
    return round(cost - regular * (USEFUL_LIFE_MONTHS - 1), 2)


def depreciation_for_month(additions: list[tuple[date, float]], year: int, month: int, on_date: date) -> float:
    """Total charge of (year, month): every addition booked on or before `on_date` (the voucher's own date)."""
    return round(sum(monthly_charge(cost, added, year, month) for added, cost in additions if added <= on_date), 2)


def depreciation_voucher(on_date: date, additions: list[tuple[date, float]]) -> Optional[Voucher]:
    """The month's depreciation voucher on the last working day of the month; None on any other day or when nothing is to be written down."""
    if on_date != last_working_day(on_date.year, on_date.month):
        return None
    amount = depreciation_for_month(additions, on_date.year, on_date.month, on_date)
    if amount <= 0:
        return None
    voucher = Voucher(
        date=on_date,
        description=f"Avskrivning maskiner og anlegg {on_date.year}-{on_date.month:02d}",
        voucherType=VoucherType.ADJUSTMENT,
        postings=[
            Posting(date=on_date, account=acct(ACCOUNT_DEPRECIATION), amount=amount),
            Posting(date=on_date, account=acct(ACCOUNT_ACCUMULATED_DEPRECIATION), amount=-amount),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher
