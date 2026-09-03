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

## Current state

Latest tag `v5.13-faza7c-major-incidents`, with the data-safety audit
above merged on `main` but not yet tagged — 17 employees (flat since
Nov 2022), 50 customers, 8 suppliers, daily-growing history from March
2019 to today. 2025 full-year margin 6.1%; 2023–2026 sit outside the
usual 5.5–9% safety band by deliberate, documented design (the major
Enterprise-client-loss incident above) rather than a calibration gap —
that band applies again, without exception, for any future change.
