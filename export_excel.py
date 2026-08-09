"""
NorFinGen — eksport danych do Excel
Poprawka: przychody z orders/order_lines (postingi INVOICE auto-generowane przez Tripletex).
"""
import psycopg2
import openpyxl
from dotenv import load_dotenv
import os

from export_queries import QUERIES

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()
wb = openpyxl.Workbook()

first = True
for sheet_name, sql in QUERIES.items():
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
