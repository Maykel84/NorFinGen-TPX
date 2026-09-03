# Try the data yourself

NorFinGen's database is available read-only for testing and exploration.
Data is live — a new day of transactions is added automatically every
day via a scheduled job.

## Option A — Direct SQL / BI tool connection

Connect any PostgreSQL-compatible tool (Power BI, Tableau, DBeaver,
psql) using:

- Host: `aws-1-eu-central-1.pooler.supabase.com`
- Port: `5432`
- Database: `postgres`
- Username: `demo_reader.<project_ref>` (ask the owner for the exact `<project_ref>` — the Supabase pooler requires this qualified form, plain `demo_reader` will not authenticate)
- Password: request via the owner
- SSL: required (`sslmode=require`)

Read-only access, 2 concurrent connections, 10s query timeout. `INSERT`/`UPDATE`/`DELETE` are rejected at the database level, not just hidden by the tool you use.

## Option B — Static export

Prefer a file over a live connection? Contact the owner for a static CSV/Parquet export.

## Suggested starting queries

```sql
SELECT * FROM v_pl_monthly ORDER BY month DESC LIMIT 12;
SELECT * FROM v_sales_flat LIMIT 20;
SELECT * FROM v_headcount_monthly ORDER BY month DESC LIMIT 12;
```

## What you'll find

7.5+ years of daily-growing financial history for a fictional Norwegian
IT managed services company — orders, invoices, payroll, bank activity,
and a full ledger. See [docs/DATA_DICTIONARY.md](DATA_DICTIONARY.md)
for the schema and [docs/DATA_SAFETY.md](DATA_SAFETY.md) for how
fictional vs. real entities are handled.

## Access notes

This is a separate role (`demo_reader`) from the one used for the
owner's own Power BI connection (`powerbi_reader`) — kept independent
so demo access can be rotated or revoked at any time without
interrupting the owner's own use. The password is never stored in this
repository; it is generated and rotated on request via
`scripts/setup_demo_reader.py` and shared through a secure channel.
