"""Samoobsługowe generowanie kluczy API (Faza — portal self-service, Zadanie 1).

Do tej pory jedyny sposób na klucz był ręczny (`api/scripts/generate_api_key.py`,
uprawnienia właściciela). Ten endpoint pozwala komukolwiek wygenerować własny
klucz bez kontaktu z właścicielem — świadomie ograniczony rate limitem
(60/h, niżej niż domyślne 100/h kluczy ręcznych) i podwójnym zabezpieczeniem
przed masowym generowaniem: licznik kluczy/IP/dobę w bazie (przetrwa restart
usługi) + ogólny limit zapytań/minutę na sam endpoint (slowapi, w pamięci -
wystarczające tu, bo chroni tylko przed szybkim automatycznym flooderem, nie
przed rozłożonym w czasie nadużyciem, które i tak łapie limit dobowy).

Nie zbiera prawdziwych adresów e-mail — `label` to dowolna etykieta tekstowa
podana przez użytkownika (imię/kurs), tak jak w treści zadania.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request

from api.db import auth_pool
from api.models import KeyRequest, KeyResponse
from api.rate_limit import limiter

router = APIRouter(prefix="/keys", tags=["keys"])

SELF_SERVICE_RATE_LIMIT = 60
IP_SIGNUP_WINDOW = timedelta(hours=24)
IP_SIGNUP_MAX_PER_DAY = 3


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def enforce_ip_signup_limit(ip: str, max_per_day: int = IP_SIGNUP_MAX_PER_DAY) -> None:
    """Odrzuca 4. i kolejne żądanie klucza z tego samego IP w ciągu doby.

    Liczy `api_keys.created_from_ip` (nie osobną tabelę) - to jest dokładnie
    to pole istnieje po to, żeby ten limit mógł działać bez dodatkowego stanu.
    """
    pool = auth_pool()
    window_start = datetime.now(UTC) - IP_SIGNUP_WINDOW
    count = await pool.fetchval(
        """
        SELECT COUNT(*) FROM api_keys
        WHERE created_from_ip = $1 AND created_at > $2
        """,
        ip,
        window_start,
    )
    if count >= max_per_day:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Zbyt wiele kluczy z tego IP w ciągu ostatnich 24h (limit {max_per_day}). "
                "Spróbuj ponownie jutro."
            ),
        )


@router.post("/request", response_model=KeyResponse)
@limiter.limit("5/minute")
async def request_key(body: KeyRequest, request: Request) -> KeyResponse:
    """Generuje nowy klucz self-service. Klucz surowy istnieje tylko w tej
    odpowiedzi - baza trzyma wyłącznie jego SHA-256 (ten sam wzorzec co
    `api/scripts/generate_api_key.py`)."""
    client_ip = request.client.host if request.client else "unknown"
    await enforce_ip_signup_limit(client_ip)

    raw_key = f"nfg_edu_{secrets.token_urlsafe(24)}"
    key_hash = _hash_key(raw_key)

    pool = auth_pool()
    await pool.execute(
        """
        INSERT INTO api_keys
            (key_hash, owner_label, requester_label, self_service,
             created_from_ip, rate_limit_per_hour)
        VALUES ($1, $2, $3, true, $4, $5)
        """,
        key_hash,
        body.label,
        body.label,
        client_ip,
        SELF_SERVICE_RATE_LIMIT,
    )

    return KeyResponse(
        api_key=raw_key,
        rate_limit_per_hour=SELF_SERVICE_RATE_LIMIT,
        message="Zapisz ten klucz teraz - nie pokaże się ponownie.",
    )
