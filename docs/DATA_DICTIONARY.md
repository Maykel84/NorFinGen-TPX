# NorFinGen — Data Dictionary

Opis wszystkich 20 tabel w schemacie Supabase (`src/norfingen/db/schema.sql`). Waluta domyślna: **NOK**. Wszystkie tabele mają włączone RLS (Faza 1) — dostęp z `run_backfill.py`/`run_daily.py` idzie przez rolę `postgres` (bypass RLS), odczyt-tylko przez rolę `analyst`.

**Najważniejsze ograniczenie całego modelu**: `Order.invoiceDate` w prawdziwym Tripletex automatycznie tworzy Voucher (konta 3000/3100, przychód). NorFinGen **nie wywołuje realnego Tripletex API** — ten Voucher nigdy nie powstaje lokalnie. Skutek: **`vouchers`/`postings` nigdy nie zawierają przychodu ze sprzedaży** — tylko koszty (payroll, dostawcy, bank). Każde zapytanie P&L musi liczyć przychód z `orders`/`order_lines`, a koszty z `vouchers`/`postings` osobno i łączyć je ręcznie (zob. przykłady w historii sesji — `WITH p AS (...orders...), k AS (...postings...)`).

---

## Warstwa 1 — wymiary / referencje

### departments
| Kolumna | Typ | Opis |
|---|---|---|
| id | INTEGER (PK) | Numer działu, 1-4 |
| name | TEXT | Salg / Leveranse / Teknologi / Økonomi |
| number | TEXT | Kod tekstowy = `id` |
| is_inactive | BOOLEAN | Zawsze `false` — brak logiki dezaktywacji działów |

Znaczenie biznesowe: struktura organizacyjna firmy, używana do przypisania pracowników i (opcjonalnie) postingów kosztowych. Ograniczenie: statyczne, nie zmienia się w czasie mimo że firma rośnie z 4 do 16 osób.

### employees
| Kolumna | Typ | Opis |
|---|---|---|
| id | INTEGER (PK) | 1-16, odpowiada `numeric_id("E01")..("E16")` |
| first_name / last_name | TEXT | Imię / nazwisko |
| employee_number | TEXT | Kod "E01"-"E16" |
| department_id | INTEGER (FK) | → departments.id |
| bank_account_number, national_identity_number, date_of_birth | TEXT/DATE | Nigdy nie wypełniane (NULL) — placeholder pod przyszłe rozszerzenia |
| allow_information_registration | BOOLEAN | Zawsze `true`, bez znaczenia biznesowego w generatorze |

Znaczenie biznesowe: kadra firmy. **Data zatrudnienia jest w `employments.start_date`, nie tutaj**. Kohorta założycielska (E01-E06) rozłożona na 4 miesiące 2019-01→2019-04 (nie jeden dzień) — zob. `employments`.

### employments
| Kolumna | Typ | Opis |
|---|---|---|
| employee_id | INTEGER (FK, UNIQUE) | → employees.id — jeden rekord na pracownika |
| start_date | DATE | Data zatrudnienia — punkt odniesienia dla `active_employees()`, podwyżek (+3%/rok w lipcu) i feriepenger |
| end_date | DATE | Zawsze NULL — brak modelu odejść pracowników |
| employment_type, remuneration_type | TEXT | Zawsze "ORDINARY" / "FIXED_SALARY" |
| weekly_working_hours, percentage | NUMERIC | Zawsze 37.5h / 100% — brak niepełnego etatu |
| payroll_tax_zone | TEXT | Zawsze "ZONE_1" (Oslo) |

Ograniczenie: brak odejść pracowników (rotacji kadry) — każdy zatrudniony zostaje na zawsze aktywny.

### customers
| Kolumna | Typ | Opis |
|---|---|---|
| id | INTEGER (PK) | 1-12, `numeric_id("K01")..("K12")` |
| name | TEXT | Nazwa firmy klienta |
| customer_number | TEXT | Kod "K01"-"K12" |
| city | TEXT | Miasto siedziby |
| **segment** | VARCHAR(20) | Enterprise / Mid-market / SMB (Faza 1) |
| **onboarding_date** | DATE | Data rozpoczęcia współpracy — klient nie generuje zamówień przed tą datą (Faza "realistyczny start firmy") |
| **churn_date** | DATE | Data zakończenia współpracy, NULL = nadal aktywny. Tylko K09 ma wartość (2024-11-30) |
| **price_multiplier** | NUMERIC(5,4) | Indywidualny mnożnik ceny ±8% (0.92-1.08), deterministyczny per klient — symuluje wynik negocjacji B2B |
| organization_number, email, phone_number, address_line1, postal_code | TEXT | Nigdy wypełniane (NULL) |
| is_private_individual | BOOLEAN | Zawsze `false` |
| country_id, currency_id | INTEGER | Zawsze 161 (Norwegia) / 1 (NOK) |
| invoices_due_in, invoices_due_in_type | INTEGER/TEXT | Kolumny istnieją, ale realny termin płatności per zamówienie jest w `orders.invoices_due_in` (per-order, nie per-customer) |

**Pogrubione kolumny to dodatki Fazy 1** — populowane przez `seed_reference_data()`/`scripts/migrate_customer_metadata.py`, nie były częścią oryginalnego schematu. Ograniczenie: tylko 1 klient ma churn (celowo niski, realistyczny wskaźnik, nie pełny model rotacji portfela).

### suppliers
| Kolumna | Typ | Opis |
|---|---|---|
| id | INTEGER (PK) | 1-8, `numeric_id("L01")..("L08")` |
| name | TEXT | Nazwa dostawcy |
| supplier_number | TEXT | Kod "L01"-"L08" |
| organization_number, email, phone_number, address_line1, postal_code, city, bank_account_number | TEXT | Nigdy wypełniane (NULL) |
| is_private_individual, is_wholesaler, show_products | BOOLEAN | Zawsze `false` |
| country_id, currency_id | INTEGER | Zawsze 161 / 1 |

Znaczenie biznesowe: 8 dostawców kosztowych (Microsoft, Telenor, Reitan, Statsbygg, Sandvik, Thommessen, Avis, Nordic Insurance) — każdy z własnym rytmem fakturowania i wariancją kwot (Q1/Q3 wyższe u Avis, sezonowość Sandvik).

### vat_types
| Kolumna | Typ | Opis |
|---|---|---|
| id | INTEGER (PK) | 0 / 1 / 3 / 6 |
| name | TEXT | Opis stawki po norwesku |
| number | TEXT | Kod tekstowy = `id` |
| percentage | NUMERIC(5,2) | Stawka % — 25.0 dla sprzedaży/zakupu, 0.0 dla zwolnionych |
| vat_code | TEXT | "0"/"1"/"3"/"6" — kod Tripletex |

Znaczenie biznesowe: stały słownik stawek VAT (jedyna realnie używana stawka w generatorach to 25%, kody "1" zakup / "3" sprzedaż).

### accounts
| Kolumna | Typ | Opis |
|---|---|---|
| number | INTEGER (PK) | Numer konta wg NS 4102 (norweski plan kont), np. 5000, 6410 |
| name | TEXT | Nazwa konta po norwesku |
| type | TEXT | ASSETS / EQUITY_AND_LIABILITY / OPERATING_INCOME / OPERATING_EXPENSE |
| vat_type_id | INTEGER (FK) | → vat_types.id, tylko dla kont przychodowych/kosztowych z VAT |

Znaczenie biznesowe: 24-pozycyjny plan kont używany przez wszystkie `postings.account_number`. **Konta 3000/3100 (przychód) istnieją w tym słowniku, ale nigdy nie mają postingów** — zob. ograniczenie na górze dokumentu.

### products
| Kolumna | Typ | Opis |
|---|---|---|
| id | INTEGER (PK) | 1-6, `numeric_id("P01")..("P06")` |
| name | TEXT | Nazwa produktu |
| number | TEXT | Kod "P01"-"P06" |
| sales_price | NUMERIC(14,2) | Cena bazowa 2019 (NOK/mies.), przed inflacją +3%/rok. NULL dla P06 (consulting — cena losowa per zlecenie) |
| vat_type_id | INTEGER (FK) | Zawsze 3 (sprzedaż 25%) |
| currency_id | INTEGER | Zawsze 1 (NOK) |
| is_inactive | BOOLEAN | Zawsze `false` |
| **service_code** | VARCHAR(10) (FK → services.code) | P01-P03→S01, P04-P05→S02, P06→S04 (Faza 1) |

Znaczenie biznesowe: 6 produktów sprzedażowych — P01-P03 IT Support (per segment), P04-P05 licencje (Enterprise/Mid-market), P06 consulting. Ceny obniżone ~17% względem oryginalnych założeń (2026-07) w celu domknięcia marży operacyjnej do 15-25%.

---

## Faza 1 — katalog usług

### services
| Kolumna | Typ | Opis |
|---|---|---|
| code | VARCHAR(10) (PK) | S01-S04 |
| name | VARCHAR(200) | Nazwa usługi |
| description | TEXT | Opis biznesowy |
| billing_model | VARCHAR(20) | SUBSCRIPTION (miesięczna) / HOURLY (rozliczana godzinowo) |
| availability | VARCHAR(30) | ALL / ENTERPRISE_MID / ENTERPRISE_ONLY — który segment może kupić |
| base_price_enterprise / base_price_mid / base_price_smb | NUMERIC(12,2) | Cena bazowa 2019: NOK/mies. dla SUBSCRIPTION, NOK/h dla HOURLY. NULL = usługa niedostępna dla tego segmentu |

Znaczenie biznesowe: katalog ofertowy niezależny od konkretnych cen per klient (te ustala `customers.price_multiplier`). Ograniczenie: S03 (Cyberbezpieczeństwo) nie ma jeszcze żadnego powiązanego produktu w `products` — usługa istnieje w katalogu, ale nie generuje jeszcze przychodu.

---

## Warstwa 2 — dokumenty źródłowe

### orders
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| customer_id | INTEGER (FK) | → customers.id |
| order_date, invoice_date | DATE | Zwykle identyczne — data wystawienia faktury sprzedaży (`customer.invoice_day`) |
| delivery_date | DATE | Ostatni dzień miesiąca rozliczeniowego |
| invoices_due_in | INTEGER | Dni do terminu płatności (`customer.payment_terms`: 14/30/45) |
| invoices_due_in_type | TEXT | Zawsze "DAYS" |
| department_id | INTEGER (FK) | Zawsze 1 (Salg) |
| our_contact_id | INTEGER | Zawsze id E01 (Erik Strand, Sales Manager) |
| comment | TEXT | Opis "Månedlig faktura — {miesiąc} {rok}" |
| **status** | TEXT | PAID (domyślnie) / OVERDUE (~1,6% zamówień, opóźnienie +90 dni) / WRITTEN_OFF (~0,4%, nigdy niezapłacone — bad debt) |

Znaczenie biznesowe: **faktura sprzedaży (przychód)**. Kwota = suma `order_lines.amount_currency`. Waluta: NOK. Ograniczenie: `status` ustalany **raz, deterministycznie, przy tworzeniu zamówienia** (nie na podstawie realnego upływu czasu) — celowe, żeby backfill był w pełni powtarzalny.

### order_lines
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| order_id | INTEGER (FK, CASCADE) | → orders.id |
| product_id | INTEGER (FK) | → products.id |
| count | NUMERIC(10,2) | Zawsze 1.0 |
| unit_price_excluding_vat_currency | NUMERIC(14,2) | Cena jednostkowa NOK, po inflacji (+3%/rok) i mnożniku klienta (±8%) |
| discount | NUMERIC(5,4) | Zawsze 0 — brak rabatów |
| amount_excluding_vat_currency | NUMERIC(14,2) | = count × cena × (1-discount). **To pole liczy się do przychodu w P&L** |
| amount_currency | NUMERIC(14,2) | Kwota brutto (+25% VAT) |
| vat_type_id | INTEGER (FK) | Zawsze 3 (sprzedaż 25%) |

Znaczenie biznesowe: pojedyncza pozycja faktury sprzedaży (1 dla wzorców A/C, 2 dla B — support+licencja).

### supplier_invoices
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| invoice_number | TEXT (UNIQUE) | Format "{L0x}-{rok}-{numer}" |
| supplier_id | INTEGER (FK) | → suppliers.id |
| invoice_date, received_date | DATE | Zwykle identyczne |
| payment_due_date | DATE | invoice_date + 30 dni |
| amount_currency | NUMERIC(14,2) | Kwota brutto NOK |
| amount_excluding_vat_currency, vat_amount_currency | NUMERIC(14,2) | Netto / VAT (25%) |
| account_number | INTEGER (FK) | Konto kosztowe (6xxx) lub kapitalizacji (1200, dla L05 ≥30 000 NOK) |
| **status** | TEXT | UNPAID / PAID — flaguje się na PAID automatycznie po zaksięgowaniu odpowiadającego `bank_transactions` (OUTGOING) |

Znaczenie biznesowe: **faktura zakupu (koszt)**. Ograniczenie: 526 historycznych faktur miało status PAID nadany starą heurystyką czasową (sprzed wdrożenia `bank_transactions`) — naprawione jednorazowo przez `scripts/fix_outgoing_transactions.py`, ale **ten skrypt trzeba uruchamiać ponownie po każdym pełnym resecie tabel** (TRUNCATE zeruje `bank_transactions`).

### salary_transactions
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| date | DATE | Ostatni dzień roboczy miesiąca (data wypłaty) |
| year, month | INTEGER | Klucz naturalny (UNIQUE razem) |
| status | TEXT | Zawsze "OPEN" — brak logiki zamykania okresu |

Znaczenie biznesowe: nagłówek jednej listy płac (miesiąc). Jeden rekord/miesiąc, 91 rekordów łącznie (2019-01 → 2026-07).

### payslips
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| transaction_id | INTEGER (FK, CASCADE) | → salary_transactions.id |
| employee_id | INTEGER (FK) | → employees.id |
| date | DATE | Data wypłaty (= salary_transactions.date) |
| amount | NUMERIC(14,2) | **Netto** (na rękę) NOK — brutto minus skattetrekk. W czerwcu wyższe niż zwykle (feriepenger nieopodatkowane) |

Znaczenie biznesowe: pasek wypłaty jednego pracownika za dany miesiąc. Ograniczenie: `amount` to netto, nie brutto — do analiz kosztowych (P&L) używać `salary_specifications` lub postingów konta 5000, nie tej kolumny.

### salary_specifications
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| payslip_id | INTEGER (FK, CASCADE) | → payslips.id |
| wage_type_id | INTEGER | Typ składnika: Fast lønn / Skattetrekk / Feriepenger |
| description | TEXT | Opis po norwesku |
| amount | NUMERIC(14,2) | NOK, dodatnie dla pensji/feriepenger, **ujemne** dla skattetrekk (potrącenie) |

Znaczenie biznesowe: rozbicie wypłaty na składniki. W czerwcu: standardowo tylko "Feriepenger" (pensja bazowa = 0, zastąpiona przez feriepenger); dla pracowników z niepełnym rokiem stażu — "Fast lønn" (dopłata) + "Feriepenger" + "Skattetrekk" od dopłaty.

---

## Warstwa 3 — ledger

### vouchers
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| date | DATE | Data księgowania |
| description | TEXT | Opis (klucz naturalny razem z `date`, UNIQUE) |
| voucher_type | TEXT | INCOMING_INVOICE / SALARY / BANK / MANUAL. **Nigdy INVOICE** (zob. ograniczenie na górze dokumentu) |

Znaczenie biznesowe: nagłówek zapisu księgowego. **Nie zawiera przychodu ze sprzedaży** — tylko koszty (faktury zakupu, payroll, ruchy bankowe) i kapitał zakładowy.

### postings
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| voucher_id | INTEGER (FK, CASCADE) | → vouchers.id |
| account_number | INTEGER (FK) | → accounts.number |
| amount | NUMERIC(14,2) | **+ = debet, − = kredyt**. Suma postingów w voucherze ≈ 0 (z tolerancją VAT, zob. `validate_balance()`) |
| vat_amount | NUMERIC(14,2) | Tylko na postingu debetowym, embedded (nie osobny posting) |
| customer_id / supplier_id / employee_id / department_id | INTEGER (FK) | Wymiary analityczne — wypełniane w zależności od typu postingu (np. customer_id dla konta 1500, employee_id dla 2710/2740) |

Znaczenie biznesowe: pojedyncza linia zapisu księgowego (DR/CR). Do analiz kosztowych: filtrować `account_number BETWEEN 5000 AND 5999` (płace) lub `BETWEEN 6000 AND 7999` (koszty operacyjne).

---

## Etap 4 — bank / projekty / timesheet

### bank_transactions
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| date | DATE | Data faktycznego przepływu gotówki (nie data faktury!) |
| amount | NUMERIC(12,2) | NOK, zawsze dodatnie |
| transaction_type | VARCHAR(20) | INCOMING (klient płaci) / OUTGOING (firma płaci dostawcy) |
| customer_id / supplier_id | INTEGER (FK) | Wypełnione zależnie od kierunku |
| order_id / supplier_invoice_id | INTEGER (FK) | Powiązany dokument źródłowy |
| account_from, account_to | INTEGER | Konta GL: INCOMING 1500→1910, OUTGOING 1910→2400 |
| voucher_id | INTEGER (FK) | → vouchers.id (typu BANK) |

Znaczenie biznesowe: rzeczywisty ruch na koncie bankowym, przesunięty w czasie względem faktury o `payment_terms` (klient) lub 30 dni (dostawca), +90 dni dla zamówień OVERDUE, nigdy dla WRITTEN_OFF. Ograniczenie: historyczne INCOMING/OUTGOING silnie nierównomierne (609 vs 531) — nie odzwierciedla to realnego cash-flow ratio, tylko artefakt kolejności wdrażania funkcji w tym projekcie.

### hour_entries
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | |
| date | DATE | Dzień roboczy (pon-pt) |
| employee_id | INTEGER (FK) | Tylko 11 z 16 pracowników loguje godziny (działy Leveranse/Teknologi, bez E05) |
| project_id | INTEGER (FK) | NULL dla INTERNAL/SICK |
| activity_type | VARCHAR(20) | BILLABLE / INTERNAL / SICK |
| hours | NUMERIC(4,1) | Godziny, suma BILLABLE+INTERNAL = 7.5/dzień (albo SICK=0) |

Znaczenie biznesowe: timesheet konsultantów. **Nie generuje żadnych postingów księgowych** — czysto operacyjne dane (nie ma wpływu na P&L). Ograniczenie: BILLABLE tylko do projektów, których klient jest już onboardowany i jeszcze nie odszedł (churn) — w przeciwnym razie cały dzień loguje się jako INTERNAL.

### projects
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | 1-8, `numeric_id("PRJ001")..("PRJ008")` |
| number | VARCHAR(20) (UNIQUE) | "PRJ001"-"PRJ008" |
| customer_id | INTEGER (FK) | → customers.id |
| start_date | DATE | Zawsze 2026-01-01 lub 2026-03-01 (statyczna data utworzenia projektu w katalogu, nie historyczna) |
| end_date | DATE | Zawsze NULL |
| status | VARCHAR(20) | Zawsze "ACTIVE" |

Znaczenie biznesowe: kontener godzin konsultanckich per klient — używany wyłącznie przez `hour_entries.project_id`, nie ma bezpośredniego związku z fakturowaniem (`orders`). Ograniczenie: `start_date` to data założenia rekordu w katalogu projektów (2026), **nie** data rozpoczęcia realnej współpracy z klientem (to `customers.onboarding_date`) — nazwa pola myląca, nie mylić przy analizach.

---

## Znane ograniczenia całościowe

1. **Brak postingów przychodowych** (konta 3000/3100) — zob. nagłówek dokumentu. Przychód wyłącznie w `orders`/`order_lines`.
2. **`bank_transactions` wymaga ręcznego doreperowania po każdym `TRUNCATE`** — `scripts/fix_outgoing_transactions.py` uzupełnia historyczne OUTGOING, ale trzeba go uruchomić po każdym pełnym resecie danych.
3. **Metadane Fazy 1** (`customers.segment/onboarding_date/churn_date/price_multiplier`, `services`, `products.service_code`) istniały wcześniej **tylko w Pythonie** (`roster.py`) — teraz są też w Supabase, ale historyczne zapytania/dashboardy pisane przed Fazą 1 mogły je pomijać.
4. **`projects.start_date` ≠ `customers.onboarding_date`** — łatwa pomyłka przy pisaniu zapytań łączących obie tabele.
5. **RLS włączone bez własnych polityk zapisu** — tylko `postgres` (bypass RLS) może pisać; rola `analyst` ma czysty odczyt (SELECT) na 14 tabelach transakcyjnych/referencyjnych.
6. **Brak rotacji kadry** (`employments.end_date` zawsze NULL) i **niemal brak churnu klientów** (tylko K09) — model celowo prosty, nie pełna symulacja dynamiki portfela.
