"""Testy run_daily.py z zamockowanymi funkcjami repository — weryfikują logikę
orkiestracji (co jest wołane, kiedy, z jakimi argumentami), bez połączenia
z prawdziwym Supabase."""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from norfingen.models.supplier_invoice import SupplierInvoice, SupplierInvoiceStatus
from norfingen.generators.voucher import Voucher, VoucherType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_daily as run_daily_module  # noqa: E402


def _patch_repository(**overrides):
    defaults = dict(
        ensure_schema=MagicMock(),
        seed_reference_data=MagicMock(),
        get_orders_for_payment_window=MagicMock(return_value=[]),
        get_orders_to_write_off=MagicMock(return_value=[]),
        save_write_off=MagicMock(),
        get_unpaid_supplier_invoices=MagicMock(return_value=[]),
        get_unpaid_cogs_payables=MagicMock(return_value=[]),
        get_unpaid_vat_settlements=MagicMock(return_value=[]),
        get_vat_period_totals=MagicMock(return_value=(0.0, 0.0)),
        save_vat_settlement=MagicMock(),
        save_cogs_accrual=MagicMock(),
        save_orders=MagicMock(),
        save_all=MagicMock(),
        save_bank_transactions=MagicMock(),
        save_hour_entries=MagicMock(),
        save_salary=MagicMock(),
    )
    defaults.update(overrides)
    return defaults


def test_run_daily_generates_orders_on_invoice_day():
    # K01 invoice_day=3
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        stats = run_daily_module.run_daily(date(2024, 1, 3))

    assert stats["orders"] >= 1
    mocks["save_orders"].assert_called_once()


def test_run_daily_no_orders_on_non_invoice_day():
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        stats = run_daily_module.run_daily(date(2024, 1, 30))

    assert stats["orders"] == 0
    mocks["save_orders"].assert_not_called()


def test_run_daily_salary_only_on_last_working_day():
    # Styczeń 2024: 31.01.2024 to środa -> ostatni dzień roboczy = 31.01.2024
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        stats_last_day = run_daily_module.run_daily(date(2024, 1, 31))
        stats_other_day = run_daily_module.run_daily(date(2024, 1, 15))

    assert stats_last_day["salary"] == 1
    assert stats_other_day["salary"] == 0
    mocks["save_salary"].assert_called_once()


def test_run_daily_hours_generated_on_weekday():
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        stats = run_daily_module.run_daily(date(2024, 1, 8))  # poniedziałek

    assert stats["hour_entries"] > 0
    mocks["save_hour_entries"].assert_called_once()


def test_run_daily_no_hours_on_weekend():
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        stats = run_daily_module.run_daily(date(2024, 1, 6))  # sobota

    assert stats["hour_entries"] == 0
    mocks["save_hour_entries"].assert_not_called()


def test_run_daily_calls_ensure_schema_and_seed_every_time():
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        run_daily_module.run_daily(date(2024, 1, 30))

    mocks["ensure_schema"].assert_called_once()
    mocks["seed_reference_data"].assert_called_once()


# --- phase 0.5b: one pipeline for history and the current day -----------------------------------

def _saved(mocks, cls):
    return [c.args[0] for c in mocks["save_all"].call_args_list if isinstance(c.args[0], cls)]


def test_run_daily_saves_supplier_invoice_with_voucher_on_its_date():
    # 2024-01-05 = L02 Telenor's monthly invoice day
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        stats = run_daily_module.run_daily(date(2024, 1, 5))

    invoices = _saved(mocks, SupplierInvoice)
    vouchers = _saved(mocks, Voucher)
    assert stats["supplier_invoices"] == len(invoices) >= 1
    assert all(i.invoiceDate == date(2024, 1, 5) for i in invoices)
    assert all(i.status == SupplierInvoiceStatus.UNPAID for i in invoices)  # PAID only via a booked payment
    assert sum(v.voucherType == VoucherType.INCOMING_INVOICE for v in vouchers) == len(invoices)


