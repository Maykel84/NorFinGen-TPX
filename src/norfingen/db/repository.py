"""Warstwa persystencji — psycopg2 + Supabase Postgres.

save_all(data) jest główną funkcją używaną jako persist_fn w generators/backfill.py
(zob. run_backfill.py / run_daily.py). Przyjmuje instancję Order, SupplierInvoice,
SalaryTransaction lub Voucher (to wszystko, co backfill.py faktycznie emituje) —
albo równoważny dict (np. z .model_dump()), żeby zostać zgodna z sygnaturą
save_all(data: dict) z zadania. Każdy zapis jest idempotentny: INSERT ... ON
CONFLICT DO NOTHING na naturalnym kluczu biznesowym (np. invoice_number,
(customer_id, order_date), (year, month), (date, description)) — wielokrotne
uruchomienie run_backfill.py / run_daily.py dla tego samego zakresu dat nie
tworzy duplikatów.

seed_reference_data() zasila tabele Warstwy 1 (departments, employees,
employments, customers, suppliers, accounts, vat_types, products) z
norfingen.seed.roster — to dane referencyjne, nigdy emitowane przez generatory
W2/W3, więc trzeba je wgrać raz na początku (run_backfill.py i run_daily()
wywołują ją zawsze, idempotentnie, na wszelki wypadek pustej bazy).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Union

import psycopg2

from norfingen.config import settings
from norfingen.generators.bank_transaction_generator import OVERDUE_PAYMENT_DELAY_DAYS
from norfingen.generators.voucher import Voucher
from norfingen.models.bank_transaction import BankTransaction, BankTransactionType
from norfingen.models.base import TripletexRef
from norfingen.models.hours import HourEntry
from norfingen.models.order import Order, OrderLine, OrderStatus
from norfingen.models.salary import SalaryTransaction
from norfingen.models.supplier_invoice import SupplierInvoice
from norfingen.seed.roster import (
    CUSTOMER_PRICE_MULTIPLIER,
    CUSTOMERS,
    DEPARTMENTS,
    EMPLOYEES,
    PRODUCTS,
    PROJECTS,
    SERVICES,
    SUPPLIERS,
    numeric_id,
)

MAX_PAYMENT_TERMS_DAYS = 45  # najdłuższy payment_terms w roster.CUSTOMERS (K03/K08)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Plan kont NS 4102 i kody MVA nie są emitowane przez żaden generator — to
# stałe dane referencyjne. Źródło: docs/norfingen_warstwa1_schemas.html.
# (number, name, type, vat_type_id)
ACCOUNTS_SEED: list[tuple[int, str, str, Optional[int]]] = [
    (1200, "Maskiner og anlegg", "ASSETS", None),
    (1500, "Kundefordringer", "ASSETS", None),
    (1910, "Bankinnskudd, driftskonto", "ASSETS", None),
    (1940, "Bankinnskudd, skattetrekkskonto", "ASSETS", None),
    (2000, "Aksjekapital", "EQUITY_AND_LIABILITY", None),
    (2400, "Leverandørgjeld", "EQUITY_AND_LIABILITY", None),
    (2700, "Skyldig arbeidsgiveravgift", "EQUITY_AND_LIABILITY", None),
    (2710, "Skyldig lønn", "EQUITY_AND_LIABILITY", None),
    (2740, "Skyldig skattetrekk", "EQUITY_AND_LIABILITY", None),
    (2770, "Skyldig merverdiavgift", "EQUITY_AND_LIABILITY", None),
    (2930, "Skyldige feriepenger", "EQUITY_AND_LIABILITY", None),
    (3000, "Salgsinntekter, IT-tjenester", "OPERATING_INCOME", 3),
    (3100, "Lisensintekter", "OPERATING_INCOME", 3),
    (5000, "Lønn, fast", "OPERATING_EXPENSE", None),
    (5400, "Arbeidsgiveravgift", "OPERATING_EXPENSE", None),
    (5900, "Annen personalkostnad", "OPERATING_EXPENSE", None),
    (6300, "Husleie og leie av lokaler", "OPERATING_EXPENSE", 1),
    (6410, "Lisenser og programvare", "OPERATING_EXPENSE", 1),
    (6540, "Inventar og utstyr", "OPERATING_EXPENSE", 1),
    (6700, "Fremmed tjeneste", "OPERATING_EXPENSE", 1),
    (6800, "Kontorkostnader", "OPERATING_EXPENSE", 1),
    (6900, "Telefon og internett", "OPERATING_EXPENSE", 1),
    (7000, "Reisekostnader", "OPERATING_EXPENSE", 1),
    (7500, "Forsikringspremier", "OPERATING_EXPENSE", 1),
]

# (id, name, number, percentage, vat_code) — id zgodny z TripletexRef(id=...)
# używanym w kodzie (SALES_VAT_TYPE_REF=3, PURCHASE_VAT_TYPE_REF=1).
VAT_TYPES_SEED: list[tuple[int, str, Optional[str], float, str]] = [
    (0, "Utenfor MVA-loven", "0", 0.0, "0"),
    (1, "Inngående MVA, høy sats", "1", 25.0, "1"),
    (3, "Utgående MVA, høy sats", "3", 25.0, "3"),
    (6, "Fritatt / eksport", "6", 0.0, "6"),
]

NORWAY_COUNTRY_ID = 161
NOK_CURRENCY_ID = 1

_conn = None


def get_connection():
    """Leniwie tworzy i cache'uje jedno połączenie psycopg2 — backfill robi
    setki/tysiące małych insertów, więc otwieranie nowego połączenia na każdy
    obiekt byłoby zbyt kosztowne."""
    global _conn
    if _conn is None or _conn.closed:
        if not settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL nie jest ustawione w środowisku (.env)")
        _conn = psycopg2.connect(settings.DATABASE_URL)
    return _conn


def close_connection() -> None:
    global _conn
    if _conn is not None and not _conn.closed:
        _conn.close()
    _conn = None


def terminate_stale_sessions(min_idle_seconds: int = 60) -> int:
    """Zabija sesje 'idle in transaction' (poza bieżącą) — pozostałość po
    zerwanych połączeniach (sieć/uśpienie maszyny w trakcie backfillu). Taka
    sesja trzyma otwartą transakcję z niezacommitowanym INSERT-em i blokuje
    kolejne insercje do tej samej tabeli/indeksu, dopóki serwer nie wykryje
    martwego peera przez TCP keepalive — co może trwać bardzo długo i objawia
    się jako "statement timeout" przy retry na zupełnie nowym połączeniu.
    Wywoływana w pętli retry run_backfill_daily po napotkaniu błędu. Zwraca
    liczbę zabitych sesji."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT pid FROM pg_stat_activity
               WHERE datname = current_database()
                 AND state = 'idle in transaction'
                 AND pid <> pg_backend_pid()
                 AND now() - state_change > (%s || ' seconds')::interval""",
            (min_idle_seconds,),
        )
        pids = [row[0] for row in cur.fetchall()]
        for pid in pids:
            cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
    conn.commit()
    return len(pids)


def ensure_schema() -> None:
    """Wykonuje db/schema.sql (16× CREATE TABLE IF NOT EXISTS) — bezpieczne do
    wielokrotnego wywołania, idempotentne."""
    sql = SCHEMA_PATH.read_text()
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def seed_reference_data() -> None:
    """Zasila tabele referencyjne Warstwy 1 z norfingen.seed.roster + statyczny
    plan kont/kody MVA. Idempotentne (ON CONFLICT DO NOTHING) — bezpieczne do
    wywołania przy każdym starcie run_backfill.py / run_daily()."""
    seed_services()  # PRZED products — products.service_code ma FK do services(code)

    conn = get_connection()
    with conn.cursor() as cur:
        for d in DEPARTMENTS:
            cur.execute(
                "INSERT INTO departments (id, name, number) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO NOTHING",
                (d.number, d.name, str(d.number)),
            )

        for vat_type in VAT_TYPES_SEED:
            cur.execute(
                "INSERT INTO vat_types (id, name, number, percentage, vat_code) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                vat_type,
            )

        for account in ACCOUNTS_SEED:
            cur.execute(
                "INSERT INTO accounts (number, name, type, vat_type_id) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (number) DO NOTHING",
                account,
            )

        for product in PRODUCTS:
            cur.execute(
                """INSERT INTO products (id, name, number, sales_price, vat_type_id, currency_id, service_code)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                       name = EXCLUDED.name,
                       number = EXCLUDED.number,
                       sales_price = EXCLUDED.sales_price,
                       service_code = EXCLUDED.service_code""",
                (numeric_id(product.number), product.name, product.number, product.default_price, 3,
                 NOK_CURRENCY_ID, product.service_code),
            )

        for employee in EMPLOYEES:
            emp_id = numeric_id(employee.number)
            cur.execute(
                "INSERT INTO employees (id, first_name, last_name, employee_number, department_id) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (emp_id, employee.first_name, employee.last_name, employee.number, employee.department_number),
            )
            cur.execute(
                "INSERT INTO employments (employee_id, start_date, employment_type, remuneration_type, "
                "weekly_working_hours, percentage, payroll_tax_zone) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (employee_id) DO NOTHING",
                (emp_id, employee.start_date, "ORDINARY", "FIXED_SALARY", 37.5, 100.0, "ZONE_1"),
            )

        for customer in CUSTOMERS:
            cur.execute(
                """INSERT INTO customers
                       (id, name, customer_number, city, country_id, currency_id,
                        onboarding_date, churn_date, segment, price_multiplier)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                       onboarding_date = EXCLUDED.onboarding_date,
                       churn_date = EXCLUDED.churn_date,
                       segment = EXCLUDED.segment,
                       price_multiplier = EXCLUDED.price_multiplier""",
                (
                    numeric_id(customer.number), customer.name, customer.number, customer.city,
                    NORWAY_COUNTRY_ID, NOK_CURRENCY_ID,
                    customer.onboarding_date, customer.churn_date, customer.segment,
                    CUSTOMER_PRICE_MULTIPLIER[customer.number],
                ),
            )

        for supplier in SUPPLIERS:
            cur.execute(
                "INSERT INTO suppliers (id, name, supplier_number, country_id, currency_id) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (numeric_id(supplier.number), supplier.name, supplier.number, NORWAY_COUNTRY_ID, NOK_CURRENCY_ID),
            )

    conn.commit()
    seed_projects()


def seed_projects() -> None:
    """Zasila tabelę projects z norfingen.seed.roster.PROJECTS. Idempotentne
    (ON CONFLICT DO NOTHING). Wydzielona jako osobna, publiczna funkcja (nie
    tylko wewnętrzna pętla w seed_reference_data()) na wypadek potrzeby
    ponownego zasilenia samych projektów bez przechodzenia całego seeda."""
    conn = get_connection()
    with conn.cursor() as cur:
        for project in PROJECTS:
            cur.execute(
                "INSERT INTO projects (id, number, name, customer_id, start_date) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (number) DO NOTHING",
                (numeric_id(project.number), project.number, project.name, project.customer_id, project.start_date),
            )
    conn.commit()


def seed_services() -> None:
    """Zasila tabelę services z norfingen.seed.roster.SERVICES (Faza 1).
    ON CONFLICT DO UPDATE (nie DO NOTHING) — katalog usług to metadane, które
    powinny odzwierciedlać aktualny stan roster.py przy każdym seedzie, nie
    tylko przy pierwszym."""
    conn = get_connection()
    with conn.cursor() as cur:
        for service in SERVICES:
            cur.execute(
                """INSERT INTO services
                       (code, name, description, billing_model, availability,
                        base_price_enterprise, base_price_mid, base_price_smb)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (code) DO UPDATE SET
                       name = EXCLUDED.name,
                       description = EXCLUDED.description,
                       billing_model = EXCLUDED.billing_model,
                       availability = EXCLUDED.availability,
                       base_price_enterprise = EXCLUDED.base_price_enterprise,
                       base_price_mid = EXCLUDED.base_price_mid,
                       base_price_smb = EXCLUDED.base_price_smb""",
                (
                    service.code, service.name, service.description,
                    service.billing_model.value, service.availability.value,
                    service.base_price_enterprise, service.base_price_mid, service.base_price_smb,
                ),
            )
    conn.commit()


def month_already_generated(year: int, month: int) -> bool:
    """Sprawdza czy orders dla danego miesiąca już istnieją w bazie — pozwala
    run_daily() pominąć generację, zamiast polegać wyłącznie na ON CONFLICT
    DO NOTHING (poprawne, ale generuje i odrzuca cały miesiąc na próżno)."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM orders WHERE EXTRACT(year FROM order_date) = %s "
            "AND EXTRACT(month FROM order_date) = %s",
            (year, month),
        )
        count = cur.fetchone()[0]
    return count > 0


