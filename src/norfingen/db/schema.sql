-- NorFinGen — Supabase Postgres schema.
--
-- All CREATE TABLE statements are idempotent (IF NOT EXISTS) — safe to run
-- repeatedly (ensure_schema() in repository.py runs this file on every
-- run_backfill.py / run_daily.py start).
--
-- Primary keys:
--   * Reference tables (departments, employees, customers, suppliers,
--     products, vat_types) use INTEGER PRIMARY KEY (NOT SERIAL) — the id
--     must match 1:1 the numeric_id()/TripletexRef(id=...) used throughout
--     the generator code (e.g. Employee E07 -> id=7). accounts uses
--     "number" (the GL account number, e.g. 6410) as PRIMARY KEY, because
--     that's how AccountRef in generators/voucher.py addresses accounts.
--   * Transactional tables (orders, order_lines, supplier_invoices,
--     salary_transactions, payslips, salary_specifications, vouchers,
--     postings) use SERIAL — the Pydantic id of these objects is always
--     None (assigned by Tripletex/the database, not by the generator).
--
-- Idempotent saves (ON CONFLICT DO NOTHING) require natural business keys —
-- hence the extra UNIQUE constraints on e.g. (customer_id, order_date),
-- invoice_number, (year, month), (date, description), etc. See repository.py.

-- ─────────────────────────────────────────── Layer 1 — dimensions / reference data

