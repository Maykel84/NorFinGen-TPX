"""In-memory fingerprint of everything the generators produce up to a fixed cutoff.

Used by test_golden_hash.py. No database, no I/O: pure generator output. The
point is to pin the *data* the generators emit for the whole history, so that a
refactor of the pipeline (ordering of calls, splitting a month into days, ...)
that silently changes a drawn value is caught immediately.

Why this works: every random draw in src/ comes from a local
`random.Random(<seed string/int>)`; there is no global stream. Two streams are
shared inside one unit of work (supplier invoices: one per month across all
suppliers; hours: one per day across all employees), so those units must always
be generated whole and then filtered - this fingerprint pins that contract.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

from norfingen.generators.backfill import months_range
from norfingen.generators.hours_generator import generate_daily_hours, is_working_day
from norfingen.generators.opex_generator import generate_monthly_opex
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.salary_generator import generate_monthly_salary
from norfingen.generators.supplier_invoice_generator import generate_monthly_supplier_invoices
from norfingen.seed.payroll import active_employees, is_date_generatable, should_generate_monthly_salary
from norfingen.seed.roster import numeric_id

CUTOFF = date(2026, 9, 30)
START = date(2019, 1, 1)


def digest(rows) -> str:
    return hashlib.sha256("\n".join(sorted(json.dumps(r, default=str) for r in rows)).encode()).hexdigest()[:16]


def build(cutoff: date = CUTOFF) -> dict:
    orders, invoices, opex, salary_v, hours = [], [], [], [], []
    gross = 0.0
    for year, month in months_range(START, cutoff):
        for o in generate_monthly_orders(year, month):
            if is_date_generatable(o.orderDate, cutoff):
                orders.append((
                    o.customer.id, o.orderDate.isoformat(), o.status.value,
                    round(sum(l.amountExcludingVatCurrency for l in o.orderLines), 2),
                    round(sum(l.amountCurrency for l in o.orderLines), 2), len(o.orderLines),
                ))
        for i in generate_monthly_supplier_invoices(year, month):
            if is_date_generatable(i.invoiceDate, cutoff):
                invoices.append((i.invoiceNumber, i.invoiceDate.isoformat(), round(i.amountCurrency, 2)))
        for v in generate_monthly_opex(year, month):
            if is_date_generatable(v.date, cutoff):
                opex.append((v.date.isoformat(), v.description, tuple((p.account.number, p.amount) for p in v.postings)))
        if should_generate_monthly_salary(year, month, cutoff):
            txn, vouchers = generate_monthly_salary(year, month)
            for v in vouchers:
                salary_v.append((v.date.isoformat(), v.description, tuple((p.account.number, p.amount) for p in v.postings)))
            for payslip in txn.payslips:
                for spec in payslip.specifications:
                    if spec.wageType.id in (100, 260):  # Fast lønn + Feriepenger
                        gross += spec.amount

    day = START
    while day <= cutoff:
        if is_working_day(day):
            ids = [numeric_id(e.number) for e in active_employees(day)]
            for e in generate_daily_hours(day.year, day.month, day.day, ids):
                hours.append((e.date.isoformat(), e.employee_id, e.project_id, e.activity_type.value, float(e.hours)))
        day += timedelta(days=1)

    return {
        "orders": (len(orders), digest(orders)),
        "supplier_invoices": (len(invoices), digest(invoices)),
        "opex_vouchers": (len(opex), digest(opex)),
        "salary_vouchers": (len(salary_v), digest(salary_v)),
        "hour_entries": (len(hours), digest(hours)),
        "revenue_net": round(sum(o[3] for o in orders)),
        "payroll_gross": round(gross),
    }
