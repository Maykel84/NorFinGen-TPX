# Try the data yourself

NorFinGen's database is available read-only for testing and exploration.
Data is live — a new day of transactions is added automatically every
day via a scheduled job.

## Option A — REST API with an API key (recommended for integrations)

A lightweight HTTP wrapper (FastAPI) over the same read-only database —
plain `GET` requests with an API key, the same pattern as the Tripletex
API or any typical weather API, no Postgres client or connection string
required.

```bash
curl -H "X-API-Key: nfg_xxxxx" \
  "https://norfingen-api.fly.dev/api/v1/pl/monthly?from=2025-01&to=2025-12"
```

The key also works as a query parameter (`?api_key=nfg_xxxxx`) for quick
testing from a browser. Request a key from the owner.

Endpoints (all under `/api/v1`, all read-only — no `POST`/`PUT`/`DELETE`
exist on this service):

| Endpoint | Returns |
|---|---|
| `GET /pl/monthly?from=YYYY-MM&to=YYYY-MM` | Monthly P&L |
| `GET /pl/yearly` | P&L aggregated by year, with margin % |
| `GET /customers?segment=&active=` | Paginated customer list |
| `GET /customers/{customer_number}` | Single customer |
| `GET /headcount/monthly` | Active (billable) headcount per month |
| `GET /orders?from=YYYY-MM-DD&to=YYYY-MM-DD` | Sales orders in a date range, paginated |
| `GET /events?year=&scope=` | Life-events log (client/company business events) |
| `GET /health` | No key required |

List endpoints are paginated (`limit`/`offset`, default 100, max 1000).
Rate limit: 100 requests/hour per key by default (adjustable per key),
plus a 300/hour per-IP limit at the infrastructure layer. Full interactive
documentation (OpenAPI/Swagger, no key required): [norfingen-api.fly.dev/docs](https://norfingen-api.fly.dev/docs).
Health check (no key required): [norfingen-api.fly.dev/health](https://norfingen-api.fly.dev/health).

The service connects to the database exclusively as `demo_reader` (the
same read-only role as Option B below) — it cannot write, and it never
uses `service_role`/`postgres`. Implementation in `api/` (FastAPI), deployed
on Fly.io (Stockholm region, `arn`) — end-to-end verified live 2026-09-04.
Machines auto-stop when idle and auto-start on the next request (a few
seconds' cold-start delay is normal after a period of no traffic).

## Option B — Direct SQL / BI tool connection

Connect any PostgreSQL-compatible tool (Power BI, Tableau, DBeaver,
psql) using:

- Host: `aws-1-eu-central-1.pooler.supabase.com`
- Port: `5432`
- Database: `postgres`
- Username: `demo_reader.<project_ref>` (ask the owner for the exact `<project_ref>` — the Supabase pooler requires this qualified form, plain `demo_reader` will not authenticate)
- Password: request via the owner
- SSL: required (`sslmode=require`)

Read-only access, 2 concurrent connections, 10s query timeout. `INSERT`/`UPDATE`/`DELETE` are rejected at the database level, not just hidden by the tool you use.

## Option C — Static export

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
