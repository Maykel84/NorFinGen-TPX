"""Żywy dostęp do bazy na żądanie — Power BI / SQL / Python (portal, trzecia
ścieżka obok kluczy API i eksportu na żądanie).

Decyzja bezpieczeństwa (dwuetapowa, ustalona z użytkownikiem):
1. Jedno wspólne, read-only hasło (`portal_reader`, zob.
   `scripts/setup_portal_reader.py`) — nie osobna rola per-osoba. Akceptowalne
   bo dane syntetyczne, dostęp wyłącznie SELECT (dziedziczy `analyst`),
   connlimit/timeout ograniczają nadużycie.
2. Hasło NIE jest wystawione na stałe na stronie — wydawane na żądanie przez
   ten endpoint, tym samym wzorcem co `POST /api/v1/keys/request` (limit
   3/dzień/IP, log żądań do celów audytowych — `db_access_requests` NIE jest
   mechanizmem kontroli dostępu, tylko dziennikiem; hasło zostaje wspólne dla
   wszystkich, którzy o nie poproszą).
"""

import os

from fastapi import APIRouter, HTTPException, Request

from api.db import auth_pool
from api.ip_limit import enforce_ip_signup_limit
from api.models import DbAccessRequest, DbAccessResponse
from api.rate_limit import get_client_ip, limiter

router = APIRouter(prefix="/db-access", tags=["db-access"])

DB_ACCESS_MAX_PER_DAY = 3


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise HTTPException(status_code=503, detail=f"Usługa nieskonfigurowana: brak {name}.")
    return value


@router.post("/request", response_model=DbAccessResponse)
@limiter.limit("5/minute")
async def request_db_access(body: DbAccessRequest, request: Request) -> DbAccessResponse:
    """Zwraca dane połączenia do wspólnej roli `portal_reader` (read-only).
    Loguje żądanie do `db_access_requests` (audyt, nie kontrola dostępu)."""
    client_ip = get_client_ip(request)
    await enforce_ip_signup_limit(
        client_ip,
        table="db_access_requests",
        max_per_day=DB_ACCESS_MAX_PER_DAY,
        ip_column="requested_from_ip",
        timestamp_column="requested_at",
    )

    pool = auth_pool()
    await pool.execute(
        "INSERT INTO db_access_requests (requester_label, requested_from_ip) VALUES ($1, $2)",
        body.label,
        client_ip,
    )

    return DbAccessResponse(
        host=_require_env("PORTAL_DB_HOST"),
        port=int(os.environ.get("PORTAL_DB_PORT", "5432")),
        database=os.environ.get("PORTAL_DB_NAME", "postgres"),
        username=_require_env("PORTAL_READER_USERNAME"),
        password=_require_env("PORTAL_READER_PASSWORD"),
        message=(
            "Read-only access. Use for Power BI, SQL clients, or Python. "
            "This is a shared credential - do not attempt writes, they will be rejected."
        ),
    )
