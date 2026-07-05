from norfingen.generators.order_generator import apply_annual_inflation
from norfingen.generators.supplier_invoice_generator import (
    MICROSOFT_COST_LINES,
    build_voucher_for_invoice,
    generate_monthly_supplier_invoices,
)
from norfingen.seed.roster import supplier_by_number


def test_microsoft_cost_split_into_four_invoices():
    invoices = generate_monthly_supplier_invoices(2024, 1)
    l01_invoices = [i for i in invoices if i.invoiceNumber.startswith("L01")]
    assert len(l01_invoices) == 4
    assert len({i.invoiceNumber for i in l01_invoices}) == 4  # numery unikalne


def test_microsoft_total_cost_matches_base_year_2019():
    # Suma bazowa (rok 2019, przed inflacją) = 53 100 NOK/mies. — niżej niż
    # poprzednie płaskie 85 000, zamierzone (stara kwota była ekonomicznie
    # nieuzasadniona, zob. docs/SESSION_HANDOFF.md).
    invoices = generate_monthly_supplier_invoices(2019, 1)
    l01_invoices = [i for i in invoices if i.invoiceNumber.startswith("L01")]
    total_netto = sum(i.amountExcludingVatCurrency for i in l01_invoices)
    expected = sum(line["base_monthly"] for line in MICROSOFT_COST_LINES)
    assert expected == 53_100
    assert round(total_netto) == expected


def test_microsoft_cost_inflates_over_years():
    invoices_2019 = generate_monthly_supplier_invoices(2019, 1)
    invoices_2024 = generate_monthly_supplier_invoices(2024, 1)
    total_2019 = sum(i.amountExcludingVatCurrency for i in invoices_2019 if i.invoiceNumber.startswith("L01"))
    total_2024 = sum(i.amountExcludingVatCurrency for i in invoices_2024 if i.invoiceNumber.startswith("L01"))
    expected_2024 = sum(round(apply_annual_inflation(line["base_monthly"], 2024), 2) for line in MICROSOFT_COST_LINES)
    assert round(total_2024) == round(expected_2024)
    assert total_2024 > total_2019


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


def test_l07_avis_higher_in_q1_q3_than_q2_q4():
    q1_q3_amounts = []
    q2_q4_amounts = []
    for year in range(2019, 2027):
        for month in range(1, 13):
            invoices = generate_monthly_supplier_invoices(year, month)
            l07 = next(i for i in invoices if i.invoiceNumber.startswith("L07"))
            netto = l07.amountExcludingVatCurrency
            if month in (1, 2, 3, 7, 8, 9):
                assert 22_000 <= netto <= 28_000
                q1_q3_amounts.append(netto)
            else:
                assert 12_000 <= netto <= 18_000
                q2_q4_amounts.append(netto)
    assert min(q1_q3_amounts) > max(q2_q4_amounts)


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