def _upsert_get_id(cur, insert_sql: str, insert_params: tuple, select_sql: str, select_params: tuple) -> int:
    """INSERT ... ON CONFLICT DO NOTHING RETURNING id; jeśli konflikt (brak
    wiersza), pobiera istniejące id przez select_sql. Wzorzec wymagany, bo
    ON CONFLICT DO NOTHING nie zwraca wiersza gdy nic nie wstawiono."""
    cur.execute(insert_sql, insert_params)
    row = cur.fetchone()
    if row is not None:
        return row[0]
    cur.execute(select_sql, select_params)
    row = cur.fetchone()
    return row[0]


def _ref_id(ref) -> Optional[int]:
    return ref.id if ref is not None else None


def _save_order(cur, order: Order) -> None:
    order_id = _upsert_get_id(
        cur,
        """INSERT INTO orders
               (customer_id, order_date, delivery_date, invoice_date, invoices_due_in,
                invoices_due_in_type, department_id, currency_id, is_prioritize_vat, comment,
                our_contact_id, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (customer_id, order_date) DO NOTHING
           RETURNING id""",
        (
            order.customer.id,
            order.orderDate,
            order.deliveryDate,
            order.invoiceDate,
            order.invoicesDueIn,
            order.invoicesDueInType.value,
            _ref_id(order.department),
            _ref_id(order.currency),
            order.isPrioritizeVat,
            order.comment,
            _ref_id(order.ourContact),
            order.status.value,
        ),
        "SELECT id FROM orders WHERE customer_id = %s AND order_date = %s",
        (order.customer.id, order.orderDate),
    )

    for line in order.orderLines:
        cur.execute(
            """INSERT INTO order_lines
                   (order_id, product_id, count, unit_price_excluding_vat_currency, vat_type_id,
                    discount, amount_excluding_vat_currency, amount_currency)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (order_id, product_id) DO NOTHING""",
            (
                order_id,
                _ref_id(line.product),
                line.count,
                line.unitPriceExcludingVatCurrency,
                _ref_id(line.vatType),
                line.discount,
                line.amountExcludingVatCurrency,
                line.amountCurrency,
            ),
        )


