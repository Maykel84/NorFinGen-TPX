"""Współdzielona instancja `slowapi.Limiter` — wydzielona z `main.py` do
osobnego modułu wyłącznie po to, żeby routery (np. `routers/keys.py`) mogły
zaimportować `limiter` do dekoratora `@limiter.limit(...)` na pojedynczym
endpoincie bez cyklicznego importu z `main.py` (który z kolei importuje te
routery)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Domyślny limit per-IP dla całej usługi (Zadanie 2c z wcześniejszej sesji) -
# chroni nawet przed kimś próbującym wielu losowych/nieprawidłowych kluczy
# naraz. Poszczególne endpointy mogą nałożyć własny, ciaśniejszy limit przez
# @limiter.limit(...).
limiter = Limiter(key_func=get_remote_address, default_limits=["300/hour"])