CREATE TABLE IF NOT EXISTS departments (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    number      TEXT,
    is_inactive BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS employees (
    id                              INTEGER PRIMARY KEY,
    first_name                      TEXT NOT NULL,
    last_name                       TEXT NOT NULL,
    employee_number                 TEXT,
    email                           TEXT,
    department_id                   INTEGER REFERENCES departments(id),
    bank_account_number              TEXT,
    national_identity_number        TEXT,
    date_of_birth                   DATE,
    allow_information_registration  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS employments (
    id                    SERIAL PRIMARY KEY,
    employee_id           INTEGER NOT NULL UNIQUE REFERENCES employees(id),
    start_date            DATE NOT NULL,
    end_date              DATE,
    employment_type       TEXT,
    remuneration_type     TEXT,
    weekly_working_hours  NUMERIC(5, 2),
    percentage            NUMERIC(5, 2),
    payroll_tax_zone      TEXT
);

CREATE TABLE IF NOT EXISTS customers (
    id                     INTEGER PRIMARY KEY,
    name                   TEXT NOT NULL,
    organization_number    TEXT,
    email                  TEXT,
    phone_number           TEXT,
    is_private_individual  BOOLEAN NOT NULL DEFAULT FALSE,
    address_line1          TEXT,
    postal_code            TEXT,
    city                   TEXT,
    country_id             INTEGER,
    currency_id            INTEGER,
    is_inactive            BOOLEAN NOT NULL DEFAULT FALSE,
    customer_number        TEXT,
    payment_terms_id       INTEGER,
    invoices_due_in        INTEGER DEFAULT 30,
    invoices_due_in_type   TEXT DEFAULT 'DAYS'
);

CREATE TABLE IF NOT EXISTS suppliers (
    id                     INTEGER PRIMARY KEY,
    name                   TEXT NOT NULL,
    organization_number    TEXT,
    email                  TEXT,
    phone_number           TEXT,
    is_private_individual  BOOLEAN NOT NULL DEFAULT FALSE,
    address_line1          TEXT,
    postal_code            TEXT,
    city                   TEXT,
    country_id             INTEGER,
    currency_id            INTEGER,
    is_inactive            BOOLEAN NOT NULL DEFAULT FALSE,
    supplier_number        TEXT,
    bank_account_number    TEXT,
    is_wholesaler          BOOLEAN NOT NULL DEFAULT FALSE,
    show_products          BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS vat_types (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    number      TEXT,
    percentage  NUMERIC(5, 2) NOT NULL,
    vat_code    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    number      INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT,
    vat_type_id INTEGER REFERENCES vat_types(id)
);

CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    number       TEXT,
    description  TEXT,
    sales_price  NUMERIC(14, 2),
    vat_type_id  INTEGER REFERENCES vat_types(id),
    currency_id  INTEGER,
    is_inactive  BOOLEAN NOT NULL DEFAULT FALSE
    -- service_code: column + FK to services(code) added below via ALTER,
    -- AFTER the services table is created (Phase 1) — not inline here, so
    -- the same migration behaves identically on a fresh DB and on
    -- already-existing production.
);

-- ─────────────────────────────────────────────── Layer 2 — source documents

CREATE TABLE IF NOT EXISTS orders (
    id                     SERIAL PRIMARY KEY,
    customer_id            INTEGER REFERENCES customers(id),
    order_date             DATE NOT NULL,
    delivery_date          DATE,
    invoice_date           DATE,
    invoices_due_in        INTEGER,
    invoices_due_in_type   TEXT,
    department_id          INTEGER REFERENCES departments(id),
    currency_id            INTEGER,
    is_prioritize_vat      BOOLEAN NOT NULL DEFAULT FALSE,
    comment                TEXT,
    our_contact_id         INTEGER,
    status                 TEXT DEFAULT 'PAID',
    UNIQUE (customer_id, order_date)
);

CREATE TABLE IF NOT EXISTS order_lines (
    id                                  SERIAL PRIMARY KEY,
    order_id                            INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id                          INTEGER REFERENCES products(id),
    count                               NUMERIC(10, 2),
    unit_price_excluding_vat_currency   NUMERIC(14, 2),
    vat_type_id                         INTEGER REFERENCES vat_types(id),
    discount                            NUMERIC(5, 4) DEFAULT 0,
    amount_excluding_vat_currency       NUMERIC(14, 2),
    amount_currency                     NUMERIC(14, 2),
    UNIQUE (order_id, product_id)
);

CREATE TABLE IF NOT EXISTS supplier_invoices (
    id                              SERIAL PRIMARY KEY,
    invoice_number                  TEXT NOT NULL UNIQUE,
    supplier_id                     INTEGER REFERENCES suppliers(id),
    invoice_date                    DATE NOT NULL,
    received_date                   DATE,
    payment_due_date                DATE,
    amount_currency                 NUMERIC(14, 2) NOT NULL,
    amount_excluding_vat_currency   NUMERIC(14, 2),
    vat_amount_currency             NUMERIC(14, 2),
    currency_id                     INTEGER,
    account_number                  INTEGER REFERENCES accounts(number),
    vat_type_id                     INTEGER REFERENCES vat_types(id),
    comment                         TEXT,
    status                          TEXT DEFAULT 'UNPAID'
);

CREATE TABLE IF NOT EXISTS salary_transactions (
    id      SERIAL PRIMARY KEY,
    date    DATE NOT NULL,
    year    INTEGER NOT NULL,
    month   INTEGER NOT NULL,
    status  TEXT DEFAULT 'OPEN',
    UNIQUE (year, month)
);

CREATE TABLE IF NOT EXISTS payslips (
    id              SERIAL PRIMARY KEY,
    transaction_id  INTEGER NOT NULL REFERENCES salary_transactions(id) ON DELETE CASCADE,
    employee_id     INTEGER REFERENCES employees(id),
    date            DATE,
    amount          NUMERIC(14, 2),
    UNIQUE (transaction_id, employee_id)
);

CREATE TABLE IF NOT EXISTS salary_specifications (
    id            SERIAL PRIMARY KEY,
    payslip_id    INTEGER NOT NULL REFERENCES payslips(id) ON DELETE CASCADE,
    wage_type_id  INTEGER,
    description   TEXT,
    amount        NUMERIC(14, 2),
    UNIQUE (payslip_id, wage_type_id)
);

-- ─────────────────────────────────────────────────── Layer 3 — ledger

CREATE TABLE IF NOT EXISTS vouchers (
    id            SERIAL PRIMARY KEY,
    date          DATE NOT NULL,
    description   TEXT,
    voucher_type  TEXT,
    UNIQUE (date, description)
);

CREATE TABLE IF NOT EXISTS postings (
    id              SERIAL PRIMARY KEY,
    voucher_id      INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
    date            DATE NOT NULL,
    description     TEXT,
    account_number  INTEGER REFERENCES accounts(number),
    amount          NUMERIC(14, 2) NOT NULL,
    currency        TEXT DEFAULT 'NOK',
    vat_type_id     INTEGER REFERENCES vat_types(id),
    vat_amount      NUMERIC(14, 2),
    customer_id     INTEGER REFERENCES customers(id),
    supplier_id     INTEGER REFERENCES suppliers(id),
    employee_id     INTEGER REFERENCES employees(id),
    department_id   INTEGER REFERENCES departments(id),
    UNIQUE (voucher_id, account_number, amount)
);

-- ─────────────────────────────────────────────────── Tier 4 — bank / projects / timesheet

CREATE TABLE IF NOT EXISTS projects (
    id          SERIAL PRIMARY KEY,
    number      VARCHAR(20) UNIQUE NOT NULL,
    name        VARCHAR(200) NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    start_date  DATE NOT NULL,
    end_date    DATE,
    status      VARCHAR(20) DEFAULT 'ACTIVE',
    description TEXT
);

CREATE TABLE IF NOT EXISTS bank_transactions (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL,
    amount              NUMERIC(12,2) NOT NULL,
    transaction_type    VARCHAR(20) NOT NULL,
    description         TEXT,
    customer_id         INTEGER REFERENCES customers(id),
    supplier_id         INTEGER REFERENCES suppliers(id),
    order_id            INTEGER REFERENCES orders(id),
    supplier_invoice_id INTEGER REFERENCES supplier_invoices(id),
    account_from        INTEGER NOT NULL,
    account_to          INTEGER NOT NULL,
    voucher_id          INTEGER REFERENCES vouchers(id),
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, order_id, transaction_type),
    UNIQUE(date, supplier_invoice_id, transaction_type)
);

CREATE TABLE IF NOT EXISTS hour_entries (
    id            SERIAL PRIMARY KEY,
    date          DATE NOT NULL,
    employee_id   INTEGER REFERENCES employees(id),
    project_id    INTEGER REFERENCES projects(id),
    activity_type VARCHAR(20) NOT NULL,
    hours         NUMERIC(4,1) NOT NULL,
    description   TEXT,
    created_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, employee_id, project_id, activity_type)
);