def test_run_daily_saves_month_end_operating_costs_and_cogs_on_the_last_working_day():
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        stats = run_daily_module.run_daily(date(2024, 2, 29))

    # COGS accruals go through save_cogs_accrual (they get a payable), the cash costs through save_all
    costs = [v for v in _saved(mocks, Voucher) if v.voucherType == VoucherType.OPERATING_COST]
    costs += [c.args[0] for c in mocks["save_cogs_accrual"].call_args_list]
    assert stats["operating_costs"] == len(costs) >= 3  # canteen, S01 COGS, S02 COGS (representation has its own day)
    assert all(v.date == date(2024, 2, 29) for v in costs)


def test_run_daily_books_founding_capital_once_on_its_date():
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        run_daily_module.run_daily(date(2019, 1, 2))
        mocks["save_all"].reset_mock()
        run_daily_module.run_daily(date(2019, 1, 3))

    assert not [v for v in _saved(mocks, Voucher) if v.voucherType == VoucherType.MANUAL]  # not on the 3rd

    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        run_daily_module.run_daily(date(2019, 1, 2))
    manual = [v for v in _saved(mocks, Voucher) if v.voucherType == VoucherType.MANUAL]
    # the share capital and (audit 2026-11-16, phase 3) the owner's start-up loan, both on the founding day
    assert len(manual) == 2 and {v.date for v in manual} == {date(2019, 1, 2)}


def test_run_daily_creates_customer_event_orders_that_the_old_daily_path_never_made():
    # 2026-10-25 (Sunday): extra-consulting orders for K02/K07/K16/K32 existed only in the monthly path.
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        stats = run_daily_module.run_daily(date(2026, 10, 25))

    saved_orders = mocks["save_orders"].call_args.args[0]
    assert {o.customer.id for o in saved_orders} >= {2, 7, 16, 32}
    assert stats["orders"] == len(saved_orders)


# --- phase 3: every invoice is booked in the ledger the day it is issued -----------------------------

def test_run_daily_books_a_sales_voucher_for_every_order_of_the_day():
    # 2026-10-03 is a Saturday: K01 and K20 are invoiced that day (weekend invoice_day).
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        stats = run_daily_module.run_daily(date(2026, 10, 3))

    saved_orders = mocks["save_orders"].call_args.args[0]
    sales = [v for v in _saved(mocks, Voucher) if v.voucherType == VoucherType.OUTGOING_INVOICE]
    assert stats["orders"] == len(saved_orders) >= 2
    assert len(sales) == len(saved_orders)
    assert all(v.date == date(2026, 10, 3) for v in sales)
    assert {p.account.number for v in sales for p in v.postings} == {1500, 3000, 2700}


def test_run_daily_books_no_sales_voucher_on_a_day_without_invoices():
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        run_daily_module.run_daily(date(2024, 1, 30))
    assert not [v for v in _saved(mocks, Voucher) if v.voucherType == VoucherType.OUTGOING_INVOICE]


# --- phase 4: a COGS accrual is saved together with its payable --------------------------------------

def test_run_daily_saves_each_cogs_accrual_with_its_payable_and_the_cash_costs_without_one():
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        run_daily_module.run_daily(date(2024, 2, 29))

    accruals = mocks["save_cogs_accrual"].call_args_list
    assert len(accruals) == 6                                             # 4291 and 4292, three suppliers each (round 2, point 3)
    for call in accruals:
        voucher, payable = call.args
        assert payable.account_number in (4291, 4292) and payable.accrual_date == voucher.date == date(2024, 2, 29)
        assert payable.payment_due_date == date(2024, 3, 29)             # last working day of the NEXT month (round 2, point 1)
    cash_costs = [v for v in _saved(mocks, Voucher) if v.voucherType == VoucherType.OPERATING_COST]
    assert cash_costs and all(not any(p.account.number == 2400 for p in v.postings) for v in cash_costs)


def test_run_daily_looks_up_the_unpaid_cogs_payables_when_it_books_payments():
    mocks = _patch_repository()
    with patch.multiple(run_daily_module, **mocks):
        run_daily_module.run_daily(date(2024, 3, 4))
    mocks["get_unpaid_cogs_payables"].assert_called_once_with(date(2024, 3, 4))
