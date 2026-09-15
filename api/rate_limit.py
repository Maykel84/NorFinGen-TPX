"""Współdzielona instancja `slowapi.Limiter` — wydzielona z `main.py` do
osobnego modułu wyłącznie po to, żeby routery (np. `routers/keys.py`) mogły
zaimportować `limiter` do dekoratora `@limiter.limit(...)` na pojedynczym
endpoincie bez cyklicznego importu z `main.py` (który z kolei importuje te
routery)."""

from fastapi import Request
from slowapi import Limiter


def get_client_ip(request: Request) -> str:
    """Prawdziwy adres IP klienta, nie wewnętrzny adres proxy Fly.io.

    `request.client.host` na Fly.io zwraca adres wewnętrznego hopa
    fly-proxy (zakres RFC1918, np. 172.16.x.x) — TEN SAM dla wielu/wszystkich
    odwiedzających, nie realny adres publiczny. Odkryte podczas tej sesji:
    3 klucze self-service wygenerowane w testach miały `created_from_ip`
    identyczny mimo być może różnych rzeczywistych źródeł. Fly Proxy wstawia
    prawdziwy adres klienta w nagłówku `Fly-Client-IP` (nie do sfałszowania
    przez klienta - Fly nadpisuje go na wejściu do swojej sieci), więc to
    pierwszeństwo. `X-Forwarded-For` jako fallback (inne środowiska/proxy),
    `request.client.host` jako ostateczny fallback (testy offline, dev
    lokalny bez proxy)."""
    fly_ip = request.headers.get("Fly-Client-IP")
    if fly_ip:
        return fly_ip
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Domyślny limit per-IP dla całej usługi (Zadanie 2c z wcześniejszej sesji) -
# chroni nawet przed kimś próbującym wielu losowych/nieprawidłowych kluczy
# naraz. Poszczególne endpointy mogą nałożyć własny, ciaśniejszy limit przez
# @limiter.limit(...).
limiter = Limiter(key_func=get_client_ip, default_limits=["300/hour"])
