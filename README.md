# NorFinGen

A live financial data generator that produces a fully realistic,
continuously growing operating history for a fictional Norwegian IT
managed services company — built to the Tripletex accounting API's
data model, calibrated against real Norwegian market benchmarks, and
delivered through a live Postgres database, a public analytics
report, and BI-ready read access.

A scheduled job adds a new day of transactions automatically, every
day — this is not a static dataset.

## What this is for

1. **Testing software against genuinely live, evolving financial
   data** — systems built on the Tripletex API model, BI dashboards
   that need real day-to-day change, or any tool that needs to be
   exercised against data that doesn't sit still
2. **An analytical/portfolio dataset** — a full, multi-dimensional
   financial database with a genuine, ongoing business history
3. **A demonstration of financial-domain modeling** — Norwegian
   employment law, double-entry bookkeeping, market calibration, and
   realistic business turbulence — not just random number generation

## What makes the data realistic

- **Full double-entry bookkeeping** — every transaction posts correct
  DR/CR entries, balances to zero, follows Norwegian VAT convention
- **Norwegian employment law, computed not hardcoded** — feriepenger
  (holiday pay), skattetrekk, arbeidsgiveravgift
- **Market-calibrated financials** — pricing, margin, and headcount
  benchmarked against real Norwegian IT services companies
  (Brønnøysundregistrene public filings)
- **A genuine business narrative** — years of history including
  organic growth, a company merger, a COVID-era slowdown, client
  churn, a major lost contract and its multi-year margin impact, and
  logged, dated business events — sourced from the generator's own
  event log, not reconstructed after the fact
- **Verified against the real world** — customer names checked against
  the public Brønnøysundregistrene registry to confirm none collide
  with a real company; suppliers, where named as real companies (e.g.
  Microsoft Norge AS, Telenor Norge AS), are verified as accurate

## Explore it

- **Live analytics report:** [maykel84.github.io/raport](https://maykel84.github.io/raport)
  — revenue, profitability, customers, headcount, cash flow, forecasts,
  and a full timeline of the business events behind the numbers
- **Try the data yourself:** a [REST API](https://norfingen-api.fly.dev/docs)
  with an API key (Tripletex-style `GET` + key), or read-only test access
  via Power BI/Tableau/direct SQL — see [docs/API_ACCESS.md](docs/API_ACCESS.md)
- **Self-service portal:** [norfingen-api.fly.dev/portal](https://norfingen-api.fly.dev/portal)
  — generate your own API key or download a fresh CSV/Excel export (full
  history or a custom date range) in one click, no sign-up. See
  [docs/EDU_ACCESS.md](docs/EDU_ACCESS.md) for students/coursework.

## Current scale

- 17 employees, 47 active customers (50 total across the company's history)
- 233-test suite, all passing
- Data from March 3, 2019 to today
- Trailing 12-month margin: 2.9% — below the usual 5.5–9% target band by
  deliberate, documented design: a major client-loss incident (see
  [docs/PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md)) whose multi-year
  margin impact was accepted as a realistic outcome rather than
  artificially offset. The band applies again, without exception, going
  forward.

## Tech stack

Python · Pydantic v2 · PostgreSQL (Supabase) · GitHub Actions ·
modeled on the Tripletex API

## Architecture

Generator (Python, deterministic seeding) writes to a Supabase
PostgreSQL database via a daily GitHub Actions job. From there, data
flows to: (a) a public analytics report (static site), (b) BI-ready
read-only access for external tools, (c) Excel/CSV export. See
[docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) for the full schema.

## Project history

This project evolved through a series of calibration and realism
phases — see [docs/PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md) for
the full development journal.

## Data safety

Fictional vs. real entities are handled under a clear rule: suppliers
may be real, named companies; customers are always fictional. See
[docs/DATA_SAFETY.md](docs/DATA_SAFETY.md).

## License / status

Portfolio/demonstration project — no formal license specified.
