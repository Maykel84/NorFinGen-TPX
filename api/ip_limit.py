"""Współdzielony licznik "N żądań / IP / dobę" — wydzielony z `routers/keys.py`
(Zadanie 1c, self-service klucze) tak, żeby `routers/db_access.py` (ten sam
wzorzec, inna tabela źródłowa) mógł go reużyć zamiast kopiować logikę.

Tabela/kolumny są parametrami wywołania, nie danymi z żądania użytkownika -
`table`/`ip_column`/`timestamp_column` pochodzą zawsze z literału w kodzie
wołającego (nigdy z `Request`), więc budowanie zapytania przez f-string tutaj
jest bezpieczne. Dodatkowa allowlista `_ALLOWED_TABLES` jako zabezpieczenie
w głąb (defense in depth) - gdyby kiedyś ktoś przekazał tu nazwę tabeli
pochodzącą od użytkownika, wywołanie i tak zostanie odrzucone."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from api.db import auth_pool

_ALLOWED_TABLES = {"api_keys", "db_access_requests"}


async def enforce_ip_signup_limit(
    ip: str,
    *,
    table: str,
    max_per_day: int,
    ip_column: str = "created_from_ip",
    timestamp_column: str = "created_at",
) -> None:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Nieznana tabela dla limitu per-IP: {table!r}")

    pool = auth_pool()
    window_start = datetime.now(UTC) - timedelta(hours=24)
    count = await pool.fetchval(
        f"SELECT COUNT(*) FROM {table} WHERE {ip_column} = $1 AND {timestamp_column} > $2",  # noqa: S608 - table/kolumny z allowlisty, nie z żądania
        ip,
        window_start,
    )
    if count >= max_per_day:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Zbyt wiele żądań z tego IP w ciągu ostatnich 24h (limit {max_per_day}). "
                "Spróbuj ponownie jutro."
            ),
        )
