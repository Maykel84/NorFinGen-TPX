"""Testy run_backfill_daily() z zamockowanym run_daily() — weryfikują pętlę
dat (pomija weekendy, obejmuje pełny zakres), bez odpalania realnych
generatorów/bazy danych."""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_backfill as run_backfill_module  # noqa: E402


def test_run_backfill_daily_skips_weekends():
    # 2024-01-08 (pon) .. 2024-01-14 (nd) -> 5 dni roboczych, 2 weekendowe
    with patch("run_daily.run_daily") as mock_run_daily:
        mock_run_daily.return_value = {"orders": 0, "bank_transactions": 0, "hour_entries": 0, "salary": 0}
        run_backfill_module.run_backfill_daily(date(2024, 1, 8), date(2024, 1, 14))

    assert mock_run_daily.call_count == 5
    called_dates = {call.kwargs["target_date"] for call in mock_run_daily.call_args_list}
    assert called_dates == {date(2024, 1, 8), date(2024, 1, 9), date(2024, 1, 10), date(2024, 1, 11), date(2024, 1, 12)}


def test_run_backfill_daily_single_day_range():
    with patch("run_daily.run_daily") as mock_run_daily:
        mock_run_daily.return_value = {"orders": 0, "bank_transactions": 0, "hour_entries": 0, "salary": 0}
        run_backfill_module.run_backfill_daily(date(2024, 1, 6), date(2024, 1, 6))  # sobota

    mock_run_daily.assert_not_called()
