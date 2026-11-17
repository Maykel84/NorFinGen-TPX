# Dashboard update prompt (Streamlit) — NorFinGen model changes of 2026-11-16

Paste everything below the line into a Claude Code session opened in the **dashboard repo** (not in this one).

---

## Task

Update the NorFinGen Streamlit dashboard to the new accounting model and add the new visualisations listed below.
Work in this order and stop after each step so I can review: **A → B → C → D**. Do not run git commands, only propose
them (commit messages in English, no `Co-Authored-By` trailer). Never print the database URL or any token.

The data source is the Supabase Postgres (read-only is enough) or the REST API `https://norfingen-api.fly.dev`.
Use whatever the dashboard already uses; do not switch. Before changing anything, read the current code and list which
queries/pages touch `v_pl_monthly`, `Faktury_sprzedazy`/orders status, VAT and COGS.

## What changed in the data (facts, already deployed and verified)

- `v_pl_monthly` has a new boolean column `is_partial`: TRUE for the month that is not over yet (payroll and COGS are
  booked at month end, so the open month shows revenue without its costs). **Every YTD / yearly / trailing KPI must use
  `WHERE NOT is_partial`**, otherwise margin is inflated. Plain monthly charts keep all months but must mark the partial one
  (hatched bar or a "month in progress" label).
- `v_pl_monthly.operating_cost` now also contains **7830 Tap på krav** (write-offs of receivables, accounts 6000–7999).
- COGS (4291/4292) are now booked **net** with 25% input VAT on 2710; 4290 equipment is a cash purchase with VAT.
  So VAT in vs out is no longer one-sided (input VAT is ~50% of output VAT).
- Founding capital is 500 000 NOK (2000) plus an owner loan of 3 500 000 NOK (2290, "lån fra eier"): drawdown at the
  start, 60 monthly instalments from 2021-01, 5% p.a., interest on 8150 "Annen rentekostnad" (financial expense, NOT part of
  `operating_result`).
- Invoice status is derived, not stored: `PAID`, `OPEN`, `OVERDUE`, `WRITTEN_OFF` (`orders.write_off_voucher_id IS NOT NULL`
  means written off, 120 days after the due date). `orders.status` in the raw table is the generator's intent; for display
  always use the derived status. In the Excel/export queries it is `Faktury_sprzedazy.invoice_status`, plus `is_overdue`
  (boolean) and `paid_late` (paid more than 7 days after the due date). Current counts: PAID 1855, OPEN 63, OVERDUE 7,
  WRITTEN_OFF 8.
- API: `GET /pl/trailing-12m` (last 12 FULL months, fields `period_from, period_to, months, revenue, labor_cost,
  operating_cost, cogs, operating_result, margin_pct`), `GET /pl/yearly` now excludes partial months and returns
  `months_included`, `GET /pl/monthly` returns `is_partial`.
- Cron runs weekdays 08:00/12:00/17:00 CET; data is up to the current day.

## Step A — fix existing pages (must do first)

1. Every yearly / YTD / "last N months" aggregate over `v_pl_monthly`: add `WHERE NOT is_partial` (or use
   `/pl/trailing-12m` for the headline margin).
2. Monthly P&L chart: mark the `is_partial` month visibly and show a caption "month in progress, costs booked at month end".
3. Anything that read invoice status from `orders.status`: switch to the derived status above (copy the CASE logic from
   the `Faktury_sprzedazy` query in this repo's `export_queries.py`, or call the API orders endpoint if it exposes it).
4. Cast/handle types: `is_overdue` is a real boolean, dates are real dates (no more text).

## Step B — receivables (new page "Należności")

- Donut: invoice amount by derived status (PAID / OPEN / OVERDUE / WRITTEN_OFF), with counts.
- Ageing buckets of OPEN + OVERDUE amounts by days past due date: not yet due, 1–30, 31–60, 61–90, 90+.
- Table: top customers by `paid_late` count and by outstanding amount.
- Line: write-offs (account 7830) per month, with a running total.

Useful SQL for write-offs per month:

```sql
SELECT TO_CHAR(v.date, 'YYYY-MM') AS month, SUM(p.amount) AS written_off
FROM vouchers v JOIN postings p ON p.voucher_id = v.id
WHERE p.account_number = 7830
GROUP BY 1 ORDER BY 1;
```

## Step C — cash, financing, VAT (new page "Płynność i finansowanie")

- Bank balance (account 1910) over time, one point per month end, with the minimum highlighted (currently ≈ +893 tys. NOK):

```sql
SELECT TO_CHAR(v.date, 'YYYY-MM') AS month,
       SUM(SUM(p.amount)) OVER (ORDER BY TO_CHAR(v.date, 'YYYY-MM')) AS bank_balance
FROM vouchers v JOIN postings p ON p.voucher_id = v.id
WHERE p.account_number = 1910
GROUP BY 1 ORDER BY 1;
```

- Owner loan: outstanding principal (account 2290, a credit balance, show as positive) stepping down over the 60
  instalments, and a stacked bar per month of principal repaid vs interest (8150).
- Financing structure at start: share capital 2000 vs loan 2290 (two numbers or a small bar).
- VAT: output VAT (2700) vs input VAT (2710) per month, and the amount to pay in the next two-monthly settlement
  (2740). Use the same sign conventions as the existing VAT page.
- COGS payables: table from `cogs_payables` with `amount_excluding_vat_currency`, `vat_amount_currency`,
  `amount_currency` (gross), due date and status.

Check the sign convention of `postings.amount` (debit positive, credit negative) before charting balances, and verify
the totals against the ledger numbers I give you at the end.

## Step D — profitability (optional, only after A–C are reviewed)

- Revenue and margin per customer (revenue minus directly attributable cost) for the 50 customers.
- Utilisation: hours from `hour_entries` per employee vs billed hours, for the 17 employees.
- Operating cost by category and month, including 4290 cash purchases.

## Rules

- Do not modify the generator or the database. If a query is too slow or a view is missing something, tell me and propose a
  change instead of working around it.
- Keep the existing styling and navigation; add pages, do not redesign.
- After each step run the app locally, take a screenshot of each changed page and show it to me.
- Reference numbers to verify against (as of 2026-11-16): vouchers 6526, orders 1935, 47 VAT settlements, 184 COGS
  payables, bank minimum +893 255.52 NOK, 12-month margin ≈ 3.06%, 2026-T5 VAT to pay 761 833.30 NOK.
