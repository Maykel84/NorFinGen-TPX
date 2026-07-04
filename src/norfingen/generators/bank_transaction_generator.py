"""BankTransaction + Voucher (typ BANK) — Warstwa 3, Etap 4.

Modeluje faktyczny wpływ/wypływ gotówki, przesunięty w czasie względem
wystawienia dokumentu źródłowego (Order/SupplierInvoice) o payment_terms /
payment_due_date — w przeciwieństwie do Vouchera INVOICE/INCOMING_INVOICE,
który księguje się w dniu wystawienia faktury.

Wzorce DR/CR:
  Płatność przychodząca (klient płaci Order):
    DR 1910 Bankinnskudd driftskonto  +kwota
    CR 1500 Kundefordringer          -kwota
    date = invoice_date + payment_terms dni (+90 dni jeśli Order.status == OVERDUE;
           brak płatności wcale jeśli Order.status == WRITTEN_OFF — bad debt, zob.
           order_generator.determine_order_status)

  Płatność wychodząca (firma płaci SupplierInvoice):
    DR 2400 Leverandørgjeld           +kwota
    CR 1910 Bankinnskudd driftskonto -kwota
    date = payment_due_date
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.models.bank_transaction import BankTransaction, BankTransactionType
from norfingen.models.order import Order, OrderStatus
from norfingen.models.supplier_invoice import SupplierInvoice
from norfingen.seed.roster import customer_by_id

ACCOUNT_BANK = 1910  # Bankinnskudd, driftskonto
ACCOUNT_KUNDEFORDRINGER = 1500
ACCOUNT_LEVERANDORGJELD = 2400

OVERDUE_PAYMENT_DELAY_DAYS = 90  # OVERDUE płaci payment_terms + 90 dni, nie na czas


def _order_gross_amount(order: Order) -> float:
    return round(sum(line.amountCurrency for line in order.orderLines), 2)


def _incoming_payment_date(order: Order, payment_terms: int) -> Optional[date]:
    """None jeśli WRITTEN_OFF — bad debt, nigdy nie zapłacone. OVERDUE płaci
    z opóźnieniem OVERDUE_PAYMENT_DELAY_DAYS względem normalnego terminu."""
    if order.status == OrderStatus.WRITTEN_OFF:
        return None
    base = order.invoiceDate + timedelta(days=payment_terms)
    if order.status == OrderStatus.OVERDUE:
        return base + timedelta(days=OVERDUE_PAYMENT_DELAY_DAYS)
    return base


def build_incoming_payment(order: Order, payment_terms: int) -> Optional[tuple[BankTransaction, Voucher]]:
    """Klient płaci fakturę sprzedaży (Order) — wpływ na konto bankowe.
    date = order.invoiceDate + payment_terms dni (net 14/30/45 per klient, zob.
    roster.CustomerSeed.payment_terms), skorygowane o Order.status (zob.
    _incoming_payment_date). Zwraca None dla WRITTEN_OFF — brak płatności."""
    assert order.invoiceDate is not None, "Order bez invoiceDate nie generuje płatności"
    payment_date = _incoming_payment_date(order, payment_terms)
    if payment_date is None:
        return None
    amount = _order_gross_amount(order)

    transaction = BankTransaction(
        date=payment_date,
        amount=amount,
        transaction_type=BankTransactionType.INCOMING,
        description=f"Innbetaling faktura K{order.customer.id:02d} — {order.invoiceDate.isoformat()}",
        customer_id=order.customer.id,
        order_id=order.id,
        account_from=ACCOUNT_KUNDEFORDRINGER,
        account_to=ACCOUNT_BANK,
    )

    voucher = Voucher(
        date=payment_date,
        description=f"Innbetaling — faktura K{order.customer.id:02d} {order.invoiceDate.isoformat()}",
        voucherType=VoucherType.BANK,
        postings=[
            Posting(date=payment_date, account=acct(ACCOUNT_BANK), amount=amount, customer=order.customer),
            Posting(date=payment_date, account=acct(ACCOUNT_KUNDEFORDRINGER), amount=-amount, customer=order.customer),
        ],
    )
    assert_voucher_valid(voucher)
    return transaction, voucher


def generate_daily_bank_transactions(
    year: int,
    month: int,
    day: int,
    orders: list[Order],
    supplier_invoices: list[SupplierInvoice],
) -> list[tuple[BankTransaction, Voucher]]:
    """Generuje płatności bankowe wypadające dokładnie na dany dzień —
    dopasowuje wśród `orders`/`supplier_invoices` z poprzednich miesięcy
    (zapłata przychodzi z opóźnieniem payment_terms/payment_due_date, nie
    w miesiącu wystawienia faktury), więc wywołujący musi przekazać dokumenty
    z odpowiednio długiej historii wstecz (max payment_terms = 45 dni + bufor
    na miesiące o różnej długości).

    Zwraca pary (BankTransaction, Voucher) — w przeciwieństwie do
    generate_monthly_orders()/generate_monthly_supplier_invoices() (które
    zwracają same dokumenty, a Voucher buduje osobno wołający), tu para jest
    nierozłączna: BankTransaction bez odpowiadającego Vouchera nie ma sensu
    księgowo, a policzenie Vouchera bez ponownego przeliczania payment_date
    byłoby niepotrzebnym powielaniem logiki z build_incoming_payment/
    build_outgoing_payment."""
    today = date(year, month, day)
    results: list[tuple[BankTransaction, Voucher]] = []

    for order in orders:
        customer = customer_by_id(order.customer.id)
        payment_date = _incoming_payment_date(order, customer.payment_terms)
        if payment_date == today:
            payment = build_incoming_payment(order, customer.payment_terms)
            if payment is not None:
                results.append(payment)

    for invoice in supplier_invoices:
        if invoice.paymentDueDate == today:
            results.append(build_outgoing_payment(invoice))

    return results


def build_outgoing_payment(invoice: SupplierInvoice) -> tuple[BankTransaction, Voucher]:
    """Firma płaci fakturę zakupu (SupplierInvoice) — wypływ z konta bankowego.
    date = invoice.paymentDueDate."""
    assert invoice.paymentDueDate is not None, "SupplierInvoice bez paymentDueDate nie generuje płatności"
    amount = round(invoice.amountCurrency, 2)
    payment_date = invoice.paymentDueDate

    transaction = BankTransaction(
        date=payment_date,
        amount=amount,
        transaction_type=BankTransactionType.OUTGOING,
        description=f"Utbetaling {invoice.invoiceNumber}",
        supplier_id=invoice.supplier.id,
        supplier_invoice_id=invoice.id,
        account_from=ACCOUNT_BANK,
        account_to=ACCOUNT_LEVERANDORGJELD,
    )

    voucher = Voucher(
        date=payment_date,
        description=f"Utbetaling {invoice.invoiceNumber}",
        voucherType=VoucherType.BANK,
        postings=[
            Posting(date=payment_date, account=acct(ACCOUNT_LEVERANDORGJELD), amount=amount, supplier=invoice.supplier),
            Posting(date=payment_date, account=acct(ACCOUNT_BANK), amount=-amount, supplier=invoice.supplier),
        ],
    )
    assert_voucher_valid(voucher)
    return transaction, voucher
