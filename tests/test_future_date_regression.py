"""Testy zapobiegające regresji błędu Fazy 5a — generator NIGDY nie powinien
tworzyć rekordów z datą późniejszą niż rzeczywista data systemowa. Zob.
docs/SESSION_HANDOFF.md ("Naprawa błędu dat w przyszłości") dla opisu
pierwotnego błędu (backfill miesięczny generował cały bieżący miesiąc
kalendarzowy, np. całą listę płac lipca zaksięgowaną 31 lipca mimo że
backfill uruchomiono 7 lipca)."""

from datetime import date, timedelta

from norfingen.generators.backfill import generate_and_persist_month, run_backfill
from norfingen.seed.payroll import (
    get_generation_cutoff_date,
    is_date_generatable,
    last_working_day,
    should_generate_monthly_salary,
)


def test_is_date_generatable_respects_cutoff():
    cutoff = date(2026, 7, 7)
    assert is_date_generatable(date(2026, 7, 7), cutoff) is True
    assert is_date_generatable(date(2026, 7, 6), cutoff) is True
    assert is_date_generatable(date(2026, 7, 8), cutoff) is False


def test_get_generation_cutoff_date_is_today():
    assert get_generation_cutoff_date() == date.today()


def test_should_generate_monthly_salary_only_after_month_ends():
    today = date.today()
    # Miesiąc bieżący: ostatni dzień roboczy jeszcze nie minął (chyba że test
    # akurat biegnie w ostatnim dniu roboczym miesiąca — wtedy i tak oczekiwane True).
    current_month_last_day = last_working_day(today.year, today.month)
    expected = current_month_last_day <= today
    assert should_generate_monthly_salary(today.year, today.month) is expected

    # Miesiąc, który na pewno się jeszcze nie zaczął (rok w przyszłości) -> zawsze False.
    future_year = today.year + 2
    assert should_generate_monthly_salary(future_year, 1) is False

    # Miesiąc na pewno zakończony (2019) -> zawsze True.
    assert should_generate_monthly_salary(2019, 1) is True


def test_generate_and_persist_month_never_exceeds_cutoff():
    """Miesiąc bieżący (rok, miesiąc dzisiejszej daty) nie powinien wygenerować
    ŻADNEGO rekordu z datą późniejszą niż dziś — dawny błąd: cały miesiąc
    (np. zamówienie z invoice_day=27) generował się niezależnie od tego, który
    dzień tego miesiąca faktycznie trwa."""
    today = date.today()
    collected: list = []
    generate_and_persist_month(today.year, today.month, persist_fn=collected.append)

    for obj in collected:
        obj_date = getattr(obj, "orderDate", None) or getattr(obj, "invoiceDate", None) or getattr(obj, "date", None)
        assert obj_date is not None
        assert obj_date <= today, f"{type(obj).__name__} ma datę {obj_date} > dziś ({today})"


def test_generate_and_persist_month_skips_unfinished_month_salary():
    """Jeśli miesiąc bieżący jeszcze się nie zakończył, lista płac NIE
    generuje się wcale (nie tylko z poprawną datą, ale wogóle nie istnieje
    w statsach tego miesiąca)."""
    today = date.today()
    month_ended = last_working_day(today.year, today.month) <= today
    stats = generate_and_persist_month(today.year, today.month)
    if not month_ended:
        assert stats["salary_transactions"] == 0
        assert stats["payslips"] == 0


def test_run_backfill_clamps_end_date_to_today():
    """run_backfill z end_date w przyszłości (albo bez end_date, w trakcie
    bieżącego miesiąca) nigdy nie generuje dat późniejszych niż dziś."""
    today = date.today()
    future_end = today + timedelta(days=60)
    collected: list = []
    run_backfill(start_date=today.replace(day=1), end_date=future_end, persist_fn=collected.append)

    for obj in collected:
        obj_date = getattr(obj, "orderDate", None) or getattr(obj, "invoiceDate", None) or getattr(obj, "date", None)
        if obj_date is not None:
            assert obj_date <= today, f"{type(obj).__name__} ma datę {obj_date} > dziś ({today})"


def test_run_daily_rejects_future_target_date():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from run_daily import run_daily

    future = date.today() + timedelta(days=5)
    result = run_daily(target_date=future, skip_setup=True)
    assert result.get("skipped") is True
    assert result["orders"] == 0
    assert result["bank_transactions"] == 0
    assert result["hour_entries"] == 0
    assert result["salary"] == 0
