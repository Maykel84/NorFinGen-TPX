# NorFinGen — Data Dictionary

Description of all 20 tables in the Supabase schema (`src/norfingen/db/schema.sql`). Default currency: **NOK**. All tables have RLS enabled (Phase 1) — access from `run_backfill.py`/`run_daily.py` goes through the `postgres` role (bypasses RLS), read-only access through the `analyst` role.

**The most important limitation of the whole model**: `Order.invoiceDate` in real Tripletex automatically creates a Voucher (accounts 3000/3100, revenue). NorFinGen **does not call the real Tripletex API** — that Voucher never gets created locally. Consequence: **`vouchers`/`postings` never contain sales revenue** — only costs (payroll, suppliers, bank). Every P&L query must compute revenue from `orders`/`order_lines`, and costs from `vouchers`/`postings` separately, and join them manually (see examples in the session history — `WITH p AS (...orders...), k AS (...postings...)`).

---

## Company industry profile (NACE/SN2007 addendum)

Norway classifies companies per SN2007 (Standard for næringsgruppering), aligned with the EU's NACE Rev.2 — every company registered in Brønnøysundregistrene has an assigned industry code (næringskode).

**The company's primary code**: `roster.COMPANY_NACE_CODE` = **62.020** "Konsulentvirksomhet tilknyttet informasjonsteknologi og forvaltning og drift av it-systemer" — explicitly covers both IT consulting/management (S02, S04) and systems operations/support (S01, S03), so it fits the whole service portfolio at once, not just one part of it. Real-world equivalent from the same segment: **Garnes Data AS** (the Phase 6 margin benchmark, registered under the related 62.030 "Forvaltning og drift av IT-systemer" — closer to pure S01/operations).

**Secondary code**: none (`COMPANY_NACE_SECONDARY_CODE = None`). The task anticipated adding 70.220 "Bedriftsrådgivning og annen administrativ rådgivning" if S04 (consulting) exceeds 20% of revenue — verified with a SQL query on the live database (`order_lines` JOIN `products.service_code`, 2025-2026): S04 is **1.9%** of revenue, far below the threshold (the S04 price was cut in Phase 6 to 950 NOK/h). Threshold not crossed, secondary code skipped.

Customer codes: see the `customers` section below (`roster.CUSTOMER_NACE`).

---

## Layer 1 — dimensions / reference data

### departments
| Column | Type | Description |
|---|---|---|
| id | INTEGER (PK) | Department number, 1-4 |
| name | TEXT | Salg / Leveranse / Teknologi / Økonomi |
| number | TEXT | Text code = `id` |
| is_inactive | BOOLEAN | Always `false` — no department deactivation logic |

Business meaning: the company's organizational structure, used to assign employees and (optionally) cost postings. Limitation: static, doesn't change over time even though the company grows from 1 to 17 people.

### employees
| Column | Type | Description |
|---|---|---|
| id | INTEGER (PK) | 1-17, matches `numeric_id("E01")..("E17")` (Phase 6 shrank this from 1-38 — see below) |
| first_name / last_name | TEXT | First / last name |
| employee_number | TEXT | Code "E01"-"E17" |
| department_id | INTEGER (FK) | → departments.id |
| bank_account_number, national_identity_number, date_of_birth | TEXT/DATE | Never populated (NULL) — placeholder for future extensions |
| allow_information_registration | BOOLEAN | Always `true`, no business meaning in the generator |

Business meaning: the company's staff. **The hire date is in `employments.start_date`, not here**. The founding cohort (E01-E06) is spread over 4 months, 2019-01→2019-04 (not a single day) — see `employments`.

**Phase 6 (REPLACES Phase 4) — the team was cut from 38 to 17 people (E18-E38 removed)**: calibration against real market data (Brønnøysundregistrene, 4 Norwegian IT companies — see `SESSION_HANDOFF.md`) showed that comparable IT drift/support firms (Garnes Data AS: 17 employees, ~48-59M NOK revenue, 5.4% margin) serve a large customer portfolio with a small team, because most of the servicing cost is a materials cost (COGS pass-through, see `accounts` 4291/4292), not a headcount cost. E17 (Vegard Lien, Leveranse, 2022-10-03) remains the only post-merger addition — further team growth (Phase 4: E18-E38, 22 hires through 2026-03) was removed entirely.

**Phase 5 — all `start_date` values snapped to the first working day of the month** (`payroll.first_working_day_of_month()`) — eliminates the need to prorate "how many days in a partial month"; the first month of employment is always a full month of work. Several pairs of employees (E02/E03, E04/E05 in the founding cohort; a few pairs from Phase 4) now have an identical `start_date` as a result of this snapping — the staggering is now expressed by the start MONTH, not the day within the month. **Bugfix**: `generate_monthly_salary()`/`brutto_earned_in_year()` compared employee activity against the calendar day 1 (`date(year, month, 1)`), which wrongly excluded from pay an employee whose first working day fell on the 2nd/3rd of the month (because the 1st was a weekend) — fixed by comparing against `first_working_day_of_month()`.

### employments
| Column | Type | Description |
|---|---|---|
| employee_id | INTEGER (FK, UNIQUE) | → employees.id — one record per employee |
| start_date | DATE | Hire date — the reference point for `active_employees()`, raises (+3%/year in July), and feriepenger |
| end_date | DATE | Always NULL — no employee-departure model |
| employment_type, remuneration_type | TEXT | Always "ORDINARY" / "FIXED_SALARY" |
| weekly_working_hours, percentage | NUMERIC | Always 37.5h / 100% — no part-time |
| payroll_tax_zone | TEXT | Always "ZONE_1" (Oslo) |

Limitation: no employee departures (staff turnover) — once hired, an employee stays active forever.

### customers
| Column | Type | Description |
|---|---|---|
| id | INTEGER (PK) | 1-50, `numeric_id("K01")..("K50")` (Phase 4: +38, K13-K50) |
| name | TEXT | Customer company name |
| customer_number | TEXT | Code "K01"-"K50" |
| city | TEXT | Headquarters city |
| **segment** | VARCHAR(20) | Enterprise / Mid-market / SMB (Phase 1) — target 15/18/17 (Phase 4) |
| **onboarding_date** | DATE | Start-of-relationship date — the customer generates no orders before this date (the "realistic company start" phase). Phase 4: spread across 2023-2026 + the merger cohort (2022-09-01, 4 customers, the same date as the employee merger) |
| **churn_date** | DATE | End-of-relationship date, NULL = still active. K09 (2024-11-30) and K15 (2025-10-31, Phase 4) — both SMB |
| **price_multiplier** | NUMERIC(5,4) | Individual price multiplier ±8% (0.92-1.08), deterministic per customer — simulates the outcome of B2B negotiations |
| **nace_code** | VARCHAR(10) | The customer's SN2007/NACE industry code (NACE addendum) — format "XX.XXX" |
| **nace_name** | VARCHAR(200) | Industry name per SN2007 (in Norwegian) |
| **postal_code** | TEXT | Postal code (postnummer) based on `city` — real Posten/Bring codes (`roster.NORWEGIAN_POSTAL_CODES`), an export fix, format "XXXX" |
| organization_number, email, phone_number, address_line1 | TEXT | Never populated (NULL) |
| is_private_individual | BOOLEAN | Always `false` |
| country_id, currency_id | INTEGER | Always 161 (Norway) / 1 (NOK) |
| invoices_due_in, invoices_due_in_type | INTEGER/TEXT | Columns exist, but the actual payment term per order is in `orders.invoices_due_in` (per-order, not per-customer) |