-- Fix for the 2026-09-04 incident (see docs/SESSION_HANDOFF.md): the UNIQUE
-- above does NOT protect INTERNAL/SICK entries (project_id is always NULL,
-- see the column description above) — Postgres treats NULL <> NULL, so two
-- identical rows with project_id=NULL don't violate this UNIQUE, and
-- `ON CONFLICT (date, employee_id, project_id, activity_type) DO NOTHING`
-- (repository.py, _save_hour_entry) never fires for them. A partial unique
-- index for project_id IS NULL only closes this gap.
CREATE UNIQUE INDEX IF NOT EXISTS hour_entries_unique_null_project
    ON hour_entries (date, employee_id, activity_type)
    WHERE project_id IS NULL;

-- ───────────────────────────────────────── Accounting phase 4 — COGS liabilities
--
-- The monthly COGS pass-through cost (4291 Microsoft/Azure resale, 4292 RMM/EDR tools) is an accrual voucher
-- Dr 4291|4292 / Cr 2400, with no SupplierInvoice behind it - so it could never be paid and 88 mln NOK sat on 2400
-- (gl_checks T8). One row per accrual makes it a payable: a due date, an amount, a status. The payment is an ordinary
-- supplier payment (Dr 2400 / Cr 1910) linked through bank_transactions.cogs_payable_id, and it flips the status.
CREATE TABLE IF NOT EXISTS cogs_payables (
    id                SERIAL PRIMARY KEY,
    voucher_id        INTEGER NOT NULL UNIQUE REFERENCES vouchers(id) ON DELETE CASCADE,
    supplier_id       INTEGER REFERENCES suppliers(id),
    account_number    INTEGER NOT NULL REFERENCES accounts(number),
    accrual_date      DATE NOT NULL,
    payment_due_date  DATE NOT NULL,
    description       TEXT NOT NULL,
    amount_excluding_vat_currency NUMERIC(14, 2) NOT NULL DEFAULT 0,
    vat_amount_currency           NUMERIC(14, 2) NOT NULL DEFAULT 0,
    amount_currency   NUMERIC(14, 2) NOT NULL,  -- GROSS (net + VAT) since the audit of 2026-11-16, phase 2
    status            TEXT NOT NULL DEFAULT 'UNPAID'
);
-- A table created before phase 2 (production) gets the two new columns; a history regenerated afterwards fills them.
ALTER TABLE cogs_payables ADD COLUMN IF NOT EXISTS amount_excluding_vat_currency NUMERIC(14, 2) NOT NULL DEFAULT 0;
ALTER TABLE cogs_payables ADD COLUMN IF NOT EXISTS vat_amount_currency NUMERIC(14, 2) NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_cogs_payables_due ON cogs_payables(payment_due_date) WHERE status = 'UNPAID';
-- (RLS and the analyst policy for this table sit with the other policies below: the analyst role is created there.)

-- Audit 2026-11-16, phase 5: the write-off voucher of an uncollectible order (phase 4). The invoice status in the exports is DERIVED
-- from the real state (payment in the bank, write-off booked, due date passed); orders.status stays the modelled behaviour.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS write_off_voucher_id INTEGER REFERENCES vouchers(id) ON DELETE SET NULL;

ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS cogs_payable_id INTEGER REFERENCES cogs_payables(id);
CREATE UNIQUE INDEX IF NOT EXISTS bank_transactions_unique_cogs_payment
    ON bank_transactions (date, cogs_payable_id, transaction_type)
    WHERE cogs_payable_id IS NOT NULL;

