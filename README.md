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

- **Live analytics report:** [norfingen-analytics.streamlit.app](https://norfingen-analytics.streamlit.app/)
  — revenue, cost, profit, margin, client coverage, and history, reading
  live from the same database (EN/PL/NO)
- **Try the data yourself:** a [REST API](https://norfingen-api.fly.dev/docs)
  with an API key (Tripletex-style `GET` + key), or read-only test access
  via Power BI/Tableau/direct SQL — see [docs/API_ACCESS.md](docs/API_ACCESS.md)
- **Self-service portal:** [norfingen-api.fly.dev/portal](https://norfingen-api.fly.dev/portal)
  — generate your own API key, download a fresh CSV/Excel export (full
  history or a custom date range), or request a live read-only database
  connection (Power BI / SQL / Python) — all in one click, no sign-up. See
  [docs/EDU_ACCESS.md](docs/EDU_ACCESS.md) for students/coursework, and
  [docs/LIVE_CONNECTION.md](docs/LIVE_CONNECTION.md) for the live DB path.

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

## Deliberate simplifications in the books

- **One account for employer's contribution (AGA): 2770.** The AGA on the feriepenger provision is booked on
  the same account as the AGA on salary, not split off to 2780 (*Påløpt arbeidsgiveravgift på feriepenger*).
  A split would need a mechanism that releases 2780 into 2770 when the feriepenger is paid out in June; the
  amounts, the P&L and the cash flow are identical either way.
- **Payroll liabilities have their own accounts** (2930 net pay, 2600 withheld tax, 2770 AGA, 2940 feriepenger
  provision); 2700/2710/2740 are reserved for VAT, as in NS 4102.

- **Operating costs are booked on realistic days** (not all on the 1st): canteen subsidy, mileage reimbursement and the
  COGS accruals (4291/4292) on the last working day of the month (with payroll), representation on a reproducible
  random working day 5-25, conference trips and the one-off cost spike on a random working day 8-25, customer
  equipment on the onboarding date (a weekend moves back to Friday). Never on a weekend. The amounts did not change
  (`opex_amounts` in the golden hash is frozen); the longest stretch without any cost posting is 10 days.
- **VAT is settled every two months** (mva-oppgjør): on the last day of the term 2700/2710 are moved to 2740, the
  difference is paid (or refunded) on 10 Apr / 10 Jun / 31 Aug / 10 Oct / 10 Dec / 10 Feb, moved to a working day.
  See `vat_settlements` in the data dictionary and the `Rozliczenia_MVA` export sheet. The VAT return is treated as
  always filed on time (no late fees, no corrections).

## Backlog (deliberately deferred)

Decisions taken while fixing the accounting model (see [docs/SPEC_poprawki_ksiegowe.md](docs/SPEC_poprawki_ksiegowe.md)):

- **Norwegian public holidays as days without bank payments** (17 May, Easter, Christmas). Today a working
  day is Monday-Friday only (`seed/workdays.py`); a payment due on a weekend is booked the next Monday,
  one due on a holiday is not moved.
- **Decimal end to end.** Amounts are Python floats rounded by Postgres on insert; `generators/money.py`
  (`pg_round2`) reproduces that rounding where Python writes an amount first, and any amount already stored is
  read back from the database, never recomputed. Moving the whole pipeline to `Decimal` is a separate,
  conscious change of history and needs a new version of the golden hash (`tests/test_golden_hash.py`).
- **COGS as real supplier invoices (variant A).** The monthly pass-through COGS (accounts 4291/4292) books a
  liability on 2400 without a purchase invoice behind it; tests and the export cover it as a separate
  "COGS payables" set instead (variant B). Giving it real supplier invoices would need a supplier for 4292.

## License / status

Portfolio/demonstration project — no formal license specified.