**Bolded columns are Phase 1 additions (+ the NACE addendum for `nace_code`/`nace_name`, + the export fix for `postal_code`)** — populated by `seed_reference_data()`/`scripts/migrate_customer_metadata.py`. `postal_code` as a column **already existed in the original schema** (`schema.sql`), it was just never populated — the export fix (2026-07) added its population, not the column itself. Limitation: only 2 customers have churned (deliberately low, a realistic rate, not a full portfolio-turnover model).

**Addendum — NACE/SN2007 industry codes** (`roster.CUSTOMER_NACE`, a dict `customer_number -> NaceCode(code, name)`, not a separate field on `CustomerSeed` — analogous to `CUSTOMER_PRICE_MULTIPLIER`, so as not to change the constructor signature in 50 places). The code is matched to the customer's actual company name (e.g. "Nordkraft Energi AS" → 35.140 Handel med elektrisitet, "Halden Design AS" → 74.100 Spesialisert designvirksomhet), not random — 18 different sectors among 50 customers. A purely descriptive addendum, **does not affect revenue/costs/margin**, requires no transactional backfill.

**Phase 4 — two pricing cohorts** (`roster.get_service_price_table()`/`service_by_code_for_customer()`): customers onboarded before `CUSTOMER_PRICING_COHORT_CUTOFF` (2023-01-01, covers K01-K12 + the 2022-09 merger cohort) pay `LEGACY_SERVICES` prices (Phase 2), customers from that date on pay `SCALE_SERVICES` (below, ~2.2x lower). Reason: one global price list for all 50 customers across the entire 2019-2026 history was retroactively breaking margin — a price cut for new customers also lowered old customers' revenue in the years when they were the sole revenue base. See `services` below and `SESSION_HANDOFF.md` (Phase 4) for the full rationale.

### suppliers
| Column | Type | Description |
|---|---|---|
| id | INTEGER (PK) | 1-8, `numeric_id("L01")..("L08")` |
| name | TEXT | Supplier name |
| supplier_number | TEXT | Code "L01"-"L08" |
| organization_number, email, phone_number, address_line1, postal_code, city, bank_account_number | TEXT | Never populated (NULL) |
| is_private_individual, is_wholesaler, show_products | BOOLEAN | Always `false` |
| country_id, currency_id | INTEGER | Always 161 / 1 |

Business meaning: 8 cost suppliers (Microsoft, Telenor, Reitan, Statsbygg, Sandvik, Thommessen, Avis, Nordic Insurance) — each with its own invoicing rhythm and amount variance (higher for Avis in Q1/Q3, Sandvik seasonality).

**`postal_code` stays NULL even after the export fix (2026-07)** — `SupplierSeed` (roster.py) never had a `city` field (unlike `CustomerSeed`), so there's nothing to derive a postal code from without inventing new address data. A deliberate limitation, not an oversight — see `SESSION_HANDOFF.md` section 10.

### vat_types
| Column | Type | Description |
|---|---|---|
| id | INTEGER (PK) | 0 / 1 / 3 / 6 |
| name | TEXT | Rate description in Norwegian |
| number | TEXT | Text code = `id` |
| percentage | NUMERIC(5,2) | Rate % — 25.0 for sales/purchases, 0.0 for exempt |
| vat_code | TEXT | "0"/"1"/"3"/"6" — the Tripletex code |

Business meaning: a fixed dictionary of VAT rates (the only rate actually used in the generators is 25%, codes "1" purchase / "3" sales).

### accounts
| Column | Type | Description |
|---|---|---|
| number | INTEGER (PK) | Account number per NS 4102 (the Norwegian chart of accounts), e.g. 5000, 6410 |
| name | TEXT | Account name in Norwegian |
| type | TEXT | ASSETS / EQUITY_AND_LIABILITY / OPERATING_INCOME / OPERATING_EXPENSE |
| vat_type_id | INTEGER (FK) | → vat_types.id, only for revenue/cost accounts with VAT |

Business meaning: a 29-entry chart of accounts (24 + 3 from Phase 3 + 2 from Phase 6) used by every `postings.account_number`. **Accounts 3000/3100 (revenue) exist in this dictionary, but never have any postings** — see the limitation at the top of this document.

**Phase 3 — 3 new cost accounts** (`generators/opex_generator.py`), all without VAT (`vat_type_id=NULL`) — cash costs booked directly (DR cost / CR 1910), without an intermediate `SupplierInvoice`:
- **4290** "Driftsmateriell for kundeleveranse" — COGS (NS4102 class 4, not 6xxx/7xxx like the rest of operating costs): a one-off piece of implementation equipment (routers/servers) at Enterprise/Mid-market customer onboarding, 45-90k NOK (Enterprise) / 15-35k NOK (Mid-market). Since the current 12 customers onboarded 2019-2022, this cost occurs almost exclusively in the historical years.
- **7350** "Kantinetilskudd" — a canteen subsidy, 820 NOK/employee/month (fixed, no inflation — company policy).
- **7420** "Representasjon" — representation costs per active customer: 1,000 NOK/month (Enterprise) / 400 NOK/month (Mid-market), with +3%/year inflation. SMB generates no cost (a purely transactional relationship). A `tax_deductible_pct` flag (the limited tax deductibility of representation costs in Norway) was **not implemented** — the task explicitly allowed this to be skipped, left as a code comment for the future.

Mileage (quarterly customer visits) and conference trips (2-3x/year, random) are booked to the **existing account 7000** "Reisekostnader" — the same account as L07 Avis (a cost supplier from an earlier phase), because it's logically the same NS4102 category (travel costs), not a separate new number. L07 Avis remains unchanged (there was no service/transport "mix" to split out — L07 is purely car rental).