def _save_supplier_invoice(cur, invoice: SupplierInvoice) -> None:
    cur.execute(
        """INSERT INTO supplier_invoices
               (invoice_number, supplier_id, invoice_date, received_date, payment_due_date,
                amount_currency, amount_excluding_vat_currency, vat_amount_currency, currency_id,
                account_number, vat_type_id, comment, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (invoice_number) DO NOTHING""",
        (
            invoice.invoiceNumber,
            invoice.supplier.id,
            invoice.invoiceDate,
            invoice.receivedDate,
            invoice.paymentDueDate,
            invoice.amountCurrency,
            invoice.amountExcludingVatCurrency,
            invoice.vatAmountCurrency,
            _ref_id(invoice.currency),
            _ref_id(invoice.account),
            _ref_id(invoice.vatType),
            invoice.comment,
            invoice.status.value,
        ),
    )


def _save_salary_transaction(cur, transaction: SalaryTransaction) -> None:
    transaction_id = _upsert_get_id(
        cur,
        """INSERT INTO salary_transactions (date, year, month, status)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (year, month) DO NOTHING
           RETURNING id""",
        (transaction.date, transaction.year, transaction.month, transaction.status.value),
        "SELECT id FROM salary_transactions WHERE year = %s AND month = %s",
        (transaction.year, transaction.month),
    )

    for payslip in transaction.payslips:
        payslip_id = _upsert_get_id(
            cur,
            """INSERT INTO payslips (transaction_id, employee_id, date, amount)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (transaction_id, employee_id) DO NOTHING
               RETURNING id""",
            (transaction_id, payslip.employee.id, payslip.date, payslip.amount),
            "SELECT id FROM payslips WHERE transaction_id = %s AND employee_id = %s",
            (transaction_id, payslip.employee.id),
        )

        for spec in payslip.specifications:
            cur.execute(
                """INSERT INTO salary_specifications (payslip_id, wage_type_id, description, amount)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (payslip_id, wage_type_id) DO NOTHING""",
                (payslip_id, spec.wageType.id, spec.description, spec.amount),
            )


