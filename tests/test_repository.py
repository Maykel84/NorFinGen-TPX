"""Testy repository.py z mockowanym psycopg2 — weryfikują, że SQL/parametry
budowane z realnych obiektów Pydantic (Order, SupplierInvoice, SalaryTransaction,
Voucher) nie wywalają się (zła liczba %s, brakujący atrybut, źle zagnieżdżone
referencje itd.), bez potrzeby łączenia się z prawdziwym Supabase."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from norfingen.generators.backfill import founding_capital_voucher
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.salary_generator import generate_monthly_salary
from norfingen.generators.supplier_invoice_generator import build_voucher_for_invoice, generate_monthly_supplier_invoices
from norfingen.seed.roster import supplier_by_number


class FakeCursor:
    def __init__(self, fetch_id: int = 1):
        self.executed: list[tuple[str, tuple]] = []
        self._fetch_id = fetch_id

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        # Symuluje zawsze "świeży insert" (RETURNING id zwraca wiersz) — testuje
        # ścieżkę happy-path budowania SQL, nie samą logikę ON CONFLICT (to wymaga
        # realnego Postgresa).
        if "RETURNING id" in self.executed[-1][0] or self.executed[-1][0].strip().upper().startswith("SELECT"):
            return (self._fetch_id,)
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    @property
    def closed(self):
        return False


@pytest.fixture
def fake_repository(monkeypatch):
    from norfingen.db import repository

    fake_conn = FakeConnection()
    monkeypatch.setattr(repository, "_conn", fake_conn)
    monkeypatch.setattr(repository, "get_connection", lambda: fake_conn)
    return repository, fake_conn


def test_save_order_with_two_lines(fake_repository):
    repository, fake_conn = fake_repository
    orders = generate_monthly_orders(2024, 1)
    k01 = next(o for o in orders if o.customer.id == 1)  # pattern B -> 2 linie
    assert len(k01.orderLines) == 2

    repository.save_all(k01)

    sql_texts = [sql for sql, _ in fake_conn.cursor_obj.executed]
    assert any("INSERT INTO orders" in s for s in sql_texts)
    assert sum("INSERT INTO order_lines" in s for s in sql_texts) == 2
    assert fake_conn.committed


def test_save_supplier_invoice(fake_repository):
    repository, fake_conn = fake_repository
    invoices = generate_monthly_supplier_invoices(2024, 1)
    invoice = invoices[0]

    repository.save_all(invoice)

    sql_texts = [sql for sql, _ in fake_conn.cursor_obj.executed]
    assert any("INSERT INTO supplier_invoices" in s for s in sql_texts)


def test_save_supplier_invoice_voucher(fake_repository):
    repository, fake_conn = fake_repository
    invoices = generate_monthly_supplier_invoices(2024, 1)
    invoice = invoices[0]
    supplier = supplier_by_number(invoice.invoiceNumber.split("-")[0])
    voucher = build_voucher_for_invoice(invoice, supplier)

    repository.save_all(voucher)

    sql_texts = [sql for sql, _ in fake_conn.cursor_obj.executed]
    assert any("INSERT INTO vouchers" in s for s in sql_texts)
    assert sum("INSERT INTO postings" in s for s in sql_texts) == len(voucher.postings)


def test_save_salary_transaction_with_payslips_and_specs(fake_repository):
    repository, fake_conn = fake_repository
    transaction, vouchers = generate_monthly_salary(2024, 6)  # czerwiec -> specs ciekawsze

    repository.save_all(transaction)

    sql_texts = [sql for sql, _ in fake_conn.cursor_obj.executed]
    assert any("INSERT INTO salary_transactions" in s for s in sql_texts)
    assert sum("INSERT INTO payslips" in s for s in sql_texts) == len(transaction.payslips)
    expected_specs = sum(len(p.specifications) for p in transaction.payslips)
    assert sum("INSERT INTO salary_specifications" in s for s in sql_texts) == expected_specs

    for voucher in vouchers:
        fake_conn.cursor_obj.executed.clear()
        repository.save_all(voucher)
        sql_texts = [sql for sql, _ in fake_conn.cursor_obj.executed]
        assert any("INSERT INTO vouchers" in s for s in sql_texts)


def test_save_founding_capital_voucher(fake_repository):
    repository, fake_conn = fake_repository
    voucher = founding_capital_voucher()

    repository.save_all(voucher)

    sql_texts = [sql for sql, _ in fake_conn.cursor_obj.executed]
    assert any("INSERT INTO vouchers" in s for s in sql_texts)
    assert sum("INSERT INTO postings" in s for s in sql_texts) == 2


def test_month_already_generated(fake_repository):
    repository, fake_conn = fake_repository

    fake_conn.cursor_obj.fetchone = lambda: (0,)
    assert repository.month_already_generated(2024, 1) is False

    fake_conn.cursor_obj.fetchone = lambda: (5,)
    assert repository.month_already_generated(2024, 1) is True


def test_save_all_accepts_dict():
    from norfingen.db import repository

    voucher = founding_capital_voucher()
    as_dict = voucher.model_dump(mode="json")

    reconstructed = repository._model_from_dict(as_dict)
    assert reconstructed.voucherType == voucher.voucherType
    assert len(reconstructed.postings) == len(voucher.postings)
