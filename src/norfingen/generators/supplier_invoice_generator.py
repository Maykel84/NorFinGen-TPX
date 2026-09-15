"""Monthly SupplierInvoice generator (Layer 2) + cost Vouchers (Layer 3).

Unlike Order — the Voucher for a SupplierInvoice must be created explicitly
(see docs/norfingen_warstwa3_schemas.html, patterns W2/W3). This module
returns both the list of invoices (per the task's signature) and a helper
function that builds their matching Voucher — used by backfill.py when
writing to the ledger.

Rule L05 (Sandvik IT Solutions): if the net amount >= capitalization_threshold
(30,000 NOK) -> capitalization account (1200, fixed asset), otherwise ->
the regular cost account (6540).
"""

from __future__ import annotations

import calendar
import random
from datetime import date, timedelta

from norfingen.generators.company_events import equipment_investment_trigger, supplier_cost_multiplier
from norfingen.generators.order_generator import apply_annual_inflation
from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid, expected_vat_amount
from norfingen.models.base import TripletexRef
from norfingen.models.supplier_invoice import SupplierInvoice
from norfingen.seed.roster import SUPPLIERS, SupplierSeed, numeric_id, supplier_by_number

GROSS_UP_FACTOR = 1.25  # amountCurrency (incl. VAT) = net * 1.25, VAT 25%
PAID_AFTER_DAYS = 45  # invoices with payment_due_date older than 45 days -> PAID

# Phase 2 — L01 Microsoft Norge split from a single flat line item
# (85,000 NOK/month, economically implausible) into cost lines that
# realistically match an IT company's spending structure (M365 licenses,
# developer tools, CSP/Premier support). 3%/year inflation like the sales
# prices (apply_annual_inflation), unlike the other suppliers (L02-L08),
# whose amounts stay flat/noisy — out of scope for this phase.
#
# Phase 6 — "Azure hosting — customer infrastructure" (35,000 NOK/month
# flat, Phase 2) REMOVED from here and REPLACED by a mechanism that scales
# with the number of S02 customers (roster.calc_azure_cogs_monthly,
# opex_generator.py) — a resale cost (COGS, account 4291), not a fixed
# operating cost (6xxx). Reason: calibration against real market data
# (Brønnøysundregistrene) — firms with an Azure/license resale component
# have high revenue/employee, but low margin, because the cost "disappears"
# into COGS pass-through, not payroll. See SESSION_HANDOFF.md (Phase 6) for
# the calibrated rates.
MICROSOFT_COST_LINES = [
    {"name": "M365 E3 licencje (16 stanowisk)", "base_monthly": 6_100},
    {"name": "Visual Studio / narzędzia deweloperskie", "base_monthly": 4_000},
    {"name": "Wsparcie CSP/Premier", "base_monthly": 8_000},
]


def with_noise(amount: float, pct: float = 0.03, rng: random.Random | None = None) -> float:
    """Adds random noise of ±pct to an amount. Result rounded to 2 decimal places."""
    generator = rng if rng is not None else random
    factor = 1 + generator.uniform(-pct, pct)
    return round(amount * factor, 2)


def avis_amount(month: int, rng: random.Random) -> float:
    """L07 Avis — higher travel costs in Q1 (Jan-Mar) and Q3 (Jul-Sep) than in Q2/Q4."""
    if month in (1, 2, 3, 7, 8, 9):
        return round(rng.uniform(22_000, 28_000), -2)
    return round(rng.uniform(12_000, 18_000), -2)


QUARTERLY_MONTHS_MAR_JUN_SEP_DEC = {3, 6, 9, 12}
QUARTERLY_MONTHS_JAN_APR_JUL_OCT = {1, 4, 7, 10}
SANDVIK_MIN_PER_YEAR = 3
SANDVIK_MAX_PER_YEAR = 5


def _sandvik_months_for_year(year: int) -> set[int]:
    """L05 — 3-5x per year in random months, deterministic per year."""
    rng = random.Random(f"L05-{year}")
    count = rng.randint(SANDVIK_MIN_PER_YEAR, SANDVIK_MAX_PER_YEAR)
    return set(rng.sample(range(1, 13), count))


