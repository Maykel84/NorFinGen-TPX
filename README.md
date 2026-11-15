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
- 549-test suite, all passing (one more test runs only against a local scratch Postgres, see below)
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

## Chart of accounts

NS 4102 accounts the generator books on (full list with names: [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md)).

| Account | Used for |
|---|---|
| 1500 Kundefordringer | receivable: Dr on every invoice, Cr when the customer pays |
| 1910 Bankinnskudd | every cash movement: customer and supplier payments, payroll, VAT |
| 2400 Leverandørgjeld | supplier ledger: purchase invoices and the COGS pass-through accruals |
| 2600 Forskuddstrekk · 2770 Skyldig AGA · 2930 Skyldig lønn · 2940 Skyldige feriepenger | payroll liabilities |
| 2700 / 2710 / 2740 | output VAT / input VAT / VAT settlement account (bi-monthly mva-oppgjør) |
| 3000 Salgsinntekt | all revenue (3100 exists but is unused, see below) |
| 4290-4292 | COGS: customer equipment, Microsoft/Azure and tooling pass-through |
| 5000 | gross salaries and feriepenger |
| 6xxx / 7xxx | operating costs |

Every voucher balances to the cent; VAT is always its own posting, never a field that excuses an imbalance.

## Deliberate test traps and assumptions

The data is meant for practising reconciliations, so some irregularities are **there on purpose** and flagged in the export:

- **Late and bad-debt customers.** A small share of invoices is paid 90 days late (`invoice_status = OVERDUE`) or never
  (`WRITTEN_OFF`, no write-off entry is booked). They are why the receivable (1500) never reaches zero; `Faktury_sprzedazy`
  has `invoice_status`, `is_overdue`, `payment_due_date` and `paid_date` so the receivable can be reconciled invoice by invoice.
- **Open items on the date of the export.** Invoices not yet due, COGS liabilities (`Zobowiazania_COGS`, status `UNPAID`) and
  the VAT term in progress (`Rozliczenia_MVA`) are expected to be open; the balances of 1500, 2400 and 2740 are exactly the
  sum of these open items.
- **June feriepenger.** Each June (from 2020) the feriepenger provision on 2940 is paid out *instead of* the normal salary.
  Salary (5000) still appears in June for employees without a full year of tenure (the top-up). That is correct, not an error
  (`gl_checks.sql` T9 pins it).
- **Revenue only on 3000.** Licence products belong to 3100 in the product catalogue, but the ledger books all revenue on 3000.
- **Fictional counterparties.** Customers are fictional; suppliers may be real companies. Supplier postal codes are static
  registry data, two of them illustrative (docs/DATA_SAFETY.md).

## Regenerating the data and checking it

Never regenerate against the production database by hand. Local, on a scratch Postgres:

```bash
scripts/local_pg.sh start                  # a throw-away Postgres on 127.0.0.1:54329 (data in .local/pg)
export DATABASE_URL="$(scripts/local_pg.sh url)"
scripts/local_regen.sh                     # schema + TRUNCATE + every day from 2019-01-01 to today (about a minute)
python tests/run_gl_checks.py              # the accounting acceptance tests (tests/gl_checks.sql), PASS/FAIL table
python tests/verify_regeneration.py        # internal consistency checks, plus a comparison with a reference database
pytest                                     # unit tests; they refuse to touch any database
NORFINGEN_TEST_PG_URL="$DATABASE_URL" pytest tests/test_money_pg_round.py   # the one test that needs a real Postgres
```

`local_regen.sh` and `run_gl_checks.py` refuse to run unless the database host is local. History and the daily cron use one
pipeline (`run_daily.process_day`), so a day generated by the cron is identical to the same day of a full regeneration.

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