-- ───────────────────────────────────────── Phase 5 — VAT settlement (mva-oppgjør)
--
-- Six two-month terms a year. On the last day of a term the balances of 2700 / 2710 are moved to 2740 (a MANUAL
-- voucher); the difference is paid / refunded on the term's due date. One row per settled term: the totals, the
-- balance (output - input: > 0 to pay, < 0 refund), the planned payment date and a status that the bank transaction
-- flips (bank_transactions.vat_settlement_id).
CREATE TABLE IF NOT EXISTS vat_settlements (
    id            SERIAL PRIMARY KEY,
    voucher_id    INTEGER NOT NULL UNIQUE REFERENCES vouchers(id) ON DELETE CASCADE,
    period_year   INTEGER NOT NULL,
    term          INTEGER NOT NULL CHECK (term BETWEEN 1 AND 6),
    period_start  DATE NOT NULL,
    period_end    DATE NOT NULL,
    payment_date  DATE NOT NULL,
    output_vat    NUMERIC(14, 2) NOT NULL,
    input_vat     NUMERIC(14, 2) NOT NULL,
    balance       NUMERIC(14, 2) NOT NULL,
    status        TEXT NOT NULL DEFAULT 'UNPAID',
    UNIQUE (period_year, term)
);
CREATE INDEX IF NOT EXISTS idx_vat_settlements_payment ON vat_settlements(payment_date) WHERE status = 'UNPAID';

ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS vat_settlement_id INTEGER REFERENCES vat_settlements(id);
CREATE UNIQUE INDEX IF NOT EXISTS bank_transactions_unique_vat_payment
    ON bank_transactions (date, vat_settlement_id, transaction_type)
    WHERE vat_settlement_id IS NOT NULL;

