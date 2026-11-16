"""Audit 2026-11-16, phase 2: input VAT on COGS (4291 / 4292) and on cash purchases of operating material (4290).

Before: 92 mln NOK of COGS carried no VAT at all, so input VAT was ~4 mln against 53 mln output VAT. Now a domestic
purchase is Dr cost (net) + Dr 2710 (25 %) / Cr 2400 or 1910 (gross); the NET cost is unchanged (golden hash
opex_net_amounts), so the margin does not move - the VAT is a receivable, the liability to the supplier is gross."""
from datetime import date

from norfingen.generators.bank_transaction_generator import build_cogs_payment
from norfingen.generators.opex_generator import (
    _cash_purchase_voucher,
    _cogs_accrual_voucher,
    _reverse_charge_cogs_voucher,
    cogs_payable_for,
    generate_monthly_opex,
)
from norfingen.models.base import TripletexRef

D = date(2024, 5, 31)


def _by_account(voucher):
    return {p.account.number: p for p in voucher.postings}


def test_cogs_accrual_books_vat_as_its_own_posting_and_credits_gross_to_the_supplier():
    v = _cogs_accrual_voucher(D, 4291, "Videresalgskostnad Microsoft/Azure mai 2024", 22_000.0)
    posts = _by_account(v)
    assert posts[4291].amount == 22_000.0 and posts[4291].vatAmount == 5_500.0
    assert posts[2710].amount == 5_500.0
    assert posts[2400].amount == -27_500.0
    assert abs(sum(p.amount for p in v.postings)) < 0.005
    assert all(p.supplier is not None for p in v.postings)  # 4291 / 4292 / 2710 / 2400 all carry the supplier


def test_vat_is_25_percent_of_net_to_the_cent_and_the_voucher_balances_exactly():
    for net in (1234.5, 0.01, 99_999.99, 53_333.33, 312.62):
        v = _cogs_accrual_voucher(D, 4292, "x", net)
        posts = _by_account(v)
        assert posts[2710].amount == round(round(net, 2) * 0.25, 2)
        assert round(sum(p.amount for p in v.postings), 2) == 0.0


def test_account_4290_is_a_cash_purchase_with_vat_and_no_supplier():
    v = _cash_purchase_voucher(D, 4290, "Driftsmateriell for kundeleveranse — K01", 63_600.0)
    posts = _by_account(v)
    assert posts[4290].amount == 63_600.0 and posts[4290].vatAmount == 15_900.0
    assert posts[2710].amount == 15_900.0
    assert posts[1910].amount == -79_500.0  # the bank pays gross
    assert 2400 not in posts
    assert all(p.supplier is None for p in v.postings)
    assert cogs_payable_for(v) is None  # paid at once: no payable


def test_reverse_charge_voucher_nets_input_and_output_vat():
    supplier = TripletexRef(id=7)
    v = _reverse_charge_cogs_voucher(D, 4291, "foreign", 10_000.0, supplier)
    posts = _by_account(v)
    assert posts[2710].amount == 2_500.0 and posts[2700].amount == -2_500.0
    assert posts[2400].amount == -10_000.0  # the foreign supplier is owed the NET amount only
    assert round(sum(p.amount for p in v.postings), 2) == 0.0


def test_payable_is_gross_and_its_payment_clears_2400_to_the_cent():
    v = _cogs_accrual_voucher(D, 4292, "Driftskostnad Managed IT Support mai 2024", 53_000.0)
    payable = cogs_payable_for(v)
    assert (payable.amount_excluding_vat_currency, payable.vat_amount_currency, payable.amount_currency) == (
        53_000.0, 13_250.0, 66_250.0)
    assert payable.supplier_id == _by_account(v)[2400].supplier.id and payable.account_number == 4292
    payable.id = 1
    transaction, payment = build_cogs_payment(payable)
    assert transaction.amount == 66_250.0
    assert _by_account(payment)[2400].amount == 66_250.0  # equals what the accrual credited


def test_every_generated_cogs_and_equipment_voucher_carries_the_vat():
    seen = {4290: 0, 4291: 0, 4292: 0}
    for year, month in ((2020, 3), (2022, 11), (2024, 5), (2026, 8)):
        for v in generate_monthly_opex(year, month):
            posts = _by_account(v)
            for account in seen:
                if account in posts:
                    seen[account] += 1
                    assert posts[2710].amount == round(posts[account].amount * 0.25, 2)
                    assert posts[account].vatAmount == posts[2710].amount
    assert seen[4291] and seen[4292]
