"""Phase 2 (docs/SPEC_poprawki_ksiegowe.md): input VAT is its own posting, vouchers balance strictly.

Before: an INCOMING_INVOICE voucher was Dr cost (net) / Cr 2400 (gross) with the VAT only as a
`vatAmount` field. It never balanced - by exactly its VAT - and validate_balance() excused the gap, so the
ledger as a whole was out of balance by the sum of input VAT (3.7 mln NOK, gl_checks T1/T2/T6).
After: Dr cost (net) + Dr 2710 (VAT) / Cr 2400 (gross), balanced to the cent.
"""

import pytest
from datetime import date

from norfingen.generators.backfill import months_range
from norfingen.generators.bank_transaction_generator import build_outgoing_payment
from norfingen.generators.supplier_invoice_generator import build_voucher_for_invoice, generate_monthly_supplier_invoices
from norfingen.generators.voucher import (
    BALANCE_TOLERANCE,
    Posting,
    Voucher,
    VoucherType,
    acct,
    assert_voucher_valid,
)
from norfingen.models.base import TripletexRef
from norfingen.models.supplier_invoice import SupplierInvoice
from norfingen.seed.roster import supplier_by_number

MONTHS = months_range(date(2019, 1, 1), date(2026, 12, 31))


def _supplier_of(invoice):
    return supplier_by_number(invoice.invoiceNumber.split("-")[0])


def _all_invoices():
    for year, month in MONTHS:
        yield from generate_monthly_supplier_invoices(year, month)


def test_every_invoice_voucher_has_the_three_legs_and_balances_to_the_cent():
    n = 0
    for invoice in _all_invoices():
        voucher = build_voucher_for_invoice(invoice, _supplier_of(invoice))
        net, gross = round(invoice.amountExcludingVatCurrency, 2), round(invoice.amountCurrency, 2)
        by_account = {p.account.number: p.amount for p in voucher.postings}

        assert len(voucher.postings) == 3
        assert by_account[2710] == round(gross - net, 2) > 0          # Dr input VAT
        assert by_account[2400] == -gross                              # Cr supplier ledger, gross
        cost_accounts = [a for a in by_account if a not in (2710, 2400)]
        assert len(cost_accounts) == 1 and by_account[cost_accounts[0]] == net  # Dr cost / capitalisation, net
        assert abs(sum(p.amount for p in voucher.postings)) <= BALANCE_TOLERANCE
        assert voucher.validate_balance()
        n += 1
    assert n > 700


def test_phase2_only_added_the_vat_line_nothing_else_moved():
    """Strip the 2710 line and what remains is exactly the pre-phase-2 voucher: cost at net, 2400 at gross.
    So no cost line - hence no P&L figure - changed."""
    for invoice in _all_invoices():
        voucher = build_voucher_for_invoice(invoice, _supplier_of(invoice))
        rest = [p for p in voucher.postings if p.account.number != 2710]
        assert [p.amount for p in rest] == [round(invoice.amountExcludingVatCurrency, 2), -round(invoice.amountCurrency, 2)]


def test_vat_posting_agrees_with_the_invoice_vat_to_within_rounding():
    """gl_checks T6 compares the sum of Dr 2710 with the sum of supplier_invoices.vat_amount_currency. Per invoice the
    posting (gross - net, both rounded) and the stored VAT (rounded float) can differ by a cent at most."""
    worst = 0.0
    for invoice in _all_invoices():
        voucher = build_voucher_for_invoice(invoice, _supplier_of(invoice))
        posted = next(p.amount for p in voucher.postings if p.account.number == 2710)
        worst = max(worst, abs(posted - invoice.vatAmountCurrency))
    assert worst <= 0.011, f"worst per-invoice VAT difference {worst:.4f}"


def test_the_ledger_credit_equals_the_payment_so_2400_clears():
    """T8 prerequisite: what the invoice voucher credits to 2400 is exactly what the bank payment debits."""
    for invoice in list(_all_invoices())[:300]:
        voucher = build_voucher_for_invoice(invoice, _supplier_of(invoice))
        credit = -next(p.amount for p in voucher.postings if p.account.number == 2400)
        payment, bank_voucher = build_outgoing_payment(invoice)
        assert credit == payment.amount == next(p.amount for p in bank_voucher.postings if p.account.number == 2400)


def test_zero_vat_invoice_gets_no_2710_line_and_still_balances():
    tiny = SupplierInvoice(
        invoiceNumber="L02-2024-001", supplier=TripletexRef(id=2), invoiceDate=date(2024, 1, 5),
        amountCurrency=0.01, account=TripletexRef(id=6900),
    )
    voucher = build_voucher_for_invoice(tiny, supplier_by_number("L02"))
    assert 2710 not in {p.account.number for p in voucher.postings}
    assert voucher.validate_balance()


# --- strict balance ----------------------------------------------------------------------------

def test_vat_amount_no_longer_excuses_an_imbalance():
    """Dr 100 (vatAmount 25) / Cr 125 balanced under the old rule ('the gap equals the vatAmount'). It must not now."""
    voucher = Voucher(date=date(2024, 1, 1), voucherType=VoucherType.MANUAL, postings=[
        Posting(date=date(2024, 1, 1), account=acct(6900), amount=100.0, vatAmount=25.0),
        Posting(date=date(2024, 1, 1), account=acct(2400), amount=-125.0),
    ])
    assert not voucher.validate_balance()
    with pytest.raises(AssertionError, match="Unbalanced"):
        assert_voucher_valid(voucher)


def test_a_cent_off_is_rejected_and_float_noise_is_not():
    def v(amount):
        return Voucher(date=date(2024, 1, 1), voucherType=VoucherType.MANUAL, postings=[
            Posting(date=date(2024, 1, 1), account=acct(6900), amount=amount),
            Posting(date=date(2024, 1, 1), account=acct(2400), amount=-100.0),
        ])
    assert v(100.0).validate_balance()
    assert v(100.0 + 1e-11).validate_balance()          # float noise
    assert not v(100.01).validate_balance()             # a cent
    assert not v(99.99).validate_balance()


def test_sales_invoice_voucher_type_replaces_the_dead_invoice_type():
    assert VoucherType.OUTGOING_INVOICE.value == "OUTGOING_INVOICE"
    with pytest.raises(ValueError):
        VoucherType("INVOICE")
