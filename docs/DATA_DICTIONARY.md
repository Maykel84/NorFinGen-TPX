# NorFinGen — Data Dictionary

Opis wszystkich 20 tabel w schemacie Supabase (`src/norfingen/db/schema.sql`). Waluta domyślna: **NOK**. Wszystkie tabele mają włączone RLS (Faza 1) — dostęp z `run_backfill.py`/`run_daily.py` idzie przez rolę `postgres` (bypass RLS), odczyt-tylko przez rolę `analyst`.

**Najważniejsze ograniczenie całego modelu**: `Order.invoiceDate` w prawdziwym Tripletex automatycznie tworzy Voucher (konta 3000/3100, przychód). NorFinGen **nie wywołuje realnego Tripletex API** — ten Voucher nigdy nie powstaje lokalnie. Skutek: **`vouchers`/`postings` nigdy nie zawierają przychodu ze sprzedaży** — tylko koszty (payroll, dostawcy, bank). Każde zapytanie P&L musi liczyć przychód z `orders`/`order_lines`, a koszty z `vouchers`/`postings` osobno i łączyć je ręcznie (zob. przykłady w historii sesji — `WITH p AS (...orders...), k AS (...postings...)`).

---

## Profil branżowy firmy (dodatek NACE/SN2007)

Norwegia klasyfikuje firmy wg SN2007 (Standard for næringsgruppering), zgodnego z unijnym NACE Rev.2 — każda firma zarejestrowana w Brønnøysundregistrene ma przypisany kod branżowy (næringskode).

**Kod główny firmy**: `roster.COMPANY_NACE_CODE` = **62.020** "Konsulentvirksomhet tilknyttet informasjonsteknologi og forvaltning og drift av it-systemer" — obejmuje explicite i konsulting/zarządzanie IT (S02, S04), i drift/wsparcie systemów (S01, S03), więc pasuje do całego portfela usług naraz, nie tylko do jednej. Realny odpowiednik z tego samego segmentu: **Garnes Data AS** (benchmark marżowy Fazy 6, zarejestrowany pod pokrewnym 62.030 "Forvaltning og drift av IT-systemer" — bliższym czystemu S01/drift).

**Kod sekundarny**: brak (`COMPANY_NACE_SECONDARY_CODE = None`). Zadanie przewidywało dodanie 70.220 "Bedriftsrådgivning og annen administrativ rådgivning", jeśli S04 (konsulting) przekracza 20% przychodu — zweryfikowane zapytaniem SQL na żywej bazie (`order_lines` JOIN `products.service_code`, lata 2025-2026): S04 to **1,9%** przychodu, daleko poniżej progu (cena S04 obniżona w Fazie 6 do 950 NOK/h). Próg nieprzekroczony, kod sekundarny pominięty.

Kody klientów: zob. sekcja `customers` niżej (`roster.CUSTOMER_NACE`).

---

## Warstwa 1 — wymiary / referencje

### departments
| Kolumna | Typ | Opis |
|---|---|---|
| id | INTEGER (PK) | Numer działu, 1-4 |
| name | TEXT | Salg / Leveranse / Teknologi / Økonomi |
| number | TEXT | Kod tekstowy = `id` |
| is_inactive | BOOLEAN | Zawsze `false` — brak logiki dezaktywacji działów |

Znaczenie biznesowe: struktura organizacyjna firmy, używana do przypisania pracowników i (opcjonalnie) postingów kosztowych. Ograniczenie: statyczne, nie zmienia się w czasie mimo że firma rośnie z 1 do 17 osób.

### employees
| Kolumna | Typ | Opis |
|---|---|---|
| id | INTEGER (PK) | 1-17, odpowiada `numeric_id("E01")..("E17")` (Faza 6 skróciła z 1-38 — zob. niżej) |
| first_name / last_name | TEXT | Imię / nazwisko |
| employee_number | TEXT | Kod "E01"-"E17" |
| department_id | INTEGER (FK) | → departments.id |
| bank_account_number, national_identity_number, date_of_birth | TEXT/DATE | Nigdy nie wypełniane (NULL) — placeholder pod przyszłe rozszerzenia |
| allow_information_registration | BOOLEAN | Zawsze `true`, bez znaczenia biznesowego w generatorze |