**Phase 6 — 2 new COGS accounts** (`generators/opex_generator.py`, pattern `_cogs_accrual_voucher`: DR cost / CR 2400 Leverandørgjeld — a liability owed to a supplier, not an immediate cash payment like the Phase 3 accounts), scaling monthly with the customer portfolio:
- **4291** "Videresalgskostnad Microsoft/Azure" — S02 pass-through, Enterprise+Mid customers only (`roster.calc_azure_cogs_monthly`): 22,000/11,500 NOK/month (2019 base year, xnumber of customers, +inflation). Replaces the flat "Azure hosting" line (35,000 NOK/month) removed from `supplier_invoices` L01 (see below).
- **4292** "Driftskostnad Managed IT Support (RMM/EDR/verktøy)" — S01 pass-through, ALL active customers regardless of segment (`roster.calc_s01_cogs_monthly`): 53,000/26,500/13,300 NOK/month (Enterprise/Mid/SMB, weight 4:2:1). Added after an offline sanity-check showed that S02-only COGS cannot physically close the gap between real revenue (~52M NOK in 2026, not the assumed ~35M) and the headcount~17/margin 7% target — S02 generates only ~13M NOK/year of revenue, too small a base. Anchored to Garnes Data AS (IT drift/support, real opex+COGS/revenue = 61.6%) — target `(traditional_opex + cogs_s02 + cogs_s01) / revenue ≈ 58-62%`. See `roster.py` (the comment on `calc_s01_cogs_monthly`) and `SESSION_HANDOFF.md` (Phase 6) for the full derivation.

### products
| Column | Type | Description |
|---|---|---|
| id | INTEGER (PK) | 1-7, `numeric_id("P01")..("P07")` (P07 added in Phase 2) |
| name | TEXT | Product name |
| number | TEXT | Code "P01"-"P07" |
| sales_price | NUMERIC(14,2) | 2019 base price (NOK/month), historical/informational. **No longer used to compute the invoice price** for P01/P04/P06/P07 as of Phase 2 (see below) — NULL for P06/P07 |
| vat_type_id | INTEGER (FK) | Always 3 (sales 25%) |
| currency_id | INTEGER | Always 1 (NOK) |
| is_inactive | BOOLEAN | Always `false` |
| **service_code** | VARCHAR(10) (FK → services.code) | P01-P03→S01, P04-P05→S02, P06→S04, **P07→S03 (Phase 2)** |

Business meaning: 7 sales products — P01-P03 IT Support (per segment), P04-P05 licenses (Enterprise/Mid-market), P06 consulting, **P07 (Phase 2) Cybersecurity**. Prices cut ~17% relative to the original assumptions (2026-07) to close the operating margin down to 15-25%.

**Phase 2 — change in the source of truth for price**: `order_generator.build_order_lines()` computes the line price directly from `services.base_price_{segment}` (not from `products.sales_price`) — one canonical product per service (`roster.product_for_service()`: P01→S01, P04→S02, P07→S03, P06→S04) referenced independently of the customer's segment, purely for FK/label purposes on the Tripletex invoice. P02/P03/P05 remain in the catalog (backward compatibility/tests), but **are no longer used to generate order lines** — replaced by segment-based bundling (see `services`, `order_lines`).

---

## Phase 1 — service catalog

### services
| Column | Type | Description |
|---|---|---|
| code | VARCHAR(10) (PK) | S01-S04 |
| name | VARCHAR(200) | Service name |
| description | TEXT | Business description |
| billing_model | VARCHAR(20) | SUBSCRIPTION (monthly) / HOURLY (billed hourly) |
| availability | VARCHAR(30) | ALL / ENTERPRISE_MID / ENTERPRISE_ONLY — which segment can buy it |
| base_price_enterprise / base_price_mid / base_price_smb | NUMERIC(12,2) | 2019 base price: NOK/month for SUBSCRIPTION, NOK/h for HOURLY. NULL = the service isn't available for that segment |

