#!/usr/bin/env python3
"""Year-by-year P&L of the generators, computed IN MEMORY (no database): the calibration tool of round 4, step 3.

It walks every calendar day with the same functions the daily pipeline calls (orders_dated, supplier_invoices_dated,
operating_vouchers_dated, generate_monthly_salary, the depreciation / OTP / write-off builders) and sums revenue, COGS, payroll,
operating cost, depreciation and write-offs per year, so a margin curve can be tuned in a couple of minutes instead of a full
regeneration. Interest, income tax and the balance sheet are not part of it (they do not move EBIT).

    python tools/calibrate.py                 # to 2026-11-24 (the data end of the production database)
    python tools/calibrate.py 2026-09-30      # to another cutoff
    python tools/calibrate.py --target        # also print the target curve and the gap to it

Its output is checked against a real regeneration (tools/verify.py + v_pl_monthly) before a calibration is trusted: the two agree
to a few thousand NOK a year (the in-memory orders carry no ids and a write-off is booked on its date, not at the cutoff).
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norfingen.generators import depreciation, pension  # noqa: E402
from norfingen.generators.day_events import operating_vouchers_dated, orders_dated, supplier_invoices_dated  # noqa: E402
from norfingen.generators.salary_generator import generate_monthly_salary  # noqa: E402
from norfingen.generators.supplier_invoice_generator import build_voucher_for_invoice  # noqa: E402
from norfingen.generators.write_off import build_write_off_voucher  # noqa: E402
from norfingen.seed.payroll import last_working_day, should_generate_monthly_salary  # noqa: E402
from norfingen.seed.roster import supplier_by_number  # noqa: E402

START = date(2019, 1, 1)
DEFAULT_CUTOFF = date(2026, 11, 24)

# Target curve of round 4 (decision D1): EBIT margin of the calendar year, before the +-1.5 point variability around it.
TARGET_EBIT_PCT = {2019: -35.0, 2020: 11.0, 2021: 9.5, 2022: 6.0, 2023: 1.3, 2024: 1.0, 2025: 4.5, 2026: 6.5}


def yearly_pl(cutoff: date) -> dict[int, dict[str, float]]:
    rows: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    monthly_revenue: dict[tuple[int, int], float] = defaultdict(float)
    additions: list[tuple[date, float]] = []
    day = START
    while day <= cutoff:
        y = day.year
        for order in orders_dated(day):
            net = round(sum(l.amountExcludingVatCurrency for l in order.orderLines), 2)
            rows[y]["revenue"] += net
            monthly_revenue[(y, day.month)] += net
            write_off = build_write_off_voucher(order)
            if write_off is not None and write_off.date <= cutoff:
                rows[write_off.date.year]["opex"] += write_off.postings[0].amount  # 7830, net
        for invoice in supplier_invoices_dated(day):
            voucher = build_voucher_for_invoice(invoice, supplier_by_number(invoice.invoiceNumber.split("-")[0]))
            for p in voucher.postings:
                if 6000 <= p.account.number <= 7999 and p.amount > 0:
                    rows[y]["opex"] += p.amount
                elif p.account.number == 1200 and p.amount > 0:
                    additions.append((voucher.date, p.amount))
        for voucher in operating_vouchers_dated(day):
            for p in voucher.postings:
                if p.amount > 0 and p.account.number != 2710:
                    if 4000 <= p.account.number <= 4999:
                        rows[y]["cogs"] += p.amount
                    elif 6000 <= p.account.number <= 7999:
                        rows[y]["opex"] += p.amount
        day += timedelta(days=1)
    for year in range(START.year, cutoff.year + 1):
        for month in range(1, 13):
            if not should_generate_monthly_salary(year, month, cutoff) or (year, month) < (START.year, START.month):
                continue
            txn, vouchers = generate_monthly_salary(year, month)
            for v in vouchers:
                rows[year]["labor"] += sum(p.amount for p in v.postings if 5000 <= p.account.number <= 5999)
            rows[year]["labor"] += round(pension.otp_base(txn) * pension.OTP_RATE, 2)
            rows[year]["depreciation"] += depreciation.depreciation_for_month(
                additions, year, month, last_working_day(year, month))
    for year in rows:
        r = rows[year]
        r["ebit"] = r["revenue"] - r["cogs"] - r["labor"] - r["opex"] - r["depreciation"]
    rows_out = {y: dict(v) for y, v in rows.items()}
    # month-to-month dispersion of the revenue around its 3-month centred average, per year (full months only)
    for year, r in rows_out.items():
        months = [monthly_revenue[(year, m)] for m in range(1, 13) if (year, m) in monthly_revenue]
        devs = [months[i] / statistics.mean(months[i - 1:i + 2]) - 1 for i in range(1, len(months) - 1)] if len(months) >= 6 else []
        r["revenue_dispersion_pct"] = 100 * statistics.pstdev(devs) if devs else 0.0
    return rows_out


def render(rows: dict[int, dict[str, float]], show_target: bool) -> str:
    head = f"{'year':5} {'revenue M':>9} {'COGS %':>7} {'labor %':>8} {'opex %':>7} {'dep %':>6} {'EBIT %':>7} {'disp %':>7}"
    if show_target:
        head += f" {'target':>7} {'gap':>6}"
    lines = [head]
    for year in sorted(rows):
        r = rows[year]
        rev = r["revenue"] or 1.0
        line = (f"{year:<5} {rev / 1e6:>9.2f} {100 * r['cogs'] / rev:>7.1f} {100 * r['labor'] / rev:>8.1f} "
                f"{100 * r['opex'] / rev:>7.1f} {100 * r['depreciation'] / rev:>6.1f} {100 * r['ebit'] / rev:>7.1f} {r['revenue_dispersion_pct']:>7.1f}")
        if show_target and year in TARGET_EBIT_PCT:
            line += f" {TARGET_EBIT_PCT[year]:>7.1f} {100 * r['ebit'] / rev - TARGET_EBIT_PCT[year]:>+6.1f}"
        lines.append(line)
    total_rev = sum(r["revenue"] for r in rows.values())
    lines.append(f"all years: revenue {total_rev / 1e6:.1f} M, EBIT {100 * sum(r['ebit'] for r in rows.values()) / total_rev:.2f} %")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("cutoff", nargs="?", type=date.fromisoformat, default=DEFAULT_CUTOFF)
    parser.add_argument("--target", action="store_true", help="show the target curve and the gap to it")
    args = parser.parse_args()
    print(render(yearly_pl(args.cutoff), args.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
