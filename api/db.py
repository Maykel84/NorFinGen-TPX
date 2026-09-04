"""Połączenia do Postgres dla usługi REST API.

Dwa OSOBNE pule połączeń, celowo różne role, żeby zachować minimalny zakres
uprawnień dla każdej ścieżki kodu:

- `data_pool` — łączy się jako `demo_reader` (read-only, RLS wymusza
  SELECT-only na 20/20 tabelach przez rolę `analyst`, zob.
  docs/DATA_DICTIONARY.md). Jedyna rola używana przez routery `routers/*.py`
  do serwowania danych finansowych/klienckich. Nigdy service_role/postgres.
- `auth_pool` — łączy się jako `api_key_manager` (wąska rola, SELECT/UPDATE
  wyłącznie na tabeli `api_keys` — zob. `scripts/setup_api_backend.py`).
  Używana WYŁĄCZNIE przez `auth.py` do walidacji kluczy i rate limitingu.
  `demo_reader` celowo NIE ma dostępu do `api_keys` (RLS bez polityki dla
  ról read-only) - stąd potrzeba osobnej roli, nie obejście przez demo_reader.

Oba connection stringi wyłącznie ze zmiennych środowiskowych, nigdy w kodzie.
"""

import os

import asyncpg

_data_pool: asyncpg.Pool | None = None
_auth_pool: asyncpg.Pool | None = None


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Brak zmiennej środowiskowej {name} - usługa nie może wystartować bez niej."
        )
    return value


async def init_pools() -> None:
    global _data_pool, _auth_pool
    _data_pool = await asyncpg.create_pool(
        dsn=_require_env("DEMO_READER_DATABASE_URL"),
        min_size=0,
        max_size=2,  # demo_reader ma CONNECTION LIMIT 2 na poziomie roli Postgres
        command_timeout=10,
    )
    _auth_pool = await asyncpg.create_pool(
        dsn=_require_env("API_KEY_MANAGER_DATABASE_URL"),
        min_size=0,
        max_size=5,
        command_timeout=10,
    )


async def close_pools() -> None:
    if _data_pool is not None:
        await _data_pool.close()
    if _auth_pool is not None:
        await _auth_pool.close()


def data_pool() -> asyncpg.Pool:
    if _data_pool is None:
        raise RuntimeError("Pula połączeń danych nie została zainicjalizowana (init_pools()).")
    return _data_pool


def auth_pool() -> asyncpg.Pool:
    if _auth_pool is None:
        raise RuntimeError("Pula połączeń auth nie została zainicjalizowana (init_pools()).")
    return _auth_pool
