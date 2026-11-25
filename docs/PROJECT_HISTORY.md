# Project History

A phase-by-phase account of how NorFinGen evolved from a basic
Tripletex-schema generator into a fully calibrated, market-realistic
financial simulator with a live, daily-growing dataset.

## Foundation (v5.0–v5.1)

Service catalog (S01–S04), customer/service metadata in Supabase,
row-level security, per-service pricing.

## Cost realism (v5.2–v5.3)

Client base scaled 12→50, new cost categories (canteen, representation,
travel, equipment), Norwegian holiday-pay (feriepenger) audit and fix.

## Market recalibration (v5.5–v5.6)

Pricing and headcount recalibrated against real Norwegian IT services
companies (Brønnøysundregistrene public filings) — headcount reduced
38→17, a three-bucket cost model (labor, opex, COGS pass-through)
introduced to match real-market margins (5.5–9%, down from an initial
14–21%). Industry classification (NACE/SN2007) added for the company
and all customers.

## Data integrity fixes (v5.10)

Found and fixed two independent bugs: 21 orphaned employee records
left over from a prior headcount reduction, and a structural gap where
payroll never generated outgoing bank transactions.

## Variability layer (v5.11–v5.13)

A stochastic life-events engine — client-level events (temporary
hardship, expansion/reduction, bankruptcy, one-off projects),
company-level events (equipment purchases, unprofitable quarters,
supplier renegotiation), a historically-grounded COVID-2020 slowdown,
and a major deliberate incident: the permanent loss of a large,
long-tenured Enterprise client, whose multi-year margin impact was
accepted as a realistic structural outcome rather than artificially
offset.

## Data safety review (post-v5.13, unreleased)

Audited all 8 supplier names against the public Brønnøysundregistrene
registry — several already matched real, well-known Norwegian vendors
(Microsoft, Telenor), one typo was corrected against a real match, and
one fully fictional supplier was replaced with a recognizable brand.
Formalized the governing rule: suppliers may be real, named companies
(money flows *to* them); customers must always remain fictional (money
would flow *from* them, which would misattribute invented results to a
real company). A companion client-name audit was scoped for a future
session and has not yet been run.

## Accounting audit (2026-11-16)

A six-phase audit of the ledger model, applied in order and each verified against a full regeneration:
(1) the month still in progress is flagged (`is_partial` in `v_pl_monthly`), not pro-rated, and every yearly / trailing
KPI uses full months only; (2) pass-through COGS is booked net with 25 % input VAT (2710), the liability to the supplier
is the gross amount; (3) share capital of 500 000 NOK plus a 3.5 mln NOK owner loan (2290, 5 % p.a., 60 monthly
instalments from 2021-01, interest on 8150), which removed the negative bank balance of the early years; (4) receivables
that stay unpaid are written off 120 days after the due date on 7830 "Tap på krav" (net cost, VAT correction on 2700,
gross out of 1500), one voucher per order; (5) the invoice status is derived from what really happened (paid / open /
overdue / written off) instead of copied from the customer's modelled behaviour, and operating costs and VAT settlements
follow a realistic calendar; (6) typed Excel cells (real dates, booleans, text postal codes). The ledger checks grew from 13
to 20 SQL tests. The same pipeline still produces history, the daily cron and catch-up.

## Review round 2 (2026-11-17)

Found while reviewing the dashboard and the 15 November export: (1) an invoice must never read WRITTEN_OFF before the
write-off voucher exists. Order 1761 is bad debt whose write-off date is 2026-12-23; the raw `orders.status` (the generator's
intent) already said WRITTEN_OFF. The state is now derived in one place, the view `v_invoice_status` (with
`write_off_pending`), the exports read it, and a test (T22) ties every written-off invoice to its voucher to the cent;
(2) COGS payments skipped months (accrual + 30 days landed on the 1st of the month after next, so some months had no
payment and the next had two); the due date is now the last working day of the month after the accrual, exactly one
payment per supplier per month (T21); (3) COGS went to two suppliers only. It is now split between six real companies
(Microsoft, Crayon, SoftwareOne for licences; Ingram Micro, Atea, Proact for tools and hardware), the largest carrying
a third; amounts, margins and VAT rules did not move, which golden hashes of the monthly totals prove (T23 guards the
distribution). Two review notes need no change: interest on the owner loan (8150, 794 792 NOK) is deliberately outside the
operating result, and the architect without hours (E05) is the documented, deliberate exception. Ledger checks: 26.

