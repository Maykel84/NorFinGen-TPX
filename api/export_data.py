"""Generowanie eksportu CSV/Excel NA ŻĄDANIE (Zadanie 3) — bez trwałego
magazynu plików, bez migawki dobowej. Każde wywołanie czyta na świeżo z
`demo_reader` (ten sam read-only pool co reszta `api/routers/*.py`) i buduje
plik w pamięci.

Świadomie NIE reużywa `export_csv.py`/`export_excel.py`/`export_queries.py`
z korzenia repo: te skrypty łączą się jako właściciel bazy (`DATABASE_URL`,
psycopg2, `%s`-style params) i piszą na dysk lokalny — żaden z tych dwóch
faktów nie pasuje do usługi `api/` (kontener Fly.io ma wyłącznie
`DEMO_READER_DATABASE_URL`/`API_KEY_MANAGER_DATABASE_URL`, nigdy dostęp
właściciela — zob. `api/db.py`). Zapytania SQL poniżej są tym samym
zestawieniem co `export_queries.QUERIES`, przepisanym na `asyncpg`
($1/$2 placeholders) i rozszerzonym o filtr zakresu dat.

CSV: `demo_reader`/`export_queries` produkuje PIĘĆ różnie ukształtowanych
zestawień (P&L miesięczny, faktury sprzedaży, faktury zakupu, payroll
miesięczny, payroll per pracownik, postingi GL) — tak jak lokalny
`export_csv.py` od zawsze zapisuje je jako pięć osobnych plików, a nie jeden
spłaszczony CSV (nie dają się sensownie połączyć w jedną tabelę bez utraty
struktury). `/export/csv` zwraca więc ZIP tych pięciu CSV — świadome
odstępstwo od szkicu w prompcie (który zakładał pojedynczy plik .csv),
udokumentowane w docs/SESSION_HANDOFF.md. `/export/excel` zwraca dokładnie
to samo jako jeden wieloarkuszowy .xlsx (bez tego kompromisu — Excel
naturalnie obsługuje wiele arkuszy w jednym pliku).
"""

import csv
import io
import zipfile
from datetime import date

import openpyxl

from api.db import data_pool

# Nazwy kolumn per zestawienie - potrzebne jako nagłówek nawet gdy zapytanie
# nie zwróci żadnego wiersza (pusty wynik asyncpg nie niesie metadanych
# kolumn tak jak psycopg2's cur.description).
_COLUMNS: dict[str, list[str]] = {
    "PL_miesiecznie": [
        "month", "revenue", "labor_cost", "operating_cost", "cogs", "operating_result",
    ],
    "Faktury_sprzedazy": [
        "order_id", "customer_id", "order_date", "invoice_date", "customer_name",
        "customer_number", "city", "postal_code", "count",
        "unit_price_excluding_vat_currency", "amount_excluding_vat_currency", "amount_currency",
    ],
    "Faktury_zakupu": [
        "invoice_number", "supplier_id", "invoice_date", "payment_due_date",
        "supplier_name", "postal_code", "amount_excluding_vat_currency",
        "vat_amount_currency", "amount_currency", "status",
    ],
    "Payroll_miesiecznie": ["month", "date", "headcount", "total_net_payroll"],
    "Payroll_per_pracownik": [
        "date", "month", "employee_id", "employee_name", "department_name",
        "net_amount", "gross_amount", "tax_amount",
    ],
    "Postingi_GL": [
        "date", "voucher_type", "description", "account_number", "amount",
        "vat_amount", "customer_id", "supplier_id", "employee_id",
    ],
}


def _queries(date_from: date, date_to: date) -> dict[str, tuple[str, list]]:
    """Te same zestawienia co `export_queries.QUERIES`, zawężone do
    [date_from, date_to] na kolumnie daty właściwej dla danego źródła
    (order_date/invoice_date/v.date/st.date — jak w oryginale, filtr
    dopisany, reszta zapytania niezmieniona)."""
    params = [date_from, date_to]
    return {
        "PL_miesiecznie": (
            """
            WITH revenue_cte AS (
                SELECT DATE_TRUNC('month', o.order_date) AS month,
                       SUM(ol.amount_excluding_vat_currency) AS revenue
                FROM orders o JOIN order_lines ol ON ol.order_id = o.id
                WHERE o.order_date BETWEEN $1 AND $2
                GROUP BY 1
            ),
            cost_cte AS (
                SELECT DATE_TRUNC('month', v.date) AS month,
                       SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 5000 AND 5999) AS labor_cost,
                       SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 6000 AND 7999) AS operating_cost,
                       SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 4000 AND 4999) AS cogs
                FROM vouchers v JOIN postings p ON p.voucher_id = v.id
                WHERE v.date BETWEEN $1 AND $2
                GROUP BY 1
            )
            SELECT TO_CHAR(COALESCE(r.month, c.month), 'YYYY-MM')       AS month,
                   ROUND(COALESCE(r.revenue, 0))                        AS revenue,
                   ROUND(COALESCE(c.labor_cost, 0))                     AS labor_cost,
                   ROUND(COALESCE(c.operating_cost, 0))                 AS operating_cost,
                   ROUND(COALESCE(c.cogs, 0))                           AS cogs,
                   ROUND(COALESCE(r.revenue, 0)
                       - COALESCE(c.labor_cost, 0)
                       - COALESCE(c.operating_cost, 0)
                       - COALESCE(c.cogs, 0))                           AS operating_result
            FROM revenue_cte r FULL OUTER JOIN cost_cte c ON r.month = c.month
            ORDER BY 1
            """,
            params,
        ),
        "Faktury_sprzedazy": (
            """
            SELECT o.id AS order_id, o.customer_id, o.order_date, o.invoice_date,
                   c.name AS customer_name, c.customer_number, c.city, c.postal_code,
                   ol.count,
                   ol.unit_price_excluding_vat_currency,
                   ol.amount_excluding_vat_currency,
                   ol.amount_currency
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            JOIN order_lines ol ON ol.order_id = o.id
            WHERE o.order_date BETWEEN $1 AND $2
            ORDER BY o.order_date, o.id
            """,
            params,
        ),
        "Faktury_zakupu": (
            """
            SELECT si.invoice_number, si.supplier_id, si.invoice_date, si.payment_due_date,
                   s.name AS supplier_name, s.postal_code,
                   si.amount_excluding_vat_currency,
                   si.vat_amount_currency,
                   si.amount_currency,
                   si.status
            FROM supplier_invoices si
            JOIN suppliers s ON s.id = si.supplier_id
            WHERE si.invoice_date BETWEEN $1 AND $2
            ORDER BY si.invoice_date
            """,
            params,
        ),
        "Payroll_miesiecznie": (
            """
            SELECT TO_CHAR(st.date, 'YYYY-MM') AS month,
                   st.date,
                   COUNT(ps.id)                AS headcount,
                   ROUND(SUM(ps.amount))       AS total_net_payroll
            FROM salary_transactions st
            JOIN payslips ps ON ps.transaction_id = st.id
            WHERE st.date BETWEEN $1 AND $2
            GROUP BY 1, 2 ORDER BY 1
            """,
            params,
        ),
        "Payroll_per_pracownik": (
            """
            SELECT st.date,
                   TO_CHAR(st.date, 'YYYY-MM') AS month,
                   ps.employee_id,
                   e.first_name || ' ' || e.last_name AS employee_name,
                   d.name AS department_name,
                   ps.amount AS net_amount,
                   COALESCE(gross.gross_amount, ps.amount) AS gross_amount,
                   COALESCE(tax.tax_amount, 0) AS tax_amount
            FROM salary_transactions st
            JOIN payslips ps ON ps.transaction_id = st.id
            JOIN employees e ON e.id = ps.employee_id
            LEFT JOIN departments d ON d.id = e.department_id
            LEFT JOIN (
                SELECT payslip_id, SUM(amount) AS gross_amount
                FROM salary_specifications
                WHERE wage_type_id IN (100, 260)
                GROUP BY payslip_id
            ) gross ON gross.payslip_id = ps.id
            LEFT JOIN (
                SELECT payslip_id, -SUM(amount) AS tax_amount
                FROM salary_specifications
                WHERE wage_type_id = 920
                GROUP BY payslip_id
            ) tax ON tax.payslip_id = ps.id
            WHERE st.date BETWEEN $1 AND $2
            ORDER BY st.date, ps.employee_id
            """,
            params,
        ),
        "Postingi_GL": (
            """
            SELECT v.date, v.voucher_type, v.description,
                   p.account_number, p.amount,
                   p.vat_amount, p.customer_id, p.supplier_id, p.employee_id
            FROM vouchers v JOIN postings p ON p.voucher_id = v.id
            WHERE v.date BETWEEN $1 AND $2
            ORDER BY v.date, v.id
            """,
            params,
        ),
    }


async def _fetch_all(date_from: date, date_to: date) -> dict[str, tuple[list[str], list[list]]]:
    pool = data_pool()
    result: dict[str, tuple[list[str], list[list]]] = {}
    async with pool.acquire() as conn:
        for name, (sql, params) in _queries(date_from, date_to).items():
            rows = await conn.fetch(sql, *params)
            columns = list(rows[0].keys()) if rows else _COLUMNS[name]
            result[name] = (columns, [list(r.values()) for r in rows])
    return result


async def generate_csv_export_bytes(date_from: date, date_to: date) -> bytes:
    """ZIP zawierający jeden .csv per zestawienie (zob. docstring modułu)."""
    data = await _fetch_all(date_from, date_to)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, (columns, rows) in data.items():
            sub = io.StringIO()
            writer = csv.writer(sub)
            writer.writerow(columns)
            writer.writerows(rows)
            zf.writestr(f"{name}.csv", sub.getvalue())
    return buf.getvalue()


async def generate_excel_export_bytes(date_from: date, date_to: date) -> bytes:
    """Jeden .xlsx, jeden arkusz per zestawienie — ten sam układ co
    lokalny `export_excel.py`."""
    data = await _fetch_all(date_from, date_to)
    wb = openpyxl.Workbook()
    first = True
    for name, (columns, rows) in data.items():
        ws = wb.active if first else wb.create_sheet(name)
        if first:
            ws.title = name
            first = False
        ws.append(columns)
        for row in rows:
            ws.append([str(v) if v is not None else "" for v in row])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
