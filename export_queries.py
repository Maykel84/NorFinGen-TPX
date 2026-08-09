"""NorFingen — zapytania SQL współdzielone przez export_excel.py i export_csv.py.

Poprawka nazewnictwa (2026-07) — wszystkie aliasy kolumn (AS) używają
angielskich nazw zgodnych z Tripletex API / db/schema.sql, nie polskich
opisowych (klient/dostawca/wartosc_netto/ilosc itd.) — zgłoszone jako
utrudnienie w pracy z eksportem w Tableau/Power BI (mieszanie konwencji w
tym samym arkuszu). Priorytet: gdzie DB ma już nazwę kolumny (np.
`amount_excluding_vat_currency`, `unit_price_excluding_vat_currency`,
`count`, `description`, `account_number`) — eksport używa DOKŁADNIE tej
samej nazwy, bez skracania/tłumaczenia, żeby zachować 100% spójność
baza<->eksport. Nazwy arkuszy (klucze tego słownika) NIE zmienione — zob.
docs/SESSION_HANDOFF.md dla pełnej mapy stara->nowa nazwa kolumny.
"""

QUERIES = {
    "PL_miesiecznie": """
        WITH revenue_cte AS (
            SELECT DATE_TRUNC('month', o.order_date) AS month,
                   SUM(ol.amount_excluding_vat_currency) AS revenue
            FROM orders o JOIN order_lines ol ON ol.order_id = o.id
            GROUP BY 1
        ),
        cost_cte AS (
            SELECT DATE_TRUNC('month', v.date) AS month,
                   SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 5000 AND 5999) AS labor_cost,
                   SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 6000 AND 7999) AS operating_cost,
                   SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 4000 AND 4999) AS cogs
            FROM vouchers v JOIN postings p ON p.voucher_id = v.id
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
    "Faktury_sprzedazy": """
        SELECT o.id AS order_id, o.customer_id, o.order_date, o.invoice_date,
               c.name AS customer_name, c.customer_number, c.city, c.postal_code,
               ol.count,
               ol.unit_price_excluding_vat_currency,
               ol.amount_excluding_vat_currency,
               ol.amount_currency
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        JOIN order_lines ol ON ol.order_id = o.id
        ORDER BY o.order_date, o.id
    """,
    "Faktury_zakupu": """
        SELECT si.invoice_number, si.supplier_id, si.invoice_date, si.payment_due_date,
               s.name AS supplier_name, s.postal_code,
               si.amount_excluding_vat_currency,
               si.vat_amount_currency,
               si.amount_currency,
               si.status
        FROM supplier_invoices si
        JOIN suppliers s ON s.id = si.supplier_id
        ORDER BY si.invoice_date
    """,
    "Payroll_miesiecznie": """
        SELECT TO_CHAR(st.date, 'YYYY-MM') AS month,
               st.date,
               COUNT(ps.id)                AS headcount,
               ROUND(SUM(ps.amount))       AS total_net_payroll
        FROM salary_transactions st
        JOIN payslips ps ON ps.transaction_id = st.id
        GROUP BY 1, 2 ORDER BY 1
    """,
    "Payroll_per_pracownik": """
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
            -- wage_type_id 100 (Fast lønn) + 260 (Feriepenger) — zob. models/salary.py
            SELECT payslip_id, SUM(amount) AS gross_amount
            FROM salary_specifications
            WHERE wage_type_id IN (100, 260)
            GROUP BY payslip_id
        ) gross ON gross.payslip_id = ps.id
        LEFT JOIN (
            -- wage_type_id 920 (Skattetrekk) — przechowywane jako ujemne, tax_amount dodatnie
            SELECT payslip_id, -SUM(amount) AS tax_amount
            FROM salary_specifications
            WHERE wage_type_id = 920
            GROUP BY payslip_id
        ) tax ON tax.payslip_id = ps.id
        ORDER BY st.date, ps.employee_id
    """,
    "Postingi_GL": """
        SELECT v.date, v.voucher_type, v.description,
               p.account_number, p.amount,
               p.vat_amount, p.customer_id, p.supplier_id, p.employee_id
        FROM vouchers v JOIN postings p ON p.voucher_id = v.id
        ORDER BY v.date, v.id
    """,
}
