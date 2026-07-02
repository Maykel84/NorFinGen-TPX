-- NorFinGen — schemat Supabase Postgres.
--
-- Wszystkie CREATE TABLE są idempotentne (IF NOT EXISTS) — bezpieczne do
-- wielokrotnego wykonania (ensure_schema() w repository.py wywołuje ten plik
-- przy każdym starcie run_backfill.py / run_daily.py).
--
-- Klucze główne:
--   * Tabele referencyjne (departments, employees, customers, suppliers,
--     products, vat_types) używają INTEGER PRIMARY KEY (NIE SERIAL) — id musi
--     się zgadzać 1:1 z numeric_id()/TripletexRef(id=...) używanym w całym
--     kodzie generatorów (np. Employee E07 -> id=7). accounts używa "number"
--     (numer konta GL, np. 6410) jako PRIMARY KEY, bo tak adresuje konta
--     AccountRef w generators/voucher.py.
--   * Tabele transakcyjne (orders, order_lines, supplier_invoices,
--     salary_transactions, payslips, salary_specifications, vouchers,
--     postings) używają SERIAL — Pydantic-owe id tych obiektów jest zawsze
--     None (nadawane przez Tripletex/bazę, nie przez generator).
--
-- Idempotentność zapisu (ON CONFLICT DO NOTHING) wymaga naturalnych kluczy
-- biznesowych — stąd dodatkowe UNIQUE na np. (customer_id, order_date),
-- invoice_number, (year, month), (date, description) itd. Patrz repository.py.

-- ─────────────────────────────────────────── Warstwa 1 — wymiary / referencje

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
);

-- ─────────────────────────────────────────────── Warstwa 2 — dokumenty źródłowe

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

-- ─────────────────────────────────────────────────── Warstwa 3 — ledger

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

-- ─────────────────────────────────────────────────── Etap 4 — bank / projekty / timesheet

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