def _month_day(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _next_invoice_number(supplier: SupplierSeed, year: int, sequence: int) -> str:
    return f"{supplier.number}-{year}-{sequence:03d}"


def generate_monthly_supplier_invoices(year: int, month: int) -> list[SupplierInvoice]:
    invoices: list[SupplierInvoice] = []
    sandvik_months = _sandvik_months_for_year(year)
    rng = random.Random(f"supplier-invoices-{year}-{month}")

    for supplier in SUPPLIERS:
        seq = month  # one invoice per month for most suppliers -> the month number is enough

        # Phase 7, Task 3c — SUPPLIER_RENEGOTIATION: a multiplier that's
        # permanent from the renegotiation month on
        # (company_events.supplier_cost_multiplier), 1.0 (unchanged) for
        # suppliers who were never renegotiated.
        renegotiation_multiplier = supplier_cost_multiplier(supplier.number, year, month)

        if supplier.number == "L01":
            invoice_date = _month_day(year, month, 1)
            payment_due = invoice_date + timedelta(days=30)
            paid = date.today() - payment_due > timedelta(days=PAID_AFTER_DAYS)
            for idx, cost_line in enumerate(MICROSOFT_COST_LINES, start=1):
                netto = round(apply_annual_inflation(cost_line["base_monthly"], year) * renegotiation_multiplier, 2)
                account_number = _account_for_invoice(supplier, netto)
                invoices.append(SupplierInvoice(
                    invoiceNumber=f"{supplier.number}-{year}-{month:02d}-{idx}",
                    supplier=TripletexRef(id=numeric_id(supplier.number)),
                    invoiceDate=invoice_date,
                    amountCurrency=round(netto * GROSS_UP_FACTOR, 2),
                    account=TripletexRef(id=account_number),
                    comment=cost_line["name"],
                    status="PAID" if paid else "UNPAID",
                ))
            continue
        elif supplier.number == "L02":
            netto = with_noise(18_000, 0.05, rng)
            invoice_date = _month_day(year, month, 5)
        elif supplier.number == "L03":
            netto = with_noise(rng.uniform(supplier.amount_min, supplier.amount_max), rng=rng)
            invoice_date = _month_day(year, month, 15)
        elif supplier.number == "L04":
            netto = supplier.amount_min  # fixed at 45,000
            invoice_date = _month_day(year, month, 1)
        elif supplier.number == "L05":
            if month not in sandvik_months:
                continue
            netto = with_noise(rng.uniform(supplier.amount_min, supplier.amount_max), rng=rng)
            invoice_date = _month_day(year, month, rng.randint(1, 28))
        elif supplier.number == "L06":
            if month not in QUARTERLY_MONTHS_MAR_JUN_SEP_DEC:
                continue
            netto = with_noise(rng.uniform(supplier.amount_min, supplier.amount_max), rng=rng)
            invoice_date = _month_day(year, month, 10)
        elif supplier.number == "L07":
            netto = avis_amount(month, rng)
            invoice_date = _month_day(year, month, 20)
        elif supplier.number == "L08":
            if month not in QUARTERLY_MONTHS_JAN_APR_JUL_OCT:
                continue
            netto = supplier.amount_min  # fixed at 38,000
            invoice_date = _month_day(year, month, 1)
        else:
            raise ValueError(f"Unknown supplier: {supplier.number}")

        netto = round(netto * renegotiation_multiplier, 2)
        account_number = _account_for_invoice(supplier, netto)
        payment_due = invoice_date + timedelta(days=30)
        paid = date.today() - payment_due > timedelta(days=PAID_AFTER_DAYS)

        invoice = SupplierInvoice(
            invoiceNumber=_next_invoice_number(supplier, year, seq),
            supplier=TripletexRef(id=numeric_id(supplier.number)),
            invoiceDate=invoice_date,
            amountCurrency=round(netto * GROSS_UP_FACTOR, 2),
            account=TripletexRef(id=account_number),
            comment=supplier.cost_category,
            status="PAID" if paid else "UNPAID",
        )
        invoices.append(invoice)

    # Phase 7, Task 3c — EQUIPMENT_INVESTMENT: a one-off L05 purchase
    # outside the regular 3-5x/year schedule (sandvik_months), always >=
    # the capitalization threshold (80k-250k >> 30k) — lands on account
    # 1200 automatically via _account_for_invoice, same as any other L05
    # invoice.
    equipment_amount = equipment_investment_trigger(year, month)
    if equipment_amount is not None:
        l05 = supplier_by_number("L05")
        invoice_date = _month_day(year, month, 28)
        account_number = _account_for_invoice(l05, equipment_amount)
        payment_due = invoice_date + timedelta(days=30)
        paid = date.today() - payment_due > timedelta(days=PAID_AFTER_DAYS)
        invoices.append(SupplierInvoice(
            invoiceNumber=f"L05-{year}-{month:02d}-EQUIP",
            supplier=TripletexRef(id=numeric_id("L05")),
            invoiceDate=invoice_date,
            amountCurrency=round(equipment_amount * GROSS_UP_FACTOR, 2),
            account=TripletexRef(id=account_number),
            comment="Utstyrsinvestering (uforutsett)",
            status="PAID" if paid else "UNPAID",
        ))

    return invoices


def _account_for_invoice(supplier: SupplierSeed, netto: float) -> int:
    if (
        supplier.capitalization_threshold is not None
        and netto >= supplier.capitalization_threshold
        and supplier.capitalization_account is not None
    ):
        return supplier.capitalization_account
    return supplier.gl_account


def build_voucher_for_invoice(invoice: SupplierInvoice, supplier: SupplierSeed) -> Voucher:
    """Builds an INCOMING_INVOICE Voucher for a SupplierInvoice — created
    explicitly by the generator (patterns W2/W3): DR cost/capitalization
    account (excl. VAT, vatType "1") / CR 2400 Leverandørgjeld (incl. VAT)."""
    netto = round(invoice.amountExcludingVatCurrency, 2)
    account_number = _account_for_invoice(supplier, netto)
    vat_amount = expected_vat_amount(netto)

    voucher = Voucher(
        date=invoice.invoiceDate,
        description=f"{invoice.invoiceNumber} — {supplier.name}",
        voucherType=VoucherType.INCOMING_INVOICE,
        postings=[
            Posting(
                date=invoice.invoiceDate,
                account=acct(account_number),
                amount=netto,
                vatType=invoice.vatType,
                vatAmount=vat_amount,
                supplier=invoice.supplier,
            ),
            Posting(
                date=invoice.invoiceDate,
                account=acct(2400),
                amount=-round(invoice.amountCurrency, 2),
                supplier=invoice.supplier,
            ),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher
