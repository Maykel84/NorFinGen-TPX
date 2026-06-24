# NorFinGen

Generator syntetycznych danych finansowych dla norweskiej firmy IT AS (managed services, 16 pracowników, 12 klientów, 8 dostawców, ~35M NOK przychodu/rok), zasilający Tripletex API v2 przez Supabase Postgres.

## Struktura

```
docs/                       Dokumentacja schematów encji (Warstwa 1-3, ERD)
run_backfill.py              CLI: python run_backfill.py --start 2019-01-01 [--end ...]
run_daily.py                 CLI + importowalna funkcja run_daily() (np. z APScheduler na Railway)
src/norfingen/
  config.py                 Ustawienia z .env (DATABASE_URL, tokeny Tripletex)
  db/
    connection.py            Połączenie SQLAlchemy (nieużywane przez repository.py — zob. niżej)
    schema.sql                16x CREATE TABLE IF NOT EXISTS — pełny schemat Supabase
    repository.py             save_all() / ensure_schema() / seed_reference_data() — psycopg2
  models/                   Modele Pydantic encji Tripletex API v2
    base.py                 TripletexRef, Address, CompanyBase (wspólne dla Customer/Supplier)
    department.py           Department
    employee.py             Employee + Employment
    customer.py             Customer
    supplier.py             Supplier
    account.py              Account (plan kont NS 4102, read-only)
    vat_type.py             VatType (kody MVA, read-only)
    product.py              Product (P01-P06)
    order.py                Order + OrderLine (przychody, Voucher auto via invoiceDate)
    supplier_invoice.py     SupplierInvoice (koszty, Voucher tworzony jawnie)
    salary.py                SalaryTransaction + Payslip + SalarySpecification
  seed/
    roster.py                Single source of truth: DEPARTMENTS, EMPLOYEES, CUSTOMERS, SUPPLIERS, PRODUCTS
    payroll.py               Funkcje obliczeniowe: brutto, skattetrekk, AGA, feriepenger, active_employees
  generators/                Warstwa 3 — Voucher/Posting + generatory dokumentów
    voucher.py                Voucher, Posting, VoucherType, validate_balance(), assert_voucher_valid()
    order_generator.py        generate_monthly_orders() — wzorce A/B/C/D z roster.CUSTOMERS
    supplier_invoice_generator.py  generate_monthly_supplier_invoices() + build_voucher_for_invoice()
    salary_generator.py       generate_monthly_salary() — lista płac, AGA, feriepenger (czerwiec)
    backfill.py                run_backfill() — pętla historyczna 2019→dziś + kapitał zakładowy
tests/                       Testy pytest
.github/workflows/           Scheduler GitHub Actions (pon-pt 08:00/12:00/17:00 CET)
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env  # uzupełnij DATABASE_URL (Supabase) i tokeny Tripletex
pytest
```

## Backfill / daily generacja do Supabase

```bash
python run_backfill.py --start 2019-01-01     # cała historia od założenia firmy
python run_backfill.py --start 2024-01-01 --end 2024-06-30   # zakres
python run_daily.py                            # bieżący miesiąc, idempotentny
```

Oba skrypty same wywołują `ensure_schema()` (tworzy 16 tabel, IF NOT EXISTS) i
`seed_reference_data()` (departments/employees/employments/customers/suppliers/
accounts/vat_types/products z `roster.py`) przed generacją — bezpieczne na
pustej bazie i przy każdym kolejnym uruchomieniu.

`run_daily.run_daily()` jest importowalne jako zwykła funkcja Python — gotowe
do podłączenia jako APScheduler job (Railway), bez potrzeby subprocessu CLI.

## Status

Warstwa 1 (Department, Employee, Customer, Supplier, Account, VatType) — modele gotowe.
Warstwa 2 (Product, Order/OrderLine, SupplierInvoice, SalaryTransaction/Payslip) — modele gotowe, roster.py jako single source of truth, payroll.py z funkcjami obliczeniowymi.
Warstwa 3 (Voucher/Posting) — generatory Order/SupplierInvoice/SalaryTransaction + budowanie i walidacja Voucherów (balans z uwzględnieniem VAT, min. 2 postingi, konto GL wymagane), backfill.py z pętlą historyczną i jednorazowym Voucherem kapitału zakładowego.
Persystencja (db/schema.sql + db/repository.py) — gotowe: psycopg2, idempotentne INSERT ON CONFLICT DO NOTHING na naturalnych kluczach biznesowych, save_all() podpięte jako persist_fn. run_backfill.py / run_daily.py jako CLI + GitHub Actions (.github/workflows/daily.yml, pon-pt 07/11/16 UTC). 43 testy przechodzą (w tym 6 z mockowanym psycopg2, bez realnego połączenia z DB).

**Nie przetestowane end-to-end na żywym Supabase** — w tym środowisku nie ma pliku `.env` z prawdziwym `DATABASE_URL` ani lokalnego Postgresa/Dockera do weryfikacji. Przed użyciem: utwórz `.env` (z `cp .env.example .env`, uzupełnij `DATABASE_URL`), uruchom `python run_backfill.py --start 2019-01-01`, sprawdź w Supabase Dashboard → Table Editor, że `vouchers` i `postings` się wypełniły.

Następne kroki: integracja z prawdziwym Tripletex API, weryfikacja end-to-end na Supabase, docelowa migracja schedulera z GitHub Actions na Railway + APScheduler (`run_daily.run_daily()` już gotowe do tego).