def _save_voucher(cur, voucher: Voucher) -> int:
    voucher_id = _upsert_get_id(
        cur,
        """INSERT INTO vouchers (date, description, voucher_type)
           VALUES (%s, %s, %s)
           ON CONFLICT (date, description) DO NOTHING
           RETURNING id""",
        (voucher.date, voucher.description, voucher.voucherType.value),
        "SELECT id FROM vouchers WHERE date = %s AND description = %s",
        (voucher.date, voucher.description),
    )

    for posting in voucher.postings:
        cur.execute(
            """INSERT INTO postings
                   (voucher_id, date, description, account_number, amount, currency,
                    vat_type_id, vat_amount, customer_id, supplier_id, employee_id, department_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (voucher_id, account_number, amount) DO NOTHING""",
            (
                voucher_id,
                posting.date,
                posting.description,
                posting.account.number,
                posting.amount,
                posting.currency,
                _ref_id(posting.vatType),
                posting.vatAmount,
                _ref_id(posting.customer),
                _ref_id(posting.supplier),
                _ref_id(posting.employee),
                _ref_id(posting.department),
            ),
        )

    return voucher_id


def _model_from_dict(data: dict):
    """Rekonstrukcja modelu Pydantic z dict (np. .model_dump()) na podstawie
    charakterystycznych pól — pozwala save_all() przyjmować dict zgodnie z
    sygnaturą save_all(data: dict) z zadania, nie tylko żywe instancje modeli."""
    if "voucherType" in data:
        return Voucher.model_validate(data)
    if "orderLines" in data:
        return Order.model_validate(data)
    if "invoiceNumber" in data:
        return SupplierInvoice.model_validate(data)
    if "payslips" in data:
        return SalaryTransaction.model_validate(data)
    raise ValueError(f"save_all: nie można rozpoznać typu danych z kluczy {sorted(data)}")


def save_all(data: Union[Order, SupplierInvoice, SalaryTransaction, Voucher, dict]) -> None:
    """Idempotentny zapis jednego obiektu wygenerowanego przez generatory W2/W3
    do Supabase. Używana jako persist_fn w generators/backfill.py — backfill
    woła ją raz na każdy Order/SupplierInvoice/SalaryTransaction/Voucher,
    razem z dzieckami (orderLines/payslips+specifications/postings)."""
    if isinstance(data, dict):
        data = _model_from_dict(data)

    conn = get_connection()
    with conn.cursor() as cur:
        if isinstance(data, Order):
            _save_order(cur, data)
        elif isinstance(data, SupplierInvoice):
            _save_supplier_invoice(cur, data)
        elif isinstance(data, SalaryTransaction):
            _save_salary_transaction(cur, data)
        elif isinstance(data, Voucher):
            _save_voucher(cur, data)
        else:
            raise TypeError(f"save_all: nieobsługiwany typ {type(data)!r}")
    conn.commit()


def save_orders(orders: list[Order]) -> None:
    """Zapisuje listę Order (np. z generate_daily_orders) — cienki wrapper
    nad save_all() na wielu obiektach naraz, jak w run_daily.py."""
    for order in orders:
        save_all(order)


def _save_bank_transaction(cur, transaction: BankTransaction, voucher_id: Optional[int]) -> None:
    cur.execute(
        """INSERT INTO bank_transactions
               (date, amount, transaction_type, description, customer_id, supplier_id,
                order_id, supplier_invoice_id, account_from, account_to, voucher_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT DO NOTHING""",
        (
            transaction.date,
            transaction.amount,
            transaction.transaction_type.value,
            transaction.description,
            transaction.customer_id,
            transaction.supplier_id,
            transaction.order_id,
            transaction.supplier_invoice_id,
            transaction.account_from,
            transaction.account_to,
            voucher_id,
        ),
    )


