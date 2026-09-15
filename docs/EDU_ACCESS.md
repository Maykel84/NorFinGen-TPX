# Get your own API key (for learning/coursework)

## Option A — Use the portal (easiest)

Visit https://norfingen-api.fly.dev/portal — generate a key with one
click, or download the latest data (full history or a custom date
range) directly, no key required for downloads.

## Option B — Request a key via API

```bash
curl -X POST https://norfingen-api.fly.dev/api/v1/keys/request \
  -H "Content-Type: application/json" \
  -d '{"label": "your-name-or-course"}'
```

**Save the returned key immediately — it won't be shown again.**

## Using your key

```bash
curl -H "X-API-Key: nfg_edu_xxxxx" \
  "https://norfingen-api.fly.dev/api/v1/pl/monthly?from=2025-01&to=2025-12"
```

Rate limit: 60 requests/hour. Max 3 keys per IP per day. See
[docs/API_ACCESS.md](API_ACCESS.md) for the full endpoint list.

## Download data (no key needed)

Full history (2019 to today):
- CSV (zip of 5 per-table CSVs): https://norfingen-api.fly.dev/api/v1/export/csv
- Excel (one workbook, 6 sheets): https://norfingen-api.fly.dev/api/v1/export/excel

Custom date range:
- https://norfingen-api.fly.dev/api/v1/export/csv?from=2023-01&to=2025-12

`from`/`to` use the `YYYY-MM` format (month, inclusive). Each request
generates a fresh export straight from the live database — not a cached
snapshot. Limited to 1 export per 5 minutes per IP.

The CSV download is a `.zip` containing one file per table (P&L monthly,
sales invoices, purchase invoices, payroll monthly, payroll per employee,
GL postings) — the tables don't share a row shape, so a single flat CSV
would lose structure. The Excel download has the same six tables as
separate sheets in one `.xlsx`.

## About this data

All figures are synthetic — a simulated Norwegian IT services company.
Customer names are fictional; some suppliers are real, well-known
companies (see [DATA_SAFETY.md](DATA_SAFETY.md)). Data updates daily.

## Suggested exercises

1. Calculate year-over-year revenue growth
2. Find the year with the lowest margin and investigate why
   (hint: check `/api/v1/events`)
3. Identify which customers churned and when
4. Compare revenue per employee across years
5. Download just 2023-2026 and analyze the margin recovery pattern
