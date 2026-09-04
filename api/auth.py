"""Walidacja klucza API + rate limiting per klucz.

Klucz akceptowany przez nagłówek `X-API-Key` LUB parametr zapytania
`?api_key=` (wzorem popularnych publicznych API pogodowych - wygoda przy
prostych testach z przeglądarki/curl bez ustawiania nagłówków).

Baza trzyma tylko `sha256(raw_key)` w `key_hash` - surowy klucz nigdy nie
trafia do żadnej tabeli, tylko na stdout w momencie generowania
(`scripts/generate_api_key.py`). Walidacja i licznik rate-limitu działają
przez rolę `api_key_manager` (zob. `db.py`) - wąski dostęp, tylko ta jedna
tabela, nigdy demo_reader.
"""

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException, Query

from api.db import auth_pool

RATE_LIMIT_WINDOW = timedelta(hours=1)


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = Query(default=None, description="Alternatywa dla nagłówka X-API-Key"),
) -> str:
    raw_key = x_api_key or api_key
    if not raw_key:
        raise HTTPException(
            status_code=401,
            detail="Brak klucza API. Podaj nagłówek 'X-API-Key' lub parametr '?api_key='.",
        )

    key_hash = _hash_key(raw_key)
    pool = auth_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, owner_label, revoked, rate_limit_per_hour,
                       request_count_this_window, window_start
                FROM api_keys
                WHERE key_hash = $1
                FOR UPDATE
                """,
                key_hash,
            )

            if row is None or row["revoked"]:
                raise HTTPException(status_code=401, detail="Nieprawidłowy lub odwołany klucz API.")

            now = datetime.now(UTC)
            window_start = row["window_start"]
            window_expired = now - window_start >= RATE_LIMIT_WINDOW

            if window_expired:
                new_count = 1
                new_window_start = now
            else:
                new_count = row["request_count_this_window"] + 1
                new_window_start = window_start

            if new_count > row["rate_limit_per_hour"]:
                retry_after = int((new_window_start + RATE_LIMIT_WINDOW - now).total_seconds())
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Limit {row['rate_limit_per_hour']} zapytań/godzinę przekroczony. "
                        f"Spróbuj ponownie za {max(retry_after, 1)}s."
                    ),
                )

            await conn.execute(
                """
                UPDATE api_keys
                SET request_count_this_window = $2,
                    window_start = $3,
                    last_used_at = $4
                WHERE id = $1
                """,
                row["id"],
                new_count,
                new_window_start,
                now,
            )

    return row["owner_label"]
