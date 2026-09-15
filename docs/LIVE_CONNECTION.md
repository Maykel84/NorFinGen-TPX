# Connect to live data (Power BI, SQL, Python)

Request read-only connection details via the portal
(https://norfingen-api.fly.dev/portal) or directly:

```bash
curl -X POST https://norfingen-api.fly.dev/api/v1/db-access/request \
  -H "Content-Type: application/json" \
  -d '{"label": "your-name-or-course"}'
```

This is a **shared, read-only credential** — connection limit 10,
15s query timeout. Writes are rejected at the database level (not
just discouraged): DELETE, UPDATE, DROP all fail with "permission
denied" or "must be owner of table", regardless of what you send.
Limited to 3 requests per IP per day; each request is logged
(label + IP + timestamp) for audit purposes only — the credential
itself stays the same for everyone who asks.

## Power BI Desktop

1. Get Data → More → Database → PostgreSQL database
2. Server: (from the request response)  |  Database: postgres
3. Data Connectivity mode: **Import** (recommended — snapshot, click
   Refresh for latest data) or **DirectQuery** (always live, slower)
4. Username/Password: from the request response
5. Start with `v_pl_monthly`, `v_sales_flat`, `v_headcount_monthly`

## SQL client (DBeaver, TablePlus, psql)

```bash
psql "postgresql://portal_reader.xxx:PASSWORD@host:5432/postgres"
```

## Python

```python
import psycopg2
import pandas as pd

conn = psycopg2.connect(host="...", port=5432, dbname="postgres",
                         user="portal_reader.xxx", password="...")
df = pd.read_sql("SELECT * FROM v_pl_monthly ORDER BY month DESC LIMIT 12", conn)
```

## Import vs. live query

- Occasional dashboard → Import mode (Power BI) or re-run script when needed
- See changes immediately → DirectQuery (Power BI) or scheduled script

## Is this safe to share widely?

Yes — read-only, synthetic data, writes are rejected at the database
permission level (verified manually, not just assumed — see
[docs/SESSION_HANDOFF.md](SESSION_HANDOFF.md) for the exact error
messages from a live `portal_reader` connection). See
[DATA_SAFETY.md](DATA_SAFETY.md) for how fictional vs. real entities
are handled.

## How this differs from the other two access paths

NorFinGen's portal offers three independent ways to get at the same
data — pick whichever fits:

| Path | Needs a key? | Best for |
|---|---|---|
| [REST API](API_ACCESS.md) (`/keys/request`) | Yes, self-service | Scripts/apps that want JSON over HTTP |
| [On-demand export](EDU_ACCESS.md) (`/export/{format}`) | No | A one-off CSV/Excel snapshot to open locally |
| **Live DB connection** (this doc) | No (shared credential) | Power BI dashboards, ad-hoc SQL, notebooks — anything that wants to query the live database directly |
