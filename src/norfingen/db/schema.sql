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

-- Naprawa incydentu 2026-09-04 (zob. docs/SESSION_HANDOFF.md): UNIQUE powyżej
-- NIE chroni wpisów INTERNAL/SICK (project_id zawsze NULL, zob. opis kolumny
-- wyżej) — Postgres traktuje NULL <> NULL, więc dwa identyczne wiersze z
-- project_id=NULL nie naruszają tego UNIQUE i `ON CONFLICT (date,
-- employee_id, project_id, activity_type) DO NOTHING` (repository.py,
-- _save_hour_entry) nigdy dla nich nie zadziała. Częściowy indeks unikalny
-- tylko dla project_id IS NULL domyka tę lukę.
CREATE UNIQUE INDEX IF NOT EXISTS hour_entries_unique_null_project
    ON hour_entries (date, employee_id, activity_type)
    WHERE project_id IS NULL;

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

-- Krok 2 — naprawa: payroll (SalaryTransaction) nigdy nie generował
-- odpowiadającej transakcji bankowej OUTGOING (luka od Tier 2, nie
-- regresja Fazy 6 — zob. SESSION_HANDOFF.md). FK jawny (nie dopasowanie po
-- opisie tekstowym ILIKE), analogicznie do order_id/supplier_invoice_id.
ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS salary_transaction_id INTEGER REFERENCES salary_transactions(id);

-- ADD CONSTRAINT nie wspiera IF NOT EXISTS w Postgresie — DO blok, ten sam
-- wzorzec co CREATE POLICY (DROP IF EXISTS) niżej w tym pliku. UNIQUE
-- potrzebne żeby ON CONFLICT DO NOTHING w _save_bank_transaction() było
-- idempotentne dla płatności payrollowych (ponowne uruchomienie backfillu
-- dla tego samego miesiąca nie tworzy duplikatu).
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

-- ─────────────────────────────────────────────────── Krok 2, Zadanie 2 — widoki BI
--
-- Dwa świadome odstępstwa od szkicu w prompcie (nie kopiowane bezrefleksyjnie):
--
-- 1. v_pl_monthly NIE liczy przychodu z postings (account_number 3000-3999) —
--    te postingi NIGDY nie istnieją w tej bazie (zweryfikowane: 0 wierszy).
--    Powód udokumentowany na samej górze DATA_DICTIONARY.md od początku
--    projektu: Order.invoiceDate w prawdziwym Tripletex automatycznie tworzy
--    Voucher przychodowy — NorFinGen nie wywołuje realnego API, więc ten
--    Voucher nigdy nie powstaje lokalnie. Przychód ZAWSZE liczy się z
--    orders/order_lines, nigdy z postings (ten sam wzorzec co
--    export_queries.PL_miesiecznie — CTE revenue z order_lines FULL OUTER
--    JOIN CTE kosztów z postings). Kopiowanie szkicu 1:1 dałoby widok, który
--    zawsze zwraca revenue=NULL.
--
-- 2. v_sales_flat.amount_including_vat_currency to ALIAS kolumny fizycznej
--    order_lines.amount_currency, NIE rename tej kolumny — "Koszyk 1"
--    (rename order_lines.amount_currency -> amount_including_vat_currency,
--    zgodnie z realną nazwą pola OrderLine w Tripletex API) był tylko
--    PROPONOWANY w tej sesji, nigdy jawnie zaakceptowany przez użytkownika
--    ani wykonany w kodzie/generatorach/testach. Ten widok daje poprawną,
--    Tripletex-zgodną nazwę w BI już teraz, bez ryzykownej zmiany fizycznego
--    schematu/generatorów w tle. Jeśli Koszyk 1 zostanie kiedyś wykonany,
--    ten alias stanie się zbędny (kolumna źródłowa już będzie się tak
--    nazywać) — do wtedy zostaje jako pomost.
--
-- security_invoker=true (PG15+, Supabase = PG17) na wszystkich trzech
-- widokach — bez tego widok domyślnie czyta tabele źródłowe z
-- uprawnieniami WŁAŚCICIELA widoku (postgres, który omija RLS), nie
-- roli faktycznie odpytującej (analyst/powerbi_reader) — znany "RLS
-- bypass przez widok" w Postgresie. Dziś polityki są USING (true), więc
-- widoczne dane są identyczne niezależnie od trybu, ale bez tej flagi
-- każda przyszła, faktycznie filtrująca polityka RLS zostałaby po cichu
-- ominięta przy odpytywaniu przez widok zamiast tabeli wprost.
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

-- v_headcount_monthly liczy TYLKO pracowników billable, którzy faktycznie
-- logują hour_entries (Leveranse/Teknologi, bez E05 — zob. hours_generator.py)
-- — Salg/Økonomi (5 z 17 etatów w Fazie 6) nigdy nie mają wpisów godzin, więc
-- ten widok NIEDOSZACOWUJE prawdziwy headcount firmy. Zostawione zgodnie ze
-- szkicem z promptu (poprawne SQL, zgodne nazwy kolumn) — to świadomy
-- kompromis nazwany "active_employees" (godzinowo aktywni), nie "headcount"
-- w sensie kadrowym; jeśli potrzebny prawdziwy headcount kadrowy, właściwe
-- źródło to employments.start_date (jak roster.active_employees() w Pythonie),
-- nie hour_entries.
CREATE OR REPLACE VIEW v_headcount_monthly WITH (security_invoker = true) AS
SELECT TO_CHAR(date, 'YYYY-MM') AS month, COUNT(DISTINCT employee_id) AS active_employees
FROM hour_entries GROUP BY 1 ORDER BY 1;

GRANT SELECT ON v_sales_flat, v_pl_monthly, v_headcount_monthly TO analyst;
