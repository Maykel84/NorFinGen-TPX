"""
NorFinGen — eksport danych do Excel
Poprawka: przychody z orders/order_lines (postingi INVOICE auto-generowane przez Tripletex).
"""
import psycopg2
import openpyxl
from dotenv import load_dotenv
import os

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()
wb = openpyxl.Workbook()

queries = {
    "PL_miesiecznie": """
        WITH przychody AS (
            SELECT DATE_TRUNC('month', o.order_date) AS miesiac,
                   SUM(ol.amount_excluding_vat_currency) AS przychody_netto
            FROM orders o JOIN order_lines ol ON ol.order_id = o.id
            GROUP BY 1
        ),
        koszty AS (
            SELECT DATE_TRUNC('month', v.date) AS miesiac,
                   SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 5000 AND 5999) AS koszty_pracownicze,
                   SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 6000 AND 7999) AS koszty_operacyjne
            FROM vouchers v JOIN postings p ON p.voucher_id = v.id
            GROUP BY 1
        )
        SELECT TO_CHAR(COALESCE(pr.miesiac, ko.miesiac), 'YYYY-MM') AS miesiac,
               ROUND(COALESCE(pr.przychody_netto, 0))              AS przychody,
               ROUND(COALESCE(ko.koszty_pracownicze, 0))           AS koszty_pracownicze,
               ROUND(COALESCE(ko.koszty_operacyjne, 0))            AS koszty_operacyjne,
               ROUND(COALESCE(pr.przychody_netto, 0)
                   - COALESCE(ko.koszty_pracownicze, 0)
                   - COALESCE(ko.koszty_operacyjne, 0))            AS wynik_operacyjny
        FROM przychody pr FULL OUTER JOIN koszty ko ON pr.miesiac = ko.miesiac
        ORDER BY 1
    """,
    "Faktury_sprzedazy": """
        SELECT o.id AS order_id, o.order_date, o.invoice_date,
               c.name AS klient, c.customer_number, c.city,
               ol.count AS ilosc,
               ol.unit_price_excluding_vat_currency AS cena_netto,
               ol.amount_excluding_vat_currency     AS wartosc_netto,
               ol.amount_currency                   AS wartosc_brutto
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        JOIN order_lines ol ON ol.order_id = o.id
        ORDER BY o.order_date, o.id
    """,
    "Faktury_zakupu": """
        SELECT si.invoice_number, si.invoice_date, si.payment_due_date,
               s.name AS dostawca,
               si.amount_excluding_vat_currency AS netto,
               si.vat_amount_currency           AS vat,
               si.amount_currency               AS brutto,
               si.status
        FROM supplier_invoices si
        JOIN suppliers s ON s.id = si.supplier_id
        ORDER BY si.invoice_date
    """,
    "Payroll_miesiecznie": """
        SELECT TO_CHAR(st.date, 'YYYY-MM') AS miesiac,
               st.date                     AS data_wyplaty,
               COUNT(ps.id)                AS liczba_pracownikow,
               ROUND(SUM(ps.amount))       AS laczne_netto
        FROM salary_transactions st
        JOIN payslips ps ON ps.transaction_id = st.id
        GROUP BY 1, 2 ORDER BY 1
    """,
    "Postingi_GL": """
        SELECT v.date, v.voucher_type, v.description AS opis,
               p.account_number AS konto, p.amount AS kwota,
               p.vat_amount AS vat, p.customer_id, p.supplier_id, p.employee_id
        FROM vouchers v JOIN postings p ON p.voucher_id = v.id
        ORDER BY v.date, v.id
    """
}

first = True
for sheet_name, sql in queries.items():
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    if first:
        ws = wb.active
        ws.title = sheet_name
        first = False
    else:
        ws = wb.create_sheet(sheet_name)
    ws.append(cols)
    for row in rows:
        ws.append([str(v) if v is not None else "" for v in row])
    print(f"✓ {sheet_name}: {len(rows)} wierszy")

wb.save("norfingen_export.xlsx")
print("\nGotowe → norfingen_export.xlsx")
conn.close()
