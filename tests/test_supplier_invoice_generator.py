from norfingen.generators.supplier_invoice_generator import build_voucher_for_invoice, generate_monthly_supplier_invoices
from norfingen.seed.roster import supplier_by_number


def test_l01_microsoft_fixed_amount_every_month():
    invoices = generate_monthly_supplier_invoices(2024, 1)
    l01 = next(i for i in invoices if i.invoiceNumber.startswith("L01"))
    assert round(l01.amountExcludingVatCurrency) == 85_000


def test_l04_statsbygg_fixed_rent():
    invoices = generate_monthly_supplier_invoices(2024, 1)
    l04 = next(i for i in invoices if i.invoiceNumber.startswith("L04"))
    assert round(l04.amountExcludingVatCurrency) == 45_000


def test_l06_thommessen_quarterly_only():
    months_with_invoice = []
    for month in range(1, 13):
        invoices = generate_monthly_supplier_invoices(2024, month)
        if any(i.invoiceNumber.startswith("L06") for i in invoices):
            months_with_invoice.append(month)
    assert months_with_invoice == [3, 6, 9, 12]


def test_l08_nordic_insurance_quarterly_fixed():
    for month in [1, 4, 7, 10]:
        invoices = generate_monthly_supplier_invoices(2024, month)
        l08 = next(i for i in invoices if i.invoiceNumber.startswith("L08"))
        assert round(l08.amountExcludingVatCurrency) == 38_000


def test_l05_capitalization_split():
    found_capitalized = False
    found_expensed = False
    for month in range(1, 13):
        invoices = generate_monthly_supplier_invoices(2024, month)
        l05 = next((i for i in invoices if i.invoiceNumber.startswith("L05")), None)
        if l05 is None:
            continue
        supplier = supplier_by_number("L05")
        voucher = build_voucher_for_invoice(l05, supplier)
        assert voucher.validate_balance()
        dr_posting = voucher.postings[0]
        if l05.amountExcludingVatCurrency >= 30_000:
            assert dr_posting.account.number == 1200
            found_capitalized = True
        else:
            assert dr_posting.account.number == 6540
            found_expensed = True
    assert found_capitalized or found_expensed  # przynajmniej jedna faktura w roku


def test_payment_due_date_is_invoice_date_plus_30_days():
    invoices = generate_monthly_supplier_invoices(2024, 1)
    for invoice in invoices:
        assert (invoice.paymentDueDate - invoice.invoiceDate).days == 30


def test_voucher_balances_for_all_invoices():
    for month in range(1, 13):
        invoices = generate_monthly_supplier_invoices(2024, month)
        for invoice in invoices:
            supplier_number = invoice.invoiceNumber.split("-")[0]
            supplier = supplier_by_number(supplier_number)
            voucher = build_voucher_for_invoice(invoice, supplier)
            assert voucher.validate_balance(), f"Niezbalansowany voucher dla {invoice.invoiceNumber}"