-- ───────────────────────────────────────── Phase 0.5a — daily pipeline watermark
--
-- run_daily used to match events on the EXACT current date, so any day the
-- cron did not run (every weekend: cron is Mon-Fri) lost its events for good.
-- The pipeline now processes every calendar day in (watermark, today] and
-- advances the watermark only after a day has been fully committed. Internal
-- bookkeeping: RLS on, no policy, so the read-only roles see nothing.
CREATE TABLE IF NOT EXISTS generation_state (
    key         TEXT PRIMARY KEY,
    value_date  DATE NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE generation_state ENABLE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────── Phase 1 — service catalog, metadata

CREATE TABLE IF NOT EXISTS services (
    code                    VARCHAR(10) PRIMARY KEY,
    name                    VARCHAR(200) NOT NULL,
    description             TEXT,
    billing_model           VARCHAR(20) NOT NULL,
    availability            VARCHAR(30) NOT NULL,
    base_price_enterprise   NUMERIC(12,2),
    base_price_mid          NUMERIC(12,2),
    base_price_smb          NUMERIC(12,2)
);

-- Columns added after the tables already existed in production —
-- CREATE TABLE IF NOT EXISTS won't add them to already-existing tables,
-- hence separate (idempotent) ALTER statements. products.service_code MUST
-- come after CREATE TABLE services (FK) — hence this whole section is
-- placed at the end of the file, after all the CREATE TABLE statements.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'PAID';
ALTER TABLE products ADD COLUMN IF NOT EXISTS service_code VARCHAR(10) REFERENCES services(code);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS onboarding_date DATE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS churn_date DATE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS segment VARCHAR(20);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS price_multiplier NUMERIC(5,4);
-- NACE/SN2007 addendum — the customer's industry code (roster.CUSTOMER_NACE), purely descriptive.
ALTER TABLE customers ADD COLUMN IF NOT EXISTS nace_code VARCHAR(10);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS nace_name VARCHAR(200);

-- Step 2 — fix: payroll (SalaryTransaction) never generated a matching
-- OUTGOING bank transaction (a gap since Tier 2, not a Phase 6 regression —
-- see SESSION_HANDOFF.md). An explicit FK (not matching by ILIKE on the
-- description text), analogous to order_id/supplier_invoice_id.
ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS salary_transaction_id INTEGER REFERENCES salary_transactions(id);

-- ADD CONSTRAINT doesn't support IF NOT EXISTS in Postgres — a DO block,
-- the same pattern as CREATE POLICY (DROP IF EXISTS) further down in this
-- file. The UNIQUE is needed so ON CONFLICT DO NOTHING in
-- _save_bank_transaction() is idempotent for payroll payments (re-running
-- the backfill for the same month doesn't create a duplicate).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'bank_transactions_salary_unique'
    ) THEN
        ALTER TABLE bank_transactions
            ADD CONSTRAINT bank_transactions_salary_unique UNIQUE (date, salary_transaction_id, transaction_type);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_lines_order ON order_lines(order_id);
CREATE INDEX IF NOT EXISTS idx_supplier_invoices_supplier ON supplier_invoices(supplier_id);
CREATE INDEX IF NOT EXISTS idx_payslips_transaction ON payslips(transaction_id);
CREATE INDEX IF NOT EXISTS idx_salary_specifications_payslip ON salary_specifications(payslip_id);
CREATE INDEX IF NOT EXISTS idx_postings_voucher ON postings(voucher_id);
CREATE INDEX IF NOT EXISTS idx_postings_account ON postings(account_number);
CREATE INDEX IF NOT EXISTS idx_vouchers_date ON vouchers(date);
CREATE INDEX IF NOT EXISTS idx_projects_customer ON projects(customer_id);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_customer ON bank_transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_supplier ON bank_transactions(supplier_id);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_date ON bank_transactions(date);
CREATE INDEX IF NOT EXISTS idx_hour_entries_employee ON hour_entries(employee_id);
CREATE INDEX IF NOT EXISTS idx_hour_entries_project ON hour_entries(project_id);

-- ─────────────────────────────────────────────────── Phase 1 — Row Level Security
--
-- Without defined POLICYs, tables become closed by default to roles without
-- BYPASSRLS (e.g. anon/authenticated in Supabase) — a deliberate "default
-- deny" before adding the target policies in the next step. Does NOT affect
-- run_backfill.py/run_daily.py/export_excel.py — they connect as "postgres"
-- (the table owner, rolbypassrls=true), so RLS is transparent to them.
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE salary_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE payslips ENABLE ROW LEVEL SECURITY;
ALTER TABLE vouchers ENABLE ROW LEVEL SECURITY;
ALTER TABLE postings ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE hour_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE services ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

-- The analyst role (read-only) — CREATE ROLE is not natively idempotent
-- (a "role already exists" error on re-run), and ensure_schema() runs this
-- file on every run_backfill.py/run_daily() start — hence a conditional
-- block instead of a bare CREATE ROLE.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst NOLOGIN;
    END IF;
END
$$;

-- CREATE POLICY is also not idempotent (no IF NOT EXISTS in Postgres) —
-- DROP POLICY IF EXISTS + CREATE POLICY instead, consistent with the rest
-- of this file.
DROP POLICY IF EXISTS analyst_read_only ON orders;
CREATE POLICY analyst_read_only ON orders FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON order_lines;
CREATE POLICY analyst_read_only ON order_lines FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON supplier_invoices;
CREATE POLICY analyst_read_only ON supplier_invoices FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON salary_transactions;
CREATE POLICY analyst_read_only ON salary_transactions FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON payslips;
CREATE POLICY analyst_read_only ON payslips FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON vouchers;
CREATE POLICY analyst_read_only ON vouchers FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON postings;
CREATE POLICY analyst_read_only ON postings FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON bank_transactions;
CREATE POLICY analyst_read_only ON bank_transactions FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON hour_entries;
CREATE POLICY analyst_read_only ON hour_entries FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON customers;
CREATE POLICY analyst_read_only ON customers FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON suppliers;
CREATE POLICY analyst_read_only ON suppliers FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON employees;
CREATE POLICY analyst_read_only ON employees FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON services;
CREATE POLICY analyst_read_only ON services FOR SELECT TO analyst USING (true);
DROP POLICY IF EXISTS analyst_read_only ON projects;
CREATE POLICY analyst_read_only ON projects FOR SELECT TO analyst USING (true);
ALTER TABLE cogs_payables ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS analyst_read_only ON cogs_payables;
CREATE POLICY analyst_read_only ON cogs_payables FOR SELECT TO analyst USING (true);
ALTER TABLE vat_settlements ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS analyst_read_only ON vat_settlements;
CREATE POLICY analyst_read_only ON vat_settlements FOR SELECT TO analyst USING (true);

-- ─────────────────────────────────────────────────── Step 2 — read-only access (Power BI)
--
-- The RLS policies above FILTER rows, but do NOT grant the underlying read
-- privilege — without GRANT SELECT, Postgres rejects the query BEFORE RLS
-- even runs ("permission denied for table"). Phase 1 created the `analyst`
-- role and the full set of policies, but never granted it anything, so the
-- role was unusable for actually reading data (this wasn't visible, because
-- nobody logged in as it — it's NOLOGIN). Fixed here.
--
-- GRANT ... ON ALL TABLES (not a comma-separated table list) — also covers
-- reference tables without RLS (accounts, departments, products, vat_types,
-- employments, salary_specifications), needed for P&L analysis in BI (e.g.
-- account names for cost breakdowns, departments for payroll). ALTER
-- DEFAULT PRIVILEGES ensures future tables are also immediately readable
-- for the analyst — without this, every new table would need a manual GRANT.
GRANT USAGE ON SCHEMA public TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analyst;

-- ─────────────────────────────────────────────────── Step 2, Task 2 — BI views
--
-- Two deliberate deviations from the prompt's sketch (not copied blindly):
--
-- 1. v_pl_monthly does NOT compute revenue from postings (account_number
--    3000-3999) — these postings NEVER exist in this database (verified:
--    0 rows). The reason has been documented at the very top of
--    DATA_DICTIONARY.md since the start of the project: Order.invoiceDate
--    in real Tripletex automatically creates a revenue Voucher — NorFinGen
--    doesn't call the real API, so that Voucher never gets created
--    locally. Revenue is ALWAYS computed from orders/order_lines, never
--    from postings (the same pattern as export_queries.PL_miesiecznie — a
--    revenue CTE from order_lines FULL OUTER JOIN a cost CTE from
--    postings). Copying the sketch verbatim would give a view that always
--    returns revenue=NULL.
--
--    UPDATE (accounting phase 3): sales invoices are now booked in the ledger
--    too (OUTGOING_INVOICE: Dr 1500 / Cr 3000 / Cr 2700), so 3000 postings DO
--    exist now and equal the revenue in order_lines to the grosz (gl_checks
--    T4). The view still reads revenue from orders/order_lines on purpose: its
--    cost CTE sums only 4000-7999, so there is no double count, and the two
--    sources agreeing is a test, not something to paper over.
--
-- 2. v_sales_flat.amount_including_vat_currency is an ALIAS of the
--    physical column order_lines.amount_currency, NOT a rename of that
--    column — "Basket 1" (renaming order_lines.amount_currency ->
--    amount_including_vat_currency, to match the real OrderLine field name
--    in the Tripletex API) was only PROPOSED in a past session, never
--    explicitly accepted by the user nor carried out in the
--    code/generators/tests. This view gives the correct,
--    Tripletex-matching name in BI right now, without a risky change to
--    the underlying physical schema/generators. If Basket 1 is ever
--    carried out, this alias becomes redundant (the source column will
--    already be named that way) — until then it stays as a bridge.
--
-- security_invoker=true (PG15+, Supabase = PG17) on all three views —
-- without this, a view by default reads its source tables with the
-- privileges of the view's OWNER (postgres, which bypasses RLS), not the
-- role actually querying it (analyst/powerbi_reader) — a known "RLS bypass
-- via view" footgun in Postgres. Today the policies are USING (true), so
-- the visible data is identical either way, but without this flag any
-- future, actually-filtering RLS policy would be silently bypassed when
-- queried through the view instead of the table directly.
CREATE OR REPLACE VIEW v_sales_flat WITH (security_invoker = true) AS
SELECT o.id AS order_id, o.customer_id, o.order_date, o.invoice_date,
       c.name AS customer_name, c.customer_number, c.segment,
       c.city, c.postal_code, c.nace_code, c.nace_name,
       ol.count, ol.unit_price_excluding_vat_currency,
       ol.amount_excluding_vat_currency,
       ol.amount_currency AS amount_including_vat_currency
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN order_lines ol ON ol.order_id = o.id;

CREATE OR REPLACE VIEW v_pl_monthly WITH (security_invoker = true) AS
WITH revenue_cte AS (
    SELECT DATE_TRUNC('month', o.order_date) AS month_start,
           SUM(ol.amount_excluding_vat_currency) AS revenue
    FROM orders o JOIN order_lines ol ON ol.order_id = o.id
    GROUP BY 1
),
cost_cte AS (
    SELECT DATE_TRUNC('month', v.date) AS month_start,
           SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 5000 AND 5999) AS labor_cost,
           SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 6000 AND 7999) AS operating_cost,
           SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 4000 AND 4999) AS cogs,
           -- Round 4, step 2: depreciation is INSIDE operating_cost (6000-7999), so operating_result is EBIT; these four are
           -- memo / below-the-line items, appended after is_partial (a view may only grow at the end).
           SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 6000 AND 6099) AS depreciation,
           SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 8000 AND 8299) AS financial_cost,
           SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 8300 AND 8399) AS tax_cost
    FROM vouchers v JOIN postings p ON p.voucher_id = v.id
    GROUP BY 1
)
SELECT TO_CHAR(COALESCE(r.month_start, c.month_start), 'YYYY-MM') AS month,
       ROUND(COALESCE(r.revenue, 0), 2)         AS revenue,
       ROUND(COALESCE(c.labor_cost, 0), 2)      AS labor_cost,
       ROUND(COALESCE(c.operating_cost, 0), 2)  AS operating_cost,
       ROUND(COALESCE(c.cogs, 0), 2)            AS cogs,
       ROUND(COALESCE(r.revenue, 0)
           - COALESCE(c.labor_cost, 0)
           - COALESCE(c.operating_cost, 0)
           - COALESCE(c.cogs, 0), 2)            AS operating_result,
       -- Audit 2026-11-16, decision #1: the month that is not over yet (its last day is after the newest generated
       -- date) is flagged, NOT pro-rated. Payroll and COGS are booked at month end, as in Tripletex, so the open
       -- month shows revenue without its costs. Every trailing/YTD KPI must filter NOT is_partial.
       ((COALESCE(r.month_start, c.month_start)::date + INTERVAL '1 month' - INTERVAL '1 day')::date
        > GREATEST((SELECT MAX(date) FROM vouchers), (SELECT MAX(order_date) FROM orders))) AS is_partial,
       -- depreciation: the part of operating_cost that is 60xx;  ebitda = operating_result + depreciation
       ROUND(COALESCE(c.depreciation, 0), 2)    AS depreciation,
       ROUND(COALESCE(r.revenue, 0) - COALESCE(c.labor_cost, 0) - COALESCE(c.operating_cost, 0) - COALESCE(c.cogs, 0)
             + COALESCE(c.depreciation, 0), 2)  AS ebitda,
       -- financial_result: interest etc. (8000-8299), income positive, cost negative; tax: income tax cost (83xx), positive;
       -- net_result = operating_result + financial_result - tax
       ROUND(-COALESCE(c.financial_cost, 0), 2) AS financial_result,
       ROUND(COALESCE(c.tax_cost, 0), 2)        AS tax,
       ROUND(COALESCE(r.revenue, 0) - COALESCE(c.labor_cost, 0) - COALESCE(c.operating_cost, 0) - COALESCE(c.cogs, 0)
             - COALESCE(c.financial_cost, 0) - COALESCE(c.tax_cost, 0), 2) AS net_result
