"""
NorFinGen — eksport danych do Excel
Poprawka: przychody z orders/order_lines (postingi INVOICE auto-generowane przez Tripletex).
"""
from decimal import Decimal

import psycopg2
import openpyxl
from dotenv import load_dotenv
import os

from export_queries import QUERIES

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()
wb = openpyxl.Workbook()

def excel_cell(value):
    """Numbers stay numbers (Decimal -> float) so that Excel/BI infer a numeric column; before phase 6 every cell was
    written as text, which is why `count` (1.00 ... 194.60 hours) looked like an integer column. Others unchanged."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return value
    return str(value)


def format_decimal_columns(ws, columns):
    """`count` is a decimal quantity (hours): shown with two decimals even when the value is a whole 1."""
    if "count" in columns:
        letter = openpyxl.utils.get_column_letter(list(columns).index("count") + 1)
        for cell in ws[letter][1:]:
            cell.number_format = "0.00"


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
        ws.append([excel_cell(v) for v in row])
    format_decimal_columns(ws, cols)
    print(f"✓ {sheet_name}: {len(rows)} wierszy")

wb.save("norfingen_export.xlsx")
print("\nGotowe → norfingen_export.xlsx")
conn.close()
