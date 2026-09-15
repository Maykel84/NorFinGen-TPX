"""Eksport CSV/Excel na żądanie (Zadanie 3) — generowany przy KAŻDYM żądaniu
wprost z żywej bazy (`demo_reader`), bez trwałego magazynu plików ani
migawki dobowej (dane zawsze aktualne co do sekundy).

Celowo BEZ klucza API (inaczej niż pozostałe `/api/v1/*`) — to jest
zamierzony, najniższy próg wejścia z Zadania 2/3 (guzik na portalu, zero
rejestracji). Chroniony zamiast tego osobnym, ciaśniejszym limitem per-IP
(Zadanie 3b, `export_requests` — zob. `scripts/setup_api_backend.py`), bo
generowanie pełnej historii jest samo w sobie kosztowniejsze niż typowe
zapytanie JSON i nie powinno być powtarzalne w pętli.
"""

import io
import re
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from api.db import auth_pool
from api.export_data import generate_csv_export_bytes, generate_excel_export_bytes
from api.rate_limit import get_client_ip

router = APIRouter(prefix="/export", tags=["export"])

_EARLIEST_MONTH = "2019-01"
EXPORT_WINDOW = timedelta(minutes=5)
EXPORT_MAX_PER_WINDOW = 1


def _validate_month(value: str, param_name: str) -> str:
    """Format YYYY-MM, zakres [2019-01, bieżący miesiąc] (Zadanie 3d) — sam
    wzorzec walidacji co `financials._validate_month`, ale zduplikowany
    świadomie: dodanie tam zależności od zakresu "rozsądnych dat" (2019-dziś)
    zmieniłoby zachowanie istniejących, już wdrożonych endpointów `/pl/*`."""
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
        raise HTTPException(
            status_code=400,
            detail=f"'{param_name}' musi być w formacie YYYY-MM, dostano '{value}'.",
        )
    current_month = date.today().strftime("%Y-%m")
    if value < _EARLIEST_MONTH or value > current_month:
        raise HTTPException(
            status_code=400,
            detail=f"'{param_name}' musi być w zakresie [{_EARLIEST_MONTH}, {current_month}].",
        )
    return value


def _month_bounds(month_from: str, month_to: str) -> tuple[date, date]:
    y1, m1 = (int(x) for x in month_from.split("-"))
    y2, m2 = (int(x) for x in month_to.split("-"))
    start = date(y1, m1, 1)
    end = date(y2, m2, monthrange(y2, m2)[1])
    return start, min(end, date.today())


async def enforce_export_rate_limit(ip: str, max_per_window: int = EXPORT_MAX_PER_WINDOW) -> None:
    pool = auth_pool()
    window_start = datetime.now(UTC) - EXPORT_WINDOW
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM export_requests WHERE ip = $1 AND created_at > $2",
        ip,
        window_start,
    )
    if count >= max_per_window:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Limit {max_per_window} eksport(ów) / 5 minut przekroczony. "
                "Spróbuj ponownie za chwilę."
            ),
        )
    await pool.execute("INSERT INTO export_requests (ip) VALUES ($1)", ip)


@router.get("/{format}")
async def download_export(
    format: str,
    request: Request,
    from_: str | None = Query(
        default=None, alias="from", description="Miesiąc początkowy YYYY-MM (domyślnie 2019-01)"
    ),
    to: str | None = Query(
        default=None, description="Miesiąc końcowy YYYY-MM, włącznie (domyślnie bieżący miesiąc)"
    ),
) -> StreamingResponse:
    if format not in ("csv", "excel"):
        raise HTTPException(status_code=404, detail="Format musi być 'csv' lub 'excel'.")

    month_from = _validate_month(from_ or _EARLIEST_MONTH, "from")
    month_to = _validate_month(to or date.today().strftime("%Y-%m"), "to")
    if month_from > month_to:
        raise HTTPException(status_code=400, detail="'from' musi być <= 'to'.")

    client_ip = get_client_ip(request)
    await enforce_export_rate_limit(client_ip)

    date_from, date_to = _month_bounds(month_from, month_to)

    if format == "csv":
        file_bytes = await generate_csv_export_bytes(date_from, date_to)
        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=norfingen_{month_from}_{month_to}.zip"
            },
        )

    file_bytes = await generate_excel_export_bytes(date_from, date_to)
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=norfingen_{month_from}_{month_to}.xlsx"
        },
    )
