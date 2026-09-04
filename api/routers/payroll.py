"""Zatrudnienie — headcount miesięczny."""

from fastapi import APIRouter, Depends

from api.auth import verify_api_key
from api.db import data_pool
from api.models import Headcount

router = APIRouter(prefix="/headcount", tags=["payroll"])


@router.get("/monthly", response_model=list[Headcount])
async def headcount_monthly(_owner: str = Depends(verify_api_key)) -> list[Headcount]:
    """Liczba aktywnych pracowników per miesiąc (`v_headcount_monthly` -
    liczy tylko pracowników billable, zob. docs/DATA_DICTIONARY.md)."""
    pool = data_pool()
    rows = await pool.fetch("SELECT month, active_employees FROM v_headcount_monthly ORDER BY month")
    return [Headcount(**dict(r)) for r in rows]