def save_bank_transactions(transactions: list[tuple[BankTransaction, Voucher]]) -> None:
    """Zapisuje pary (BankTransaction, Voucher) z generate_daily_bank_transactions.
    Dla płatności OUTGOING oznacza powiązaną supplier_invoice jako PAID —
    dzięki temu get_unpaid_supplier_invoices() nie zwróci jej ponownie następnego
    dnia (bez tego status pozostałby na sztywno UNPAID/heurystyce z generatora)."""
    conn = get_connection()
    with conn.cursor() as cur:
        for transaction, voucher in transactions:
            voucher_id = _save_voucher(cur, voucher)
            _save_bank_transaction(cur, transaction, voucher_id)
            if transaction.transaction_type == BankTransactionType.OUTGOING and transaction.supplier_invoice_id is not None:
                cur.execute(
                    "UPDATE supplier_invoices SET status = 'PAID' WHERE id = %s",
                    (transaction.supplier_invoice_id,),
                )
    conn.commit()


def _save_hour_entry(cur, entry: HourEntry) -> None:
    cur.execute(
        """INSERT INTO hour_entries (date, employee_id, project_id, activity_type, hours, description)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (date, employee_id, project_id, activity_type) DO NOTHING""",
        (entry.date, entry.employee_id, entry.project_id, entry.activity_type.value, entry.hours, entry.description),
    )


def save_hour_entries(entries: list[HourEntry]) -> None:
    conn = get_connection()
    with conn.cursor() as cur:
        for entry in entries:
            _save_hour_entry(cur, entry)
    conn.commit()


def save_salary(transaction: SalaryTransaction, vouchers: list[Voucher]) -> None:
    """Zapisuje SalaryTransaction (+payslips+specifications) i odpowiadające
    Vouchery (lista płac, AGA, ew. feriepenger) — para zwracana przez
    generate_monthly_salary()."""
    save_all(transaction)
    for voucher in vouchers:
        save_all(voucher)


ORDER_PAYMENT_LOOKBACK_DAYS = MAX_PAYMENT_TERMS_DAYS + OVERDUE_PAYMENT_DELAY_DAYS  # OVERDUE płaci +90 dni później


