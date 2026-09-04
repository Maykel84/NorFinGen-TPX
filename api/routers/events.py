"""Warstwa zdarzeń losowych (Faza 7) — klient/firmowe zdarzenia biznesowe.

Ta warstwa NIE ma własnej tabeli w Supabase (żyje wyłącznie w generatorach
Pythona - zob. docs/DATA_DICTIONARY.md, "Faza 7"). Jedyny materialny zapis
zdarzeń to `docs/faza7_life_events_log.csv`, wygenerowany przez
`scripts/log_life_events.py` - ten endpoint go czyta i filtruje, nie odpytuje
bazy danych.
"""

import csv
import functools
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from api.auth import verify_api_key
from api.models import LifeEvent

router = APIRouter(prefix="/events", tags=["events"])

_CSV_PATH = Path(__file__).resolve().parents[2] / "docs" / "faza7_life_events_log.csv"


@functools.lru_cache(maxsize=1)
def _load_events() -> list[dict]:
    if not _CSV_PATH.exists():
        return []
    with _CSV_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@router.get("", response_model=list[LifeEvent])
async def list_events(
    year: int | None = Query(default=None, description="Filtruj do jednego roku kalendarzowego"),
    scope: str | None = Query(default=None, description="'client' lub 'company'"),
    _owner: str = Depends(verify_api_key),
) -> list[LifeEvent]:
    rows = _load_events()
    result = []
    for r in rows:
        if year is not None and int(r["year"]) != year:
            continue
        if scope is not None and r["scope"] != scope:
            continue
        result.append(
            LifeEvent(
                scope=r["scope"],
                code=r["code"],
                year=int(r["year"]),
                month=int(r["month"]),
                customer_number=r["customer_number"] or None,
                customer_name=r["customer_name"] or None,
                segment=r["segment"] or None,
                detail=r["detail"] or None,
            )
        )
    return result
