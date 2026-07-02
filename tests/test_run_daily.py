"""Testy run_daily.py z zamockowanymi funkcjami repository — weryfikują logikę
orkiestracji (co jest wołane, kiedy, z jakimi argumentami), bez połączenia
z prawdziwym Supabase."""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_daily as run_daily_module  # noqa: E402


def _patch_repository(**overrides):
    defaults = dict(
        ensure_schema=MagicMock(),
        seed_reference_data=MagicMock(),
        get_orders_for_payment_window=MagicMock(return_value=[]),
        get_unpaid_supplier_invoices=MagicMock(return_value=[]),
        save_orders=MagicMock(),
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
