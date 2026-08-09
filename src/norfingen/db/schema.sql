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
    -- service_code: kolumna + FK do services(code) dodane niżej przez ALTER,
    -- PO utworzeniu tabeli services (Faza 1) — nie tutaj inline, żeby ta sama
    -- migracja działała identycznie na fresh DB i na już istniejącej produkcji.
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

-- ─────────────────────────────────────────────────── Faza 1 — katalog usług, metadane

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

-- Kolumny dodane po utworzeniu tabel w produkcji — CREATE TABLE IF NOT EXISTS
-- ich nie doda do już istniejących tabel, stąd osobne ALTER (idempotentne).
-- products.service_code MUSI iść po CREATE TABLE services (FK) — stąd cała
-- ta sekcja umieszczona na końcu pliku, po wszystkich CREATE TABLE.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'PAID';
ALTER TABLE products ADD COLUMN IF NOT EXISTS service_code VARCHAR(10) REFERENCES services(code);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS onboarding_date DATE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS churn_date DATE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS segment VARCHAR(20);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS price_multiplier NUMERIC(5,4);
-- Dodatek NACE/SN2007 — kod branżowy klienta (roster.CUSTOMER_NACE), czysto opisowy.
ALTER TABLE customers ADD COLUMN IF NOT EXISTS nace_code VARCHAR(10);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS nace_name VARCHAR(200);

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

-- ─────────────────────────────────────────────────── Faza 1 — Row Level Security
--
-- Bez zdefiniowanych POLICY tabele stają się domyślnie zamknięte dla ról bez
-- BYPASSRLS (np. anon/authenticated w Supabase) — świadome "default deny"
-- przed dodaniem docelowych polityk w kolejnym kroku. NIE wpływa na
-- run_backfill.py/run_daily.py/export_excel.py — łączą się jako "postgres"
-- (właściciel tabel, rolbypassrls=true), więc RLS jest dla nich przezroczyste.
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

-- Rola analyst (read-only) — CREATE ROLE nie jest natywnie idempotentne
-- (błąd "role already exists" przy powtórnym wykonaniu), a ensure_schema()
-- odpala ten plik przy każdym starcie run_backfill.py/run_daily() — stąd
-- warunkowy blok zamiast gołego CREATE ROLE.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst NOLOGIN;
    END IF;
END
$$;

-- CREATE POLICY też nie jest idempotentne (brak IF NOT EXISTS w Postgresie) —
-- DROP POLICY IF EXISTS + CREATE POLICY zamiast tego, spójnie z resztą pliku.
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

-- ─────────────────────────────────────────────────── Krok 2 — dostęp read-only (Power BI)
--
-- Polityki RLS wyżej FILTRUJĄ wiersze, ale NIE nadają samego prawa odczytu —
-- bez GRANT SELECT Postgres odrzuca zapytanie ZANIM RLS w ogóle się uruchomi
-- ("permission denied for table"). Faza 1 utworzyła rolę `analyst` i komplet
-- polityk, ale nigdy nie nadała jej GRANT-ów, więc rola była nieużywalna do
-- faktycznego czytania danych (nie było to widoczne, bo nikt się nią nie
-- logował — jest NOLOGIN). Naprawione tutaj.
--
-- GRANT ... ON ALL TABLES (nie lista tabel po przecinku) — obejmuje też
-- tabele referencyjne bez RLS (accounts, departments, products, vat_types,
-- employments, salary_specifications), niezbędne do analizy P&L w BI
-- (np. nazwy kont do rozbicia kosztów, działy do payrollu). ALTER DEFAULT
-- PRIVILEGES pilnuje, żeby przyszłe tabele też były od razu czytelne dla
-- analysta — bez tego każda nowa tabela wymagałaby ręcznego GRANT-a.
GRANT USAGE ON SCHEMA public TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analyst;
