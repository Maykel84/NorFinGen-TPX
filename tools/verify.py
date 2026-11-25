#!/usr/bin/env python3
"""NorFinGen verification: run it after EVERY regeneration (and any time you want to know that the data is sane).

Prints PASS/FAIL for every invariant of the ledger and for the data-quality fields a real ERP quality check looks at, and
writes the result to docs/verify_<date of the newest data>.md.

What it checks
  * all of tests/gl_checks.sql (T1..T23 + the REG_* regression pins): every voucher balances, account 3000 = sales invoices
    without VAT, the VAT sheet = accounts 2700/2710/2740, 2400 = unpaid purchase invoices + COGS payables, 1500 = open and
    overdue invoices, the bank (1910) never below zero, loan, write-offs, invoice status ...
  * Q1..Q5, the quality fields of an ERP data-quality report: vouchers without lines, unbalanced vouchers (count AND sum),
    invoices without lines, PL_miesiecznie (v_pl_monthly) = the general ledger in every month, account 3000 in total.

READ-ONLY by construction: the session is `readonly=True`, nothing is created or written, so it can be pointed at the
production database as well as at a local one. The database comes from DATABASE_URL or from .env; the address itself is never
printed or written to the report (only "local" / "remote").

    python tools/verify.py                 # prints the table, writes docs/verify_<date>.md, exit code 1 if anything fails
    python tools/verify.py --no-report     # only print
    python tools/verify.py --out /tmp      # write the report elsewhere
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from export_queries import QUERIES  # noqa: E402
from run_gl_checks import _statements, _strip_order_by  # noqa: E402

# The export queries the SQL in gl_checks.sql was written against (table name -> export sheet).
EXPORT_TABLES = {
    "gl": "Postingi_GL",
    "sales": "Faktury_sprzedazy",
    "purch": "Faktury_zakupu",
    "cogs": "Zobowiazania_COGS",
    "vat": "Rozliczenia_MVA",
    "pay": "Payroll_per_pracownik",
}

# Data-quality checks beyond gl_checks.sql: (id, description, SQL returning the VIOLATIONS; no rows = PASS)
EXTRA_CHECKS: list[tuple[str, str, str]] = [
    ("Q1", "no voucher without lines",
     """SELECT 'Q1', v.id AS voucher_id FROM vouchers v LEFT JOIN postings p ON p.voucher_id = v.id
        WHERE p.id IS NULL"""),
    ("Q2", "no unbalanced voucher (count and sum of the imbalance both 0)",
     """SELECT 'Q2', voucher_id, ROUND(SUM(amount), 2) AS imbalance FROM postings
        GROUP BY voucher_id HAVING ABS(SUM(amount)) >= 0.005"""),
    ("Q3", "no sales invoice (order) without lines",
     """SELECT 'Q3', o.id AS order_id FROM orders o LEFT JOIN order_lines ol ON ol.order_id = o.id
        WHERE ol.id IS NULL"""),
    ("Q4", "PL_miesiecznie (v_pl_monthly) = the general ledger in every month: labour 5xxx, operating 6xxx-7xxx, COGS 4xxx",
     """WITH g AS (
            SELECT TO_CHAR(v.date, 'YYYY-MM') AS month,
                   COALESCE(SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 5000 AND 5999), 0) AS labor,
                   COALESCE(SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 6000 AND 7999), 0) AS opex,
                   COALESCE(SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 4000 AND 4999), 0) AS cogs
            FROM vouchers v JOIN postings p ON p.voucher_id = v.id GROUP BY 1)
        SELECT 'Q4', pl.month, pl.labor_cost, g.labor, pl.operating_cost, g.opex, pl.cogs, g.cogs
        FROM v_pl_monthly pl LEFT JOIN g ON g.month = pl.month
        WHERE g.month IS NULL
           OR ABS(pl.labor_cost - ROUND(g.labor, 2)) > 0.02
           OR ABS(pl.operating_cost - ROUND(g.opex, 2)) > 0.02
           OR ABS(pl.cogs - ROUND(g.cogs, 2)) > 0.02"""),
    ("Q5", "account 3000 in total = sales invoices without VAT (to the cent)",
     """SELECT 'Q5', ROUND(-gl_total, 2) AS gl_3000, ROUND(sales_total, 2) AS invoices
        FROM (SELECT (SELECT COALESCE(SUM(p.amount), 0) FROM postings p WHERE p.account_number = 3000) AS gl_total,
                     (SELECT COALESCE(SUM(amount_excluding_vat_currency), 0) FROM order_lines) AS sales_total) x
        WHERE ABS(-gl_total - sales_total) > 0.05"""),
]

METRICS: list[tuple[str, str]] = [
    ("vouchers", "SELECT COUNT(*) FROM vouchers"),
    ("postings", "SELECT COUNT(*) FROM postings"),
    ("orders (sales invoices)", "SELECT COUNT(*) FROM orders"),
    ("order_lines", "SELECT COUNT(*) FROM order_lines"),
    ("supplier_invoices", "SELECT COUNT(*) FROM supplier_invoices"),
    ("bank_transactions", "SELECT COUNT(*) FROM bank_transactions"),
    ("unbalanced vouchers (count)", "SELECT COUNT(*) FROM (SELECT 1 FROM postings GROUP BY voucher_id HAVING ABS(SUM(amount)) >= 0.005) x"),
    ("unbalanced vouchers (sum of imbalance)", "SELECT COALESCE(ROUND(SUM(ABS(s)), 2), 0) FROM (SELECT SUM(amount) AS s FROM postings GROUP BY voucher_id HAVING ABS(SUM(amount)) >= 0.005) x"),
    ("vouchers without lines", "SELECT COUNT(*) FROM vouchers v WHERE NOT EXISTS (SELECT 1 FROM postings p WHERE p.voucher_id = v.id)"),
    ("invoices without lines", "SELECT COUNT(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM order_lines ol WHERE ol.order_id = o.id)"),
    ("newest voucher date", "SELECT MAX(date) FROM vouchers"),
    ("generation watermark", "SELECT MAX(value_date) FROM generation_state"),
]


@dataclass
class Result:
    check_id: str
    description: str
    status: str  # PASS | FAIL | ERROR
    rows: int
    sample: list = field(default_factory=list)


def connection_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        from dotenv import dotenv_values

        url = dotenv_values(ROOT / ".env").get("DATABASE_URL", "") or ""
    if not url:
        sys.exit("set DATABASE_URL (or put it in .env)")
    return url


def host_kind(url: str) -> str:
    return "local" if urlparse(url).hostname in ("127.0.0.1", "localhost", "::1") else "remote"


def descriptions(sql_text: str) -> dict[str, str]:
    """First comment line that names each check in gl_checks.sql: `-- T1: ...` / `-- T14 (audit ...): ...` / `-- REG_A: ...`."""
    out: dict[str, str] = {}
    for m in re.finditer(r"^--\s*(T\d+|REG_[A-Z])\b[^:\n]*:?\s*(.*)$", sql_text, flags=re.MULTILINE):
        out.setdefault(m.group(1), m.group(2).strip().rstrip("."))
    return out


def with_export_tables(sql: str) -> str:
    """gl_checks.sql reads the export sheets as tables gl / sales / purch / cogs / vat / pay. A read-only session cannot
    create views, so the export queries are put in front of the statement as CTEs (unused ones are never executed). A CTE the
    statement defines itself (T21 has its own `pay`) is left alone: its own definition wins."""
    body = sql.strip()
    own = set(re.findall(r"(?:\bWITH|,)\s*(\w+)\s+AS\s*\(", body, flags=re.IGNORECASE))
    ctes = ", ".join(f"{name} AS ({_strip_order_by(QUERIES[sheet])})" for name, sheet in EXPORT_TABLES.items() if name not in own)
    if not ctes:
        return body
    if body.upper().startswith("WITH"):
        return f"WITH {ctes}, {body[4:].lstrip()}"
    return f"WITH {ctes} {body}"


def run_check(cur, check_id: str, description: str, sql: str) -> Result:
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        return Result(check_id, description, "PASS" if not rows else "FAIL", len(rows), rows[:3])
    except psycopg2.Error as exc:
        return Result(check_id, description, "ERROR", 0, [str(exc).splitlines()[0]])


def run_all(conn) -> tuple[list[Result], list[tuple[str, object]]]:
    cur = conn.cursor()
    sql_text = (ROOT / "tests" / "gl_checks.sql").read_text(encoding="utf-8")
    described = descriptions(sql_text)
    results = [
        run_check(cur, test_id, described.get(test_id, ""), with_export_tables(sql))
        for test_id, sql in _statements(sql_text)
    ]
    results += [run_check(cur, cid, desc, sql) for cid, desc, sql in EXTRA_CHECKS]
    metrics = []
    for name, sql in METRICS:
        try:
            cur.execute(sql)
            metrics.append((name, cur.fetchone()[0]))
        except psycopg2.Error as exc:
            conn.rollback()
            metrics.append((name, f"n/a ({str(exc).splitlines()[0]})"))
    return results, metrics


def render_table(results: list[Result]) -> str:
    lines = [f"{'check':6} {'result':6} {'rows':>5}  description / detail"]
    for r in results:
        detail = r.description if r.status == "PASS" else f"{r.description}  {str(r.sample)[:140]}"
        lines.append(f"{r.check_id:6} {r.status:6} {r.rows:>5}  {detail}")
    failed = [r for r in results if r.status != "PASS"]
    lines.append(f"\n{len(results) - len(failed)}/{len(results)} PASS")
    return "\n".join(lines)


def render_markdown(results: list[Result], metrics: list[tuple[str, object]], data_date: object, kind: str) -> str:
    failed = [r for r in results if r.status != "PASS"]
    out = [
        f"# Verification of {data_date}",
        "",
        f"- Newest data: **{data_date}**; database: **{kind}**; run: {datetime.now().strftime('%Y-%m-%d %H:%M')} (`tools/verify.py`, read-only).",
        f"- Result: **{len(results) - len(failed)}/{len(results)} PASS**" + ("" if not failed else f", **{len(failed)} not passing**") + ".",
        "",
        "| check | result | rows | what it proves |",
        "|---|---|---|---|",
    ]
    for r in results:
        out.append(f"| {r.check_id} | {r.status} | {r.rows} | {(r.description or '').replace('|', '/')} |")
    if failed:
        out += ["", "## Failures", ""]
        for r in failed:
            out.append(f"- **{r.check_id}** ({r.status}): `{str(r.sample)[:300]}`")
    out += ["", "## Data-quality fields", "", "| field | value |", "|---|---|"]
    out += [f"| {name} | {value} |" for name, value in metrics]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--no-report", action="store_true", help="only print, do not write docs/verify_<date>.md")
    parser.add_argument("--out", type=Path, default=ROOT / "docs", help="directory for the report (default: docs/)")
    args = parser.parse_args(argv)

    url = connection_url()
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.set_session(readonly=True, autocommit=True)  # READ ONLY: this tool never writes
    results, metrics = run_all(conn)
    conn.close()

    print(f"database: {host_kind(url)}  (address not shown)")
    print(render_table(results))
    data_date = next((v for n, v in metrics if n == "newest voucher date"), None) or date.today()
    if not args.no_report:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"verify_{data_date}.md"
        path.write_text(render_markdown(results, metrics, data_date, host_kind(url)), encoding="utf-8")
        print(f"report: {path}")
    return 0 if all(r.status == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
