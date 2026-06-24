from datetime import date

from norfingen.models import (
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