Znaczenie biznesowe: kadra firmy. **Data zatrudnienia jest w `employments.start_date`, nie tutaj**. Kohorta założycielska (E01-E06) rozłożona na 4 miesiące 2019-01→2019-04 (nie jeden dzień) — zob. `employments`.

**Faza 6 (ZASTĘPUJE Fazę 4) — zespół obcięty z 38 do 17 osób (E18-E38 usunięte)**: kalibracja względem realnych danych rynkowych (Brønnøysundregistrene, 4 norweskie firmy IT — zob. `SESSION_HANDOFF.md`) wykazała, że porównywalne firmy IT drift/support (Garnes Data AS: 17 pracowników, ~48-59 mln NOK przychodu, marża 5,4%) obsługują duży portfel klientów małym zespołem, bo większość kosztu obsługi jest kosztem materiałowym (COGS pass-through, zob. `accounts` 4291/4292), nie osobowym. E17 (Vegard Lien, Leveranse, 2022-10-03) pozostaje jedynym dociążeniem po fuzji 2022-09 — dalszy wzrost zespołu (Faza 4: E18-E38, 22 rekrutacje do 2026-03) usunięty w całości.

**Faza 5 — wszystkie `start_date` przyciągnięte do pierwszego dnia roboczego miesiąca** (`payroll.first_working_day_of_month()`) — eliminuje potrzebę liczenia proporcji "ile dni w niepełnym miesiącu"; pierwszy miesiąc zatrudnienia jest zawsze pełnym miesiącem pracy. Kilka par pracowników (E02/E03, E04/E05 w kohorcie założycielskiej; kilka par z Fazy 4) ma teraz identyczny `start_date` w efekcie tego przyciągnięcia — staggering wyraża się przez MIESIĄC startu, nie już przez dzień w miesiącu. **Naprawiony bugfix**: `generate_monthly_salary()`/`brutto_earned_in_year()` porównywały aktywność pracownika do kalendarzowego dnia 1 (`date(year, month, 1)`), co błędnie wykluczało z wypłaty pracownika, którego pierwszy dzień roboczy wypadał 2./3. dnia miesiąca (bo 1. to weekend) — naprawione porównaniem do `first_working_day_of_month()`.

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
| id | INTEGER (PK) | 1-50, `numeric_id("K01")..("K50")` (Faza 4: +38, K13-K50) |
| name | TEXT | Nazwa firmy klienta |
| customer_number | TEXT | Kod "K01"-"K50" |
| city | TEXT | Miasto siedziby |
| **segment** | VARCHAR(20) | Enterprise / Mid-market / SMB (Faza 1) — docelowo 15/18/17 (Faza 4) |
| **onboarding_date** | DATE | Data rozpoczęcia współpracy — klient nie generuje zamówień przed tą datą (Faza "realistyczny start firmy"). Faza 4: rozłożone 2023-2026 + kohorta fuzji (2022-09-01, 4 klientów, ta sama data co fuzja pracownicza) |
| **churn_date** | DATE | Data zakończenia współpracy, NULL = nadal aktywny. K09 (2024-11-30) i K15 (2025-10-31, Faza 4) — oba SMB |
| **price_multiplier** | NUMERIC(5,4) | Indywidualny mnożnik ceny ±8% (0.92-1.08), deterministyczny per klient — symuluje wynik negocjacji B2B |
| **nace_code** | VARCHAR(10) | Kod branżowy SN2007/NACE klienta (dodatek NACE) — format "XX.XXX" |
| **nace_name** | VARCHAR(200) | Nazwa branży wg SN2007 (po norwesku) |
| **postal_code** | TEXT | Kod pocztowy (postnummer) na podstawie `city` — realne kody Posten/Bring (`roster.NORWEGIAN_POSTAL_CODES`), poprawka eksportu, format "XXXX" |
| organization_number, email, phone_number, address_line1 | TEXT | Nigdy wypełniane (NULL) |
| is_private_individual | BOOLEAN | Zawsze `false` |
| country_id, currency_id | INTEGER | Zawsze 161 (Norwegia) / 1 (NOK) |
| invoices_due_in, invoices_due_in_type | INTEGER/TEXT | Kolumny istnieją, ale realny termin płatności per zamówienie jest w `orders.invoices_due_in` (per-order, nie per-customer) |

**Pogrubione kolumny to dodatki Fazy 1 (+ dodatek NACE dla `nace_code`/`nace_name`, + poprawka eksportu dla `postal_code`)** — populowane przez `seed_reference_data()`/`scripts/migrate_customer_metadata.py`. `postal_code` jako kolumna **istniała już w oryginalnym schemacie** (`schema.sql`), tylko nigdy nie była wypełniana — poprawka eksportu (2026-07) dodała jej wypełnianie, nie samą kolumnę. Ograniczenie: tylko 2 klienci mają churn (celowo niski, realistyczny wskaźnik, nie pełny model rotacji portfela).

**Dodatek — kody branżowe NACE/SN2007** (`roster.CUSTOMER_NACE`, dict `customer_number -> NaceCode(code, name)`, nie osobne pole na `CustomerSeed` — analogicznie do `CUSTOMER_PRICE_MULTIPLIER`, żeby nie zmieniać sygnatury konstrukcji w 50 miejscach). Kod dopasowany do rzeczywistej nazwy firmy klienta (np. "Nordkraft Energi AS" → 35.140 Handel med elektrisitet, "Halden Design AS" → 74.100 Spesialisert designvirksomhet), nie losowo — 18 różnych sektorów wśród 50 klientów. Czysto opisowy dodatek, **nie wpływa na przychód/koszty/marżę**, nie wymaga backfillu transakcyjnego.

**Faza 4 — dwie kohorty cenowe** (`roster.get_service_price_table()`/`service_by_code_for_customer()`): klienci onboardowani przed `CUSTOMER_PRICING_COHORT_CUTOFF` (2023-01-01, obejmuje K01-K12 + kohortę fuzji 2022-09) płacą ceny `LEGACY_SERVICES` (Faza 2), klienci od tej daty płacą `SCALE_SERVICES` (niżej, ~2,2x). Powód: jeden globalny cennik dla wszystkich 50 klientów przez całą historię 2019-2026 psuł retroaktywnie marżę — obniżka dla nowych klientów obniżała też przychód starych klientów w latach, gdy byli jedyną bazą przychodową. Zob. `services` niżej i `SESSION_HANDOFF.md` (Faza 4) po pełne uzasadnienie.

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

**`postal_code` zostaje NULL nawet po poprawce eksportu (2026-07)** — `SupplierSeed` (roster.py) nigdy nie miał pola `city` (w przeciwieństwie do `CustomerSeed`), więc nie ma z czego wyprowadzić kodu pocztowego bez wymyślania nowych danych adresowych. Świadome ograniczenie, nie przeoczenie — zob. `SESSION_HANDOFF.md` p. 10.

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

Znaczenie biznesowe: 29-pozycyjny plan kont (24 + 3 z Fazy 3 + 2 z Fazy 6) używany przez wszystkie `postings.account_number`. **Konta 3000/3100 (przychód) istnieją w tym słowniku, ale nigdy nie mają postingów** — zob. ograniczenie na górze dokumentu.

**Faza 3 — 3 nowe konta kosztowe** (`generators/opex_generator.py`), wszystkie bez VAT (`vat_type_id=NULL`) — koszty gotówkowe księgowane bezpośrednio (DR koszt / CR 1910), bez pośredniego `SupplierInvoice`:
- **4290** "Driftsmateriell for kundeleveranse" — COGS (klasa 4 NS4102, nie 6xxx/7xxx jak reszta kosztów operacyjnych): jednorazowy sprzęt wdrożeniowy (routery/serwery) przy onboardingu klienta Enterprise/Mid-market, 45-90 tys. NOK (Enterprise) / 15-35 tys. NOK (Mid-market). Ponieważ obecni 12 klientów onboardowali się 2019-2022, ten koszt występuje niemal wyłącznie w latach historycznych.
- **7350** "Kantinetilskudd" — dopłata do kantyny, 820 NOK/pracownika/miesiąc (stała, bez inflacji — polityka firmy).
- **7420** "Representasjon" — koszty reprezentacyjne per aktywny klient: 1000 NOK/mies. (Enterprise) / 400 NOK/mies. (Mid-market), z inflacją +3%/rok. SMB nie generuje kosztu (relacja czysto transakcyjna). **Nie zaimplementowano** flagi `tax_deductible_pct` (ograniczona odliczalność podatkowa reprezentacji w Norwegii) — zadanie explicite dopuszczało pominięcie, zostawione jako komentarz w kodzie na przyszłość.

Kilometrówka (kwartalne wizyty u klientów) i wyjazdy konferencyjne (2-3x/rok, losowe) księgowane na **istniejące konto 7000** "Reisekostnader" — to samo konto co L07 Avis (dostawca kosztowy z Fazy wcześniejszej), bo to logicznie ta sama kategoria NS4102 (koszty podróży), nie osobny nowy numer. L07 Avis pozostaje bez zmian (żadnego "miksu" service/transport nie było do rozdzielenia — L07 to czysto wynajem samochodów).

**Faza 6 — 2 nowe konta COGS** (`generators/opex_generator.py`, wzorzec `_cogs_accrual_voucher`: DR koszt / CR 2400 Leverandørgjeld — zobowiązanie wobec dostawcy, nie natychmiastowa płatność gotówkowa jak konta Fazy 3), skalujące się co miesiąc z portfelem klientów:
- **4291** "Videresalgskostnad Microsoft/Azure" — pass-through dla S02, tylko klienci Enterprise+Mid (`roster.calc_azure_cogs_monthly`): 22 000/11 500 NOK/mies. (rok bazowy 2019, ×liczba klientów, +inflacja). Zastępuje płaską pozycję "Azure hosting" (35 000 NOK/mies.) usuniętą z `supplier_invoices` L01 (zob. niżej).
- **4292** "Driftskostnad Managed IT Support (RMM/EDR/verktøy)" — pass-through dla S01, WSZYSCY aktywni klienci niezależnie od segmentu (`roster.calc_s01_cogs_monthly`): 53 000/26 500/13 300 NOK/mies. (Enterprise/Mid/SMB, waga 4:2:1). Dodany po tym, jak offline sanity-check wykazał, że S02-only COGS fizycznie nie może wypełnić luki między realnym przychodem (~52 mln NOK w 2026, nie zakładane ~35 mln) a celem headcount~17/marża 7% — S02 generuje tylko ~13 mln NOK/rok przychodu, za mało jako baza. Zakotwiczone w Garnes Data AS (IT drift/support, realny opex+COGS/przychód = 61,6%) — cel `(opex_tradycyjny + cogs_s02 + cogs_s01) / przychód ≈ 58-62%`. Zob. `roster.py` (komentarz przy `calc_s01_cogs_monthly`) i `SESSION_HANDOFF.md` (Faza 6) dla pełnego wyprowadzenia.

### products
| Kolumna | Typ | Opis |
|---|---|---|
| id | INTEGER (PK) | 1-7, `numeric_id("P01")..("P07")` (P07 dodany w Fazie 2) |
| name | TEXT | Nazwa produktu |
| number | TEXT | Kod "P01"-"P07" |
| sales_price | NUMERIC(14,2) | Cena bazowa 2019 (NOK/mies.), historyczna/informacyjna. **Od Fazy 2 NIE jest już używana do liczenia ceny na fakturze** dla P01/P04/P06/P07 (zob. niżej) — NULL dla P06/P07 |
| vat_type_id | INTEGER (FK) | Zawsze 3 (sprzedaż 25%) |
| currency_id | INTEGER | Zawsze 1 (NOK) |
| is_inactive | BOOLEAN | Zawsze `false` |
| **service_code** | VARCHAR(10) (FK → services.code) | P01-P03→S01, P04-P05→S02, P06→S04, **P07→S03 (Faza 2)** |

Znaczenie biznesowe: 7 produktów sprzedażowych — P01-P03 IT Support (per segment), P04-P05 licencje (Enterprise/Mid-market), P06 consulting, **P07 (Faza 2) Cyberbezpieczeństwo**. Ceny obniżone ~17% względem oryginalnych założeń (2026-07) w celu domknięcia marży operacyjnej do 15-25%.

**Faza 2 — zmiana źródła prawdy dla ceny**: `order_generator.build_order_lines()` liczy cenę linii bezpośrednio z `services.base_price_{segment}` (nie z `products.sales_price`) — jeden kanoniczny produkt per usługa (`roster.product_for_service()`: P01→S01, P04→S02, P07→S03, P06→S04) referencjonowany niezależnie od segmentu klienta, tylko dla celów FK/etykiety na fakturze Tripletex. P02/P03/P05 pozostają w katalogu (zgodność wsteczna/testy), ale **nie są już używane do generowania linii zamówień** — zastąpione bundlingiem segmentowym (zob. `services`, `order_lines`).

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

Znaczenie biznesowe: katalog ofertowy niezależny od konkretnych cen per klient (te ustala `customers.price_multiplier`). **Faza 2**: każda usługa ma teraz produkt referencyjny (`products.service_code`) i realny bundling per segment (`roster.get_customer_services()` — Enterprise S01+S02+S03, Mid-market S01+S02, SMB S01) — S03 (Cyberbezpieczeństwo) generuje przychód dla wszystkich klientów Enterprise od momentu ich onboardingu (produkt P07).

**Ograniczenie Fazy 4**: ta tabela zawiera TYLKO `LEGACY_SERVICES` (ceny Fazy 2: S01 133k/84,5k/49k NOK/mies., S02 59k/37,5k, S03 44k) — klucz PK jest `code`, jedna cena per usługę, więc `SCALE_SERVICES` (ceny obniżone dla klientów onboardowanych od 2023-01-01: S01 60k/24k/6k, S02 25k/10k, S03 18k) **istnieje tylko w kodzie Python** (`roster.SCALE_SERVICES`), nie ma reprezentacji w tej tabeli. Zapytania SQL liczące przychód per usługa (`order_lines JOIN products`) są poprawne (cena faktycznie wystawiona jest w `order_lines.unit_price_excluding_vat_currency`), ale zapytania odczytujące `services.base_price_*` bezpośrednio pokażą tylko cennik legacy, nie faktyczny cennik nowych klientów.

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

Znaczenie biznesowe: pojedyncza pozycja faktury sprzedaży. **Faza 2**: jedna linia per usługa, którą klient kupuje wg segmentu (Enterprise 3 linie S01+S02+S03, Mid-market 2 linie S01+S02, SMB 1 linia S01) — zastąpiło dawne liczenie wg litery `order_pattern` (A=1/B=2/C=1). `order_lines` nie ma własnej kolumny `product_service_code` — kod usługi danej linii wynika z joina `product_id → products.service_code` (zob. `products`, `services`).

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

**Faza 2 — L01 (Microsoft Norge) rozbite na kilka faktur/miesiąc** (nie 1 płaska pozycja 85 000 NOK) — `supplier_invoice_generator.MICROSOFT_COST_LINES`: M365 E3 licencje, Visual Studio/narzędzia deweloperskie, wsparcie CSP/Premier. Suma bazowa 2019 = 18 100 NOK/mies., z inflacją +3%/rok (`apply_annual_inflation`, w przeciwieństwie do L02-L08, które pozostają płaskie). `invoice_number` dla L01 ma dodatkowy sufiks `-{1..3}` (np. `L01-2024-01-1`).

**Faza 6 — "Azure hosting" (4. pozycja, 35 000 NOK/mies. płaska) USUNIĘTA stąd**, zastąpiona COGS pass-through skalującym się z liczbą klientów S02 (konto 4291, zob. `accounts` wyżej) — koszt odsprzedaży, nie stały koszt operacyjny.

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
| voucher_type | TEXT | INCOMING_INVOICE / SALARY / BANK / MANUAL / **OPERATING_COST (Faza 3)**. **Nigdy INVOICE** (zob. ograniczenie na górze dokumentu) |