FROM revenue_cte r FULL OUTER JOIN cost_cte c ON r.month_start = c.month_start
ORDER BY 1;

-- v_balance_monthly: the balance sheet at the END of every month (round 4, step 2), cumulative since the first voucher.
--   assets      = every 1xxx account (debit balance): fixed assets net of depreciation (1200 + 1209), receivables (1500), cash
--                 (19xx), anything else
--   liabilities = 21xx-29xx (credit balance): long-term debt (22xx: the owner loan), trade payables (24xx), income tax payable
--                 (25xx), VAT net (2700 + 2710 + 2740), payroll and pension liabilities (26xx, 2770-2799, 29xx), the rest
--   equity      = share capital (20xx) + retained earnings (the results of the EARLIER calendar years, nothing is closed in the
--                 ledger) + the result of the current year to the month end
--   balance_check = assets - liabilities - equity: ZERO in every month, because every voucher balances (gl_checks T24).
CREATE OR REPLACE VIEW v_balance_monthly WITH (security_invoker = true) AS
WITH bounds AS (
    SELECT DATE_TRUNC('month', MIN(date))::date AS first_month, DATE_TRUNC('month', MAX(date))::date AS last_month FROM vouchers
), months AS (
    SELECT GENERATE_SERIES(first_month, last_month, INTERVAL '1 month')::date AS month_start FROM bounds
), base AS (
    SELECT mo.month_start,
           SUM(p.amount) FILTER (WHERE p.account_number IN (1200, 1209)) AS fixed_assets_net,
           SUM(p.amount) FILTER (WHERE p.account_number = 1500) AS receivables,
           SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 1900 AND 1999) AS cash,
           SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 1000 AND 1999) AS total_assets,
           -SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 2200 AND 2299) AS long_term_debt,
           -SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 2400 AND 2499) AS trade_payables,
           -SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 2500 AND 2599) AS tax_payable,
           -SUM(p.amount) FILTER (WHERE p.account_number IN (2700, 2710, 2740)) AS vat_net,
           -SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 2600 AND 2699
                                     OR p.account_number IN (2770, 2780, 2790) OR p.account_number BETWEEN 2900 AND 2999) AS payroll_and_pension,
           -SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 2100 AND 2999) AS total_liabilities,
           -SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 2000 AND 2099) AS share_capital,
           -SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 3000 AND 8999 AND v.date < DATE_TRUNC('year', mo.month_start)) AS retained_earnings,
           -SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 3000 AND 8999 AND v.date >= DATE_TRUNC('year', mo.month_start)) AS result_ytd
    FROM months mo
    JOIN vouchers v ON v.date < (mo.month_start + INTERVAL '1 month')
    JOIN postings p ON p.voucher_id = v.id
    GROUP BY mo.month_start
)
SELECT TO_CHAR(month_start, 'YYYY-MM') AS month,
       ROUND(COALESCE(fixed_assets_net, 0), 2) AS fixed_assets_net,
       ROUND(COALESCE(receivables, 0), 2) AS receivables,
       ROUND(COALESCE(cash, 0), 2) AS cash,
       ROUND(COALESCE(total_assets, 0) - COALESCE(fixed_assets_net, 0) - COALESCE(receivables, 0) - COALESCE(cash, 0), 2) AS other_assets,
       ROUND(COALESCE(total_assets, 0), 2) AS total_assets,
       ROUND(COALESCE(long_term_debt, 0), 2) AS long_term_debt,
       ROUND(COALESCE(trade_payables, 0), 2) AS trade_payables,
       ROUND(COALESCE(tax_payable, 0), 2) AS tax_payable,
       ROUND(COALESCE(vat_net, 0), 2) AS vat_net,
       ROUND(COALESCE(payroll_and_pension, 0), 2) AS payroll_and_pension,
       ROUND(COALESCE(total_liabilities, 0) - COALESCE(long_term_debt, 0) - COALESCE(trade_payables, 0) - COALESCE(tax_payable, 0)
             - COALESCE(vat_net, 0) - COALESCE(payroll_and_pension, 0), 2) AS other_liabilities,
       ROUND(COALESCE(total_liabilities, 0), 2) AS total_liabilities,
       ROUND(COALESCE(share_capital, 0), 2) AS share_capital,
       ROUND(COALESCE(retained_earnings, 0), 2) AS retained_earnings,
       ROUND(COALESCE(result_ytd, 0), 2) AS result_ytd,
       ROUND(COALESCE(share_capital, 0) + COALESCE(retained_earnings, 0) + COALESCE(result_ytd, 0), 2) AS total_equity,
       ROUND(COALESCE(total_assets, 0) - COALESCE(total_liabilities, 0)
             - COALESCE(share_capital, 0) - COALESCE(retained_earnings, 0) - COALESCE(result_ytd, 0), 2) AS balance_check,
       -- the month that is not over yet (same convention as v_pl_monthly.is_partial): payroll and COGS are booked at month end, so its
       -- equity and cash are not final
       ((month_start + INTERVAL '1 month' - INTERVAL '1 day')::date
        > GREATEST((SELECT MAX(date) FROM vouchers), (SELECT MAX(order_date) FROM orders))) AS is_partial
