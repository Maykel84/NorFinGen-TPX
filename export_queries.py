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
                   - COALESCE(c.cogs, 0))                           AS operating_result,
               ((COALESCE(r.month, c.month)::date + INTERVAL '1 month' - INTERVAL '1 day')::date
                   > GREATEST((SELECT MAX(date) FROM vouchers), (SELECT MAX(order_date) FROM orders))) AS is_partial
        FROM revenue_cte r FULL OUTER JOIN cost_cte c ON r.month = c.month
        ORDER BY 1
    """,
    # The invoice status is DERIVED from what really happened (audit 2026-11-16, phase 5), not copied from the customer's modelled
    # behaviour (orders.status: PAID | OVERDUE | WRITTEN_OFF, still what drives the generator):
    #   invoice_status    PAID         a payment is booked in the bank (paid_date is set) - always, so PAID <=> paid_date
    #                     OPEN         no payment yet and the bank day of the due date has not passed
    #                     OVERDUE      no payment yet and the due date (moved to a working day) has passed
    #                     WRITTEN_OFF  the write-off voucher is booked (Dr 7830 + Dr 2700 / Cr 1500, phase 4)
    #   is_overdue        true while the invoice is OVERDUE (open and past due)
    #   paid_late         true when it was paid more than 7 days after the due date (the model's late payers pay +90 days;
    #                     weekend and holiday shifts are a few days and do not count)
    #   payment_due_date  invoice_date + payment terms
    #   paid_date         date of the customer's payment in the bank; NULL = not paid (yet, or never)
    # "Today" is the newest generated date, not the clock, so a database that stopped yesterday is still consistent.
    "Faktury_sprzedazy": """
        SELECT o.id AS order_id, o.customer_id, o.order_date, o.invoice_date,
               c.name AS customer_name, c.customer_number, c.city, c.postal_code,
               ol.count,
               ol.unit_price_excluding_vat_currency,
               ol.amount_excluding_vat_currency,
               ol.amount_currency,
               s.st AS invoice_status,
               (s.st = 'OVERDUE') AS is_overdue,
               (o.invoice_date + o.invoices_due_in) AS payment_due_date,
               b.date AS paid_date,
               COALESCE(b.date > (o.invoice_date + o.invoices_due_in) + 7, FALSE) AS paid_late
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        JOIN order_lines ol ON ol.order_id = o.id
        LEFT JOIN bank_transactions b ON b.order_id = o.id AND b.transaction_type = 'INCOMING'
        CROSS JOIN LATERAL (SELECT CASE WHEN o.write_off_voucher_id IS NOT NULL THEN 'WRITTEN_OFF'
                  WHEN b.date IS NOT NULL THEN 'PAID'
                  WHEN (o.invoice_date + o.invoices_due_in
                        + CASE EXTRACT(ISODOW FROM o.invoice_date + o.invoices_due_in) WHEN 6 THEN 2 WHEN 7 THEN 1 ELSE 0 END)
                       < GREATEST((SELECT MAX(date) FROM vouchers), (SELECT MAX(order_date) FROM orders)) THEN 'OVERDUE'
                  ELSE 'OPEN' END AS st) s
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
    # Accounting phase 4: the COGS pass-through liabilities (accounts 4291 / 4292) that sit on 2400 next to the purchase
    # invoices, one row per monthly accrual. They have no purchase invoice behind them, so without this sheet the
    # supplier ledger (2400) cannot be reconciled to Faktury_zakupu: GL balance on 2400 = -(UNPAID purchase invoices
    # + UNPAID rows here).  status UNPAID = flagged as open; paid_date = the bank payment, NULL while unpaid.
    "Zobowiazania_COGS": """
        SELECT cp.id AS payable_id, cp.accrual_date, cp.payment_due_date,
               cp.account_number, cp.supplier_id, s.name AS supplier_name,
               cp.description, cp.amount_excluding_vat_currency, cp.vat_amount_currency, cp.amount_currency, cp.status,
               b.date AS paid_date
        FROM cogs_payables cp
        JOIN suppliers s ON s.id = cp.supplier_id
        LEFT JOIN bank_transactions b ON b.cogs_payable_id = cp.id AND b.transaction_type = 'OUTGOING'
        ORDER BY cp.accrual_date, cp.id
    """,
    # Phase 5: the VAT return of each two-month term. balance = output - input: > 0 is paid to the tax authority, < 0 is
    # refunded.  status UNPAID = settled on the last day of the term, payment still ahead; paid_date = the bank booking.
    "Rozliczenia_MVA": """
        SELECT vs.period_year || '-T' || vs.term AS term, vs.period_start, vs.period_end,
               vs.output_vat, vs.input_vat, vs.balance, vs.payment_date, vs.status,
               b.date AS paid_date
        FROM vat_settlements vs
        LEFT JOIN bank_transactions b ON b.vat_settlement_id = vs.id
        ORDER BY vs.period_end
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
        SELECT v.date, v.id AS voucher_number, v.voucher_type, v.description,
               p.account_number, p.amount,
               p.vat_amount, p.customer_id, p.supplier_id
        FROM vouchers v JOIN postings p ON p.voucher_id = v.id
        ORDER BY v.date, v.id
    """,
}
