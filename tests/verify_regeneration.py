#!/usr/bin/env python3
"""Checks a freshly regenerated LOCAL database (docs/SPEC_poprawki_ksiegowe.md) and compares it, read-only,
with a reference database (production) for the part of history that must not change.

    DATABASE_URL=postgresql://user@127.0.0.1:54329/scratch \\
    REFERENCE_DATABASE_URL=<production URL, only ever SELECTed> \\
    python tests/verify_regeneration.py [--frozen-until 2026-09-30]

* DATABASE_URL must be local (the script refuses anything else; it never writes anyway).
* REFERENCE_DATABASE_URL is opened as a read-only session. Optional: without it only the internal checks run.
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlparse

import psycopg2

FROZEN_REVENUE = 209_030_662       # net revenue up to 2026-09-30 (docs/SPEC_poprawki_ksiegowe.md, decision (c))
FROZEN_PAYROLL_GROSS = 81_422_455  # wage types 100 + 260 up to 2026-09-30


def f(x):
    return float(x) if hasattr(x, "as_tuple") else x


class Q:
    def __init__(self, url: str, readonly: bool):
        self.conn = psycopg2.connect(url)
        if readonly:
            self.conn.set_session(readonly=True)
        self.cur = self.conn.cursor()

    def all(self, sql, args=None):
        self.cur.execute(sql, args)
        return self.cur.fetchall()

    def one(self, sql, args=None):
        return self.all(sql, args)[0][0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen-until", default="2026-09-30")
    args = ap.parse_args()
    frozen = args.frozen_until

    url = os.environ.get("DATABASE_URL", "")
    if urlparse(url).hostname not in ("127.0.0.1", "localhost", "::1"):
        sys.exit("refusing to run: DATABASE_URL must be a local database")
    local = Q(url, readonly=True)
    ref_url = os.environ.get("REFERENCE_DATABASE_URL")
    ref = Q(ref_url, readonly=True) if ref_url else None

    rows: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        rows.append((name, bool(ok), detail))

    # ------------------------------------------------------------------ frozen history vs reference
    check(f"revenue <= {frozen} == {FROZEN_REVENUE:,}",
          round(f(local.one("select sum(ol.amount_excluding_vat_currency) from orders o join order_lines ol on ol.order_id=o.id where o.order_date<=%s", (frozen,)))) == FROZEN_REVENUE,
          f"{f(local.one('select round(sum(ol.amount_excluding_vat_currency),0) from orders o join order_lines ol on ol.order_id=o.id where o.order_date<=%s', (frozen,))):,.0f}")
    check(f"payroll gross <= {frozen} == {FROZEN_PAYROLL_GROSS:,}",
          round(f(local.one("select sum(ss.amount) from salary_specifications ss join payslips p on p.id=ss.payslip_id join salary_transactions st on st.id=p.transaction_id where ss.wage_type_id in (100,260) and st.date<=%s", (frozen,)))) == FROZEN_PAYROLL_GROSS)

    if ref:
        def same(sql, label, norm_local=lambda r: tuple(f(x) for x in r), note=""):
            a = {norm_local(r) for r in local.all(sql, (frozen,))}
            b = {tuple(f(x) for x in r) for r in ref.all(sql, (frozen,))}
            check(f"{label} <= {frozen} identical to reference{note}", a == b,
                  f"local={len(a)} ref={len(b)} only_local={len(a - b)} only_ref={len(b - a)}")

        same("""select o.customer_id, o.order_date::text, o.status, sum(ol.amount_excluding_vat_currency), sum(ol.amount_currency), count(*)
                from orders o join order_lines ol on ol.order_id=o.id where o.order_date<=%s group by o.id""",
             "orders (status, net, gross, lines)")
        same("select invoice_number, invoice_date::text, amount_currency from supplier_invoices where invoice_date<=%s", "supplier invoices")
        same("""select v.date::text, v.description, p.account_number, p.amount from vouchers v join postings p on p.voucher_id=v.id
                where v.voucher_type='OPERATING_COST' and v.date<=%s""", "operating cost / COGS postings")
        same("select date::text, employee_id, project_id, activity_type, hours from hour_entries where date<=%s", "hour entries")
        # Phase 1 renumbered the payroll liabilities (tests/golden_fingerprint.PHASE1_TO_LEGACY_ACCOUNTS):
        # map the new accounts back and the postings must equal the reference exactly - same dates, same
        # amounts, only the account numbers moved. Drop this mapping once production is regenerated.
        legacy = {2930: 2710, 2600: 2740, 2770: 2700, 2940: 2930}
        same("""select v.date::text, v.description, p.account_number, p.amount from vouchers v join postings p on p.voucher_id=v.id
                where v.voucher_type='SALARY' and v.date<=%s""", "payroll postings",
             norm_local=lambda r: (r[0], r[1], legacy.get(r[2], r[2]), f(r[3])), note=" (accounts mapped back)")

    # ------------------------------------------------------------------ after the frozen date
    new_orders = local.all("""select o.customer_id, o.order_date::text, to_char(o.order_date,'Dy'), sum(ol.amount_excluding_vat_currency)
                              from orders o join order_lines ol on ol.order_id=o.id where o.order_date>%s group by o.id order by 2,1""", (frozen,))
    if ref:
        ref_keys = {(r[0], r[1]) for r in ref.all("select customer_id, order_date::text from orders where order_date>%s", (frozen,))}
        added = [r for r in new_orders if (r[0], r[1]) not in ref_keys]
        removed = ref_keys - {(r[0], r[1]) for r in new_orders}
        check("after the frozen date: nothing removed vs reference", not removed, f"removed={sorted(removed)[:5]}")
        print(f"\nOrders after {frozen} that the reference lacks: {len(added)}, net {sum(f(r[3]) for r in added):,.2f}")
        for r in added:
            print(f"   K{r[0]:02d}  {r[1]}  {r[2]}  {f(r[3]):>12,.2f}")

    # ------------------------------------------------------------------ internal consistency
    unexplained = local.all("""
        with inv as (select o.id, o.status, o.invoice_date, o.invoices_due_in, sum(ol.amount_currency) gross
                     from orders o join order_lines ol on ol.order_id=o.id group by o.id),
        np as (select i.* from inv i where not exists (select 1 from bank_transactions b where b.order_id=i.id and b.transaction_type='INCOMING'))
        select case when status='WRITTEN_OFF' then 'written off (by design)'
                    when status='OVERDUE' and invoice_date+invoices_due_in+90 > current_date then 'overdue, +90d still ahead'
                    when status='PAID' and invoice_date+invoices_due_in > current_date then 'due date ahead'
                    when extract(isodow from invoice_date+invoices_due_in+(case when status='OVERDUE' then 90 else 0 end)) in (6,7)
                         and invoice_date+invoices_due_in+(case when status='OVERDUE' then 90 else 0 end)+2 > current_date then 'weekend due, Monday still ahead'
                    else 'UNEXPLAINED' end cause, count(*), round(sum(gross)/1e6,2)
        from np group by 1 order by 1""")
    print("\nInvoices without a customer payment, by cause:")
    for r in unexplained:
        print(f"   {r[0]:34} n={r[1]:>4}  gross {f(r[2])} mln")
    check("every missing customer payment is explained", not any(r[0] == "UNEXPLAINED" for r in unexplained))

    check("every customer payment is on a working day", local.one("select count(*) from bank_transactions where transaction_type='INCOMING' and extract(isodow from date) in (6,7)") == 0)
    check("every supplier payment is on a working day", local.one("select count(*) from bank_transactions where transaction_type='OUTGOING' and supplier_invoice_id is not null and extract(isodow from date) in (6,7)") == 0)
    check("customer payment == SUM(order_lines.amount_currency), always",
          local.one("""select count(*) from bank_transactions b join (select order_id, sum(amount_currency) g from order_lines group by order_id) l
                       on l.order_id=b.order_id where b.transaction_type='INCOMING' and b.amount<>l.g""") == 0)
    check("no order paid twice", local.one("select count(*) from (select order_id from bank_transactions where transaction_type='INCOMING' group by 1 having count(*)>1) t") == 0)
    check("every bank transaction has its voucher", local.one("select count(*) from bank_transactions where voucher_id is null") == 0)

    # supplier invoices: status follows the payments, and nothing is paid before it is due
    check("supplier invoice is PAID  <=>  it has an OUTGOING payment",
          local.one("""select count(*) from supplier_invoices si where (si.status='PAID') <>
                       exists (select 1 from bank_transactions b where b.supplier_invoice_id=si.id and b.transaction_type='OUTGOING')""") == 0)
    check("no supplier invoice still UNPAID although its (shifted) due date has passed",
          local.one("""select count(*) from supplier_invoices where status='UNPAID' and payment_due_date + (case extract(isodow from payment_due_date)
                       when 6 then 2 when 7 then 1 else 0 end) <= current_date""") == 0)
    n_unpaid = local.one("select count(*) from supplier_invoices where status='UNPAID'")
    print(f"\nsupplier invoices UNPAID (due date ahead): {n_unpaid}")

    check("voucher ids follow the calendar (chronological pipeline)",
          local.one("select count(*) from (select date, lag(date) over (order by id) prev from vouchers) t where prev > date") == 0)
    check("watermark == today (the pipeline ran up to the present)",
          local.one("select value_date from generation_state where key='daily_pipeline'") == local.one("select current_date"),
          str(local.all("select value_date from generation_state")))

    last_cost = local.one("""select max(v.date) from vouchers v join postings p on p.voucher_id=v.id
                             where p.account_number between 4000 and 4999 or p.account_number between 6000 and 7999""")
    last_any = local.one("select max(date) from vouchers")
    print(f"\nlast cost posting {last_cost} | last voucher of any kind {last_any}")

    print("\n" + "-" * 118)
    for name, ok, detail in rows:
        print(f"{'PASS' if ok else 'FAIL':5} {name}   {('[' + detail + ']') if detail else ''}")
    failed = [r for r in rows if not r[1]]
    print(f"\n{len(rows) - len(failed)}/{len(rows)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
