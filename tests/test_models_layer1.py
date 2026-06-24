from datetime import date

from norfingen.models import (
    Account,
    AccountType,
    Customer,
    Department,
    Employee,
    Employment,
    Supplier,
    VatType,
)


def test_department():
    d = Department(name="Salg", number="1")
    assert d.isInactive is False


def test_employee_with_employment():
    e = Employee(firstName="Erik", lastName="Strand", employeeNumber="E01")
    emp = Employment(startDate=date(2019, 1, 2))
    assert emp.weeklyWorkingHours == 37.5
    assert e.allowInformationRegistration is True


def test_customer():
    c = Customer(name="Bergström Industri AS", customerNumber="K01")
    assert c.invoicesDueIn == 30
    assert c.currency.id == 1


def test_supplier():
    s = Supplier(name="Microsoft Norge AS", supplierNumber="L01")
    assert s.isWholesaler is False


def test_account():
    a = Account(number=3000, name="Salgsinntekter, IT-tjenester", type=AccountType.OPERATING_INCOME)
    assert a.number == 3000


def test_vat_type():
    v = VatType(name="Utgående MVA, 25%", vatCode="3", percentage=25.0)
    assert v.percentage == 25.0
