"""Testy run_backfill_daily() z zamockowanym run_daily() — weryfikują pętlę
dat (obejmuje KAŻDY dzień kalendarzowy, także weekendy; ustawia watermark),
bez odpalania realnych generatorów/bazy danych.

Faza 0.5a: wcześniej pętla pomijała weekendy, więc wpłata z terminem w sobotę
lub niedzielę nigdy nie powstawała. Teraz weekendy są przetwarzane (wpłaty
i tak lądują w następnym dniu roboczym; godziny i płace pilnują dni roboczych
same)."""

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_backfill as run_backfill_module  # noqa: E402

EMPTY_STATS = {"orders": 0, "bank_transactions": 0, "hour_entries": 0, "salary": 0}


def test_run_backfill_daily_visits_every_calendar_day_including_weekends():
    # 2024-01-08 (pon) .. 2024-01-14 (nd) -> 7 dni, w tym sobota i niedziela
    with patch("run_daily.run_daily") as mock_run_daily, patch("norfingen.db.repository.set_watermark"):
        mock_run_daily.return_value = EMPTY_STATS
        run_backfill_module.run_backfill_daily(date(2024, 1, 8), date(2024, 1, 14))

    assert mock_run_daily.call_count == 7
    called_dates = [call.kwargs["target_date"] for call in mock_run_daily.call_args_list]
    assert called_dates == [date(2024, 1, 8) + timedelta(days=i) for i in range(7)]
    assert date(2024, 1, 13) in called_dates and date(2024, 1, 14) in called_dates  # sob + nd


def test_run_backfill_daily_single_weekend_day_is_processed():
    with patch("run_daily.run_daily") as mock_run_daily, patch("norfingen.db.repository.set_watermark"):
        mock_run_daily.return_value = EMPTY_STATS
        run_backfill_module.run_backfill_daily(date(2024, 1, 6), date(2024, 1, 6))  # sobota

    mock_run_daily.assert_called_once()
    assert mock_run_daily.call_args.kwargs["target_date"] == date(2024, 1, 6)


def test_run_backfill_daily_sets_watermark_to_end_date():
    with patch("run_daily.run_daily") as mock_run_daily, patch("norfingen.db.repository.set_watermark") as mock_set:
        mock_run_daily.return_value = EMPTY_STATS
        run_backfill_module.run_backfill_daily(date(2024, 1, 8), date(2024, 1, 14))

    mock_set.assert_called_once_with(date(2024, 1, 14))


def test_run_backfill_pipeline_never_goes_past_today_and_keeps_the_old_name():
    today = date.today()
    with patch("run_daily.run_daily") as mock_run_daily, patch("norfingen.db.repository.set_watermark") as mock_set:
        mock_run_daily.return_value = EMPTY_STATS
        run_backfill_module.run_backfill_pipeline(today - timedelta(days=1), today + timedelta(days=5))

    called = [c.kwargs["target_date"] for c in mock_run_daily.call_args_list]
    assert called == [today - timedelta(days=1), today]          # nothing from the future
    mock_set.assert_called_once_with(today)                       # watermark never ahead of today
    assert run_backfill_module.run_backfill_daily is run_backfill_module.run_backfill_pipeline
