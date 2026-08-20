"""Generator miesięcznych SupplierInvoice (Warstwa 2) + Vouchery kosztowe (Warstwa 3).

W przeciwieństwie do Order — Voucher dla SupplierInvoice musi być tworzony jawnie
(zob. docs/norfingen_warstwa3_schemas.html, wzorce W2/W3). Ten moduł zwraca
zarówno listę faktur (per sygnatura z zadania), jak i pomocniczą funkcję budującą
odpowiadający im Voucher — używaną przez backfill.py przy zapisie do ledgera.

Reguła L05 (Sandvik IT Solutions): jeśli kwota netto >= capitalization_threshold
(30 000 NOK) → konto kapitalizacji (1200, środek trwały), inaczej → zwykłe konto
kosztowe (6540).
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

GROSS_UP_FACTOR = 1.25  # amountCurrency (incl. VAT) = netto * 1.25, VAT 25%
PAID_AFTER_DAYS = 45  # faktury z payment_due_date starszym niż 45 dni → PAID

# Faza 2 — L01 Microsoft Norge rozbite z jednej płaskiej pozycji (85 000 NOK/mies.,
# ekonomicznie nieuzasadnionej) na pozycje kosztowe realnie odpowiadające
# strukturze wydatków firmy IT (licencje M365, narzędzia deweloperskie,
# wsparcie CSP/Premier). Inflacja +3%/rok jak przy cenach sprzedaży
# (apply_annual_inflation), w przeciwieństwie do pozostałych dostawców (L02-L08),
# których kwoty pozostają płaskie/z szumem — poza zakresem tej fazy.
#
# Faza 6 — "Azure hosting — infrastruktura klientów" (35 000 NOK/mies. płaskie,
# Faza 2) USUNIĘTA stąd i ZASTĄPIONA mechanizmem skalującym się z liczbą
# klientów S02 (roster.calc_azure_cogs_monthly, opex_generator.py) — koszt
# odsprzedaży (COGS, konto 4291), nie stały koszt operacyjny (6xxx). Powód:
# kalibracja względem realnych danych rynkowych (Brønnøysundregistrene) —
# firmy z komponentem odsprzedaży Azure/licencji mają wysoki przychód/
# pracownika, ale niską marżę, bo koszt "znika" w COGS pass-through, nie w
# płacach. Zob. SESSION_HANDOFF.md (Faza 6) dla kalibrowanych stawek.
MICROSOFT_COST_LINES = [
    {"name": "M365 E3 licencje (16 stanowisk)", "base_monthly": 6_100},
    {"name": "Visual Studio / narzędzia deweloperskie", "base_monthly": 4_000},
    {"name": "Wsparcie CSP/Premier", "base_monthly": 8_000},
]


def with_noise(amount: float, pct: float = 0.03, rng: random.Random | None = None) -> float:
    """Dodaje losowy szum ±pct do kwoty. Wynik zaokrąglony do 2 miejsc."""
    generator = rng if rng is not None else random
    factor = 1 + generator.uniform(-pct, pct)
    return round(amount * factor, 2)


def avis_amount(month: int, rng: random.Random) -> float:
    """L07 Avis — wyższe koszty podróży w Q1 (sty-mar) i Q3 (lip-wrz) niż w Q2/Q4."""
    if month in (1, 2, 3, 7, 8, 9):
        return round(rng.uniform(22_000, 28_000), -2)
    return round(rng.uniform(12_000, 18_000), -2)


QUARTERLY_MONTHS_MAR_JUN_SEP_DEC = {3, 6, 9, 12}
QUARTERLY_MONTHS_JAN_APR_JUL_OCT = {1, 4, 7, 10}
SANDVIK_MIN_PER_YEAR = 3
SANDVIK_MAX_PER_YEAR = 5


def _sandvik_months_for_year(year: int) -> set[int]:
    """L05 — 3-5x rocznie w losowych miesiącach, deterministyczne per rok."""
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
        seq = month  # jedna faktura per miesiąc dla większości dostawców -> wystarczy numer miesiąca

        # Faza 7, Zadanie 3c — SUPPLIER_RENEGOTIATION: mnożnik trwały od
        # miesiąca renegocjacji (company_events.supplier_cost_multiplier),
        # 1.0 (bez zmian) dla dostawców, którzy nigdy nie byli renegocjowani.
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
            netto = supplier.amount_min  # stałe 45 000
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
            netto = supplier.amount_min  # stałe 38 000
            invoice_date = _month_day(year, month, 1)
        else:
            raise ValueError(f"Nieznany dostawca: {supplier.number}")

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

    # Faza 7, Zadanie 3c — EQUIPMENT_INVESTMENT: jednorazowy zakup L05 poza
    # zwykłym harmonogramem 3-5x/rok (sandvik_months), zawsze >= progu
    # kapitalizacji (80k-250k >> 30k) — trafia na konto 1200 automatycznie
    # przez _account_for_invoice, tak jak każda inna faktura L05.
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
    """Buduje Voucher INCOMING_INVOICE dla SupplierInvoice — generator jawnie
    (wzorce W2/W3): DR konto kosztowe/kapitalizacji (excl. VAT, vatType "1") /
    CR 2400 Leverandørgjeld (incl. VAT)."""
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