## Review round 3 (2026-11-24)

The export of 24 November confirmed the round-2 fixes. What it found was a type problem in the Excel export only: a NULL was
written as an empty text cell, so id and date columns that contain blanks (`customer_id`, `supplier_id`, `paid_date`) mixed
text and numbers or dates. A NULL is now a truly empty cell and identifiers are whole numbers. The database types were right
all along, the postal codes were stored as text, and the fractional quantities are the deliberate consulting hours. One
check waits for a date: the write-off of order 1761 is planned for 2026-12-23 and must book on that day.

## Review round 4 (2026-11-25, in progress)

A completeness and realism round: what the generator still lacks compared with a real ERP / bookkeeping system (balance sheet,
depreciation, income tax, mandatory pension, currencies, analytical dimensions) and a controlled amount of the dirt real data
carries. Six steps, each with its own acceptance test, run in this order: (1) a verification script, (2) the missing
accounting structure, (3) natural variability in the clean data, (4) document-level dirt, (5) currencies, (6) dimensions.

Decisions taken on 2026-11-25, before any implementation:
- **D1, target margin:** recalibrate top-down (target EBIT margin 3-7 % with a +-2 point yearly spread, then the cost budget, then
  headcount), keeping the dip after the loss of the large client in 2023-24 and the recovery in 2025-26. Depreciation and pension
  take about 1-1.5 points off the margin, so without this 2024-25 would turn negative.
- **D2, dirt:** two profiles of the same seed: `clean` (default, for the dashboard and the invariants) and `dirty` (the same data
  plus injected anomalies with a ground-truth table `dq_ground_truth`). Production stays clean.
- **D3, currencies:** yes: EUR and USD supplier invoices with historical NOK rates, realised gains and losses (8060 / 8160) and
  period-end revaluation, rates in `ref_currencies`.
- **D4, tax:** yes: 22 % income tax with losses carried forward (the 2019 loss reduces 2020-21), no deferred tax.

Step 2 is done: the structure a real set of books has and the generator lacked. Fixed assets (account 1200) are depreciated
straight line over five years; 2 % mandatory pension (OTP) is accrued with every payroll and paid quarterly; 22 % income tax is booked
on 31 December with losses carried forward (the 2019 start-up loss covers 2020 and part of 2021) and paid in two equal instalments
on 15 February and 15 April; and a new sheet `Bilans_miesiecznie` gives the balance sheet at every month end, which balances to the
cent. The P&L gained depreciation, EBITDA, financial result, tax and net result. Pension and depreciation take the EBIT margin of
2024-25 to -0.5 % and -1.0 %, as anticipated in D1: the margin recalibration is the next step. Ledger checks: 37.

Step 1 is done: `tools/verify.py`, a read-only script (it runs against production as safely as against a local database) that
prints PASS/FAIL for every ledger invariant (all of `tests/gl_checks.sql`) and for the data-quality fields of an ERP quality
report (vouchers without lines, unbalanced vouchers by count and by sum, invoices without lines, P&L = ledger in every month) and
writes `docs/verify_<date>.md`. On the data of 2026-11-24 it reports 31/31 PASS.

## Current state

Latest tag `v5.13-faza7c-major-incidents`, with the data-safety audit
above merged on `main` but not yet tagged — 17 employees (flat since
Nov 2022), 50 customers, 13 suppliers (8 invoice suppliers + 5 COGS-only), daily-growing history from March
2019 to today. 2025 full-year margin 6.1%; 2023–2026 sit outside the
usual 5.5–9% safety band by deliberate, documented design (the major
Enterprise-client-loss incident above) rather than a calibration gap —
that band applies again, without exception, for any future change.
