"""NorFinGen — eksport danych do CSV (jeden plik per zestawienie, zob. export_queries.py)."""
import csv
import os

import psycopg2
from dotenv import load_dotenv

from export_queries import QUERIES

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

for name, sql in QUERIES.items():
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    filename = f"{name}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerows(rows)
    print(f"✓ {filename}: {len(rows)} wierszy")

conn.close()
print("\nGotowe.")