FROM base
ORDER BY month_start;

-- v_invoice_status: ONE row per sales invoice (order), the single source of truth for "what happened to this invoice"
-- (round 2, review 2026-11-17, point 1). The status is DERIVED from the ledger and the bank, NEVER copied from orders.status:
-- orders.status is the generator's internal intent (the customer's modelled behaviour: PAID / OVERDUE / WRITTEN_OFF) and
-- says WRITTEN_OFF from the day the order is created, months before the write-off voucher exists (120 days after the due
-- date). Read the status from here; Faktury_sprzedazy (Excel + API export) uses this view too.
--   invoice_status  WRITTEN_OFF  the write-off voucher is booked (orders.write_off_voucher_id; Dr 7830 + Dr 2700 / Cr 1500)
--                   PAID         a customer payment is booked in the bank
--                   OVERDUE      unpaid and the due date (moved to a working day) has passed
--                   OPEN         unpaid and not yet due
--   write_off_pending / write_off_planned_date: the generator already decided this invoice is bad debt, but the voucher is
--                   not booked yet - the invoice is still OVERDUE until that day, never WRITTEN_OFF without a voucher.
-- "Today" is the newest generated date, not the clock.
CREATE OR REPLACE VIEW v_invoice_status WITH (security_invoker = true) AS
SELECT o.id AS order_id,
       s.st AS invoice_status,
       (s.st = 'OVERDUE') AS is_overdue,
       (o.invoice_date + o.invoices_due_in) AS payment_due_date,
       b.date AS paid_date,
       COALESCE(b.date > (o.invoice_date + o.invoices_due_in) + 7, FALSE) AS paid_late,
       o.write_off_voucher_id,
       (o.status = 'WRITTEN_OFF' AND o.write_off_voucher_id IS NULL) AS write_off_pending,
       CASE WHEN o.status = 'WRITTEN_OFF' AND o.write_off_voucher_id IS NULL
            THEN (o.invoice_date + o.invoices_due_in + 120
                  + CASE EXTRACT(ISODOW FROM o.invoice_date + o.invoices_due_in + 120) WHEN 6 THEN 2 WHEN 7 THEN 1 ELSE 0 END)
       END AS write_off_planned_date
