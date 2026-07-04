from datetime import date

from norfingen.generators.backfill import founding_capital_voucher, months_range, run_backfill


def test_founding_capital_voucher_balances():
    voucher = founding_capital_voucher()
    assert voucher.validate_balance()
    assert voucher.date == date(2019, 1, 2)


def test_months_range_inclusive():
    months = months_range(date(2024, 11, 1), date(2025, 2, 1))
    assert months == [(2024, 11), (2024, 12), (2025, 1), (2025, 2)]


def test_run_backfill_short_window():
    # Sty-luty 2019: przed onboardingiem pierwszego klienta (K01, 2019-03-01) ->
    # zero zamówień, ale payroll/salary działa od pierwszego dnia firmy.
    stats = run_backfill(start_date=date(2019, 1, 1), end_date=date(2019, 2, 28))
    assert stats["months"] == 2
    assert stats["orders"] == 0
    assert stats["salary_transactions"] == 2
    # Voucher kapitału zakładowego + przynajmniej lista płac/AGA per miesiąc.
    assert stats["vouchers"] >= 1 + 2 * 2


def test_run_backfill_orders_start_after_first_customer_onboarding():
    # K01 onboarduje się 2019-03-01 -> okno obejmujące marzec powinno mieć zamówienia.
    stats = run_backfill(start_date=date(2019, 1, 1), end_date=date(2019, 3, 31))
    assert stats["orders"] > 0


def test_run_backfill_collects_via_persist_fn():
    collected = []
    run_backfill(start_date=date(2024, 6, 1), end_date=date(2024, 6, 30), persist_fn=collected.append)
    assert len(collected) > 0
