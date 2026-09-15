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

from fastapi import APIRouter, Request

from api.db import auth_pool
from api.ip_limit import enforce_ip_signup_limit
from api.models import KeyRequest, KeyResponse
from api.rate_limit import get_client_ip, limiter

router = APIRouter(prefix="/keys", tags=["keys"])

SELF_SERVICE_RATE_LIMIT = 60
IP_SIGNUP_MAX_PER_DAY = 3


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@router.post("/request", response_model=KeyResponse)
@limiter.limit("5/minute")
async def request_key(body: KeyRequest, request: Request) -> KeyResponse:
    """Generuje nowy klucz self-service. Klucz surowy istnieje tylko w tej
    odpowiedzi - baza trzyma wyłącznie jego SHA-256 (ten sam wzorzec co
    `api/scripts/generate_api_key.py`)."""
    client_ip = get_client_ip(request)
    await enforce_ip_signup_limit(client_ip, table="api_keys", max_per_day=IP_SIGNUP_MAX_PER_DAY)

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