Znaczenie biznesowe: nagłówek zapisu księgowego. **Nie zawiera przychodu ze sprzedaży** — tylko koszty (faktury zakupu, payroll, ruchy bankowe, Faza 3: kantyna/reprezentacja/transport/sprzęt wdrożeniowy) i kapitał zakładowy. `OPERATING_COST` (Faza 3, `generators/opex_generator.py`) — koszty gotówkowe bez odpowiadającego dokumentu źródłowego (w przeciwieństwie do `INCOMING_INVOICE`, które zawsze mają `SupplierInvoice`).

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
| employee_id | INTEGER (FK) | Tylko 12 z 17 pracowników loguje godziny (działy Leveranse/Teknologi, bez E05) |
| project_id | INTEGER (FK) | NULL dla INTERNAL/SICK |
| activity_type | VARCHAR(20) | BILLABLE / INTERNAL / SICK |
| hours | NUMERIC(4,1) | Godziny, suma BILLABLE+INTERNAL = 7.5/dzień (albo SICK=0) |

Znaczenie biznesowe: timesheet konsultantów. **Nie generuje żadnych postingów księgowych** — czysto operacyjne dane (nie ma wpływu na P&L, niezależne od `salary_generator`). Ograniczenie: BILLABLE tylko do projektów, których klient jest już onboardowany i jeszcze nie odszedł (churn) — w przeciwnym razie cały dzień loguje się jako INTERNAL.

**Faza 6 — dwa modele dzienne wg działu** (`hours_generator.py`, zastępują wzorzec "jeden klient dziennie" z Fazy 4 — realizm danych, bez wpływu na przychód/payroll):
- **Leveranse (support)** — model ticketowy (`generate_daily_support_hours`): konsultant obsługuje 2-5 klientów dziennie, krótkie bloki godzin proporcjonalne do segmentu (`TICKET_AVG_HOURS`), suma billable dąży do losowego celu 5,5-7,0h.
- **Teknologi (projekty)** — cykl życia klienta (`client_lifecycle_phase`): pełny dzień (7,5h) u klienta w fazie ONBOARDING (pierwsze 2-6 tygodni od `onboarding_date`, zależnie od segmentu), rozproszona konserwacja (jak model ticketowy) u klientów w fazie MAINTENANCE poza tym. Mały zespół (2 billable Teknologi) prowadzi jeden aktywny projekt wdrożeniowy naraz (`CONCURRENT_ONBOARDING_CAPACITY=1`).

### projects
| Kolumna | Typ | Opis |
|---|---|---|
| id | SERIAL (PK) | 1-50, `numeric_id("PRJ001")..("PRJ050")` (Faza 4: 1:1 z `customers`, nie 8 ręcznie utrzymywanych wpisów) |
| number | VARCHAR(20) (UNIQUE) | "PRJ001"-"PRJ050" — ten sam numer co odpowiadający `customer_id` |
| customer_id | INTEGER (FK) | → customers.id (1:1, dokładnie jeden projekt per klient) |
| start_date | DATE | **Faza 4**: = `customers.onboarding_date` (naprawione poprzednie mylące ograniczenie — przed Fazą 4 zawsze 2026-01-01/03-01, data założenia rekordu w katalogu, nie data współpracy) |
| end_date | DATE | Zawsze NULL |
| status | VARCHAR(20) | Zawsze "ACTIVE" |

Znaczenie biznesowe: kontener godzin konsultanckich per klient — używany wyłącznie przez `hour_entries.project_id`, nie ma bezpośredniego związku z fakturowaniem (`orders`). **Faza 4**: rozszerzone z 8 (tylko część klientów, wybranych ręcznie) do 50 (wszystkie, w tym SMB, które wcześniej nie miały żadnego projektu) — niezbędne dla dynamicznego przydziału konsultantów (`hours_generator.assign_customers_to_consultants`), zastępującego statyczny `EMPLOYEE_PROJECT_MAP` sprzed tej fazy.

