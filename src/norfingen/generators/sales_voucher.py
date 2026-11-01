"""Sales invoice -> ledger voucher (phase 3, docs/SPEC_poprawki_ksiegowe.md).

In real Tripletex an Order with an invoiceDate makes the system book the sales voucher itself. NorFinGen does not
call the API, so until this phase the ledger held no revenue, no receivable and no output VAT: `vouchers`/`postings`
showed only the money coming IN (customer payments, Dr 1910 / Cr 1500) with nothing on the other side, and account 1500
sat at -185 mln NOK. Now every invoice books:

    Dr 1500 Kundefordringer          gross     (customer dimension: accounts-receivable ageing)
    Cr 3000 Salgsinntekt             net       (department dimension; vatType "3", vatAmount = the VAT it contains)
    Cr 2700 Utgående merverdiavgift  VAT       (own posting, as for input VAT in phase 2)

dated on the invoice date - weekends included, an invoice keeps its own date.

One amount, one source. `order_gross_amount()` is the single definition of what a customer owes for an Order, and
both this voucher (Dr 1500) and the customer's payment (Dr 1910 / Cr 1500, bank_transaction_generator) take it from
here, so the receivable clears to the grosz when the customer pays. For an Order read back from the database it is the
stored SUM(order_lines.amount_currency); for a fresh Order it is the sum of the lines rounded the way Postgres will
round them (generators/money.py). The net amount is built the same way, so the revenue in the ledger equals the
revenue in `order_lines` (gl_checks T4) and no amount of the sales side changes - only its booking appears.

Revenue goes to 3000 only. 3100 (Lisensintekter) exists in the chart of accounts and is the `gl_account` of the licence
products in the roster, but the specification books revenue on 3000 and the P&L views read revenue from `orders`, so
splitting off licences would change no figure; it stays unused until someone wants a revenue breakdown.
"""

from __future__ import annotations

from norfingen.generators.money import pg_round2
from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.models.order import Order
from norfingen.models.product import SALES_VAT_TYPE_REF
from norfingen.seed.roster import customer_by_id

ACCOUNT_RECEIVABLES = 1500  # Kundefordringer
ACCOUNT_SALES_REVENUE = 3000  # Salgsinntekt, avgiftspliktig
ACCOUNT_OUTPUT_VAT = 2700  # Utgående merverdiavgift


def order_gross_amount(order: Order) -> float:
    """What the customer owes for the invoice (incl. VAT) - the one definition, shared by the sales voucher and the
    payment. Read from the database when the Order came from there, otherwise rounded as Postgres will store it."""
    if order.storedGrossAmountCurrency is not None:
        return round(order.storedGrossAmountCurrency, 2)
    return round(sum(pg_round2(line.amountCurrency) for line in order.orderLines), 2)


def order_net_amount(order: Order) -> float:
    """Revenue of the invoice (excl. VAT), rounded line by line as Postgres stores it."""
    return round(sum(pg_round2(line.amountExcludingVatCurrency) for line in order.orderLines), 2)


def build_sales_voucher(order: Order) -> Voucher:
    """The OUTGOING_INVOICE voucher for one Order. The VAT line is gross - net (both already to the cent), so the voucher
    balances exactly by construction; an invoice with no VAT gets no 2700 line."""
    assert order.invoiceDate is not None, "An Order without invoiceDate is not an invoice"
    customer = customer_by_id(order.customer.id)
    net = order_net_amount(order)
    gross = order_gross_amount(order)
    vat = round(gross - net, 2)
    day = order.invoiceDate

    postings = [
        Posting(date=day, account=acct(ACCOUNT_RECEIVABLES), amount=gross, customer=order.customer),
        Posting(
            date=day, account=acct(ACCOUNT_SALES_REVENUE), amount=-net, department=order.department,
            vatType=SALES_VAT_TYPE_REF if vat else None, vatAmount=vat or None,
        ),
    ]
    if vat:
        postings.append(Posting(date=day, account=acct(ACCOUNT_OUTPUT_VAT), amount=-vat, vatType=SALES_VAT_TYPE_REF))

    voucher = Voucher(
        date=day,
        description=f"Faktura {customer.number} {day.isoformat()} — {customer.name}",
        voucherType=VoucherType.OUTGOING_INVOICE,
        postings=postings,
    )
    assert_voucher_valid(voucher)
    return voucher
