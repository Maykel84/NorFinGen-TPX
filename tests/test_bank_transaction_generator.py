from datetime import date, timedelta

from norfingen.generators.bank_transaction_generator import (
    OVERDUE_PAYMENT_DELAY_DAYS,
    build_incoming_payment,
    build_outgoing_payment,
    generate_daily_bank_transactions,
)
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.supplier_invoice_generator import generate_monthly_supplier_invoices
from norfingen.models.bank_transaction import BankTransactionType
from norfingen.models.order import OrderStatus
from norfingen.seed.roster import customer_by_number


def test_incoming_payment_matches_order_gross_amount():
    orders = generate_monthly_orders(2024, 1)
    order = next(o for o in orders if o.customer.id == 1)  # K01, payment_terms=30
    expected_gross = round(sum(line.amountCurrency for line in order.orderLines), 2)

    transaction, voucher = build_incoming_payment(order, payment_terms=30)

    assert transaction.transaction_type == BankTransactionType.INCOMING
    assert transaction.amount == expected_gross
    assert transaction.customer_id == 1
    assert transaction.account_from == 1500
    assert transaction.account_to == 1910
    assert transaction.date == order.invoiceDate + timedelta(days=30)

    assert voucher.validate_balance()
    dr = next(p for p in voucher.postings if p.account.number == 1910)
    cr = next(p for p in voucher.postings if p.account.number == 1500)
    assert dr.amount == expected_gross
    assert cr.amount == -expected_gross
    assert dr.customer.id == 1
    assert voucher.date == transaction.date


def test_outgoing_payment_matches_supplier_invoice_gross_amount():
    invoices = generate_monthly_supplier_invoices(2024, 1)
    invoice = invoices[0]

    transaction, voucher = build_outgoing_payment(invoice)

    assert transaction.transaction_type == BankTransactionType.OUTGOING
    assert transaction.amount == round(invoice.amountCurrency, 2)
    assert transaction.supplier_id == invoice.supplier.id
    assert transaction.account_from == 1910
    assert transaction.account_to == 2400
    assert transaction.date == invoice.paymentDueDate

    assert voucher.validate_balance()
    dr = next(p for p in voucher.postings if p.account.number == 2400)
    cr = next(p for p in voucher.postings if p.account.number == 1910)
    assert dr.amount == round(invoice.amountCurrency, 2)
    assert cr.amount == -round(invoice.amountCurrency, 2)
    assert dr.supplier.id == invoice.supplier.id


def test_written_off_order_never_generates_incoming_payment():
    orders = generate_monthly_orders(2024, 1)
    order = next(o for o in orders if o.customer.id == 1)
    written_off_order = order.model_copy(update={"status": OrderStatus.WRITTEN_OFF})

    assert build_incoming_payment(written_off_order, payment_terms=30) is None


def test_overdue_order_delays_payment_by_extra_days():
    orders = generate_monthly_orders(2024, 1)
    order = next(o for o in orders if o.customer.id == 1)
    overdue_order = order.model_copy(update={"status": OrderStatus.OVERDUE})

    normal_date = order.invoiceDate + timedelta(days=30)
    transaction, voucher = build_incoming_payment(overdue_order, payment_terms=30)

    assert transaction.date == normal_date + timedelta(days=OVERDUE_PAYMENT_DELAY_DAYS)
    assert voucher.validate_balance()


def test_generate_daily_bank_transactions_skips_written_off_order():
    orders = generate_monthly_orders(2024, 1)
    order = next(o for o in orders if o.customer.id == 1)
    written_off_order = order.model_copy(update={"status": OrderStatus.WRITTEN_OFF})
    payment_date = order.invoiceDate + timedelta(days=30)

    results = generate_daily_bank_transactions(
        payment_date.year, payment_date.month, payment_date.day, [written_off_order], []
    )
    assert results == []


def test_all_incoming_payments_balance():
    for month in range(1, 13):
        orders = generate_monthly_orders(2024, month)
        for order in orders:
            _, voucher = build_incoming_payment(order, payment_terms=30)
            assert voucher.validate_balance()


def test_all_outgoing_payments_balance():
    for month in range(1, 13):
        invoices = generate_monthly_supplier_invoices(2024, month)
        for invoice in invoices:
            _, voucher = build_outgoing_payment(invoice)
            assert voucher.validate_balance()


def test_generate_daily_bank_transactions_incoming_on_payment_day():
    # K02: invoice_day=7, payment_terms=14 -> zapłata 2024-01-21
    k02 = customer_by_number("K02")
    orders = generate_monthly_orders(2024, 1)
    order = next(o for o in orders if o.customer.id == 2)
    payment_day = order.invoiceDate + timedelta(days=k02.payment_terms)

    on_day = generate_daily_bank_transactions(payment_day.year, payment_day.month, payment_day.day, [order], [])
    assert len(on_day) == 1
    transaction, voucher = on_day[0]
    assert transaction.transaction_type == BankTransactionType.INCOMING
    assert transaction.customer_id == 2
    assert voucher.validate_balance()

    other_day = generate_daily_bank_transactions(
        payment_day.year, payment_day.month, payment_day.day + 1, [order], []
    )
    assert other_day == []


def test_generate_daily_bank_transactions_outgoing_on_due_date():
    invoices = generate_monthly_supplier_invoices(2024, 1)
    invoice = invoices[0]

    on_day = generate_daily_bank_transactions(
        invoice.paymentDueDate.year, invoice.paymentDueDate.month, invoice.paymentDueDate.day, [], [invoice]
    )
    assert len(on_day) == 1
    transaction, voucher = on_day[0]
    assert transaction.transaction_type == BankTransactionType.OUTGOING
    assert transaction.supplier_id == invoice.supplier.id
    assert voucher.validate_balance()


def test_generate_daily_bank_transactions_combines_incoming_and_outgoing():
    k02 = customer_by_number("K02")
    orders = generate_monthly_orders(2024, 1)
    order = next(o for o in orders if o.customer.id == 2)
    payment_day = order.invoiceDate + timedelta(days=k02.payment_terms)

    invoices = generate_monthly_supplier_invoices(2024, 1)
    invoice = invoices[0].model_copy(update={"paymentDueDate": payment_day})

    results = generate_daily_bank_transactions(
        payment_day.year, payment_day.month, payment_day.day, [order], [invoice]
    )
    types = {t.transaction_type for t, _ in results}
    assert types == {BankTransactionType.INCOMING, BankTransactionType.OUTGOING}
