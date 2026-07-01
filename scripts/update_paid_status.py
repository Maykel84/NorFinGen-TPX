"""
Jednorazowa migracja: ustawia status = 'PAID' dla faktur zakupu,
których payment_due_date minął ponad 45 dni temu.

Uruchomienie:
    python scripts/update_paid_status.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SQL = """
UPDATE supplier_invoices
SET status = 'PAID'
WHERE status = 'UNPAID'
  AND payment_due_date < CURRENT_DATE - INTERVAL '45 days'
"""

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
with conn.cursor() as cur:
    cur.execute(SQL)
    updated = cur.rowcount
conn.commit()
conn.close()

print(f"Zaktualizowano {updated} faktur → PAID")
