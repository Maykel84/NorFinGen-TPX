from datetime import date

from norfingen.models import (
    ActivityType,
    BankTransaction,
    BankTransactionType,
    HourEntry,
    Order,
    OrderLine,
    Product,
    SalarySpecification,
    SalaryTransaction,
    Payslip,
    SupplierInvoice,
)
from norfingen.models.base import TripletexRef
from norfingen.models.salary import WAGE_TYPE_FAST_LONN, WAGE_TYPE_SKATTETREKK


def test_bank_transaction_incoming_from_customer():
    tx = BankTransaction(
        date=date(2024, 1, 15),
        amount=250_000.0,
        transaction_type=BankTransactionType.INCOMING,
        description="Betaling K01-2024-001",
        customer_id=1,
        order_id=1,
        account_from=1500,
        account_to=1910,
    )
    assert tx.amount == 250_000.0
    assert tx.supplier_id is None
    assert tx.transaction_type == BankTransactionType.INCOMING


def test_hour_entry_billable_requires_project():
    entry = HourEntry(
        date=date(2024, 1, 15),
        employee_id=2,
        project_id=1,
        activity_type=ActivityType.BILLABLE,
        hours=7.5,
        description="IT Support — Bergström",
    )
    assert entry.project_id == 1
    assert entry.activity_type == ActivityType.BILLABLE


def test_hour_entry_internal_and_sick_without_project():
    internal = HourEntry(date=date(2024, 1, 16), employee_id=2, activity_type=ActivityType.INTERNAL, hours=1.0)
    sick = HourEntry(date=date(2024, 1, 17), employee_id=2, activity_type=ActivityType.SICK, hours=7.5)
    assert internal.project_id is None
    assert sick.project_id is None


def test_bank_transaction_outgoing_to_supplier():
    tx = BankTransaction(
        date=date(2024, 1, 20),
        amount=85_000.0,
        transaction_type=BankTransactionType.OUTGOING,
        description="Betaling L01-2024-001",
        supplier_id=1,
        supplier_invoice_id=1,
        account_from=1910,
        account_to=2400,
    )
    assert tx.customer_id is None
    assert tx.transaction_type == BankTransactionType.OUTGOING


def test_product():
    p = Product(name="IT Support — Enterprise", number="P01", salesPrice=220_000)
    assert p.vatType.id == 3


def test_order_line_computed_amounts():
    line = OrderLine(order=TripletexRef(id=1), product=TripletexRef(id=1), count=1.0, unitPriceExcludingVatCurrency=220_000)
    assert line.amountExcludingVatCurrency == 220_000
    assert line.amountCurrency == 275_000


def test_order_with_lines():
    order = Order(customer=TripletexRef(id=1), orderDate=date(2024, 1, 1), invoiceDate=date(2024, 1, 1))
    assert order.invoicesDueIn == 30
    assert order.orderLines == []


def test_supplier_invoice_defaults_and_vat_split():
    inv = SupplierInvoice(
        invoiceNumber="L01-2024-001",
        supplier=TripletexRef(id=1),
        invoiceDate=date(2024, 1, 1),
        amountCurrency=106_250,
    )
    assert inv.receivedDate == date(2024, 1, 1)
    assert inv.paymentDueDate == date(2024, 1, 31)
    assert round(inv.vatAmountCurrency) == 21_250
    assert round(inv.amountExcludingVatCurrency) == 85_000
    assert inv.status == "UNPAID"


def test_payslip_amount_sums_specifications():
    payslip = Payslip(
        transaction=TripletexRef(id=1),
        employee=TripletexRef(id=1),
        specifications=[
            SalarySpecification(wageType=WAGE_TYPE_FAST_LONN, description="Fast lønn", amount=73_333),
            SalarySpecification(wageType=WAGE_TYPE_SKATTETREKK, description="Skattetrekk", amount=-24_200),
        ],
    )
    assert payslip.amount == 49_133


def test_salary_transaction_defaults():
    tx = SalaryTransaction(date=date(2024, 1, 31), year=2024, month=1)
    assert tx.status == "OPEN"
    assert tx.payslips == []