Business meaning: a product catalog independent of per-customer pricing (that's set by `customers.price_multiplier`). **Phase 2**: every service now has a reference product (`products.service_code`) and real per-segment bundling (`roster.get_customer_services()` — Enterprise S01+S02+S03, Mid-market S01+S02, SMB S01) — S03 (Cybersecurity) generates revenue for every Enterprise customer from the moment they onboard (product P07).

**Phase 4 limitation**: this table contains ONLY `LEGACY_SERVICES` (Phase 2 prices: S01 133k/84.5k/49k NOK/month, S02 59k/37.5k, S03 44k) — the PK is `code`, one price per service, so `SCALE_SERVICES` (cut prices for customers onboarded from 2023-01-01: S01 60k/24k/6k, S02 25k/10k, S03 18k) **exists only in Python code** (`roster.SCALE_SERVICES`), with no representation in this table. SQL queries computing revenue per service (`order_lines JOIN products`) are correct (the price actually invoiced is in `order_lines.unit_price_excluding_vat_currency`), but queries reading `services.base_price_*` directly will only show the legacy price list, not the actual price list for newer customers.

---

## Layer 2 — source documents

### orders
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| customer_id | INTEGER (FK) | → customers.id |
| order_date, invoice_date | DATE | Usually identical — the sales invoice issue date (`customer.invoice_day`) |
| delivery_date | DATE | Last day of the billing month |
| invoices_due_in | INTEGER | Days until due date (`customer.payment_terms`: 14/30/45) |
| invoices_due_in_type | TEXT | Always "DAYS" |
| department_id | INTEGER (FK) | Always 1 (Salg) |
| our_contact_id | INTEGER | Always E01's id (Erik Strand, Sales Manager) |
| comment | TEXT | Description "Månedlig faktura — {month} {year}" |
| **status** | TEXT | PAID (default) / OVERDUE (~1.6% of orders, +90 days delayed) / WRITTEN_OFF (~0.4%, never paid — bad debt) |

Business meaning: **sales invoice (revenue)**. Amount = the sum of `order_lines.amount_currency`. Currency: NOK. Limitation: `status` is decided **once, deterministically, when the order is created** (not based on actual elapsed time) — deliberate, so the backfill is fully reproducible.

### order_lines
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| order_id | INTEGER (FK, CASCADE) | → orders.id |
| product_id | INTEGER (FK) | → products.id |
| count | NUMERIC(10,2) | Always 1.0 |
| unit_price_excluding_vat_currency | NUMERIC(14,2) | Unit price in NOK, after inflation (+3%/year) and the customer's multiplier (±8%) |
| discount | NUMERIC(5,4) | Always 0 — no discounts |
| amount_excluding_vat_currency | NUMERIC(14,2) | = count x price x (1-discount). **This field is what counts toward revenue in the P&L** |
| amount_currency | NUMERIC(14,2) | Gross amount (+25% VAT) |
| vat_type_id | INTEGER (FK) | Always 3 (sales 25%) |

Business meaning: a single sales invoice line item. **Phase 2**: one line per service the customer buys based on segment (Enterprise 3 lines S01+S02+S03, Mid-market 2 lines S01+S02, SMB 1 line S01) — replaced the old count-by-`order_pattern`-letter logic (A=1/B=2/C=1). `order_lines` has no `product_service_code` column of its own — a line's service code is derived by joining `product_id → products.service_code` (see `products`, `services`).

### supplier_invoices
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| invoice_number | TEXT (UNIQUE) | Format "{L0x}-{year}-{number}" |
| supplier_id | INTEGER (FK) | → suppliers.id |
| invoice_date, received_date | DATE | Usually identical |
| payment_due_date | DATE | invoice_date + 30 days |
| amount_currency | NUMERIC(14,2) | Gross amount in NOK |
| amount_excluding_vat_currency, vat_amount_currency | NUMERIC(14,2) | Net / VAT (25%) |
| account_number | INTEGER (FK) | Cost account (6xxx) or capitalization account (1200, for L05 >= 30,000 NOK) |
| **status** | TEXT | UNPAID / PAID — flipped to PAID automatically once the matching `bank_transactions` row (OUTGOING) is booked |

Business meaning: **purchase invoice (cost)**. Limitation: 526 historical invoices had PAID status assigned by an old time-based heuristic (predating the `bank_transactions` rollout) — fixed once by `scripts/fix_outgoing_transactions.py`, but **this script needs to be re-run after every full table reset** (TRUNCATE zeroes out `bank_transactions`).

**Phase 2 — L01 (Microsoft Norge) split into several invoices/month** (not 1 flat 85,000 NOK line) — `supplier_invoice_generator.MICROSOFT_COST_LINES`: M365 E3 licenses, Visual Studio/developer tools, CSP/Premier support. 2019 base total = 18,100 NOK/month, with +3%/year inflation (`apply_annual_inflation`, unlike L02-L08, which stay flat). L01's `invoice_number` has an extra `-{1..3}` suffix (e.g. `L01-2024-01-1`).

**Phase 6 — "Azure hosting" (the 4th line item, a flat 35,000 NOK/month) REMOVED from here**, replaced by a COGS pass-through scaling with the number of S02 customers (account 4291, see `accounts` above) — a resale cost, not a fixed operating cost.

### salary_transactions
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| date | DATE | The last working day of the month (payout date) |
| year, month | INTEGER | Natural key (UNIQUE together) |
| status | TEXT | Always "OPEN" — no period-closing logic |

Business meaning: the header of one payroll run (month). One record/month, 91 records total (2019-01 → 2026-07).

### payslips
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| transaction_id | INTEGER (FK, CASCADE) | → salary_transactions.id |
| employee_id | INTEGER (FK) | → employees.id |
| date | DATE | Payout date (= salary_transactions.date) |
| amount | NUMERIC(14,2) | **Net** pay in NOK — gross minus skattetrekk. Higher than usual in June (feriepenger is untaxed) |

Business meaning: one employee's payslip for a given month. Limitation: `amount` is net, not gross — for cost analysis (P&L), use `salary_specifications` or postings on account 5000, not this column.

### salary_specifications
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| payslip_id | INTEGER (FK, CASCADE) | → payslips.id |
| wage_type_id | INTEGER | Component type: Fast lønn / Skattetrekk / Feriepenger |
| description | TEXT | Description in Norwegian |
| amount | NUMERIC(14,2) | NOK, positive for salary/feriepenger, **negative** for skattetrekk (a deduction) |

Business meaning: the breakdown of a payslip into its components. In June: normally just "Feriepenger" (base salary = 0, replaced by feriepenger); for employees with less than a full year of tenure — "Fast lønn" (the top-up) + "Feriepenger" + "Skattetrekk" on the top-up.

---

## Layer 3 — ledger

### vouchers
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| date | DATE | Booking date |
| description | TEXT | Description (natural key together with `date`, UNIQUE) |
| voucher_type | TEXT | INCOMING_INVOICE / SALARY / BANK / MANUAL / **OPERATING_COST (Phase 3)**. **Never INVOICE** (see the limitation at the top of this document) |

Business meaning: the header of an accounting entry. **Contains no sales revenue** — only costs (purchase invoices, payroll, bank movements, Phase 3: canteen/representation/transport/implementation equipment) and founding capital. `OPERATING_COST` (Phase 3, `generators/opex_generator.py`) — cash costs with no matching source document (unlike `INCOMING_INVOICE`, which always has a `SupplierInvoice`).

### postings
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| voucher_id | INTEGER (FK, CASCADE) | → vouchers.id |
| account_number | INTEGER (FK) | → accounts.number |
| amount | NUMERIC(14,2) | **+ = debit, - = credit**. The sum of postings in a voucher ≈ 0 (with a VAT tolerance, see `validate_balance()`) |
| vat_amount | NUMERIC(14,2) | Only on the debit posting, embedded (not a separate posting) |
| customer_id / supplier_id / employee_id / department_id | INTEGER (FK) | Analytical dimensions — populated depending on the posting type (e.g. customer_id for account 1500, employee_id for 2710/2740) |

Business meaning: a single line of an accounting entry (DR/CR). For cost analysis: filter `account_number BETWEEN 5000 AND 5999` (payroll) or `BETWEEN 6000 AND 7999` (operating costs).

---

## Tier 4 — bank / projects / timesheet

### bank_transactions
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| date | DATE | The actual cash-flow date (not the invoice date!) |
| amount | NUMERIC(12,2) | NOK, always positive |
| transaction_type | VARCHAR(20) | INCOMING (customer pays) / OUTGOING (company pays a supplier or payroll) |
| customer_id / supplier_id | INTEGER (FK) | Populated depending on direction |
| order_id / supplier_invoice_id | INTEGER (FK) | The linked source document |
| **salary_transaction_id** | INTEGER (FK) | → salary_transactions.id — populated for OUTGOING rows that are payroll payouts (addendum: "Fix: orphaned records + payroll OUTGOING") |
| account_from, account_to | INTEGER | GL accounts: INCOMING 1500→1910, OUTGOING (supplier) 1910→2400, OUTGOING (payroll) 1910→2710 |
| voucher_id | INTEGER (FK) | → vouchers.id (of type BANK) |

Business meaning: the actual movement on the bank account, time-shifted relative to the invoice by `payment_terms` (customer) or 30 days (supplier), +90 days for OVERDUE orders, never for WRITTEN_OFF. Payroll is paid the same day as the payroll run (`salary_transaction.date` = the last working day of the month) — no delay like invoices have.

**A fixed inaccuracy (in a previous version of this document)**: it used to say "the INCOMING/OUTGOING asymmetry is an artifact of the order features were implemented in" — **that was an incomplete explanation**. The real cause: `bank_transaction_generator.py` had logic ONLY for `Order` (INCOMING) and `SupplierInvoice` (OUTGOING) since Tier 2 — **payroll (the single largest cost line item) never generated any bank transaction at all**. Detected via the mismatch between the published report and the database (1264 INCOMING/187.6M vs 719 OUTGOING/17.5M — physically impossible at costs on the order of 30M+/year). Fixed: `generate_payroll_bank_transaction()` (one aggregated transaction/month: net pay+skattetrekk+AGA, a deliberate simplification — in reality skattetrekk/AGA are remitted to Skatteetaten with a delay, not the same day, but that was beyond the scope of this fix) + a one-time migration `scripts/archive/fix_missing_payroll_transactions.py` (91 missing). After the fix: 810 OUTGOING (107.6M) vs 1267 INCOMING (188.3M) — still unequal (the company is profitable, that's expected), but no longer a structural gap.

### hour_entries
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| date | DATE | A working day (Mon-Fri) |
| employee_id | INTEGER (FK) | 16 of 17 employees log hours — all departments except E05 (see below) |
| project_id | INTEGER (FK) | NULL for anything but BILLABLE |
| activity_type | VARCHAR(20) | BILLABLE / INTERNAL / SICK / VACATION / PARENTAL_LEAVE / WELFARE_LEAVE |
| hours | NUMERIC(4,1) | Leveranse/Teknologi: BILLABLE+INTERNAL sum = 7.5/day (or 0 for an absence type). Salg: 0-4h, irregular. Okonomi: ~6.5-9h/day. |

Business meaning: employee time tracking, not just consultant timesheets. **Generates no accounting postings at all** — purely operational data (no effect on the P&L, independent of `salary_generator`; salary keeps being paid through any absence exactly as through any other day, matching how it actually works in Norway — the employer pays and reclaims part of it from NAV). Limitation: BILLABLE only for projects whose customer is already onboarded and hasn't churned yet — otherwise the whole day is logged as INTERNAL.

**All departments now log hours, one department excluded (`hours_generator.py`)**: Leveranse/Teknologi use the Phase 6 billable/ticketing model below. **Salg** (`generate_salg_daily_hours`) logs irregularly — only ~40% of working days, 1.5-4h, `INTERNAL` ("kundemøte / tilbud") — deliberately not full days, since sales work is episodic, not timesheet-driven; verified this can't affect revenue, since `order_generator.py` has zero dependency on `hour_entries`. **Okonomi** (`generate_okonomi_daily_hours`) logs a near-full day every working day (6.5-7.5h, `INTERNAL`), with a ~1.3x spike (capped at 9h) on the last 3 working days of each month (`is_month_end_closing_period` — regnskapsavslutning). **E05** (System Architect, nominally Teknologi) stays fully excluded from hour tracking, as before this feature — a pre-existing, deliberate exception (`NON_BILLABLE_OVERRIDES`), not extended to absence tracking either, to avoid touching an explicitly tested "never logs anything" invariant.

**Absence types, all four departments (`generators/leave_events.py` + `generators/vacation.py`)**: on top of the ~5% per-day chance of a short, self-certified SICK day (rolled per employee, per day), every employee (except E05) also gets:
- **VACATION** — a hard 25 working days/year (Norwegian statutory minimum, prorated for a mid-year hire), placed with a realistic shape: a ~15-day contiguous "fellesferie" block in July, shorter 2-4 day clusters around Easter (computed via the standard computus algorithm) and Christmas, the remainder scattered through the year (`vacation.employee_vacation_days`, memoized per `(employee_id, year)`). If an employee's year is mostly consumed by a long SICK/PARENTAL_LEAVE block, fewer than 25 days end up actually placed — there's nowhere left to put them; accepted, not worked around further.
- **SICK (long)** — a small, once-per-tenure chance (12%) of a longer, certified block (~3-12 weeks), independent of the short daily 5% roll.
- **PARENTAL_LEAVE** — Norwegian-style `foreldrepermisjon`, rolled independently **every year** an employee is active (6%/year, ~1 case/year across a 17-person team), 20-49 weeks, with a 2-year cooldown after a triggered event. Deliberately **not gender-assigned** — `EmployeeSeed` has no gender field, so every employee has the same symmetric chance; a single type instead of splitting "maternity vs paternity" by a field this project doesn't model.
- **WELFARE_LEAVE** — short (1-3 days), occasional (15%/year), no cooldown (unlike parental leave, it can recur).

All of these are precomputed deterministically per `employee_id` (`employee_leave_periods()`, memoized like `client_events.py`/`company_events.py` — pure functions, no "today" input, safe across the backfill's separate OS processes) and, while active, replace that whole day with a single 0h entry of the matching type — no BILLABLE/INTERNAL/Salg/Okonomi hours logged for that employee that day.

**Safety check performed before backfilling this change** (per the task's own threshold): total annual BILLABLE hours for Leveranse/Teknologi, 2025, computed offline — **9603.1h before this change (long SICK/parental leave only) vs 9018.6h after (adding VACATION + the yearly-rolled PARENTAL_LEAVE + WELFARE_LEAVE) — a 6.09% drop, well under the 15% stop threshold.** No change to revenue logic (order_generator) or payroll (salary_generator) — see `test_payroll_unaffected_by_hours_changes`/`test_salary_generator_module_does_not_import_hours_at_all` in `tests/test_salary_generator.py`.

**A fixed idempotency bug (the 2026-09-04 incident, see `SESSION_HANDOFF.md`)**: `UNIQUE(date, employee_id, project_id, activity_type)` **never protected INTERNAL/SICK rows** (`project_id` is always `NULL` — Postgres treats `NULL <> NULL`, so two identical such rows don't violate this UNIQUE). Two overlapping `run_daily()` runs for the same day (the backfill + probably `daily.yml`) actually duplicated 12 entries in the live database — BILLABLE rows (`project_id NOT NULL`) deduplicated correctly, INTERNAL/SICK didn't. Fixed: a partial index `hour_entries_unique_null_project ON hour_entries (date, employee_id, activity_type) WHERE project_id IS NULL` (`schema.sql`) + `repository._save_hour_entry` changed from a named `ON CONFLICT (...)` to `ON CONFLICT DO NOTHING` with no column list (catches both indexes).

**Phase 6 — two daily models by department** (`hours_generator.py`, replacing the "one customer per day" pattern from Phase 4 — purely data realism, no effect on revenue/payroll):
- **Leveranse (support)** — a ticketing model (`generate_daily_support_hours`): a consultant serves 2-5 customers per day, short hour blocks proportional to segment (`TICKET_AVG_HOURS`), the billable total aims for a random target of 5.5-7.0h.
- **Teknologi (projects)** — a customer lifecycle (`client_lifecycle_phase`): a full day (7.5h) at a customer in the ONBOARDING phase (the first 2-6 weeks from `onboarding_date`, depending on segment), dispersed maintenance (like the ticketing model) for customers in the MAINTENANCE phase otherwise. The small Teknologi team (2 billable staff) runs one active implementation project at a time (`CONCURRENT_ONBOARDING_CAPACITY=1`).

### projects
| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | 1-50, `numeric_id("PRJ001")..("PRJ050")` (Phase 4: 1:1 with `customers`, not 8 manually maintained entries) |
| number | VARCHAR(20) (UNIQUE) | "PRJ001"-"PRJ050" — the same number as the matching `customer_id` |
| customer_id | INTEGER (FK) | → customers.id (1:1, exactly one project per customer) |
| start_date | DATE | **Phase 4**: = `customers.onboarding_date` (fixed a previously misleading limitation — before Phase 4 it was always 2026-01-01/03-01, the date the catalog record was created, not the relationship start date) |
| end_date | DATE | Always NULL |
| status | VARCHAR(20) | Always "ACTIVE" |

Business meaning: a container for consultant hours per customer — used exclusively by `hour_entries.project_id`, has no direct relationship to invoicing (`orders`). **Phase 4**: expanded from 8 (only some customers, manually picked) to 50 (all of them, including SMB, which previously had no project at all) — needed for dynamic consultant assignment (`hours_generator.assign_customers_to_consultants`), replacing the static `EMPLOYEE_PROJECT_MAP` from before this phase.

---

## Phase 7 — the random life-events layer

A deterministically random layer of business events, added so the data stops looking too smooth/linear between the checkpoints from previous phases. **This is not ML** — it's a probability space with assigned probabilities, rolled via `random.Random(string)` (never `hash()`), so it's deterministic: the same seed = the same result on every repeated backfill. Adds no new column/table in Supabase — the whole layer lives in the generators (Python) layer, affecting already-existing tables (`orders`, `order_lines`, `supplier_invoices`, `vouchers`, `hour_entries`) exactly like any other generator mechanism.

**Architecture — a pure, memoized state function, not a mutable ledger.** The Phase 7 prompt (Task 2d) assumed "in-memory state, a single sequential backfill run is enough." Checked and found **not accurate** for this repo: the backfill is in practice TWO separate processes run one after the other (`run_backfill.py --mode monthly`, then `--mode daily`), and `--mode daily` and the live cron (`run_daily.py`, `.github/workflows/daily.yml`) share the same function, called once per process/day. No mutable state object passed in from outside would survive between them. Instead: `customer_event_state_asof(customer_number, year, month)` / `company_event_state_asof(year, month)` — pure functions, recursively advancing month by month from the starting point (the customer's onboarding / the company's 2019-01 founding), cached via `functools.lru_cache`. They give an identical result regardless of which process/call asks for them — a stronger version of the same determinism requirement, not a violation of it. See `SESSION_HANDOFF.md` Phase 7 for the full rationale.

### Client-level events (`src/norfingen/generators/client_events.py`)

The `CLIENT_LIFE_EVENTS` catalog (5 codes), rolled every month per active subscription customer (patterns A/B/C — **K06, the only pattern-D/consulting customer with no fixed service bundle, is deliberately excluded**, see the file):

| Code | Segments | Probability/month | Effect |
|---|---|---|---|
| `OFFER_EXPANSION` | Mid-market, SMB | 0.4% | Permanently adds service S04 (the only one with `availability=ALL` — S02/S03 have segment restrictions that would break pricing, see below) |
| `OFFER_REDUCTION` | Enterprise, Mid-market | 0.3% | Permanently removes one service (never S01) |
| `TEMPORARY_HARDSHIP` | all | 0.4% | 2-4 months: 40-60% reduction of THIS customer's support ticket volume + a raised bad-debt threshold (x5, 2%→10%) |
| `BANKRUPTCY` | SMB | 0.08% | Permanent churn starting next month; the trigger month's final invoice is forced to `WRITTEN_OFF` |
| `ONE_OFF_LARGE_PROJECT` | Enterprise, Mid-market | 0.5% | An extra S04 order, 80-200h at the hourly rate (vs. the standard 20-50k NOK flat fee from Phase 2's `should_generate_extra_consulting`) |

A customer has at most one "big" event at a time — while a `TEMPORARY_HARDSHIP` window is active, nothing new is rolled; `OFFER_EXPANSION`/`OFFER_REDUCTION` are permanent (applied once, never rolled again).

**A bug found and fixed during implementation**: the original expansion map (SMB→S02, Mid-market→S03) violated the already-existing `Service.availability` constraints (S02=`ENTERPRISE_MID`, S03=`ENTERPRISE_ONLY`) — the missing price for SMB/Mid-market caused a `TypeError`. Both segments now expand into S04.

**Scope deliberately limited to the monthly backfill** (like the existing `should_generate_extra_consulting` precedent): revenue/cost effects live in `generate_monthly_orders`/`generate_monthly_opex`. `generate_daily_orders` (the live cron) only respects `event_aware_is_customer_active` (BANKRUPTCY) — otherwise the cron would keep invoicing a customer that already went bankrupt in the backfill history.

### Company-level events (`src/norfingen/generators/company_events.py`)

The `COMPANY_LIFE_EVENTS` catalog (3 codes), rolled once a year (`roll_company_events` — for the whole company, not per customer):

| Code | Probability/year | Effect |
|---|---|---|
| `EQUIPMENT_INVESTMENT` | 35% | A one-off L05 Sandvik invoice, 80-250k NOK (always > the 30k capitalization threshold → account 1200), independent of L05's regular schedule (3-5x/year) |
| `UNPROFITABLE_QUARTER` | 25% | Real transactions across the whole quarter: a 0.85-0.95x reduction in ticket volume (company-wide, multiplies with fellesferie) + a one-off opex cost (account 7790 "Annen driftskostnad", new, 40-120k NOK — an amount chosen independently, the task only gave a `magnitude_range` for the volume) |
| `SUPPLIER_RENEGOTIATION` | 30% | A permanent cost change for one of L01-L08 (randomly chosen), -15%..+10%, starting the rolled month; successive renegotiations of the same supplier compound |

### Norwegian B2B seasonality (`src/norfingen/generators/seasonality.py`)

Pure multipliers with no randomness: `fellesferie_activity_multiplier` (July x0.5 of ticket volume), `q4_budget_flush_multiplier` (November/December x1.4 of the extra-consulting threshold for Enterprise/Mid-market), `january_new_initiative_boost` — **written, but deliberately not wired up** (there's no discrete "new S02 project" mechanism in the code analogous to extra-consulting).

### Log of actually-rolled events

`scripts/log_life_events.py` — generates `docs/faza7_life_events_log.csv` (purely reporting, doesn't touch the database) with the full list of client- and company-level events along with their details (amounts, the rolled service, the supplier). Re-run it after any change to this layer's calibration.

### A known bug found and fixed (Task 4)

`test_fellesferie_reduces_july_ticket_volume` (Task 4's regression tests, run against the full `generate_daily_hours` pipeline, not an isolated call with a manually shared seed) showed that July had MORE tickets than June — the opposite of intended. Cause: the seasonal multipliers scaled only `target_billable`, which in practice is almost never the binding constraint of the loop in `generate_daily_support_hours` (the actual ceiling is `n_clients_today`, max 5 customers x ~1h ≈ 5h, already below the unreduced 5.5-7h target). Fixed: the multiplier now also scales `n_clients_today`.

---

## Read-only access (BI / Power BI, Step 2)

Two roles, layered:

- **`analyst`** (`NOLOGIN`) — purely technical, defines the target privilege set: `GRANT SELECT ON ALL TABLES IN SCHEMA public` (**20/20 tables with an active RLS policy `USING (true)`** — see "Security audit" below, previously 6 reference tables had no RLS at all) + `ALTER DEFAULT PRIVILEGES` (future tables automatically readable, no manual GRANT needed on each migration).
- **`powerbi_reader`** (`LOGIN`, `CONNECTION LIMIT 3`) — the real role for actually logging in from Power BI (or any other BI tool). Inherits the full set of `analyst`'s privileges/policies via `GRANT analyst TO powerbi_reader` — nothing is duplicated. Created/rotated by `scripts/setup_powerbi_reader.py` (password generated randomly on every run, printed ONLY to stdout, never lands in the repo/`.env`).
- **`demo_reader`** (`LOGIN`, `CONNECTION LIMIT 2`, `statement_timeout=10s`) — publicly available test access (`docs/API_ACCESS.md`). A separate role from `powerbi_reader` (independent rotation/revocation), but the same `analyst` inheritance mechanism. **Since 2026-09-04 this is also the role the REST API service (`api/`) connects as** — the only role used by `api/db.py` for data queries, never `service_role`/`postgres`.
- **`api_key_manager`** (`LOGIN`, `CONNECTION LIMIT 5`, `statement_timeout=10s`, 2026-09-04) — does NOT inherit `analyst`, has no access to any table besides `api_keys`/`export_requests` (`GRANT SELECT, INSERT, UPDATE` on `api_keys`, `GRANT SELECT, INSERT` on `export_requests`). Used by `api/auth.py` (key validation + rate limiting), `api/routers/keys.py` (self-service key generation — `INSERT` added in the self-service portal session), and `api/routers/export.py` (the `export_requests` counter). See `scripts/setup_api_backend.py`.

**Connection string for Power BI Desktop** (Get Data → PostgreSQL database): host/port/dbname from `DATABASE_URL`, but **the username must be in the Supabase pooler format** `powerbi_reader.<project_ref>` (not just `powerbi_reader`) — `scripts/setup_powerbi_reader.py` prints the ready, correct username. `Encrypt connection` (SSL) is required.

Verified working (not just configured): connecting as `powerbi_reader`/`demo_reader` correctly **reads** RLS and reference tables, and correctly **rejects** a write attempt (`INSERT` → `InsufficientPrivilege: permission denied for table orders`).

### Security audit (2026-09-04) — two gaps found and fixed

A full, purely diagnostic audit of roles/RLS/views/API keys (a separate session) found two gaps, both fixed immediately in the next session:

1. **6 reference tables with no RLS** (`accounts`, `departments`, `employments`, `products`, `salary_specifications`, `vat_types`) — this was a deliberate Step 2 decision (catalog data, not per-row), but combined with gap #2 below it constituted a real write risk. **Fixed**: RLS enabled on all 6, policy `analyst_read_only FOR SELECT TO analyst USING (true)` — identical to the other 14. **Now 20/20 tables have RLS.**
2. **The default Supabase roles `anon`/`authenticated` had full CRUD privileges** (`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`, not just `SELECT`) on all tables — an automatic `ALTER DEFAULT PRIVILEGES` granted by Supabase at project creation, never deliberately revoked. For the 14 tables with RLS this was mostly a theoretical problem (RLS denies roles outside a policy by default), but for the 6 tables without RLS (before fix #1) it was a **real, open write/delete vector** for anyone holding a public Supabase `anon` key (PostgREST is automatically exposed on every project, regardless of whether the code uses it). **Fixed**: `REVOKE ALL ON ALL TABLES/SEQUENCES/FUNCTIONS IN SCHEMA public FROM anon, authenticated` + an analogous `ALTER DEFAULT PRIVILEGES REVOKE`, so future tables don't automatically inherit this either. This project doesn't use (and never has used) Supabase API keys in its code (only a direct Postgres connection via `DATABASE_URL`) — `anon`/`authenticated` had no legitimate reason for any privileges here.

Verified after the fix: `run_daily.py` still saves correctly (the `postgres` role has `rolbypassrls=true`, owns all the tables — RLS doesn't apply to it), `demo_reader`/`powerbi_reader` still read correctly (through `analyst`), `anon`/`authenticated` (tested via `SET ROLE`, since both are `NOLOGIN` — only reachable through the PostgREST layer) now get `permission denied` on every `SELECT`/`INSERT` attempt, on any table. 233/233 tests unchanged.

### BI views (Step 2, Task 2)

Three flat views (`CREATE OR REPLACE VIEW ... WITH (security_invoker = true)`, PG15+/Supabase PG17) — Power BI gets ready-made tables instead of writing JOINs on every report:

| View | Source | Note |
|---|---|---|
| `v_sales_flat` | `orders` JOIN `customers` JOIN `order_lines` | `amount_including_vat_currency` is an **alias** of the `order_lines.amount_currency` column (not a rename — see below) |
| `v_pl_monthly` | `orders`/`order_lines` (revenue) FULL OUTER JOIN `vouchers`/`postings` (costs) | The same pattern as `export_queries.PL_miesiecznie` |
| `v_headcount_monthly` | `hour_entries` | Counts distinct employees logging hours that month. Used to undercount by excluding Salg/Økonomi (billable-only tracking) — **fixed as a side effect of the "realistic hours model" feature**: all departments now log hours, so this tracks the true headcount minus E05 (the one permanent exception), once the backfill for that change has run |

All three: `GRANT SELECT ... TO analyst` (inherited by `powerbi_reader`).

**Two deliberate deviations from the prompt's SQL sketch** (not copied blindly):
1. `v_pl_monthly` computes `revenue` from `orders`/`order_lines`, **not** from `postings` (`account_number BETWEEN 3000 AND 3999`, as the sketch suggested) — these postings never exist in this database (verified: 0 rows), see the header of this document. Copying the sketch verbatim would give a view that always returns `revenue = NULL`.
2. `v_sales_flat.amount_including_vat_currency` is an alias, not a physical rename of `order_lines.amount_currency` — "Basket 1" (renaming the column to match the real Tripletex API) was only **proposed**, never explicitly accepted or carried out in the generators/tests. The view gives the correct name in BI right now without a risky change to the physical schema.

**`security_invoker = true`** on all three — without this, a view by default reads its source tables with the privileges of the *view's owner* (`postgres`, which bypasses RLS), not the role actually querying it. Today the policies are `USING (true)` so this doesn't change the visible data, but it prevents a view from silently bypassing RLS if someone ever adds an actually-filtering policy.

### `api_keys` (2026-09-04, REST API service infrastructure)

| Column | Type | Description |
|---|---|---|
| id | SERIAL (PK) | |
| key_hash | TEXT (UNIQUE) | `sha256(raw_key)` — the raw key never lands in the database, only on stdout once at generation time (`api/scripts/generate_api_key.py`) |
| owner_label | TEXT | Description/owner of the key (e.g. "demo-curl-test") |
| rate_limit_per_hour | INT | Requests/hour limit, default 100, configurable per key |
| revoked | BOOLEAN | Revokes a key without deleting the row (audit trail) |
| request_count_this_window / window_start | INT / TIMESTAMPTZ | The rate-limit counter, updated atomically in `api/auth.py` (`SELECT ... FOR UPDATE`) — an extension beyond the prompt's sketch (which only had `last_used_at`), so the limit survives a service restart without holding state in process memory |
| last_used_at | TIMESTAMPTZ | The key's last use |
| requester_label | TEXT | Self-service portal (Task 1, `api/routers/keys.py`) — exactly what the user typed into the form; deliberately duplicates `owner_label`, so self-service keys could one day be distinguished from manual ones without guessing from the label's content |
| self_service | BOOLEAN | `true` for keys generated via `POST /api/v1/keys/request`, `false`/`NULL` for manually issued keys (`api/scripts/generate_api_key.py`) |
| created_from_ip | TEXT | The requester's IP at generation time — the only identifying data collected (deliberately **no email address**), used solely for the 3 keys/IP/day limit |

RLS enabled, **with no policy for `analyst`/`demo_reader`/`powerbi_reader`** — deliberately invisible to read-only data consumers, only `api_key_manager` (policy `api_key_manager_access FOR ALL USING (true)`) and `postgres` (RLS bypass). Since the self-service portal, `api_key_manager` can also `INSERT` new keys (`POST /api/v1/keys/request`) — `api/scripts/generate_api_key.py` (manual issuance) still connects as the owner, independently. Not counted among the 20 domain tables tallied elsewhere in this document.

### `export_requests` (self-service portal, export on demand)

The rate-limit counter for `GET /api/v1/export/{format}` (1 export/5 min/IP) — a deliberately separate, minimal table (`id`, `ip`, `created_at`) rather than extending `api_keys`'s semantics, since export doesn't require an API key at all. Handled by the same `api_key_manager` role (`GRANT SELECT, INSERT`), RLS enabled, a policy analogous to `api_keys` (only `api_key_manager`/`postgres`).

## Known overall limitations

1. **No revenue postings** (accounts 3000/3100) — see the header of this document. Revenue lives exclusively in `orders`/`order_lines`.
2. **`bank_transactions` requires manual re-repair after every `TRUNCATE`** — `scripts/fix_outgoing_transactions.py` backfills historical OUTGOING rows, but must be re-run after every full data reset.
3. **Phase 1 metadata** (`customers.segment/onboarding_date/churn_date/price_multiplier`, `services`, `products.service_code`) previously existed **only in Python** (`roster.py`) — it's now also in Supabase, but historical queries/dashboards written before Phase 1 may have omitted it.
4. **`projects.start_date` = `customers.onboarding_date` since Phase 4** (before Phase 4 it was independent, a static 2026-01-01/03-01 — a limitation that has been FIXED, kept in the history as an example of an earlier design mistake).
5. **RLS enabled with no write policies of its own** — only `postgres` (RLS bypass) can write; the `analyst` role has pure read (SELECT) on **20/20 tables with active RLS** (see "Read-only access" below — until 2026-09-04, 6 reference tables had no RLS at all, fixed in that day's security audit). **Step 2 (2026-07) fixed a Phase 1 gap**: RLS policies alone weren't enough for reading — the base `GRANT SELECT` was missing, so `analyst` (and `powerbi_reader`, which inherits from it) would get "permission denied" on every query despite having correct policies.
6. **No staff turnover** (`employments.end_date` always NULL) and **low customer churn** (K09, K15 — both SMB) — the model is deliberately simple, not a full portfolio-dynamics simulation.
7. **The `services` table shows only `LEGACY_SERVICES`** (Phase 4) — `SCALE_SERVICES` (prices for customers onboarded from 2023-01-01) exists only in Python code, not in Supabase. See the `services` and `customers` sections above.
8. **Extra-consulting (S04 beyond K06) doesn't run in `run_daily.py`'s daily mode** — `should_generate_extra_consulting`/K06-style consulting only run in `generate_monthly_orders` (historical backfill), not in the daily production rhythm. See `SESSION_HANDOFF.md` (Phase 2).
9. **E17's salary (950,000 NOK/year)** was set under the pressure of Phase 4's payroll-budget calibration (top-down from the margin target) — **not from an analysis of real Norwegian salary levels**, left unchanged in Phase 6 (headcount, not the rate, was that correction's lever). A candidate for revision if someone further calibrates the model against real-world pay rates.
10. **Retry/reconnect exists for the backfill** (`run_backfill_daily()`, `terminate_stale_sessions()`) **but the process itself does not survive an actual computer shutdown/sleep, nor a hung (not fail-fast) network connection** — in that case the process hangs with no error logged (observed in Phase 6: `ps` showed the process alive, but with no CPU-time growth and no new database rows for >30 min) and has to be killed manually, then the backfill resumed from the last processed day (`SELECT MAX(date) FROM hour_entries`) — check whether a process is alive by **actual progress in the database**, not just whether the process still exists.
11. **Phase 6 — the GitHub Actions `daily.yml` (cron 3x/day on `main`) writes to the SAME production Supabase database** — during this phase's backfill, the cron fired using old (pre-Phase-6, 38-person) code and inserted tainted `hour_entries`/`bank_transactions` for the current day AFTER `TRUNCATE`, before the problem was noticed. The workflow was manually disabled in the GitHub UI for the duration of the backfill — **it must not be re-enabled until AFTER the Phase 6 commit is pushed to `main`**, otherwise it will fire with the old code again. Every future data reset must first pause this workflow.
12. **`TRUNCATE` deliberately skips reference tables** (`employees`/`employments`, `customers`, `suppliers` — the same pattern as Phase 6) **— a FIXED discovery**: `seed_reference_data()` with `ON CONFLICT DO NOTHING` adds new employees as `roster.EMPLOYEES` grows, but never removed old ones as it shrinks. Result: 21 orphaned records (E18-E38) survived in `employees`/`employments` from Phase 4, even though Phase 6 correctly reduced headcount to 17 in ALL transactional tables (`hour_entries`/`payslips` — verified, always clean). Only detected via a mismatch with the published BI report (headcount 38 instead of 17). Fixed with a targeted `DELETE` + `_prune_orphaned_employees()` in `repository.py` (called at the start of every `seed_reference_data()` — automatically removes orphaned records, safe by construction thanks to the lack of `ON DELETE CASCADE` on the `employee_id` FK, so real transactional data can never be silently deleted). **General takeaway**: any future change to the size of `roster.EMPLOYEES`/`CUSTOMERS`/`SUPPLIERS` carries the same risk unless an analogous pruning function also exists for those tables (today it only exists for `employees`).
