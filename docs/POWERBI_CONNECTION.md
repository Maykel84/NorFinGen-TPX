# Connecting NorFinGen to Power BI

See `DATA_DICTIONARY.md` (the "Read-only access" section) for the full description of the `powerbi_reader` role, GRANTs, and views — this document is just the connection instructions.

## Connection details

In Power BI Desktop: **Get Data → More → Database → PostgreSQL database**

- **Server**: `aws-1-eu-central-1.pooler.supabase.com:5432` (Session pooler — verified, this port; a Transaction pooler on 6543 also exists in Supabase, but hasn't been tested with this role in this project)
- **Database**: `postgres`
- **Data Connectivity mode**: Import (recommended) or DirectQuery (live, but slower report refreshes)
- **Authentication**: Database
  - **User**: `powerbi_reader.<project_ref>` — **NOTE**: this is NOT just `powerbi_reader`. The Supabase Pooler requires a qualified username in the format `<role>.<project_ref>` (e.g. `powerbi_reader.zijotdnqunkwqztpxhiv`). Without this suffix, login fails. `scripts/setup_powerbi_reader.py` prints the exact, ready-to-paste username on every run.
  - **Password**: [shared securely, not in this document — see `scripts/setup_powerbi_reader.py`]
- **Encrypt connection**: enabled (Supabase requires SSL — the connection won't establish without it)

## Recommended tables/views to connect to

For basic financial analytics, 3 views are enough (see `DATA_DICTIONARY.md`, "BI views"):
- **`v_sales_flat`** — sales with full customer context (segment, city, postal code, NACE)
- **`v_pl_monthly`** — monthly P&L (revenue, labor_cost, operating_cost, cogs, operating_result), ready to chart
- **`v_headcount_monthly`** — headcount trend — **note**: this only counts billable employees who log hours (Leveranse/Teknologi), not the true HR headcount (support roles Salg/Økonomi never log `hour_entries`). If you need the true headcount, connect to `employments`/`employees` instead of this view.

For deeper analysis — connect directly to the source tables:
`orders`, `order_lines`, `supplier_invoices`, `customers`, `suppliers`, `employees`, `hour_entries`, `bank_transactions`, `vouchers`, `postings`.

## Data refresh

- **Power BI Desktop**: manual "Refresh" or scheduled in Power BI Service
- Data in Supabase updates incrementally — GitHub Actions (`.github/workflows/daily.yml`) runs the generator 3x/day on weekdays: **07:00, 11:00, 16:00 UTC = 08:00, 12:00, 17:00 CET** (during winter; in summer CEST shifts the effective local times one hour forward — the GitHub Actions cron always runs in UTC, with no DST)
- Recommended scheduled refresh in Power BI Service: **18:00 CET/CEST** (an hour after the generator's last run), to make sure that day's data is already in the database
- **Power BI Service != Power BI Desktop**: a scheduled refresh in the cloud (Power BI Service) requires configuring the data source credentials in the dataset settings AFTER publishing the report — Supabase Postgres is a cloud data source, so **no on-premises data gateway is needed** (that's only required for local/behind-a-firewall sources)

## Limits and security

- The `powerbi_reader` role has **read-only** access (`SELECT`) — verified end-to-end (`scripts/test_powerbi_connection.py`): `INSERT`/`UPDATE`/`DELETE` are all correctly rejected (`InsufficientPrivilege`)
- A limit of **3 concurrent connections** (`CONNECTION LIMIT 3`) — protects the database from overload with several parallel refreshes (e.g. several Power BI Service reports at once)
- **Don't share the password in public repositories or documents** — the password is NEVER stored anywhere in this repo; it's generated randomly by `scripts/setup_powerbi_reader.py` and printed once to stdout only. Save it in a password manager right after generating it. Every re-run of the script rotates the password and invalidates the previous one.

## Verifying the connection before connecting Power BI

```bash
python scripts/test_powerbi_connection.py powerbi_reader.<project_ref>
```

Provide the password via the `POWERBI_READER_PASSWORD` environment variable or interactively (the script will prompt, without echo) — **never as a command-line argument** (it would end up in the shell history and be visible in the process list to other users on the same machine). The script checks `SELECT` on the 3 BI views + 3 source tables, and confirms `INSERT`/`UPDATE`/`DELETE` are blocked.