def get_orders_for_payment_window(as_of: date, lookback_days: int = ORDER_PAYMENT_LOOKBACK_DAYS) -> list[Order]:
    """Rekonstruuje Order (+orderLines) z bazy, wystawione w oknie
    [as_of-lookback_days, as_of]. Okno pokrywa najdłuższy payment_terms w
    roster.CUSTOMERS (45 dni) + opóźnienie płatności OVERDUE (90 dni) —
    inaczej opóźnione faktury nigdy nie zostałyby dopasowane do swojej
    (późniejszej) daty płatności. generate_daily_bank_transactions() i tak
    dopasowuje tylko zamówienia, których obliczona data płatności == as_of
    (i pomija WRITTEN_OFF), więc powtórne przetworzenie tego samego okna
    kolejnego dnia jest nieszkodliwe (ON CONFLICT DO NOTHING w
    save_bank_transactions)."""
    conn = get_connection()
    start = as_of - timedelta(days=lookback_days)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, customer_id, order_date, delivery_date, invoice_date,
                      invoices_due_in, department_id, comment, status
               FROM orders WHERE invoice_date BETWEEN %s AND %s""",
            (start, as_of),
        )
        order_rows = cur.fetchall()

        order_ids = [row[0] for row in order_rows]
        lines_by_order: dict[int, list] = {}
        if order_ids:
            cur.execute(
                """SELECT order_id, product_id, count, unit_price_excluding_vat_currency,
                          vat_type_id, discount
                   FROM order_lines WHERE order_id = ANY(%s)""",
                (order_ids,),
            )
            for row in cur.fetchall():
                lines_by_order.setdefault(row[0], []).append(row)

    orders: list[Order] = []
    for oid, customer_id, order_date, delivery_date, invoice_date, invoices_due_in, department_id, comment, status in order_rows:
        order_lines = [
            OrderLine(
                product=TripletexRef(id=l_product_id) if l_product_id is not None else None,
                count=float(l_count) if l_count is not None else 1.0,
                unitPriceExcludingVatCurrency=float(l_price) if l_price is not None else 0.0,
                vatType=TripletexRef(id=l_vat_type_id) if l_vat_type_id is not None else None,
                discount=float(l_discount) if l_discount is not None else 0.0,
            )
            for (_, l_product_id, l_count, l_price, l_vat_type_id, l_discount) in lines_by_order.get(oid, [])
        ]
        orders.append(Order(
            id=oid,
            customer=TripletexRef(id=customer_id),
            orderDate=order_date,
            deliveryDate=delivery_date,
            invoiceDate=invoice_date,
            invoicesDueIn=invoices_due_in or 30,
            department=TripletexRef(id=department_id) if department_id is not None else None,
            comment=comment,
            status=OrderStatus(status) if status else OrderStatus.PAID,
            orderLines=order_lines,
        ))
    return orders


def get_unpaid_supplier_invoices(as_of: date, lookback_days: int = MAX_PAYMENT_TERMS_DAYS) -> list[SupplierInvoice]:
    """Rekonstruuje SupplierInvoice ze statusem UNPAID, których payment_due_date
    wypada w oknie [as_of-lookback_days, as_of]. Status przełącza się na PAID w
    save_bank_transactions() po zaksięgowaniu płatności — raz przetworzona
    faktura nie pojawi się tu ponownie."""
    conn = get_connection()
    start = as_of - timedelta(days=lookback_days)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, invoice_number, supplier_id, invoice_date, received_date,
                      payment_due_date, amount_currency, account_number, comment
               FROM supplier_invoices
               WHERE status = 'UNPAID' AND payment_due_date BETWEEN %s AND %s""",
            (start, as_of),
        )
        rows = cur.fetchall()

    invoices: list[SupplierInvoice] = []
    for iid, invoice_number, supplier_id, invoice_date, received_date, payment_due_date, amount_currency, account_number, comment in rows:
        invoices.append(SupplierInvoice(
            id=iid,
            invoiceNumber=invoice_number,
            supplier=TripletexRef(id=supplier_id),
            invoiceDate=invoice_date,
            receivedDate=received_date,
            paymentDueDate=payment_due_date,
            amountCurrency=float(amount_currency),
            account=TripletexRef(id=account_number) if account_number is not None else None,
            comment=comment,
        ))
    return invoices
