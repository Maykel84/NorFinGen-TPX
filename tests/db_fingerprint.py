"""Per-table SHA-256 of a LOCAL database INCLUDING surrogate ids (excluding created_at/updated_at).

Used to prove that two full regenerations with the same seed give identical ids (voucher_number = vouchers.id
depends on it, docs/SPEC_poprawki_ksiegowe.md). Run it, regenerate, run it again, diff the output:

    DATABASE_URL=postgresql://user@127.0.0.1:54329/scratch python tests/db_fingerprint.py > before.txt

Read-only, but still refuses non-local URLs so it can never be pointed at production by accident.
"""
import hashlib
import os
import sys
from urllib.parse import urlparse

import psycopg2

URL = os.environ.get("DATABASE_URL", "")
if urlparse(URL).hostname not in ("127.0.0.1", "localhost", "::1"):
    sys.exit("refusing to run: set DATABASE_URL to a local database")
TABLES = ["orders", "order_lines", "supplier_invoices", "salary_transactions", "payslips", "salary_specifications",
          "vouchers", "postings", "bank_transactions", "hour_entries", "generation_state"]
conn = psycopg2.connect(URL)
cur = conn.cursor()
out = {}
for t in TABLES:
    cur.execute("select column_name from information_schema.columns where table_name=%s and table_schema='public' "
                "and column_name not in ('created_at','updated_at') order by ordinal_position", (t,))
    cols = [r[0] for r in cur.fetchall()]
    order = "id" if "id" in cols else cols[0]
    cur.execute(f"select {', '.join(cols)} from {t} order by {order}")
    h = hashlib.sha256()
    n = 0
    for row in cur:
        h.update(repr(row).encode())
        n += 1
    out[t] = (n, h.hexdigest()[:16])
for t, (n, h) in out.items():
    print(f"{t:22} rows={n:>6} sha={h}")
