"""The safety net in conftest.py works: an unpatched repository call fails at once and never reaches a database."""

import psycopg2
import pytest

from norfingen.config import settings
from norfingen.db import repository


def test_database_url_is_unreachable_during_tests():
    assert settings.DATABASE_URL.startswith("postgresql://tests-never-touch-a-database@127.0.0.1:1/")


def test_an_unpatched_repository_call_fails_fast_instead_of_reaching_a_database():
    repository.close_connection()
    with pytest.raises(psycopg2.OperationalError):
        repository.get_unpaid_supplier_invoices(__import__("datetime").date(2024, 1, 31))
    repository.close_connection()
