#!/usr/bin/env python3
"""Runs tests/gl_checks.sql (docs/SPEC_poprawki_ksiegowe.md) against a freshly regenerated database
and prints a PASS/FAIL table. Not collected by pytest (it needs a database); run it after every phase.

The SQL was written against the CSV exports (tables gl / sales / purch / pay). To run it on Postgres this
script builds those four as VIEWS in a throw-away schema, from the same queries export_csv.py uses
(export_queries.QUERIES) - so what is tested is what is exported. Until phase 6 puts `voucher_number`
into the real GL export, the gl view here adds it as `vouchers.id` (the agreed definition).

SAFETY: it creates and drops a schema, so it refuses to run against anything but a local database.

    DATABASE_URL=postgresql://user@127.0.0.1:54329/scratch python tests/run_gl_checks.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from export_queries import QUERIES  # noqa: E402

SCHEMA = "gl_check"

GL_VIEW = """
    SELECT v.date, v.voucher_type, v.id AS voucher_number, v.description,
           p.account_number, p.amount, p.vat_amount, p.customer_id, p.supplier_id, p.employee_id
    FROM vouchers v JOIN postings p ON p.voucher_id = v.id
"""


def _assert_local(url: str) -> None:
    host = urlparse(url).hostname
    if host not in ("127.0.0.1", "localhost", "::1"):
        sys.exit(f"refusing to run: DATABASE_URL host is {host!r}, this script only runs on a local database")


def _strip_order_by(sql: str) -> str:
    return re.sub(r"\s+ORDER BY[^()]*$", "", sql.strip(), flags=re.IGNORECASE)


def _statements(sql_text: str) -> list[tuple[str, str]]:
    """[(test id, sql)] - one entry per SELECT in gl_checks.sql."""
    out = []
    # drop comment lines BEFORE splitting on ';' - a ';' inside a comment must not cut a statement in two
    uncommented = "\n".join(l for l in sql_text.splitlines() if not l.strip().startswith("--"))
    for chunk in uncommented.split(";"):
        body = chunk.strip()
        if not body.upper().startswith(("SELECT", "WITH")):
            continue
        m = re.search(r"SELECT\s+'([A-Za-z0-9_]+)'", body)
        out.append((m.group(1) if m else f"stmt{len(out) + 1}", body))
    return out


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("set DATABASE_URL to the local scratch database")
    _assert_local(url)

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    cur.execute(f"CREATE SCHEMA {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")
    cur.execute(f"CREATE VIEW gl AS {GL_VIEW}")
    cur.execute(f"CREATE VIEW sales AS {_strip_order_by(QUERIES['Faktury_sprzedazy'])}")
    cur.execute(f"CREATE VIEW purch AS {_strip_order_by(QUERIES['Faktury_zakupu'])}")
    cur.execute(f"CREATE VIEW cogs AS {_strip_order_by(QUERIES['Zobowiazania_COGS'])}")
    cur.execute(f"CREATE VIEW vat AS {_strip_order_by(QUERIES['Rozliczenia_MVA'])}")
    cur.execute(f"CREATE VIEW pay AS {_strip_order_by(QUERIES['Payroll_per_pracownik'])}")

    results = []
    for test_id, sql in _statements((ROOT / "tests" / "gl_checks.sql").read_text(encoding="utf-8")):
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            results.append((test_id, "PASS" if not rows else "FAIL", len(rows), rows[:2]))
        except psycopg2.Error as exc:
            results.append((test_id, "ERROR", 0, [str(exc).splitlines()[0]]))

    cur.execute(f"DROP SCHEMA {SCHEMA} CASCADE")
    conn.close()

    print(f"{'test':6} {'result':6} {'rows':>5}  detail")
    for test_id, status, n, sample in results:
        detail = "" if status == "PASS" else str(sample)[:150]
        print(f"{test_id:6} {status:6} {n:>5}  {detail}")
    failed = [r for r in results if r[1] != "PASS"]
    print(f"\n{len(results) - len(failed)}/{len(results)} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
