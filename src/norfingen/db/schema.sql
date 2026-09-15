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
           SUM(p.amount) FILTER (WHERE p.account_number BETWEEN 4000 AND 4999) AS cogs
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
           - COALESCE(c.cogs, 0), 2)            AS operating_result
FROM revenue_cte r FULL OUTER JOIN cost_cte c ON r.month_start = c.month_start
ORDER BY 1;

-- v_headcount_monthly counts ONLY billable employees who actually log
-- hour_entries (Leveranse/Teknologi, excluding E05 — see hours_generator.py)
-- — Salg/Økonomi (5 of 17 FTEs in Phase 6) never have hour entries, so this
-- view UNDERESTIMATES the company's true headcount. Left as per the
-- prompt's sketch (correct SQL, matching column names) — this is a
-- deliberate tradeoff named "active_employees" (hour-active), not
-- "headcount" in the HR sense; if a true HR headcount is needed, the
-- correct source is employments.start_date (like roster.active_employees()
-- in Python), not hour_entries.
CREATE OR REPLACE VIEW v_headcount_monthly WITH (security_invoker = true) AS
SELECT TO_CHAR(date, 'YYYY-MM') AS month, COUNT(DISTINCT employee_id) AS active_employees
FROM hour_entries GROUP BY 1 ORDER BY 1;

GRANT SELECT ON v_sales_flat, v_pl_monthly, v_headcount_monthly TO analyst;
