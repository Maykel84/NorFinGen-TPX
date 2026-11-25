"""Corporate income tax (22 %) with losses carried forward - round 4, step 2 (2026-11-25).

A real company pays tax on its profit. NorFinGen earned a profit for years and never booked any tax, so its equity was overstated by
about a fifth of every profit. Now, at the end of every calendar year:

    31 December:   Dr 8300 Skattekostnad på ordinært resultat   tax for the year
                   Cr 2500 Betalbar skatt                       (the "provision": a liability until it is paid)
    15 February and 15 April of the NEXT year (moved to a working day), two EQUAL instalments, the advance tax (forskuddsskatt) of
    a limited company - "to like terminer, 15. februar og 15. april i året etter inntektsåret" (Skatteetaten):
                   Dr 2500 / Cr 1910

Tax for a year = 22 % x max(0, result before tax of the year - loss carried forward), where the result before tax is the ledger result
of accounts 3000-8299 (so it includes financial items such as the owner-loan interest and, since this round, depreciation and
pension) and the loss carried forward is every earlier loss not yet used (the 2019 loss reduces the profit of 2020 and 2021). No
deferred tax. A pure function of the yearly results read from the ledger (repository.get_results_before_tax_by_year): the instalments
are computed from the year's tax, never from a balance, so re-running a payment day gives the same amount.
Simplifications, on purpose: the result before tax is the taxable income (no permanent differences, no group contribution), the
advance tax equals the final tax (no assessment difference), and a loss year produces no voucher.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.seed.workdays import next_working_day

ACCOUNT_TAX_EXPENSE = 8300
ACCOUNT_TAX_PAYABLE = 2500
ACCOUNT_BANK = 1910
TAX_RATE = 0.22


def loss_carried_forward(year: int, results: dict[int, float]) -> float:
    """Losses of the years BEFORE `year` that no profit has used up yet."""
    carried = 0.0
    for y in sorted(k for k in results if k < year):
        carried = max(0.0, round(carried - results[y], 2))  # a loss grows the pot, a profit uses it up
    return carried


def tax_for_year(year: int, results: dict[int, float]) -> float:
    taxable = max(0.0, round(results.get(year, 0.0) - loss_carried_forward(year, results), 2))
    return round(taxable * TAX_RATE, 2)


def tax_voucher(on_date: date, results: dict[int, float]) -> Optional[Voucher]:
    """The year's tax on 31 December; None on any other day and for a year without taxable profit."""
    if (on_date.month, on_date.day) != (12, 31):
        return None
    tax = tax_for_year(on_date.year, results)
    if tax <= 0:
        return None
    voucher = Voucher(
        date=on_date,
        description=f"Skattekostnad {on_date.year} (22 % av skattbart resultat)",
        voucherType=VoucherType.ADJUSTMENT,
        postings=[
            Posting(date=on_date, account=acct(ACCOUNT_TAX_EXPENSE), amount=tax),
            Posting(date=on_date, account=acct(ACCOUNT_TAX_PAYABLE), amount=-tax),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher


def instalment_dates(year: int) -> tuple[date, date]:
    """The two payment days of the tax of `year - 1`, paid in `year`: 15 February and 15 April, moved to a working day."""
    return next_working_day(date(year, 2, 15)), next_working_day(date(year, 4, 15))


def advance_tax_payment_voucher(on_date: date, results: dict[int, float]) -> Optional[Voucher]:
    """Half of the previous year's tax on 15 February, the other half on 15 April; None on any other day or when there is no tax."""
    first, second = instalment_dates(on_date.year)
    if on_date not in (first, second):
        return None
    tax = tax_for_year(on_date.year - 1, results)
    if tax <= 0:
        return None
    half = round(tax / 2, 2)
    term, amount = (1, half) if on_date == first else (2, round(tax - half, 2))
    voucher = Voucher(
        date=on_date,
        description=f"Forskuddsskatt {on_date.year - 1} termin {term}",
        voucherType=VoucherType.BANK,
        postings=[
            Posting(date=on_date, account=acct(ACCOUNT_TAX_PAYABLE), amount=amount),
            Posting(date=on_date, account=acct(ACCOUNT_BANK), amount=-amount),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher
