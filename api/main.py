"""NorFinGen REST API — wrapper HTTP z kluczem API nad istniejącą bazą
read-only (`demo_reader`), wzorem Tripletex API / popularnych API pogodowych
(GET z nagłówkiem/parametrem klucza). Nie zmienia żadnej logiki generatora -
osobna usługa czytająca z tej samej bazy Supabase.

Uruchomienie lokalne:
    DEMO_READER_DATABASE_URL=... API_KEY_MANAGER_DATABASE_URL=... \\
        uvicorn api.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from api.db import auth_pool, close_pools, data_pool, init_pools
from api.models import HealthStatus
from api.routers import customers, events, financials, payroll

# Warstwa dodatkowa NIEZALEŻNA od per-klucz rate limitu w auth.py (Zadanie 2c)
# - per-IP, chroni nawet przed kimś próbującym wielu losowych/nieprawidłowych
# kluczy naraz (te nie dotrą nawet do liczników w tabeli api_keys).
limiter = Limiter(key_func=get_remote_address, default_limits=["300/hour"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pools()
    yield
    await close_pools()


app = FastAPI(
    title="NorFinGen API",
    version="1.0.0",
    description=(
        "Read-only REST API nad syntetyczną, żywo rosnącą bazą finansową "
        "fikcyjnej norweskiej firmy IT (modelowaną na Tripletex API). "
        "Wymaga klucza API (nagłówek `X-API-Key` lub `?api_key=`) - "
        "zob. https://github.com/ dla instrukcji uzyskania klucza."
    ),
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(financials.router, prefix="/api/v1")
app.include_router(customers.router, prefix="/api/v1")
app.include_router(payroll.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")


@app.get("/health", response_model=HealthStatus, tags=["meta"])
async def health() -> HealthStatus:
    """Bez klucza API - sprawdza tylko czy usługa i baza żyją."""
    try:
        await data_pool().fetchval("SELECT 1")
        await auth_pool().fetchval("SELECT 1")
        db_status = "ok"
    except Exception as exc:  # noqa: BLE001 - health check celowo łapie wszystko
        db_status = f"unreachable: {exc}"
    return HealthStatus(status="ok", database=db_status)


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request, exc: RuntimeError) -> JSONResponse:
    # Pule niezainicjalizowane (np. brak env var przy starcie) - 503, nie 500 z tracebackiem.
    return JSONResponse(status_code=503, content={"detail": str(exc)})