FROM orders o
LEFT JOIN bank_transactions b ON b.order_id = o.id AND b.transaction_type = 'INCOMING'
CROSS JOIN LATERAL (SELECT CASE WHEN o.write_off_voucher_id IS NOT NULL THEN 'WRITTEN_OFF'
          WHEN b.date IS NOT NULL THEN 'PAID'
          WHEN (o.invoice_date + o.invoices_due_in
                + CASE EXTRACT(ISODOW FROM o.invoice_date + o.invoices_due_in) WHEN 6 THEN 2 WHEN 7 THEN 1 ELSE 0 END)
               < GREATEST((SELECT MAX(date) FROM vouchers), (SELECT MAX(order_date) FROM orders)) THEN 'OVERDUE'
          ELSE 'OPEN' END AS st) s;

-- v_headcount_monthly counts DISTINCT employee_id in hour_entries for the
-- month. Historically this UNDERESTIMATED the company's true headcount,
-- because only billable employees (Leveranse/Teknologi) ever had any
-- hour_entries at all. As of the "realistic hours model" feature
-- (hours_generator.py/leave_events.py/vacation.py), ALL departments log
-- hours (Salg/Okonomi included) — only E05 (the one deliberate, permanent
-- exception) is still excluded — so this view now tracks the true headcount
-- minus that one person, once the backfill for the new code has run. Still
-- named "active_employees" (hour-active), not "headcount" in the strict HR
-- sense; if an exact HR headcount including E05 is ever needed, the correct
-- source is employments.start_date (like roster.active_employees() in
-- Python), not hour_entries.
CREATE OR REPLACE VIEW v_headcount_monthly WITH (security_invoker = true) AS
SELECT TO_CHAR(date, 'YYYY-MM') AS month, COUNT(DISTINCT employee_id) AS active_employees
FROM hour_entries GROUP BY 1 ORDER BY 1;

GRANT SELECT ON v_sales_flat, v_pl_monthly, v_invoice_status, v_balance_monthly, v_headcount_monthly TO analyst;
