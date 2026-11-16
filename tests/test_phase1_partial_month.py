"""Audit 2026-11-16, decision #1: the month that is not over yet is FLAGGED (`is_partial`), not pro-rated.

Payroll and COGS are booked at month end (as in Tripletex), so the open month shows revenue without its costs
(2026-11: margin 97%). The trailing-12M margin was 10.5% with that month and 3.15% without it. The tests pin the flag
in the view, in both export queries and the API, and that the KPI endpoints leave the open month out."""
import asyncio
from pathlib import Path

import export_queries
from api.routers import financials

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = (ROOT / "src/norfingen/db/schema.sql").read_text()


def _month_row(month, revenue, result):
    return {"month": month, "revenue": revenue, "labor_cost": 0.0, "operating_cost": 0.0, "cogs": 0.0,
            "operating_result": result}


class _FakePool:
    def __init__(self, rows):
        self.rows, self.sql = rows, []

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        return self.rows


def test_view_and_exports_carry_is_partial():
    start = SCHEMA_SQL.index("CREATE OR REPLACE VIEW v_pl_monthly")
    view = SCHEMA_SQL[start:SCHEMA_SQL.index("v_headcount_monthly", start)]
    assert "AS is_partial" in view
    assert "AS is_partial" in export_queries.QUERIES["PL_miesiecznie"]
    api_export = (ROOT / "api/export_data.py").read_text()
    assert api_export.count("AS is_partial") == 1 and '"operating_result", "is_partial"' in api_export


def test_partial_month_is_decided_by_the_newest_generated_date_not_by_the_calendar():
    """No dependency on today's date (a stale database must not mark every month partial)."""
    assert "GREATEST((SELECT MAX(date) FROM vouchers), (SELECT MAX(order_date) FROM orders))" in SCHEMA_SQL
    assert "CURRENT_DATE" not in SCHEMA_SQL[SCHEMA_SQL.index("CREATE OR REPLACE VIEW v_pl_monthly"):
                                           SCHEMA_SQL.index("CREATE OR REPLACE VIEW v_headcount_monthly")]


def test_yearly_and_trailing_kpis_filter_out_the_partial_month(monkeypatch):
    pool = _FakePool([_month_row(f"2025-{m:02d}", 100.0, 10.0) for m in range(11, 13)]
                     + [_month_row(f"2026-{m:02d}", 100.0, 10.0) for m in range(1, 11)])
    monkeypatch.setattr(financials, "data_pool", lambda: pool)
    result = asyncio.run(financials.pl_trailing_12m(_owner="x"))
    assert "WHERE NOT is_partial" in pool.sql[0] and "LIMIT 12" in pool.sql[0]
    assert (result.period_from, result.period_to, result.months) == ("2025-11", "2026-10", 12)
    assert result.revenue == 1200.0 and result.operating_result == 120.0 and result.margin_pct == 10.0
    yearly = _FakePool([{"year": 2026, "revenue": 1000.0, "labor_cost": 0.0, "operating_cost": 0.0, "cogs": 0.0,
                         "operating_result": 100.0, "months_included": 10}])
    monkeypatch.setattr(financials, "data_pool", lambda: yearly)
    out = asyncio.run(financials.pl_yearly(_owner="x"))
    assert "WHERE NOT is_partial" in yearly.sql[0] and out[0].months_included == 10 and out[0].margin_pct == 10.0


def test_trailing_without_any_closed_month_is_404(monkeypatch):
    monkeypatch.setattr(financials, "data_pool", lambda: _FakePool([]))
    try:
        asyncio.run(financials.pl_trailing_12m(_owner="x"))
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("expected 404")