---

## Znane ograniczenia całościowe

1. **Brak postingów przychodowych** (konta 3000/3100) — zob. nagłówek dokumentu. Przychód wyłącznie w `orders`/`order_lines`.
2. **`bank_transactions` wymaga ręcznego doreperowania po każdym `TRUNCATE`** — `scripts/fix_outgoing_transactions.py` uzupełnia historyczne OUTGOING, ale trzeba go uruchomić po każdym pełnym resecie danych.
3. **Metadane Fazy 1** (`customers.segment/onboarding_date/churn_date/price_multiplier`, `services`, `products.service_code`) istniały wcześniej **tylko w Pythonie** (`roster.py`) — teraz są też w Supabase, ale historyczne zapytania/dashboardy pisane przed Fazą 1 mogły je pomijać.
4. **`projects.start_date` = `customers.onboarding_date` od Fazy 4** (przed Fazą 4 było niezależne, statyczne 2026-01-01/03-01 — ograniczenie NAPRAWIONE, zostawione w historii jako przykład wcześniejszej pomyłki projektowej).
5. **RLS włączone bez własnych polityk zapisu** — tylko `postgres` (bypass RLS) może pisać; rola `analyst` ma czysty odczyt (SELECT) na 14 tabelach transakcyjnych/referencyjnych.
6. **Brak rotacji kadry** (`employments.end_date` zawsze NULL) i **niski churn klientów** (K09, K15 — oba SMB) — model celowo prosty, nie pełna symulacja dynamiki portfela.
7. **`services` tabela pokazuje tylko `LEGACY_SERVICES`** (Faza 4) — `SCALE_SERVICES` (ceny dla klientów onboardowanych od 2023-01-01) istnieje tylko w kodzie Python, nie w Supabase. Zob. sekcja `services` i `customers` wyżej.
8. **Extra-consulting (S04 poza K06) nie działa w trybie dziennym `run_daily.py`** — `should_generate_extra_consulting`/K06-style consulting działają tylko w `generate_monthly_orders` (backfill historyczny), nie w rytmie dziennym produkcyjnym. Zob. `SESSION_HANDOFF.md` (Faza 2).
9. **Pensja E17 (950 000 NOK/rok)** ustalona pod presją kalibracji budżetu płacowego Fazy 4 (top-down z celu marży) — **nie z analizy rynkowej płac w Norwegii**, zostawiona bez zmian w Fazie 6 (headcount, nie stawka, był dźwignią tamtej korekty). Do ewentualnej rewizji, jeśli ktoś dalej kalibruje model względem realnych stawek.
10. **Retry/reconnect istnieje dla backfillu** (`run_backfill_daily()`, `terminate_stale_sessions()`) **ale sam proces nie przetrwa faktycznego wyłączenia/uśpienia komputera ani zawieszonego (nie failed-fast) połączenia sieciowego** — w takim wypadku proces wisi bez logowania błędu (obserwowane w Fazie 6: `ps` pokazywał proces żywy, ale bez przyrostu czasu CPU i bez nowych wierszy w bazie przez >30 min) i trzeba go zabić ręcznie oraz wznowić backfill od ostatniego przetworzonego dnia (`SELECT MAX(date) FROM hour_entries`) — sprawdzać żywotność procesu po **realnym postępie w bazie**, nie tylko po tym czy proces nadal istnieje.
11. **Faza 6 — GitHub Actions `daily.yml` (cron 3x/dzień na `main`) zapisuje do TEJ SAMEJ produkcyjnej bazy Supabase** — podczas backfillu tej fazy cron odpalił się starym (przed-Fazą-6, 38-osobowym) kodem i wstawił skażone `hour_entries`/`bank_transactions` dla bieżącego dnia PO `TRUNCATE`, zanim zauważono problem. Workflow został ręcznie wyłączony w GitHub UI na czas backfillu — **wymaga ponownego włączenia dopiero PO wypchnięciu commitu Fazy 6 na `main`**, inaczej znów odpali się starym kodem. Każdy przyszły reset danych musi najpierw wstrzymać ten workflow.
