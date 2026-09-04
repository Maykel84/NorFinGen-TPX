"""Testy usługi REST API (`api/`) — walidacja klucza, rate limit, i strukturalne
potwierdzenie że nie istnieje żaden endpoint zapisu. Celowo bez połączenia do
prawdziwej bazy (jak reszta pakietu `tests/`, zob. `tests/test_repository.py`
dla jedynego wyjątku w istniejącym pakiecie) — `api.db._data_pool`/`_auth_pool`
są podmieniane na lekkie atrapy w pamięci, żeby ten plik nie zależał od
sieci/Supabase i nie liczył się do limitów połączeń `demo_reader`/`api_key_manager`.
"""

import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api import db, main


class _NoopTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeAuthConn:
    """Emuluje wystarczająco dużo asyncpg.Connection, żeby auth.py działało:
    jedna tabela `api_keys` trzymana jako lista dictów w pamięci."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def transaction(self):
        return _NoopTransaction()

    async def fetchrow(self, query, key_hash):
        for r in self._rows:
            if r["key_hash"] == key_hash:
                return dict(r)
        return None

    async def execute(self, query, row_id, new_count, new_window_start, now):
        for r in self._rows:
            if r["id"] == row_id:
                r["request_count_this_window"] = new_count
                r["window_start"] = new_window_start
                r["last_used_at"] = now


class FakeAuthPool:
    def __init__(self, rows: list[dict]):
        self._conn = FakeAuthConn(rows)

    def acquire(self):
        pool = self

        @asynccontextmanager
        async def _acquire():
            yield pool._conn

        return _acquire()

    async def fetchval(self, query):
        return 1

    async def fetch(self, query):
        return []


def _make_key_row(row_id: int, raw_key: str, *, rate_limit: int = 100, revoked: bool = False) -> dict:
    return {
        "id": row_id,
        "key_hash": hashlib.sha256(raw_key.encode()).hexdigest(),
        "owner_label": f"test-key-{row_id}",
        "revoked": revoked,
        "rate_limit_per_hour": rate_limit,
        "request_count_this_window": 0,
        "window_start": datetime.now(UTC) - timedelta(minutes=1),
    }


@pytest.fixture
def client(monkeypatch):
    async def _noop_init():
        return None

    async def _noop_close():
        return None

    monkeypatch.setattr(main, "init_pools", _noop_init)
    monkeypatch.setattr(main, "close_pools", _noop_close)
    with TestClient(main.app) as c:
        yield c


def _install_keys(monkeypatch, rows: list[dict]) -> None:
    monkeypatch.setattr(db, "_auth_pool", FakeAuthPool(rows))
    monkeypatch.setattr(db, "_data_pool", FakeAuthPool([]))  # nieużywany w tych testach


def test_api_requires_key(client, monkeypatch):
    """Zapytanie bez klucza (ani nagłówka, ani ?api_key=) zwraca 401."""
    _install_keys(monkeypatch, [])
    resp = client.get("/api/v1/customers")
    assert resp.status_code == 401


def test_api_rejects_invalid_key(client, monkeypatch):
    """Zapytanie z nieprawidłowym (nieznanym) kluczem zwraca 401."""
    _install_keys(monkeypatch, [_make_key_row(1, "nfg_realkey")])
    resp = client.get("/api/v1/customers", headers={"X-API-Key": "nfg_wrongkey"})
    assert resp.status_code == 401


def test_api_rejects_revoked_key(client, monkeypatch):
    _install_keys(monkeypatch, [_make_key_row(1, "nfg_revoked", revoked=True)])
    resp = client.get("/api/v1/customers", headers={"X-API-Key": "nfg_revoked"})
    assert resp.status_code == 401


def test_api_enforces_rate_limit(client, monkeypatch):
    """Po przekroczeniu limitu (tu: 1/h) zapytanie zwraca 429."""
    _install_keys(monkeypatch, [_make_key_row(1, "nfg_ratelimited", rate_limit=1)])
    headers = {"X-API-Key": "nfg_ratelimited"}

    first = client.get("/health")  # /health nie wymaga klucza, użyj chronionego endpointu zamiast
    assert first.status_code == 200

    # /api/v1/headcount/monthly nie dotyka data_pool poza jednym fetch - ale
    # w tym teście liczy się tylko warstwa auth, więc wystarczy że dependency
    # przepuści/odrzuci przed dotarciem do handlera; data_pool jest atrapą.
    r1 = client.get("/api/v1/headcount/monthly", headers=headers)
    r2 = client.get("/api/v1/headcount/monthly", headers=headers)
    # Pierwsze zapytanie może zwrócić 200 lub 500 (atrapa data_pool nie ma
    # fetch()) - istotne jest wyłącznie że DRUGIE jest odrzucone przez rate limit.
    assert r1.status_code != 429
    assert r2.status_code == 429


def test_api_accepts_key_via_query_param(client, monkeypatch):
    """Klucz podany jako ?api_key= (nie tylko nagłówek) jest akceptowany przez auth (nie 401)."""
    _install_keys(monkeypatch, [_make_key_row(1, "nfg_querykey")])
    resp = client.get("/api/v1/headcount/monthly?api_key=nfg_querykey")
    assert resp.status_code != 401


def test_api_read_only_no_write_endpoints():
    """Żaden endpoint danych finansowych nie dopuszcza POST/PUT/PATCH/DELETE -
    usługa jest strukturalnie read-only (dane płyną z demo_reader, który sam
    odrzuca zapis na poziomie bazy, ale API nie powinno nawet wystawiać
    takiej trasy)."""
    forbidden_methods = {"POST", "PUT", "PATCH", "DELETE"}
    for route in main.app.routes:
        methods = getattr(route, "methods", set()) or set()
        offending = methods & forbidden_methods
        assert not offending, f"Endpoint zapisu znaleziony: {route.path} {offending}"
