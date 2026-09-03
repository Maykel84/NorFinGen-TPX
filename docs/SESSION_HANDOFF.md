# NorFinGen — Session Handoff

Data sporządzenia: 2026-07-09. Ostatni tag przed tą fazą: `v5.4a-future-date-fix`. Ta faza: `v5.5-faza6-kalibracja-rynkowa`.

**Faza 6 — poza pierwotnym 5-fazowym planem** — koryguje model wolumenu pracy konsultantów i kalibruje marżę operacyjną względem realnych danych rynkowych (Brønnøysundregistrene), zamiast dalszego zgadywania. Zastępuje Fazę 4 w zakresie harmonogramu zatrudnienia.

---

## 1. Kalibracja rynkowa — punkt wyjścia

4 realne norweskie firmy IT (Brønnøysundregistrene/Proff.no, NACE 62.020/62.200/62.030):

| Firma | Pracownicy | Przychód/prac. | Marża EBIT |
|---|---|---|---|
| IT Consult AS (holding, reseller) | 40 | 5,20M | 3,8% |
| Computas AS (duża, rozwojowa) | 329 | 2,62M | 3,0% |
| Kantega AS (100% pracownicza, czysty consulting) | 186 | 1,65M | 9,7% |
| **Garnes Data AS (IT drift/support — odpowiednik S01)** | **17** | **3,48M** | **5,4%** |

Wniosek: realne marże branżowe to 3-10%, nie poprzednio skalibrowane 14,6-21% (Fazy 3-5). Firmy z komponentem odsprzedaży (Azure/licencje/narzędzia) mają wysoki przychód/pracownika, ale niską marżę — koszt "znika" w COGS pass-through, nie w płacach. Garnes Data AS (ten sam segment usługowy co S01) jest głównym benchmarkiem: 17 pracowników, marża 5,4%.

Nowy cel: **TARGET_MARGIN = 0,07** (środek zakresu 5,5-9%), **headcount ~17**.

---

## 2. Offline sanity-check #1 — sprzeczność COGS S02-only

Pierwsza próba (S02-only Azure COGS, zgodnie z pierwotną treścią zadania) wykryła sprzeczność: rzeczywisty przychód generatora w 2026 to **~52,4M NOK** (nie zakładane ~35M). Przy tym przychodzie i realistycznym COGS S02 (ograniczonym własnym przychodem S02, ~13,1M NOK/rok, 33 klientów Enterprise+Mid) top-down dawał headcount **~31**, nie ~17 — S02 fizycznie nie mógł wypełnić luki.

Zdecydowano (opcja użytkownika): **rozszerzyć COGS pass-through na S01** (Managed IT Support), zakotwiczone w Garnes Data AS (opex+COGS/przychód = 61,6%, realny odpowiednik segmentu S01). Cel: `(opex_tradycyjny + cogs_s02 + cogs_s01) / przychód ≈ 58-62%`.

---

## 3. Implementacja

### Zadanie 1 — cena S04
`base_price_enterprise/mid/smb` = 950 NOK/h (z 1450), obie kohorty cenowe (`LEGACY_SERVICES`/`SCALE_SERVICES`). Ceny S01/S02/S03 **niezmienione** (świadoma decyzja — trzecia próba kalibracji, ceny sprzedaży zostają stabilne, dźwignią jest COGS + headcount).

### Zadanie 2 — COGS S02 (Azure, konto 4291)
`roster.calc_azure_cogs_monthly()` — Enterprise 22 000 / Mid-market 11 500 NOK/mies. (baza 2019, +inflacja +3%/rok), tylko klienci kupujący S02. Zastępuje płaską pozycję "Azure hosting" (35 000 NOK/mies.) usuniętą z `supplier_invoice_generator.MICROSOFT_COST_LINES` (L01 teraz 3 pozycje zamiast 4, baza 18 100 NOK/mies. zamiast 53 100).

### Zadanie 2b (rozszerzenie po sanity-checku #1) — COGS S01 (konto 4292)
`roster.calc_s01_cogs_monthly()` — Enterprise 53 000 / Mid-market 26 500 / SMB 13 300 NOK/mies. (baza 2019, waga 4:2:1), **wszyscy** aktywni klienci (S01 kupują wszystkie segmenty). Voucher: `_cogs_accrual_voucher` (DR 4292 / CR 2400 Leverandørgjeld), analogicznie do 4291.

### Zadanie 3 — model ticketowy Leveranse
`hours_generator.generate_daily_support_hours()` — konsultant obsługuje 2-5 klientów dziennie (zamiast jednego), krótkie bloki godzin proporcjonalne do segmentu (`TICKET_AVG_HOURS`: Enterprise 1,2h / Mid 0,9h / SMB 0,6h), suma billable dąży do losowego celu 5,5-7,0h. Czysto realizm danych — **nie wpływa na przychód ani payroll** (te są niezależne od `hour_entries`).

### Zadanie 4 — cykl życia klienta Teknologi
`hours_generator.client_lifecycle_phase()` — ONBOARDING (pełny dzień, 7,5h) przez 2-6 tygodni od `onboarding_date` (zależnie od segmentu), potem MAINTENANCE (model ticketowy jak Leveranse). `CONCURRENT_ONBOARDING_CAPACITY=1` — mały zespół (2 billable Teknologi: E08, E15) prowadzi jeden projekt wdrożeniowy naraz.

### Zadanie 5 — headcount 38→17
`roster.EMPLOYEES` obcięte do E01-E17 (usunięte E18-E38, 21 osób z Fazy 4). E17 (Vegard Lien, Leveranse, 2022-10-03) — jedyne dociążenie po fuzji 2022-09. Zespół **przestaje rosnąć z portfelem klientów** (12→48 aktywnych 2019→2026) — uzasadnienie: model ticketowy (Zadanie 3) pozwala jednemu konsultantowi obsłużyć wielu klientów, a większość kosztu obsługi jest kosztem materiałowym (COGS), nie osobowym. `TARGET_MARGIN` 0,19→0,07 w `roster.py`.

### Zadanie 6 — testy
`tests/test_faza6_market_calibration.py` (nowy plik): skalowanie COGS S01/S02, headcount w [14,20], **test regresyjny marży** (uruchamia prawdziwy `run_backfill()` w pamięci, sprawdza 2025/2026 w [5,5%, 9%]), model ticketowy Leveranse, cykl życia Teknologi. Zaktualizowane: `test_faza4_scaling.py` (usunięte testy 22-hire, zastąpione `test_only_one_new_hire_after_merger`), `test_faza5_feriepenger_audit.py`/`test_hours_generator.py`/`test_salary_generator.py`/`test_seed_roster_payroll.py`/`test_supplier_invoice_generator.py` (referencje do usuniętych E18-E38 zastąpione istniejącymi pracownikami, liczby dostosowane). **171/171 testów przechodzi.**

---

## 4. Offline sanity-check #2 (finalny, przed backfillem)

Uruchomiony prawdziwym kodem generatorów (`run_backfill()` w pamięci, `persist_fn` tylko agreguje kwoty — nie formułą/szacunkiem):

| Rok | Przychód | Płacowe | Opex | COGS | Wynik | Marża | opex+COGS/przychód |
|---|---|---|---|---|---|---|---|
| 2019 | 7,3M | 4,7M | 1,9M | 2,6M | -1,9M | -25,7% | 58,4% |
| 2020 | 17,8M | 6,9M | 1,8M | 5,6M | 3,4M | 19,1% | 41,8% |
| 2021 | 19,9M | 8,4M | 1,9M | 6,1M | 3,5M | 17,4% | 40,3% |
| 2022 | 23,3M | 11,2M | 1,9M | 7,5M | 2,7M | 11,5% | 40,3% |
| 2023 | 31,8M | 15,6M | 2,0M | 11,9M | 2,3M | 7,1% | 43,9% |
| 2024 | 38,5M | 16,3M | 2,2M | 17,3M | 2,8M | 7,3% | 50,5% |
| **2025** | 44,8M | 16,7M | 2,2M | 22,5M | 3,4M | **7,5%** | 55,1% |
| **2026** (pełny/częściowy) | 52,4M | 8,8M* | 1,3M* | 16,4M* | 2,0M* | **6,9-7,9%** | 59,5-64,4% |

*2026 częściowy — tylko do rzeczywistego cutoff (`date.today()`).

Płynny spadek marży 2020→2026 do celu 5,5-9%, nigdy poniżej progu bezpieczeństwa w latach dojrzałych (2025-2026). Trajektoria zatrudnienia: 6 (2019) → 8 (2020) → 10 (2021) → 16 (2022 po fuzji) → **17 (2022-10, E17)** → 17 (bez zmian do 2026).

---

## 5. Reset i backfill — wykonane

**TRUNCATE** wszystkich 10 tabel transakcyjnych (RESTART IDENTITY CASCADE), potem:
1. `run_backfill.py --start 2019-01-01` (tryb monthly) — bez błędów.
2. `run_backfill.py --mode daily --start 2019-01-01` (tryb daily, bank_transactions/hour_entries) — **dwie przerwy sieciowe**:
   - Crash przy 2023-01-13 (DNS resolution failure, 3 nieudane próby retry) — wznowiono `--start 2023-01-13`.
   - Zawieszenie (proces żywy, ale bez postępu w bazie >30 min, prawdopodobnie zawieszone gniazdo TCP bez fail-fast) przy ~2024-10-21 — zabito proces ręcznie, `terminate_stale_sessions()`, wznowiono `--start 2024-10-31` (`python -u` dla niebuforowanego logu, żeby odróżnić bufor stdout od realnego zawieszenia następnym razem). Zob. `DATA_DICTIONARY.md` p. 10.
3. `scripts/fix_outgoing_transactions.py` — naprawiono 703 faktury PAID bez transakcji OUTGOING.

**Stan bazy po backfillu**: orders=1777, order_lines=3633, supplier_invoices=725, salary_transactions=90, payslips=1126, salary_specifications=2178, vouchers=3289, postings=6665, bank_transactions=1929 (OUTGOING 709 / INCOMING 1220), hour_entries=54228. `MAX(employee_id)` w `hour_entries` = 17, zero wierszy z `employee_id > 17`.

### ⚠️ Incydent uboczny — GitHub Actions cron nadpisał dane starym kodem

`.github/workflows/daily.yml` odpala `run_daily.py` 3x/dzień (07:00/11:00/16:00 UTC, pn-pt) **na tej samej produkcyjnej bazie Supabase**, checkout z `main`. Podczas backfillu tej fazy cron odpalił się (16:00 UTC slot) **starym, przed-Fazą-6 kodem** (38 pracowników) i wstawił 57 skażonych `hour_entries` + 2 `bank_transactions` dla bieżącego dnia (`employee_id` do 38) — PO `TRUNCATE`, zanim backfill dzienny zdążył tam dotrzeć. Wykryte i wyczyszczone (`DELETE ... WHERE date='<dzień>'`) przed wznowieniem backfillu. **Workflow ręcznie wyłączony przez użytkownika w GitHub UI** na czas dokańczania tej fazy.

**WAŻNE dla następnej sesji**: `daily.yml` musi zostać **ponownie włączony DOPIERO PO** wypchnięciu commitu tej fazy na `main` — w przeciwnym razie kolejne uruchomienie crona znów wstawi dane starym (38-osobowym, bez COGS S01/S02) kodem. Każdy przyszły pełny reset danych (TRUNCATE) powinien najpierw wstrzymać ten workflow.

---

## 6. Weryfikacja końcowa (Zadanie 7)

Zapytanie SQL z promptu Fazy 6 (przychód z `orders`/`order_lines`, płacowe/opex/COGS z `vouchers`/`postings` wg zakresów kont 5000-5999/6000-7999/4000-4999) na żywej bazie po backfillu:

| Rok | Przychód | Płacowe | Opex | COGS | Wynik | Marża |
|---|---|---|---|---|---|---|
| 2019 | 7 306 506 | 4 702 822 | 1 859 931 | 2 619 500 | -1 875 747 | -25,7% |
| 2020 | 17 770 538 | 6 948 806 | 1 841 673 | 5 579 095 | 3 400 964 | 19,1% |
| 2021 | 19 922 564 | 8 436 433 | 1 887 916 | 6 135 291 | 3 462 924 | 17,4% |
| 2022 | 23 294 689 | 11 210 947 | 1 935 045 | 7 462 222 | 2 686 476 | 11,5% |
| 2023 | 31 771 579 | 15 582 464 | 2 032 553 | 11 904 767 | 2 251 794 | 7,1% |
| 2024 | 38 538 133 | 16 257 989 | 2 151 424 | 17 312 770 | 2 815 950 | 7,3% |
| **2025** | 44 842 653 | 16 745 730 | 2 200 839 | 22 512 883 | 3 383 200 | **7,5%** |
| **2026** | 28 733 124 | 8 787 672 | 1 275 496 | 16 409 085 | 2 260 871 | **7,9%** |

**Obie wartości progu bezpieczeństwa (2025: 7,5%, 2026: 7,9%) w zakresie 5,5-9%.** Zgodne co do rzędu wielkości z offline sanity-checkiem (drobne różnice — dokładny cutoff dnia, kolejność zaokrągleń).

---

## 7. Co zostało z prompta niewykonane / świadomie ograniczone

- Nie zaimplementowano osobnej fazy STABILIZATION w cyklu życia klienta Teknologi (tylko ONBOARDING→MAINTENANCE) — zadanie nie podało konkretnego czasu trwania stabilizacji, w przeciwieństwie do ONBOARDING (`ONBOARDING_DURATION_WEEKS`).
- `test_headcount_matches_realistic_target` **nie wymagał zmiany zakresu** (14-20) — 17 mieści się bez korekty, zgodnie z oczekiwaniem z promptu.
- `git push` i ponowne włączenie `daily.yml` — świadomie odłożone do jawnej zgody użytkownika (zob. p. 5, incydent uboczny).

---

## 8. Kontekst poprzednich faz

Faza 6 następuje po zamknięciu 5-fazowego planu (`v5.0-faza1-fundament` → `v5.4-faza5-final`) i hotfixu dat w przyszłość (`v5.4a-future-date-fix`, zob. commit `b482ac0` i wcześniejsza wersja tego dokumentu w historii git dla pełnych szczegółów). Zastępuje harmonogram zatrudnienia Fazy 4 (38 osób, TARGET_MARGIN 0,19) nowym, skalibrowanym względem realnych danych rynkowych (17 osób, TARGET_MARGIN 0,07). Kluczowa lekcja pozostaje aktualna: offline sanity-check PRZED każdym pełnym backfillem, top-down kalibracja zatrudnienia z celu marży (nie z zgadywanych godzin/przychodu per konsultant), `random.Random(string)` nigdy `hash()`.

---

## 9. Dodatek — kody branżowe NACE/SN2007 (`v5.6-nace-classification`)

Niezależny od modelu finansowego dodatek metadanych — **nie zmienia cen/kosztów/przychodu, nie wymaga backfillu transakcyjnego**.

- **Kod główny firmy**: `roster.COMPANY_NACE_CODE = "62.020"` (Konsulentvirksomhet tilknyttet informasjonsteknologi og forvaltning og drift av it-systemer) — obejmuje S01+S02+S03+S04 naraz. Realny odpowiednik: Garnes Data AS (benchmark Fazy 6), zarejestrowany pod pokrewnym 62.030.
- **Kod sekundarny**: pominięty — udział S04 (konsulting) w przychodzie 2025-2026 to **1,9%** (zweryfikowane SQL na żywej bazie, `order_lines` JOIN `products.service_code`), daleko poniżej progu 20% z zadania. Cena S04 obniżona w Fazie 6 do 950 NOK/h — sprawdzono aktualny stan, nie założono wyniku sprzed tej zmiany.
- **Kody klientów**: `roster.CUSTOMER_NACE` — dict `customer_number -> NaceCode(code, name)` dla wszystkich 50 klientów (K01-K50), dopasowany do rzeczywistej nazwy firmy (nie losowo), 18 różnych sektorów. Nowe kolumny `customers.nace_code`/`customers.nace_name` (schema.sql, `seed_reference_data()`, `scripts/migrate_customer_metadata.py` — ten sam wzorzec `ON CONFLICT DO UPDATE` co pozostałe metadane Fazy 1).
- **Weryfikacja**: `tests/test_nace_classification.py` (4 testy, 175/175 łącznie), migracja uruchomiona na żywej bazie, zapytanie kontrolne (rozkład przychodu per sektor) pokazuje sensowny podział bez braków (`nace_code IS NULL` → 0 wierszy).

---

## 10. Poprawki eksportu (`v5.7-export-bi-ready`) — ID kontrahentów, kody pocztowe, payroll per pracownik, ujednolicenie nazewnictwa

Niezależny od modelu finansowego — **nie zmienia logiki generowania danych, cen ani kosztów**, wyłącznie `export_excel.py`/`export_csv.py`/`export_queries.py` + metadane adresowe. SQL zapytań wydzielony do `export_queries.py` (Faza 6, druga sesja) — ta zmiana edytuje tylko ten jeden plik, oba skrypty eksportu automatycznie dziedziczą poprawki.

### 10a. Mapa zmian nazw kolumn (stara polska → nowa, Tripletex/DB-zgodna)

**PL_miesiecznie:**
| Stara nazwa | Nowa nazwa |
|---|---|
| `miesiac` | `month` |
| `przychody` | `revenue` |
| `koszty_pracownicze` | `labor_cost` |
| `koszty_operacyjne` | `operating_cost` |
| `wynik_operacyjny` | `operating_result` |
| `cogs` | *(bez zmian — już angielskie z Fazy 6)* |

**Faktury_sprzedazy:**
| Stara nazwa | Nowa nazwa |
|---|---|
| `klient` | `customer_name` |
| `ilosc` | `count` |
| `cena_netto` | `unit_price_excluding_vat_currency` |
| `wartosc_netto` | `amount_excluding_vat_currency` |
| `wartosc_brutto` | `amount_currency` |
| *(brak)* | **`customer_id`** (nowa kolumna, Zadanie 1) |
| *(brak)* | **`postal_code`** (nowa kolumna, Zadanie 2) |
| `order_id`, `order_date`, `invoice_date`, `customer_number`, `city` | bez zmian |

**Faktury_zakupu:**
| Stara nazwa | Nowa nazwa |
|---|---|
| `dostawca` | `supplier_name` |
| `netto` | `amount_excluding_vat_currency` |
| `vat` | `vat_amount_currency` |
| `brutto` | `amount_currency` |
| *(brak)* | **`supplier_id`** (nowa kolumna, Zadanie 1) |
| *(brak)* | **`postal_code`** (nowa kolumna, Zadanie 2) |
| `invoice_number`, `invoice_date`, `payment_due_date`, `status` | bez zmian |

**Payroll_miesiecznie:**
| Stara nazwa | Nowa nazwa |
|---|---|
| `miesiac` | `month` |
| `data_wyplaty` | `date` |
| `liczba_pracownikow` | `headcount` |
| `laczne_netto` | `total_net_payroll` |

**Postingi_GL:**
| Stara nazwa | Nowa nazwa |
|---|---|
| `opis` | `description` |
| `konto` | `account_number` |
| `kwota` | `amount` |
| `vat` | `vat_amount` |
| `date`, `voucher_type`, `customer_id`, `supplier_id`, `employee_id` | bez zmian |

**Nowy arkusz — Payroll_per_pracownik** (Zadanie 3, nazwa arkusza po polsku, jak zaznaczono w zadaniu — tylko kolumny są angielskie): `date`, `month`, `employee_id`, `employee_name`, `department_name`, `net_amount`, `gross_amount`, `tax_amount`.

**Nazwy arkuszy (klucze `queries`/`QUERIES`) nie zmienione** — `PL_miesiecznie`, `Faktury_sprzedazy`, `Faktury_zakupu`, `Payroll_miesiecznie`, `Postingi_GL`, `Payroll_per_pracownik` — zgodnie z Zadaniem 0.

### 10b. Świadome odstępstwa od podanych fragmentów kodu

- **`ps.gross_amount`/`ps.tax_amount` z przykładu Zadania 3a NIE ISTNIEJĄ w `payslips`** (tabela ma tylko `amount` = netto, zob. `DATA_DICTIONARY.md`) — gross/tax policzone przez `LEFT JOIN` z `salary_specifications` zagregowanym per `payslip_id`: `gross_amount` = suma `wage_type_id IN (100, 260)` (Fast lønn + Feriepenger), `tax_amount` = `-SUM(wage_type_id = 920)` (Skattetrekk, przechowywane jako ujemne). Zob. `models/salary.py` dla stałych `WAGE_TYPE_*`.
- **`e.department`/`e.role` z przykładu Zadania 3a NIE ISTNIEJĄ na `employees`** — tabela ma tylko `department_id` (FK), żadnej kolumny `role` w ogóle (rola istnieje wyłącznie w `EmployeeSeed.role` w Pythonie, nigdy nie była persystowana do Supabase). `department_name` doklejone przez `LEFT JOIN departments`; `role` **pominięte całkowicie** z eksportu — dodanie go wymagałoby rozszerzenia schematu (nowa kolumna na `employees`), co wykracza poza "poprawka eksportu" tego promptu.
- **Wewnętrzne aliasy CTE w `PL_miesiecznie` też przepisane na angielski** (`przychody`→`revenue_cte`, `koszty`→`cost_cte`, `miesiac`→`month` w środku zapytania) — nie tylko finalne kolumny wyjściowe. Wychwycone przez `tests/test_export_naming.py::test_export_queries_use_consistent_naming` (sprawdza WSZYSTKIE aliasy `AS` w tekście SQL, nie tylko ostatni `SELECT`).
- **`suppliers.postal_code` zostaje `NULL`** — `SupplierSeed` (roster.py) nigdy nie miał pola `city` (dostawcy nie mają przypisanego miasta w tym modelu, potwierdzone `DATA_DICTIONARY.md`), więc nie ma z czego wyprowadzić kodu pocztowego bez wymyślania nowych danych adresowych spoza zakresu zadania. Kolumna `suppliers.postal_code` (już istniała w schema.sql, nieużywana) zostaje pusta, udokumentowane świadomie.
- **Żadnego `ALTER TABLE ... ADD COLUMN postal_code`** — `customers.postal_code`/`suppliers.postal_code` **już istniały** w oryginalnym `CREATE TABLE` (schema.sql), po prostu nigdy nie były wypełniane. Zadanie 2b z promptu było już zrealizowane wcześniej niż ten prompt zakładał.

### 10c. Breaking change dla zewnętrznych narzędzi

**Brak pliku dashboardu HTML w repo** (`find . -iname "*dashboard*"` → nic) — jeśli istnieje POZA repo (np. lokalnie u użytkownika, Tableau/Power BI z zapisanymi zapytaniami), **złamie się** przy odczycie starych polskich nazw kolumn (`klient`, `dostawca`, `wartosc_netto`, `wartosc_brutto`, `cena_netto`, `ilosc`, `przychody`, `koszty_pracownicze`, `koszty_operacyjne`, `wynik_operacyjny`, `miesiac`, `liczba_pracownikow`, `laczne_netto`, `opis`, `konto`) — zob. mapa w 10a. **Nie naprawiane w tym prompcie** (świadomie, zgodnie z zadaniem) — jeśli taki dashboard/raport istnieje, wymaga osobnej aktualizacji referencji do kolumn.

### 10d. Weryfikacja

`tests/test_export_naming.py` (4 testy, offline — sprawdza tekst `export_queries.QUERIES` i `roster.py`, bez połączenia do bazy, zgodnie z konwencją reszty pakietu testów) + **179/179 łącznie**. Migracja (`scripts/migrate_customer_metadata.py`) uruchomiona na żywej bazie — `customers.postal_code IS NULL` → 0 wierszy. Oba eksporty (`export_excel.py`, `export_csv.py`) wygenerowane i nagłówki sprawdzone programowo (`openpyxl`, brak GUI Excela w tym środowisku) — wszystkie 6 arkuszy mają spójne, angielskie nazwy kolumn.

---

## 11. Krok 2 — dostęp read-only gotowy pod Power BI

**Odkrycie przy okazji weryfikacji (Zadanie 1c)**: RLS z Fazy 1 miał komplet poprawnych polityk `SELECT` na dokładnie 14 tabelach z promptu (zweryfikowane `pg_policies` na żywej bazie — nic nie brakowało), **ale rola `analyst` nigdy nie dostała bazowego `GRANT SELECT`** — `information_schema.role_table_grants` dla `analyst` był pusty. RLS filtruje wiersze, nie zastępuje uprawnień tabelowych — bez GRANT-a każde zapytanie kończyłoby się `permission denied` zanim RLS w ogóle by się uruchomił. `analyst` była więc od Fazy 1 rolą deklaratywnie poprawną, ale funkcjonalnie bezużyteczną do odczytu (niewidoczne wcześniej, bo `NOLOGIN` — nikt się nią nie logował).

Naprawione w `schema.sql` (idempotentne, bezpieczne do wielokrotnego `ensure_schema()`):
```sql
GRANT USAGE ON SCHEMA public TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analyst;
```
`ALL TABLES` (nie lista 14 z promptu) — świadome rozszerzenie: objęło też 6 tabel referencyjnych bez RLS (`accounts`, `departments`, `products`, `vat_types`, `employments`, `salary_specifications`), bez których Power BI nie mogłoby np. rozwiązać nazw kont przy rozbiciu kosztów czy nazw działów przy payrollu — bez tych tabel eksport BI byłby technicznie "read-only", ale praktycznie bezużyteczny do analizy. `ALTER DEFAULT PRIVILEGES` pilnuje, żeby przyszłe tabele (kolejne fazy) nie wymagały ręcznego GRANT-a.

**`powerbi_reader`** — nowa rola `LOGIN`, `CONNECTION LIMIT 3`, dziedziczy `analyst` przez `GRANT analyst TO powerbi_reader` (żadnej duplikacji polityk). Tworzona/rotowana przez `scripts/setup_powerbi_reader.py` — hasło losowe (32 znaki, `secrets`), wypisywane WYŁĄCZNIE na stdout, nigdy do pliku. **Hasło pokazane w tej sesji użytkownikowi bezpośrednio w terminalu — nie zapisane tutaj ani nigdzie w repo.** Każde ponowne uruchomienie skryptu rotuje hasło (poprzednie przestaje działać) — świadomy, bezpieczny sposób na "zapomniałem/skompromitowane hasło", nie bug.

**Świadome odstępstwo od promptu**: pominięty jawny `ALTER ROLE powerbi_reader WITH NOCREATEDB NOCREATEROLE NOSUPERUSER` (był w pierwszej wersji skryptu) — Supabase'owa rola `postgres`, którą łączy się ten projekt, nie jest prawdziwym superuserem (ma tylko `CREATEROLE`), więc Postgres odrzucał tę komendę (`Only roles with the SUPERUSER attribute may alter roles with the SUPERUSER attribute`) i wywalał całą transakcję (DDL w Postgresie jest transakcyjne — nic się nie zapisywało, zweryfikowane `SELECT * FROM pg_roles` po błędzie). Usunięte jako zbędne: świeżo utworzona `CREATE ROLE ... WITH LOGIN` i tak domyślnie nie ma żadnego z tych atrybutów.

**Weryfikacja end-to-end** (nie tylko "GRANT się wykonał") — połączenie jako `powerbi_reader` z prawdziwym hasłem: `SELECT COUNT(*) FROM orders` (RLS) i `SELECT COUNT(*) FROM accounts`/`departments` (referencyjne, bez RLS) działają; `INSERT INTO orders (...)` poprawnie odrzucony (`InsufficientPrivilege`). Test wykonany przez rotację hasła w locie (żeby nie zostawiać działającego hasła w historii poleceń/logach) — finalne, aktualne hasło wygenerowane osobnym, czystym uruchomieniem skryptu po teście.

**Connection string dla Power BI** — `username` musi być w formacie poolera Supabase `powerbi_reader.<project_ref>`, NIE sam `powerbi_reader` — skrypt wypisuje to poprawnie sformatowane. Zob. `DATA_DICTIONARY.md` (sekcja "Dostęp read-only") po pełne instrukcje Power BI Desktop.

### 11a. Zadanie 2 — widoki BI, dwa poprawione błędy ze szkicu w prompcie

`v_sales_flat`, `v_pl_monthly`, `v_headcount_monthly` — pełny opis w `DATA_DICTIONARY.md` ("Widoki BI"). Skrót dwóch rzeczy, których **nie skopiowałem bezrefleksyjnie** ze szkicu SQL z promptu:

1. **`v_pl_monthly` liczący revenue z `postings` (`account_number 3000-3999`) byłby zawsze pusty** — zweryfikowane na żywej bazie (`SELECT COUNT(*) FROM postings WHERE account_number BETWEEN 3000 AND 3999` → 0). To najstarsze, najczęściej powtarzane ograniczenie w tym projekcie (nagłówek `DATA_DICTIONARY.md` od Fazy 1): NorFinGen nie wywołuje realnego Tripletex API, więc automatyczny Voucher przychodowy (który Tripletex tworzyłby przy `invoiceDate`) nigdy nie powstaje lokalnie. Poprawione na ten sam wzorzec co `export_queries.PL_miesiecznie` (CTE `revenue_cte` z `orders`/`order_lines` FULL OUTER JOIN CTE `cost_cte` z `postings`). Zweryfikowane na żywej bazie po naprawie: `v_pl_monthly` ma realny przychód w 90/91 miesiącach (zgodny z `PL_miesiecznie.csv`).
2. **`v_sales_flat.amount_including_vat_currency` to ALIAS**, nie fizyczny rename `order_lines.amount_currency` — poprzednia sesja (rozmowa o zgodności z realnym Tripletex OpenAPI) tylko **zaproponowała** taki rename ("Koszyk 1"), nigdy nie został jawnie zaakceptowany ani wykonany. Widok daje poprawną nazwę w BI bez zmiany fizycznego schematu/generatorów.

Dodatkowo (nie ze szkicu, moja inicjatywa): wszystkie 3 widoki mają `security_invoker = true` (PG15+, Supabase = PG17) — bez tego widok czyta tabele źródłowe z uprawnieniami właściciela (`postgres`, omija RLS), nie odpytującej roli; znany footgun Postgresa. Dziś bez praktycznego znaczenia (polityki `USING (true)`), ale zapobiega cichemu ominięciu RLS w przyszłości.

**Zweryfikowane end-to-end jako `powerbi_reader`** (nie tylko `postgres`): wszystkie 3 widoki czytelne, `v_pl_monthly` ma niezerowy przychód.

**3 nowe testy offline** (regresja: revenue nie z postings, `security_invoker` obecny, GRANT na widokach) — **185 testów łącznie, 184 przechodzi + 1 test pre-istniejący (`test_margin_within_safety_threshold_2025_2026`) zaczął failować niezależnie od tej pracy** — zob. p. 11b.

### 11b. Odkryty przy okazji, niezwiązany dryf: marża 2026 wyszła poza próg bezpieczeństwa

`tests/test_faza6_market_calibration.py::test_margin_within_safety_threshold_2025_2026` failuje **od 2026-08-10** (miesiąc po kalibracji Fazy 6 z 2026-07-08/09), niezależnie od zmian w tej sesji (zweryfikowane `git stash` — failuje identycznie bez żadnych zmian Kroku 2). Margin 2026 (częściowy rok, do dzisiejszego cutoff) = **9,12%**, próg to [5,5%, 9%] — **0,12 punktu procentowego nad górną granicą**. Przyczyna: symulacja offline w pamięci (nie żywa baza — test woła `run_backfill(persist_fn=collect)`) jest wrażliwa na to, który dokładnie miesiąc jest "dzisiaj" w częściowym 2026 — w miarę jak realny czas płynie do przodu (miesiąc różnicy między kalibracją a teraz), mix miesięcy uwzględnionych w częściowym roku się zmienia i drobno przesuwa marżę.

**Naprawione osobno (2026-08-18, na wyraźną prośbę użytkownika)**: przyczyna dokładnie taka jak opisano wyżej — trwający miesiąc ma zawsze payroll=0 (księguje się dopiero na koniec miesiąca), ale pełny COGS/opex, co tymczasowo zawyża marżę kumulatywną. `run_backfill()` w teście ograniczony do `end_date=last_fully_closed_month_end(date.today())` zamiast domyślnego `date.today()` — test liczy marżę tylko z w pełni zamkniętych miesięcy. Zweryfikowane: 2025=7,54% (bez zmian), 2026=7,47% (do lipca) — oba w progu. **187/187 wtedy, później rozszerzone dalszymi naprawami poniżej.**

---

## 12. Naprawa: osierocone rekordy employees + brakujące OUTGOING dla payrollu (2026-08-18/19)

Zgłoszenie od użytkownika: opublikowany raport (`maykel84.github.io/raport`) pokazywał headcount=38 (nie 17) i fizycznie niemożliwą asymetrię `bank_transactions` (1264 INCOMING/187,6M vs 719 OUTGOING/17,5M). Diagnoza (osobna sesja, tylko SELECT-y, bez żadnych zmian) potwierdziła **dwa niezależne, prawdziwe problemy w bazie** — raport nie czytał złych/cache'owanych danych, baza faktycznie była w tym stanie.

### 12a. Krok 1 — 21 osieroconych rekordów `employees` (E18-E38)

**Przyczyna**: `TRUNCATE` Fazy 6 celowo pomijał tabele referencyjne (`employees`/`employments`, jak `customers`/`suppliers`) — świadoma decyzja z tamtej sesji. `seed_reference_data()` wstawia pracowników przez `INSERT ... ON CONFLICT (id) DO NOTHING`, co dodaje nowych, ale **nigdy nie usuwa** tych, którzy wypadli z `roster.EMPLOYEES`. Gdy Faza 6 zredukowała roster z 38 do 17, baza miała już wszystkie 38 wierszy od Fazy 4 — 21 nadmiarowych (E18-E38) nigdy nie zostało usuniętych. **Nie regresja Fazy 6 samej w sobie — przeoczenie w jej weryfikacji**: `hour_entries`/`payslips` sprawdzano wtedy (poprawnie, zawsze czyste — `employee_id` 1-17), ale samą tabelę `employees` nigdy.

**Naprawa**:
- Zweryfikowano `hour_entries`/`payslips`/`salary_specifications` (przez JOIN payslips — nie ma bezpośrednio `employee_id`) — zero referencji do `employee_id > 17`.
- `DELETE FROM employments WHERE employee_id > 17; DELETE FROM employees WHERE id > 17` — 21+21 usuniętych, `employees` teraz poprawnie 17.
- **`_prune_orphaned_employees()`** (nowa funkcja, `repository.py`) — wywoływana na starcie każdego `seed_reference_data()`, usuwa rekordy spoza aktualnego `roster.EMPLOYEES` automatycznie na przyszłość. Bezpieczna z konstrukcji: `employee_id` na `payslips`/`postings`/`hour_entries` nie ma `ON DELETE CASCADE` (zwykłe `REFERENCES`) — gdyby jakiś osierocony ID miał jednak prawdziwe dane transakcyjne, Postgres odrzuci `DELETE` naruszeniem FK zamiast po cichu skasować dane.
- **2 nowe testy offline** (mockowany kursor, wzorem `test_repository.py` — nie żywa baza jak sugerował prompt) — `test_prune_orphaned_employees_deletes_stale_ids`/`test_prune_orphaned_employees_no_op_when_db_matches_roster`.

### 12b. Krok 2 — payroll nigdy nie generował transakcji bankowej OUTGOING

**Przyczyna**: `bank_transaction_generator.py` od Tier 2 miał logikę WYŁĄCZNIE dla `Order` (INCOMING) i `SupplierInvoice` (OUTGOING) — payroll (największa pojedyncza pozycja kosztowa) nigdy nie był w zakresie. **Nie regresja — strukturalna luka od zawsze**, częściowo (błędnie) opisana wcześniej w `DATA_DICTIONARY.md` jako "artefakt kolejności wdrażania funkcji" — to niepełne wyjaśnienie, poprawione.

**Naprawa**:
- Nowe pole `BankTransaction.salary_transaction_id` (model + `bank_transactions.salary_transaction_id` FK w schemacie, z `UNIQUE (date, salary_transaction_id, transaction_type)` dla idempotencji) — **jawny FK, nie dopasowanie po opisie ILIKE**, zgodnie z sugestią w prompcie.
- **`generate_payroll_bank_transaction()`** (`bank_transaction_generator.py`) — **jedna zagregowana transakcja/miesiąc** (netto+skattetrekk+AGA), świadomie prostszy wybór niż trzy osobne (do pracowników + 2x Skatteetaten) — prompt explicite dopuszczał to uproszczenie. Kwota **wyciągnięta z postingów zobowiązaniowych** (2710/2740/2700) już istniejących voucherów listy płac, nie liczona od nowa — gwarancja zgodności co do grosza. Voucher dotyka WYŁĄCZNIE kont bilansowych (2700/2710/2740/1910) — nigdy P&L (4xxx-7xxx), więc marża z definicji nie może się zmienić.
- `save_salary()` zmienione, żeby zwracać prawdziwe `salary_transactions.id` z bazy (potrzebne do FK) — woła `_save_salary_transaction()` bezpośrednio zamiast przez generyczny `save_all()` (który ma jednolitą sygnaturę `persist_fn(obj) -> None`, nie mógłby zwracać ID).
- Podłączone do `run_daily.py`, krok 4 (lista płac) — od teraz każda przyszła wypłata automatycznie generuje odpowiadającą transakcję bankową.
- **`scripts/fix_missing_payroll_transactions.py`** — jednorazowa migracja dla 91 istniejących `salary_transactions`. Nie liczy kwot ręcznie z SQL — **ponownie woła `generate_monthly_salary(year, month)`** (w pełni deterministyczne, bez losowości) dla każdego historycznego miesiąca, podmienia `transaction.id` na prawdziwe ID z bazy, buduje płatność. Wynik: 91/91 zapisanych, 0 pominiętych.
- **10 nowych testów offline** (`test_payroll_bank_transactions.py`) — sprawdzają `generate_payroll_bank_transaction()` bezpośrednio (deterministyczne, bez bazy) dla reprezentatywnej próbki miesięcy 2019-2026 (zwykłe + czerwiec/feriepenger + miesiąc fuzji), zamiast żywego zapytania `NOT EXISTS` jak sugerował prompt — zgodnie z konwencją reszty pakietu testów (zob. nagłówek `test_repository.py`).

**Stan po naprawie (żywa baza)**: `employees`=17. `bank_transactions`: 810 OUTGOING (107,6M) / 1267 INCOMING (188,3M) — dalej nierówne (firma rentowna, oczekiwane), ale bez strukturalnej dziury. **Marża zweryfikowana identyczna przed/po** (2025=7,54%, wszystkie lata bit-for-bit) — te zmiany dotyczą wyłącznie `bank_transactions`/kont bilansowych, nie P&L. **199/199 testów.**

### 12c. Czy raport (`maykel84.github.io/raport`) wymaga przegenerowania?

**Tak, prawdopodobnie** — nie wiem dokładnie, jak ten raport jest zasilany (nie jest częścią tego repo, nie mam do niego dostępu ani wglądu w jego źródło danych/pipeline). Jeśli czyta bezpośrednio z tej samej bazy Supabase na żądanie — pokaże poprawne dane od razu. Jeśli ma jakikolwiek cache/snapshot/eksport pośredni (podobnie jak `norfingen_export.xlsx` wymaga ręcznego `python export_excel.py` po każdej zmianie danych) — wymaga ręcznego przegenerowania po tej naprawie. **Do zweryfikowania przez użytkownika**, poza zakresem tej sesji.

**Aktualizacja (2026-08-20)** — znaleziono i zweryfikowano: raport ma OSOBNE repo, `~/Claude takie tam/raport-site` (git remote `github.com/Maykel84/raport.git`, serwowane jako `maykel84.github.io/raport`), niezależne od tego repo (`Symulator danych tripletex`). Dane w `index.html` (osadzony JSON, `#report-data`) już były zregenerowane po naprawie Kroku 2 — `pnl_monthly`/`headcount_now`=17/`bank_transactions` w tabeli zgadzają się co do grosza z żywą bazą po naprawie (zweryfikowane bezpośrednio). Sekcja "Bank activity" miała jednak nieaktualne/nieprecyzyjne zdanie objaśniające — poprawione: **suma cash-flow (IN−OUT = 80,7M) i skumulowany EBITDA (~20,6M) to CELOWO różne miary** (cash jest brutto z VAT, EBITDA netto po kosztach) — NIE należy ich zestawiać jako "spójne", to błąd merytoryczny, jaki omal nie trafił do raportu. Zdanie w `index.html` zaktualizowane, żeby to jasno tłumaczyć zamiast fałszywie sugerować zgodność.

**Rozstrzygnięte (2026-08-20, potwierdzone przez użytkownika)**: `raport-site/v1/index.html` jest celowo zachowanym archiwalnym snapshotem sprzed naprawy Kroku 2 (headcount 38, bank OUT 17,5M) — **NIE aktualizować przy przyszłych zmianach raportu**, to jest zamierzone archiwum pokazujące stan przed naprawą integralności danych.

`raport-site/index.html` — poprawka zdania w sekcji "Bank activity" (cash flow vs EBITDA, zob. wyżej) **zacommitowana i wypchnięta** tego samego dnia (`0e7da2a`, `github.com/Maykel84/raport.git`).

---

## 13. Faza 7 — warstwa zdarzeń losowych (life events), Zadanie 1: sezonowe wzorce B2B (2026-08-20)

Rozpoczęto Fazę 7 — dodaje warstwę deterministycznie losowych zdarzeń biznesowych (przestrzeń prawdopodobieństw, nie ML; `random.Random(string)`, nigdy `hash()`). **W tej sesji wykonano wyłącznie Zadanie 1** (sezonowość norweskiego B2B, poziom firmy) — reszta fazy (kolejne Zadania, offline sanity-check marży, pełny backfill) **czeka na dalszy ciąg prompta**, zgodnie z decyzją użytkownika: backfill wymagany jest dopiero na końcu CAŁEJ fazy, nie po każdym Zadaniu.

### 13a. Zaimplementowane (1a, 1b)

Nowy moduł `src/norfingen/generators/seasonality.py` — trzy czyste funkcje mnożnikowe, bez RNG (skalują istniejące progi w miejscu wywołania, zamiast dodawać równoległe mechanizmy losowości):

- **`fellesferie_activity_multiplier(month)`** — lipiec ×0,5. Podłączone w `hours_generator.generate_daily_support_hours()` (mnoży `target_billable` przed losowaniem) — **czysto realizm `hour_entries`, nie wpływa na przychód/payroll** (jak reszta modelu godzin z Fazy 6).
- **`q4_budget_flush_multiplier(month, segment)`** — listopad/grudzień ×1,4 dla Enterprise/Mid-market. Podłączone w `order_generator.should_generate_extra_consulting()` (mnoży próg prawdopodobieństwa) — **WPŁYWA na przychód** (więcej zamówień S04 w Q4), stąd wymaga offline sanity-checku marży przed backfillem, tak jak wszystkie poprzednie fazy dotykające przychodu.

Testy: `tests/test_seasonality.py` (nowy, 3 testy funkcji czystych) + rozszerzenia `test_order_generator.py`/`test_hours_generator.py` (2 nowe testy integracyjne). **204/204 offline** (`pytest -q --ignore=scripts`).

Przy okazji: `test_extra_consulting_more_frequent_in_q4_than_q2_budsjettflukt` pierwotnie failował przy próbie 100 lat (200-300 losowań) — różnica progów (0,15 vs 0,21) bywała zamaskowana szumem statystycznym. Naprawione zwiększeniem próby do 5000 lat.

### 13b. Świadomie NIE wykonane w tej sesji (potwierdzone przez użytkownika)

- **Onboarding K17 (Drammen Eiendom AS, `onboarding_date=2023-07-03`) NIE przesunięty**, mimo że 1a każe unikać lipcowych startów nowych klientów. `roster.CUSTOMERS` to statyczna, historyczna lista (nie generowana dynamicznie per backfill) — K17 ma już lata zbackfillowanych, przetestowanych danych w produkcyjnej bazie (orders/hour_entries/vouchers za 2023+). Reguła "unikaj lipca" traktowana jako obowiązująca **na przyszłość** (gdyby kiedyś powstał dynamiczny generator nowych klientów), nie jako nakaz retroaktywnej korekty istniejącej historii — koszt/ryzyko takiej korekty porównywalne do incydentu z p. 12.
- **1c (`january_new_initiative_boost`) napisane w `seasonality.py`, ale świadomie NIEPODŁĄCZONE** — w kodzie nie istnieje żaden dyskretny mechanizm "nowy projekt S02" analogiczny do `should_generate_extra_consulting` (S02 sprzedawany wyłącznie jako część stałego bundla segmentowego, `roster.get_customer_services`). Zaprojektowanie takiego mechanizmu wykraczałoby poza treść Zadania 1 — czeka na jawną decyzję/kolejne zadanie, jeśli ma powstać.
- **Offline sanity-check marży i pełny backfill NIE wykonane** — Zadanie 1 to tylko fragment Fazy 7 (prompt urwał się po 1c). Mimo że 1b wpływa na przychód, uruchamianie sanity-checku/backfillu teraz byłoby przedwczesne — trzeba by je powtórzyć po dojściu kolejnych Zadań tej fazy. Zmiany są na razie tylko commitowane lokalnie, niewypchnięte.
- **Niezwiązany, przedistniejący błąd znaleziony przy okazji**: `pytest -q` (bez `--ignore=scripts`) wybucha na `scripts/test_powerbi_connection.py` (ERROR przy kolekcji — plik to ręczne narzędzie weryfikacyjne, nie prawdziwy test pytest, istnieje od `00c7998`/2026-08-11). Niedotknięte w tej sesji, zgłoszone osobno.

### 13c. Faza 7, Zadanie 2 — zdarzenia na poziomie klienta (life events), 2026-08-20

Nowy moduł `src/norfingen/generators/client_events.py` — katalog `CLIENT_LIFE_EVENTS` (5 kodów: OFFER_EXPANSION, OFFER_REDUCTION, TEMPORARY_HARDSHIP, BANKRUPTCY, ONE_OFF_LARGE_PROJECT), zgodny z treścią Zadania 2a.

**Świadoma zmiana architektury względem Zadania 2d** (udokumentowana w docstringu modułu): prompt zakładał "stan w pamięci, jeden sekwencyjny przebieg backfillu wystarczy". Sprawdzone i **nietrafne** dla tego repo — backfill to w praktyce DWA osobne procesy uruchamiane ręcznie po sobie (`run_backfill.py --mode monthly`, potem `--mode daily`, zob. p. 5), a `--mode daily` i żywy cron dzielą tę samą funkcję `run_daily()` wołaną raz per proces. Żaden mutowalny obiekt stanu przekazywany z zewnątrz nie przetrwałby między nimi. Zamiast tego: `customer_event_state_asof(customer_number, year, month)` — **czysta, memoizowana funkcja** (rekurencyjnie dokłada miesiąc po miesiącu od onboardingu, `functools.lru_cache`), więc daje identyczny wynik niezależnie od tego, który proces/wywołanie o nią zapyta. Mocniejsza wersja tego samego wymogu determinizmu, nie jego złamanie.

**Zaimplementowane efekty (Zadanie 2c)**:
- `effective_customer_services()` — trwałe dodanie/usunięcie usługi (nigdy S01), podłączone w `order_generator.build_order_lines()` (działa identycznie w monthly i daily generowaniu).
- `event_aware_is_customer_active()` — rozszerza `roster.is_customer_active()` o BANKRUPTCY (klient aktywny jeszcze w miesiącu triggera — ostatnia, odpisana faktura — trwale nieaktywny od kolejnego). Podłączone w `generate_monthly_orders`, `generate_daily_orders` (order_generator) i `generate_daily_hours` (hours_generator) — bankrutujący klient znika ze wszystkich strumieni jednocześnie.
- `hardship_ticket_multiplier_for()` — redukcja 40-60% wolumenu ticketów wsparcia PER KLIENT (nie cały dzień konsultanta), stała przez całe okno kryzysu (losowana raz przy starcie). Podłączone w `hours_generator.generate_daily_support_hours`.
- BANKRUPTCY: ostatnia faktura miesiąca triggera wymuszona na `WRITTEN_OFF` (`_build_order(..., status_override=...)`).
- TEMPORARY_HARDSHIP: podwyższony próg bad-debt (`determine_order_status(..., bad_debt_probability=...)`) — `HARDSHIP_BAD_DEBT_MULTIPLIER=5.0` (0,02→0,10), wartość dobrana samodzielnie (zadanie nie podało liczby, tylko "podnieś próg").
- ONE_OFF_LARGE_PROJECT: dodatkowe zamówienie S04, 80-200h wg stawki godzinowej usługi (nie ryczałt 20-50k NOK jak standardowy extra-consulting) — wyraźnie większe, zweryfikowane testem.

**Dwa rzeczywiste błędy znalezione i naprawione podczas implementacji (nie przez ślepe kopiowanie zadania)**:
1. **Crash**: pierwotna mapa ekspansji (SMB→S02, Mid-market→S03) łamała już istniejące ograniczenia katalogu usług (`Service.availability` — S02 to `ENTERPRISE_MID`, brak `base_price_smb`; S03 to `ENTERPRISE_ONLY`, brak `base_price_mid`) — `TypeError: None * float` przy próbie wyceny. Naprawione: oba segmenty ekspandują w S04 (`availability=ALL`, wyceniony dla każdego segmentu) — jedyna usługa, którą mogą legalnie dokupić jako trwałą linię.
2. **Zaniżona marża po pierwszym pełnym sanity-checku** (2025: 4,9%, poniżej progu 5,5%) — przyczyna NIE była kalibracją prawdopodobieństw, tylko luką integracyjną: `opex_generator.generate_monthly_opex` liczył COGS S01/S02 (i reprezentację/transport) z **statycznej** `active_customers()` i heurystyki `c.segment == "Enterprise"` (zakładającej że każdy Enterprise/Mid-market zawsze kupuje S02) — klient po BANKRUPTCY dalej generował koszty, a klient po OFFER_REDUCTION (usunięcie S02) dalej był obciążany kosztem Azure za usługę, za którą już nam nie płacił. Naprawione filtrowaniem listy klientów w `opex_generator.py` przez `event_aware_is_customer_active` (wszystkie koszty per-klient) i dodatkowo przez `effective_customer_services` (tylko Azure COGS S02). Po naprawie: **2025 margin=6,1%, 2026 margin=7,0%**, oba w progu 5,5-9%, płynna trajektoria przez wszystkie dojrzałe lata (zweryfikowane 2019-2026, nie tylko para testowana przez `test_faza6_market_calibration.py`).

**Świadomie wykluczone**: K06 (jedyny klient wzorca D, consulting bez stałego bundla usług) — `customer_event_state_asof` zwraca dla niego zawsze pusty stan; OFFER_EXPANSION/REDUCTION nie miałyby się do czego zastosować (K06 nie przechodzi przez `build_order_lines`), a BANKRUPTCY byłby martwy (branch `pattern=="D"` nie sprawdza aktywności event-aware) — podłączenie wymagałoby przeprojektowania osobnej logiki K06, poza zakresem tego zadania.

**Zakres celowo ograniczony do backfillu miesięcznego** (jak istniejący precedens `should_generate_extra_consulting`/K06): efekty przychodowe (extra order, podwyższony bad-debt) i kosztowe żyją wyłącznie w `generate_monthly_orders`/`generate_monthly_opex`. `generate_daily_orders` (żywy cron) respektuje TYLKO `event_aware_is_customer_active` (BANKRUPTCY) — bo inaczej cron wystawiałby faktury klientowi, który już (w historii backfillu) zbankrutował.

Testy: `tests/test_client_events.py` (nowy, 9 testów — zamrażają konkretne, deterministycznie znalezione zdarzenia jako regresję, wzorem reszty pakietu) + poprawka pre-istniejącego gapu w `tests/test_bank_transaction_generator.py::test_all_incoming_payments_balance` (nie obsługiwał `WRITTEN_OFF`, nigdy wcześniej nie trafiony losowo w 2024 — pierwszy deterministyczny WRITTEN_OFF w tym roku to K12/BANKRUPTCY). **213/213 offline** (`pytest -q --ignore=scripts`).

**Offline sanity-check marży wykonany i pozytywny** (zob. wyżej) — ale **backfill na żywej bazie jeszcze NIE wykonany**, zgodnie z tą samą zasadą co Zadanie 1: czekamy na potwierdzenie, czy to koniec Fazy 7, czy będą kolejne Zadania (backfill wymagany dopiero na końcu CAŁEJ fazy). Zmiany zacommitowane lokalnie, niewypchnięte.

### 13d. Faza 7, Zadanie 3 — zdarzenia na poziomie firmy, 2026-08-20

Nowy moduł `src/norfingen/generators/company_events.py`, ten sam wzorzec co `client_events.py` (czysta memoizowana funkcja `company_event_state_asof(year, month)`, nie mutowalny ledger — z tych samych powodów architektonicznych, zob. p. 13c). Jedyny element wymagający pamięci między latami to `SUPPLIER_RENEGOTIATION` ("trwale od tego miesiąca") — `EQUIPMENT_INVESTMENT`/`UNPROFITABLE_QUARTER` są w pełni wyprowadzalne z samego `roll_company_events(year)` (Zadanie 3b, zaimplementowane dosłownie wg podanego pseudokodu), bez żadnego stanu.

**Zaimplementowane efekty (Zadanie 3c)**:
- `EQUIPMENT_INVESTMENT` — jednorazowa faktura L05 (`{L05}-{rok}-{miesiąc}-EQUIP`), kwota 80k-250k NOK (zawsze > progu kapitalizacji 30k → konto 1200, automatycznie przez istniejącą `_account_for_invoice`), w wylosowanym miesiącu, NIEZALEŻNA od zwykłego harmonogramu L05 (3-5x/rok) — może wystąpić w tym samym miesiącu co regularna faktura Sandvika, to dwie osobne pozycje.
- `UNPROFITABLE_QUARTER` — dwa osobne, rzeczywiste efekty (nie ukryta korekta P&L, zgodnie z zadaniem): (a) mnożnik wolumenu ticketów 0,85-0,95 aktywny przez WSZYSTKIE 3 miesiące kwartału zawierającego wylosowany miesiąc (`unprofitable_quarter_ticket_multiplier`, podłączony w `hours_generator` obok fellesferie — mnożą się, jeśli oba trafią ten sam miesiąc, niezależne zdarzenia); (b) jednorazowy koszt opex zaksięgowany DOKŁADNIE w wylosowanym miesiącu (nie cały kwartał — "jednorazowy" per zadanie), nowe konto 7790 "Annen driftskostnad" (NS4102, nieużywane dotąd w tym repo), kwota 40k-120k NOK — **wartość dobrana samodzielnie** (zadanie podało `magnitude_range` tylko dla wolumenu/ticketów, nie dla kwoty kosztu).
- `SUPPLIER_RENEGOTIATION` — trwały mnożnik kosztu (`supplier_cost_multiplier`) dla jednego z L01-L08 (wylosowanego), ±(-15%..+10%) od wylosowanego miesiąca. Podłączony w `supplier_invoice_generator.py` PRZED zaokrągleniem netto — działa jednolicie dla L01 (3 osobne linie Microsoft) i L02-L08 (pojedyncza kwota). Kolejne renegocjacje TEGO SAMEGO dostawcy w różnych latach się mnożą (kolejne negocjacje kontraktu) — świadomy wybór, zadanie nie precyzuje.

**Offline sanity-check marży PO Zadaniu 3**: 2025=6,1%, 2026=7,0% (identyczne z checkpointem po Zadaniu 2 co do jednego miejsca po przecinku) — koszty/przychody z tej fazy są rzędu wielkości zbyt małego, żeby zauważalnie poruszyć roczną marżę firmy z 43-52 tabela produkcyjnego przychodu. Zweryfikowane na pełnej historii 2019-2026, oba lata w progu 5,5-9%.

Testy: `tests/test_company_events.py` (nowy, 7 testów — te same zasady co `test_client_events.py`: zamrożone konkretne, deterministycznie znalezione zdarzenia jako regresja). **220/220 offline** (`pytest -q`, teraz bez potrzeby `--ignore=scripts` — zob. `ac0a601`).

**Backfill na żywej bazie wciąż NIE wykonany** — czekamy na potwierdzenie końca Fazy 7 (ta sama zasada co po Zadaniach 1 i 2). Zmiany zacommitowane lokalnie, niewypchnięte.

### 13e. Faza 7, Zadanie 4 — testy, i NAPRAWA prawdziwego błędu z Zadania 1, 2026-08-20

Cztery testy referencyjne z zadania zaadaptowane do rzeczywistego API (`roll_client_events()` w tym repo zwraca `Optional[str]`, nie listę dictów — model "jeden aktywny event na klienta", zob. p. 13c) — `tests/test_faza7_task4_regression.py` (4 testy): determinizm, BANKRUPTCY tylko dla SMB (1000 losowych prób), redukcja wolumenu ticketów w lipcu, bilans księgowy (DR=CR) na pełnym backfillu 2019-2024 (jawna weryfikacja na zebranych Voucherach, nie tylko poleganie na `assert_voucher_valid()` przy konstrukcji).

**`test_fellesferie_reduces_july_ticket_volume` złapał prawdziwy, żywy błąd z Zadania 1** — nie w teście, w kodzie produkcyjnym. Uruchomiony na pełnym pipeline (`generate_daily_hours`, nie izolowane wywołanie `generate_daily_support_hours` z jednym, wspólnym seedem rng jak testy z Zadania 1) pokazał, że **lipiec miał WIĘCEJ ticketów niż czerwiec** (704 vs 635 wpisów), odwrotnie niż zamierzone.

**Przyczyna**: mnożnik `fellesferie_activity_multiplier`/`unprofitable_quarter_ticket_multiplier` (Zadania 1a/3c) skalował wyłącznie `target_billable`. W praktyce `target_billable` (5,5-7h) prawie NIGDY nie jest wiążącym ograniczeniem pętli w `generate_daily_support_hours` — realnym sufitem jest `n_clients_today` (max 5 klientów/dzień × ~1h/ticket ≈ 5h, już poniżej niepomniejszonego celu). Testy z Zadania 1 (`test_hours_generator.py::test_fellesferie_reduces_july_billable_ticket_hours`) przechodziły, bo używały **jednego, wspólnego, ręcznie dobranego seeda rng** dla obu miesięcy — sztucznie wymuszały sytuację, w której `target_billable` akurat był wiążący, maskując że w normalnym, zróżnicowanym pipeline (osobny rng per dzień) efekt był w praktyce niewidoczny lub odwracany przez inne źródła szumu (więcej dni roboczych w lipcu, rotacja portfela klientów).

**Naprawa**: mnożnik teraz skaluje też `n_clients_today` (`max(1, round(n_clients_today * mnożnik))`) — czyli faktyczne, wiążące ograniczenie — `target_billable` zostaje jako dodatkowe zabezpieczenie. Zweryfikowane bezpośrednio: lipiec 2025 411 ticketów/420h vs czerwiec 2025 595/589h (~30% mniej, mimo 2 dodatkowe dni robocze w lipcu). Nie wpływa na marżę (hours_generator z definicji nie dotyka przychodu/payrollu, zob. moduł-level docstring) — pełny sanity-check marży niepotrzebny dla tej poprawki, potwierdzone niezmienionym wynikiem `test_faza6_market_calibration.py` w pełnym przebiegu testów.

**224/224 testów offline** (`pytest -q`).

**Backfill na żywej bazie wciąż NIE wykonany** — Zadanie 4 to testy, nie nowa funkcjonalność biznesowa, ale zasada "backfill dopiero na końcu CAŁEJ fazy" zostaje aktualna do wyraźnego potwierdzenia użytkownika.

### 13f. Faza 7, Zadanie 5 — finalny offline sanity-check (OBOWIĄZKOWY), 2026-08-20

Pełny `run_backfill()` w pamięci, 2019 - ostatni w pełni zamknięty miesiąc (2026-07), marża i wariancja miesięczna per rok:

| Rok | Przychód | Marża | StdDev marży miesięcznej (pkt. proc.) |
|---|---|---|---|
| 2019 | 7 306 506 | -25,67% | 73,81* |
| 2020 | 18 151 002 | 20,57% | 5,57 |
| 2021 | 20 019 397 | 17,30% | 5,01 |
| 2022 | 23 382 082 | 11,61% | 5,70 |
| 2023 | 32 154 882 | 8,04% | 3,37 |
| 2024 | 38 193 105 | 7,00% | 5,28 |
| 2025 | 43 579 585 | 6,06% | 5,05 |
| 2026 | 29 693 022 (częściowy, do lipca) | 7,03% | 4,83 |

*2019: pierwsze miesiące (styczeń-luty) mają koszt (payroll pierwszych pracowników) bez przychodu (pierwszy klient dopiero marzec) — skrajne wartości procentowe miesięczne, nie błąd.

**WYNIK: PASS** — wszystkie lata dojrzałe (2023-2026) w progu 5,5-9%, bez korekty prawdopodobieństw/kwot z Zadań 1-4. Widoczna zwiększona zmienność miesiąc-do-miesiąca (3,4-5,7 pkt. proc. w latach dojrzałych) — dowód że dane są mniej liniowe niż przed Fazą 7 (poprzednie fazy nie miały tego rodzaju szumu wewnątrzrocznego poza sezonowością Q2/Q4/lipiec).

**Przy okazji znaleziony i naprawiony błąd w skrypcie diagnostycznym tego sanity-checku** (nie w kodzie produkcyjnym): pierwsza wersja pomijała miesiące z kosztem, ale bez przychodu (styczeń/luty 2019, przed pierwszym klientem) przez `if key not in revenue_m: continue` — to fałszywie zaniżało sumę kosztów całego roku (2019 pokazywał -17,6% zamiast poprawnych -25,67%, potwierdzonych zgodnością z wcześniejszymi checkpointami z Zadań 2/3). Naprawione iterowaniem po sumie kluczy z WSZYSTKICH czterech słowników (revenue/payroll/opex/cogs), nie tylko revenue.

**Log faktycznie wylosowanych zdarzeń**: `scripts/log_life_events.py` → `docs/faza7_life_events_log.csv` (29 zdarzeń, 2019 - lipiec 2026: 22 klienckie, 7 firmowych — pełna lista z kwotami/usługami w pliku CSV, podsumowanie w `docs/DATA_DICTIONARY.md`).

**`docs/DATA_DICTIONARY.md` zaktualizowany** — nowa sekcja "Faza 7 — warstwa zdarzeń losowych" (katalogi, architektura czystej funkcji stanu, oba znalezione i naprawione błędy).

### 13g. TRUNCATE + backfill na żywej bazie — NIE WYKONANE przeze mnie, wymaga Twojej ręki

Zadanie 5 każe: wyłączyć `daily.yml` w GitHub UI, `TRUNCATE ... RESTART IDENTITY CASCADE`, `run_backfill.py --start 2019-01-01`, `run_backfill.py --mode daily`, `scripts/fix_outgoing_transactions.py`, potem włączyć `daily.yml` z powrotem.

**Świadomie NIE wykonałem `TRUNCATE` ani reszty tej sekwencji** — trwałe usuwanie danych z produkcyjnej bazy jest poza tym, co wykonuję samodzielnie, niezależnie od tego, że to udokumentowany, wielokrotnie już powtórzony wzorzec tego projektu (Faza 6 robiła dokładnie to samo). Sanity-check (warunek wstępny) jest zrobiony i pozytywny — reszta sekwencji czeka na Ciebie:

```bash
# 1. Wyłącz .github/workflows/daily.yml w GitHub UI (Actions -> daily -> Disable workflow)

# 2. W psql/Supabase SQL editor:
TRUNCATE orders, order_lines, supplier_invoices,
         salary_transactions, payslips, salary_specifications,
         vouchers, postings, bank_transactions, hour_entries
RESTART IDENTITY CASCADE;

# 3. W repo:
python run_backfill.py --start 2019-01-01
python run_backfill.py --mode daily --start 2019-01-01
python scripts/fix_outgoing_transactions.py

# 4. Włącz z powrotem daily.yml w GitHub UI DOPIERO PO pushu commitów tej fazy na main
```

Po Twoim uruchomieniu — wróć z wynikami (albo wklej błąd, jeśli coś pójdzie nie tak) i zrobię Zadanie 6 (zapytania weryfikacyjne na żywej bazie).

### 13h. Faza 7, Zadanie 6 — dokumentacja finalna (2026-08-20)

**Status backfillu produkcyjnego: NIEROZPOCZĘTY.** Sekwencja z p. 13g (TRUNCATE + backfill + `daily.yml`) jeszcze nie wykonana — potwierdzone przez użytkownika. Liczby marży poniżej to **offline sanity-check** (p. 13f), nie odczyt z żywej bazy — będą zweryfikowane zapytaniem SQL na Supabase, gdy backfill faktycznie się odbędzie.

**Finalna marża (offline, przed backfillem)**:

| Rok | Marża |
|---|---|
| 2023 | 8,04% |
| 2024 | 7,00% |
| 2025 | 6,06% |
| 2026 (do lipca) | 7,03% |

Wszystkie w progu bezpieczeństwa 5,5-9%.

**`daily.yml`: NIE dotknięty** — bo TRUNCATE jeszcze się nie odbył, workflow jest w swoim normalnym, włączonym stanie (nie było potrzeby go wyłączać). **Nie potwierdzam "włączenia z powrotem"**, bo nigdy nie został wyłączony w ramach tej fazy.

**Faktycznie wylosowane zdarzenia w historii 2019 - lipiec 2026** (29, z `docs/faza7_life_events_log.csv`, deterministyczne — te same wystąpią przy backfillu na żywej bazie):

*Klienckie (22):*
| Rok-mies. | Klient | Segment | Zdarzenie | Szczegóły |
|---|---|---|---|---|
| 2020-02 | K07 Østfold Finans AS | Mid-market | TEMPORARY_HARDSHIP | do 2020-05, mnożnik 0,464 |
| 2020-05 | K01 Bergström Industri AS | Enterprise | ONE_OFF_LARGE_PROJECT | |
| 2020-07 | K01 Bergström Industri AS | Enterprise | ONE_OFF_LARGE_PROJECT | |
| 2022-01 | K07 Østfold Finans AS | Mid-market | OFFER_EXPANSION | +S04 |
| 2022-10 | K01 Bergström Industri AS | Enterprise | TEMPORARY_HARDSHIP | do 2022-12, mnożnik 0,513 |
| 2022-11 | K09 Vestfold Handel AS | SMB | TEMPORARY_HARDSHIP | do 2023-02, mnożnik 0,584 |
| 2023-01 | K10 Kristiansen Gruppen AS | Mid-market | ONE_OFF_LARGE_PROJECT | |
| 2023-03 | K11 Rogaland Teknikk AS | Enterprise | ONE_OFF_LARGE_PROJECT | |
| 2024-01 | K34 Kristiansund Transport AS | Mid-market | OFFER_REDUCTION | -S02 |
| 2024-02 | K32 Harstad Finans AS | Mid-market | OFFER_EXPANSION | +S04 |
| 2024-11 | K12 Agder Maritime AS | SMB | **BANKRUPTCY** | churn, ostatnia faktura WRITTEN_OFF |
| 2024-11 | K19 Sandefjord Transport AS | Mid-market | OFFER_REDUCTION | -S02 |
| 2024-12 | K02 Halvorsen & Partnere AS | Mid-market | TEMPORARY_HARDSHIP | do 2025-01, mnożnik 0,582 |
| 2024-12 | K16 Vestland Maritime AS | Enterprise | ONE_OFF_LARGE_PROJECT | |
| 2025-06 | K27 Grenland Energi AS | Enterprise | TEMPORARY_HARDSHIP | do 2025-09, mnożnik 0,548 |
| 2025-08 | K16 Vestland Maritime AS | Enterprise | TEMPORARY_HARDSHIP | do 2025-10, mnożnik 0,450 |
| 2026-02 | K21 Buskerud Finans AS | Mid-market | ONE_OFF_LARGE_PROJECT | |
| 2026-02 | K25 Halden Design AS | SMB | TEMPORARY_HARDSHIP | do 2026-05, mnożnik 0,509 |
| 2026-03 | K16 Vestland Maritime AS | Enterprise | ONE_OFF_LARGE_PROJECT | |
| 2026-04 | K50 Jessheim Design AS | SMB | TEMPORARY_HARDSHIP | do 2026-06, mnożnik 0,451 |
| 2026-07 | K25 Halden Design AS | SMB | OFFER_EXPANSION | +S04 |
| 2026-08 | K20 Nordland Havbruk AS | Enterprise | ONE_OFF_LARGE_PROJECT | |

*Firmowe (7):*
| Rok-mies. | Zdarzenie | Szczegóły |
|---|---|---|
| 2020-04 | UNPROFITABLE_QUARTER | koszt jednorazowy 46 900 NOK |
| 2021-02 | UNPROFITABLE_QUARTER | koszt jednorazowy 96 900 NOK |
| 2022-01 | EQUIPMENT_INVESTMENT | 231 904 NOK (L05, kapitalizowane) |
| 2022-04 | UNPROFITABLE_QUARTER | koszt jednorazowy 58 100 NOK |
| 2023-08 | UNPROFITABLE_QUARTER | koszt jednorazowy 50 900 NOK |
| 2024-09 | EQUIPMENT_INVESTMENT | 187 486 NOK (L05, kapitalizowane) |
| 2025-09 | SUPPLIER_RENEGOTIATION | L01 Microsoft, -1,8% |

Żadne zdarzenie BANKRUPTCY poza K12, żadna renegocjacja poza L01/2025-09 — jedna SUPPLIER_RENEGOTIATION (2026-09, dostawca L07 +2,2%) wypada POZA zasięgiem backfillu (po lipcu 2026), świadomie wykluczona z tej listy (zob. `scripts/log_life_events.py` — filtruje do cutoffu, żeby log pokazywał wyłącznie to, co faktycznie trafi do bazy).

### 13i. Incydent podczas produkcyjnego backfillu — brakujące konto 7790 (2026-08-20)

Użytkownik wykonał pełną sekwencję (`daily.yml` disabled, `TRUNCATE`, `run_backfill.py --start 2019-01-01`) — **backfill wywalił się z `psycopg2.errors.ForeignKeyViolation`** na pierwszym `UNPROFITABLE_QUARTER` (kwiecień 2020): `Key (account_number)=(7790) is not present in table "accounts"`.

**Przyczyna**: konto 7790 ("Annen driftskostnad", Zadanie 3c) zostało zdefiniowane jako stała w `company_events.py`, ale **nigdy nie dodane do `repository.ACCOUNTS_SEED`** — tabeli referencyjnej, którą `seed_reference_data()` wypełnia na starcie każdego uruchomienia. Offline sanity-check (Zadanie 5) tego nie złapał, bo `run_backfill(persist_fn=collect)` w pamięci nigdy nie dotyka prawdziwej bazy ani jej ograniczeń FK — dziura w metodologii testowej tej fazy: **testy jednostkowe/offline weryfikują logikę generatorów, nie zgodność z rzeczywistym schematem bazy**. Żadna z poprzednich faz nie miała tego problemu, bo nowe konta (4291, 4292 w Fazie 6) były dodawane do `ACCOUNTS_SEED` przy okazji, tu to zwyczajnie przeoczone.

**Naprawa**: `(7790, "Annen driftskostnad", "OPERATING_EXPENSE", None)` dodane do `ACCOUNTS_SEED` (`repository.py`). Zweryfikowano na żywej bazie po crashu: **brak osieroconych rekordów** (dane 2019-01→2020-04 kompletne aż do etapu opex miesiąca kwietnia, kolejność w `generate_and_persist_month`: orders→invoices→salary→opex — salary kwietnia 2020 już zapisane, crash na pierwszym voucherze opex tego miesiąca, żaden posting/voucher nie osierocony). Ponowne uruchomienie `run_backfill.py --start 2019-01-01` jest bezpieczne bez powtórnego `TRUNCATE` — `seed_reference_data()`/`ON CONFLICT DO NOTHING` na już zapisanych miesiącach są idempotentne.

**Zrobione od razu, nie odłożone**: `tests/test_accounts_seed_coverage.py` — automatycznie odkrywa każdą stałą `ACCOUNT_*` w `generators/*.py` (introspekcja modułów, nie ręczna lista) i sprawdza obecność w `ACCOUNTS_SEED`. Zapobiega dokładnie tej klasie błędu na przyszłość, bez potrzeby dotykania żywej bazy.

### 13j. Backfill produkcyjny ZAKOŃCZONY i zweryfikowany (2026-08-20)

Po naprawie konta 7790 (p.13i) użytkownik dokończył całą sekwencję: `run_backfill.py --start 2019-01-01` (od nowa, idempotentnie) → `run_backfill.py --mode daily --start 2019-01-01` → `scripts/fix_outgoing_transactions.py` (717 faktur PAID bez OUTGOING naprawionych) → **`daily.yml` włączony z powrotem, potwierdzone działa**.

**Stan bazy po backfillu**: `orders`=1845 (90/90 miesięcy), `order_lines`=3802, `supplier_invoices`=736, `vouchers`=2762, `postings`=5791, `bank_transactions`=1380 (INCOMING 1277 / OUTGOING 820 — po migracji), `hour_entries`=53 911 (91/91 miesięcy). K12 (BANKRUPTCY, listopad 2024) ma poprawnie `WRITTEN_OFF` na ostatniej fakturze — zweryfikowane bezpośrednio.

**Marża — zapytanie SQL na żywej bazie (Zadanie 6), zamiast offline symulacji**:

| Rok | Przychód | Payroll | Opex | COGS | Marża |
|---|---|---|---|---|---|
| 2019 | 7 306 506 | 4 702 822 | 1 859 931 | 2 619 500 | -25,67% |
| 2020 | 18 151 002 | 6 948 806 | 1 888 573 | 5 579 095 | 20,57% |
| 2021 | 20 019 397 | 8 436 433 | 1 984 816 | 6 135 291 | 17,30% |
| 2022 | 23 382 082 | 11 210 947 | 1 993 145 | 7 462 222 | 11,61% |
| 2023 | 32 154 882 | 15 582 464 | 2 083 453 | 11 904 767 | **8,04%** |
| 2024 | 38 193 105 | 16 257 989 | 2 151 424 | 17 110 709 | **7,00%** |
| 2025 | 43 579 585 | 16 745 730 | 2 199 037 | 21 992 754 | **6,06%** |
| 2026 (do lipca, w pełni zamknięte) | 29 693 022 | 10 197 745 | 1 310 524 | 16 096 575 | **7,03%** |

**Identyczne co do grosza (2019-2025) z offline sanity-checkiem z p.13f** — potwierdza że backfill wiernie odtworzył to, co przewidziano offline. **2026 pełny rok (do 2026-08-20) daje 10,82%** — poza progiem, ale to oczekiwany, udokumentowany artefakt niedomkniętego miesiąca (sierpień jeszcze bez zaksięgowanego payrollu, zob. p.11b) — po ograniczeniu do w pełni zamkniętych miesięcy wraca do 7,03%, identycznie z offline. **Wszystkie 4 lata dojrzałe (2023-2026) w progu bezpieczeństwa 5,5-9%.**

**`daily.yml`**: wyłączony przed `TRUNCATE`, pozostał wyłączony przez całą sekwencję backfillu, **włączony z powrotem po jej zakończeniu — potwierdzone przez użytkownika, działa**.

Lista faktycznie wylosowanych zdarzeń — zob. p.13h (29 zdarzeń, niezmienione — deterministyczne, więc backfill odtworzył dokładnie te same).

**Faza 7 — kompletna, w pełni wdrożona na produkcji.** Kod zacommitowany i wypchnięty (`v5.11-faza7-life-events` + naprawa konta 7790, commit `aac427d`, do wypchnięcia razem z tą aktualizacją dokumentacji).

---

## Faza 7b — szok makroekonomiczny 2020 (MACRO_SHOCK), 2026-08-20

Rozszerzenie Fazy 7 — nowa kategoria zdarzenia, jakościowo różna od reszty katalogu: **deterministycznie wstawiony fakt historyczny** (realny szok COVID-19 w Norwegii, marzec-czerwiec 2020), nie losowana możliwość. Zaimplementowane w nowym module `src/norfingen/generators/macro_shock.py` — świadomie oddzielonym od `client_events.py`/`company_events.py`/`seasonality.py`, bez żadnego `random.Random()` (nie ma czego losować).

### Zaimplementowane efekty (Zadanie 1)

- **1b — wolumen ticketów**: `apply_macro_shock_multiplier()` — ×0,65 dla WSZYSTKICH aktywnych klientów jednocześnie (szok rynkowy, nie per-klient jak `TEMPORARY_HARDSHIP`), marzec-czerwiec 2020. Podłączone w `hours_generator.generate_daily_support_hours` obok fellesferie/UNPROFITABLE_QUARTER (mnożnikowo, na `target_billable` I `n_clients_today` — ta sama naprawa co Zadanie 4 Fazy 7a, żeby mnożnik był faktycznie wiążący).
- **1c — wstrzymanie onboardingu**: sprawdzone — **jeden klient miał onboarding w oknie** (K10 Kristiansen Gruppen AS, pierwotnie 2020-04-01). Przesunięty deterministycznie na **2020-07-01** (pierwszy miesiąc po oknie) w `roster.py`, potwierdzone przez użytkownika mimo że dotyka już zbackfillowanej historii — bezpieczne, bo pełny reset+backfill jest zaplanowany w tej samej sesji (Zadanie 3).
- **1d — tłumienie extra-consultingu**: `extra_consulting_shock_multiplier()` — próg `should_generate_extra_consulting` × 0,3 w oknie. W praktyce marzec jest i tak poza `EXTRA_CONSULTING_MONTHS` (Q2/Q4), więc realny efekt dotyczy tylko kwietnia-czerwca.
- **1e — opóźnienia płatności, nie fala bankructw**: `payment_delay_adjusted_bad_debt()` — podnosi P(OVERDUE) ×1,8, ale przelicza `written_off_share` tak, żeby **absolutne** P(WRITTEN_OFF) zostało DOKŁADNIE na poziomie sprzed korekty (matematyka w docstringu funkcji). Nowy parametr `written_off_share` w `determine_order_status`/`_build_order`, składa się poprawnie z istniejącym `HARDSHIP_BAD_DEBT_MULTIPLIER` (Faza 7, Zadanie 2) jeśli oba akurat się nałożą.

### Testy (Zadanie 2)

`tests/test_faza7b_macro_shock.py` (4 testy z prompta, zaadaptowane do rzeczywistego API — `CUSTOMERS` to `CustomerSeed` dataclasses, nie dicty):
- Redukcja wolumenu ticketów — porównanie WEWNĄTRZ 2020 (miesiące COVID vs pozostałe), nie cross-rok (2019→2020→2021 baza klientów rośnie 2→8→10, co samo w sobie zmienia surowe liczby niezależnie od COVID — cross-rok byłby mylący)
- Marża 2023-2026 niezmieniona — pełny `run_backfill()` w pamięci, ten sam próg co `test_faza6_market_calibration.py`
- Brak onboardingu w oknie COVID — po korekcie K10 przechodzi
- WRITTEN_OFF rate 2020 < 2% (wyraźnie poniżej podniesionego OVERDUE, blisko bazowych ~0,4%)

**229/229 testów offline** (`pytest -q`).

### Offline sanity-check (Zadanie 3)

| Rok | Marża przed Fazą 7b | Marża po Fazie 7b | Uwaga |
|---|---|---|---|
| 2019 | -25,67% | -25,67% | bez zmian (MACRO_SHOCK dotyczy tylko 2020) |
| **2020** | 20,57% (Faza 7a) | **19,22%** | spadek ~1,4pp — miękka wytyczna spełniona (nie poniżej -50%, nie powyżej poprzedniego poziomu) |
| 2021 | 17,30% | 17,30% | bez zmian |
| 2023-2026 | 8,04% / 7,00% / 6,06% / 7,03% | **identyczne** | twardy próg 5,5-9% nienaruszony, zweryfikowane bezpośrednio |

Efekt na 2020 jest umiarkowany (nie ekstremalny) — spójne z charakterem "trudnego roku startowego" opisanym w zadaniu, nie tworzy niczego w rodzaju -300%. Główna dźwignia przychodowa to przesunięcie onboardingu K10 (3 miesiące mniej przychodu Mid-market w 2020) — reszta efektów (redukcja ticketów, tłumienie extra-consultingu, opóźnienia płatności) jest z definicji przychodowo-neutralna lub prawie neutralna (`hour_entries` nie dotyka P&L; OVERDUE przesuwa TERMIN wpłaty, nie kwotę zaksięgowanego przychodu).

**WYNIK: PASS.** Zgodnie z procedurą — TRUNCATE + backfill na żywej bazie **NIE wykonane przeze mnie** (trwałe usuwanie danych produkcyjnych, ta sama zasada co w Fazie 7), czeka na użytkownika: wyłącz `daily.yml` → `TRUNCATE` (te same 10 tabel) → `run_backfill.py --start 2019-01-01` → `run_backfill.py --mode daily --start 2019-01-01` → `scripts/fix_outgoing_transactions.py` → włącz `daily.yml` z powrotem. **Uwaga**: ponieważ K10 zmienił `onboarding_date`, to MUSI być pełny reset (nie inkrementalny) — stary rekord K10 z kwietnia 2020 w obecnej bazie produkcyjnej stałby się niespójny z nowym kodem bez `TRUNCATE`.

### Backfill produkcyjny ZAKOŃCZONY i zweryfikowany (2026-09-01)

Użytkownik wykonał pełną sekwencję: `daily.yml` disabled → `TRUNCATE` (10 tabel) → `run_backfill.py --start 2019-01-01` → `run_backfill.py --mode daily --start 2019-01-01` (2001 dni roboczych) → `scripts/fix_outgoing_transactions.py` (720 faktur naprawionych, `INCOMING 1282 / OUTGOING 825`) → `daily.yml` z powrotem włączony.

**Marża — zapytanie SQL na żywej bazie, identyczne co do grosza z offline sanity-checkiem:**

| Rok | Marża offline | Marża żywa baza |
|---|---|---|
| 2019 | -25,67% | -25,67% |
| **2020** | **19,22%** | **19,22%** |
| 2021 | 17,30% | 17,30% |
| 2023 | 8,04% | 8,04% |
| 2024 | 7,00% | 7,00% |
| 2025 | 6,06% | 6,06% |
| 2026 (do lipca, w pełni zamknięte) | 7,03% | 7,03% |

**K10 na żywej bazie**: `onboarding_date=2020-07-01`, pierwsze zamówienie `2020-07-08` (zgodne z `invoice_day=8`) — poprawnie zbackfillowane z nową datą.

**Decyzja o K10 (retroaktywna zmiana danych historycznych)** — udokumentowana w pełni: K10 (Kristiansen Gruppen AS) to jeden z oryginalnych klientów K01-K12 z wieloletnią historią już w produkcyjnej bazie. Jedyny klient z onboardingiem w oknie COVID (2020-04-01). Analogiczna sytuacja do K17 w Fazie 7a Zadanie 1 (tam użytkownik zdecydował: zostaw bez zmian) — tym razem, ponieważ pełny `TRUNCATE`+backfill i tak był zaplanowany w tej samej sesji, użytkownik zdecydował: **przesuń na 2020-07-01**, zgodnie z literą Zadania 1c. Zasada na przyszłość: retroaktywne zmiany tożsamości/dat klientów zawsze wymagają jawnego potwierdzenia użytkownika — nie ma tu ustalonej reguły domyślnej, zależy od kontekstu (czy backfill i tak się odbywa).

### Raport publiczny (raport-site) — zregenerowany po Fazie 7b

`raport-site/index.html` nie ma własnego skryptu generującego w repo (potwierdzone — brak `.github/workflows`, brak skryptu w tamtym repo). Zregenerowany ręcznie jednorazowym skryptem (`/tmp/.../regen_report.py`, nie część żadnego repo — czysto pomocniczy) łączącym się read-only do żywej bazy: przeliczone sekcje **historyczne** (`pnl_monthly`, `annual_revenue`, `headcount_monthly`, `top_customers`, `nace`, `product_rev`, `segment_totals`/`segment_customers`, `utilization`, większość `kpi`) bezpośrednio z Supabase. Sekcja **prognozy** (`forecast_monthly`, `aug_2026_full_estimate`, `kpi.fy2026_estimate`, `kpi.fy2027_forecast_trend`) **świadomie NIE odświeżona** — metodologia (regresja liniowa na 24 miesiącach) nie jest znana w żadnym z tych repo (raport zbudowany kiedyś poza nimi), stopka raportu jawnie to teraz zaznacza: "reflects the operations database as of 20 August 2026 and has not been refreshed alongside the historical sections above".

**Znaleziony i naprawiony błąd przy okazji**: pierwsza wersja przeliczenia użyła `v_headcount_monthly` (widok BI) dla `headcount_now` — dała 12 zamiast 17, bo ten widok liczy tylko pracowników billable (Leveranse/Teknologi), nie pełny headcount kadrowy (dokładnie ta pułapka opisana w `POWERBI_CONNECTION.md`). Naprawione: liczone bezpośrednio z `employments` (start_date/end_date), zgodnie z definicją używaną przez oryginalny raport.

Zweryfikowane wizualnie (browser, brak błędów w konsoli) i liczbowo (marża 2020 z raportu = 19,22%, identyczna z bazą). **Nie zacommitowane/wypchnięte przeze mnie** — publikacja publicznej strony wymaga jawnej zgody, użytkownik zdecydował zrobić to sam (komendy podane w czacie).

---

## Faza 7c — duży incydent 2023 (utrata klienta Enterprise), 2026-09-01

**Wybrany klient**: **K03 (Nordkraft Energi AS)**, spośród 4 kandydatów Enterprise (Bergström Industri, Nordkraft Energi, Rogaland Teknikk, Innlandet Helse) — jedyny (razem z K08) bez ŻADNYCH wcześniejszych zdarzeń z Fazy 7/7b, a przy tym druga co do wielkości (24,05M NOK skumulowanego przychodu, tuż za K01 z 24,57M) — realny ciężar utraty, czysta historia bez nakładających się efektów. `churn_date=2023-04-01`, ten sam mechanizm co K09/K15 (statyczne pole, bez wymuszonego `WRITTEN_OFF` — utrata przychodu na przyszłość, nie problem ze ściągalnością).

### Odrzucone podejścia — pełna historia decyzji (żeby nie powtarzać tej samej ścieżki w przyszłości)

1. **Zadanie 2 (mniejsze echo Mid-market 2025) z K05** (Fjord Logistikk AS, największy Mid-market, 11,7M) — pierwsza próba dała **margin 2025 = -0,28%**, drastycznie poza miękką wytyczną (~3-4%). K05 był po prostu za duży na "mniejsze echo".
2. **Zamiana na K32** (Harstad Finans AS, 6,5M, mniejszy) — poprawiło 2025, ale offline sanity-check ujawnił, że **samo K03 w izolacji (bez żadnego echa) już depresuje 2024-2026 trwale** (1,06% / 0,61% / 2,40%), nie tylko 2023 — problem strukturalny, nie kwestia doboru drugiego klienta.
3. **Kompensujący "wygrany kontrakt" — K51** (Sunnmøre Sjømat AS, Enterprise, onboarding 2023-09-01, świadomie po fellesferie — nawiązanie do reguły z Fazy 7a "unikaj lipca") — wygenerował tylko 1,35M/rok vs 3,21M jakie dawał K03, bo klienci onboardowani po `CUSTOMER_PRICING_COHORT_CUTOFF` (2023-01-01) dostają tańszy cennik `SCALE_SERVICES` (Faza 4, różnica ~2,3x vs `LEGACY_SERVICES`) — jeden klient fizycznie nie odtwarza przychodu.
4. **Drugi kompensujący klient — K52** (Fosen Vind AS, onboarding 2023-11-01) — nawet dwóch klientów SCALE łącznie (2,75M) nie odtworzyło przychodu K03 (3,36M), a DODATKOWO **podwoiło koszt COGS S01+S02** (naliczany per klient Enterprise, ~900k NOK/rok bazowo, niezależnie od jego wielkości przychodowej) — więcej klientów o mniejszym przychodzie jest w tym modelu kosztowo NIEEFEKTYWNE. 2024=2,66%, 2025=1,28%, 2026=1,95% — lepiej, ale wciąż daleko poza pasmem.
5. **Finalna decyzja**: K51 i K52 (oraz cała idea sztucznej kompensacji) **całkowicie wycofane**. Zadanie 2 (echo Mid-market) **całkowicie wycofane** — jeden incydent bez wymuszonej kompensacji już dał wystarczająco realistyczny, wieloletni efekt. Marża odbudowuje się **wyłącznie** dzięki już istniejącemu w modelu, organicznemu tempu wzrostu portfela klientów (harmonogram onboardingu K13-K50 z Fazy 4/6) przy stałym `headcount=17` (mechanizm z Fazy 6: stały zespół + rosnący portfel = rosnąca marża w czasie) — bez żadnych nowych, syntetycznych klientów dodanych w tym celu.

### Finalny wynik — marża 2023-2026 (dokładne liczby, offline = żywa baza po backfillu)

| Rok | Przychód | Payroll | Opex | COGS | Marża | vs pasmo 5,5-9% |
|---|---|---|---|---|---|---|
| 2022 (przed incydentem) | 23 382 082 | 11 210 947 | 1 993 145 | 7 462 222 | 11,61% | powyżej (Faza 6, nietknięte) |
| **2023** | 29 978 922 | 15 582 464 | 2 072 874 | 11 229 462 | **3,65%** | poniżej (cel zadania: 2-4% ✓) |
| **2024** | 34 831 247 | 16 257 989 | 2 135 412 | 16 067 362 | **1,06%** | poniżej — NIE odbudowa jak oczekiwano w pierwotnym zadaniu |
| **2025** | 40 090 592 | 16 745 730 | 2 182 608 | 20 918 107 | **0,61%** | poniżej — najgłębszy punkt (nie 2024) |
| **2026** (do sierpnia, w pełni zamknięte) | 31 767 910 | 11 607 818 | 1 466 761 | 17 784 207 | **2,86%** | poniżej, ale wyraźna tendencja wzrostowa |

**Ilość lat do pełnego powrotu w pasmo 5,5-9%: nieznana — NIE nastąpił w obecnie wygenerowanej historii (2019-2026)**. Trajektoria nie jest monotoniczna (dołek w 2025, nie 2024), z wyraźnym odbiciem dopiero w 2026. To **realistyczny, zaakceptowany strukturalny wynik modelu**: trwała utrata dużego klienta Enterprise przy stałym zespole (COGS per-klient + payroll niezależny od portfela) tworzy wieloletnią "bliznę" (scar), którą sam organiczny wzrost klientów nie nadrabia w pełni w rozsądnym czasie — to jest ekonomicznie sensowne, nie błąd kalibracji.

### ⚠️ Jawne odnotowanie zgodnie z decyzją biznesową tej fazy

**Próg bezpieczeństwa 5,5-9% wraca do obowiązywania BEZ WYJĄTKÓW od tej fazy w przód.** Wyjątek dla 2023-2026 wprowadzony w Fazie 7c jest **jednorazowy i świadomy** — nie jest nową, luźniejszą regułą. Każda przyszła zmiana modelu musi respektować pasmo 5,5-9% dla lat 2023+ tak jak przed tą fazą, chyba że zostanie osobno, jawnie ustalona nowa decyzja biznesowa analogiczna do tej.

### Testy

`tests/test_faza7c_major_incidents.py` (nowy, 3 testy — pełny churn K03, brak wymuszonego WRITTEN_OFF, lata 2019-2022 bit-identyczne z zamrożonymi wartościami sprzed tej fazy) + poprawki w istniejących testach, które kodowały teraz-nieaktualne założenia:
- `test_order_generator.py::test_only_smb_customers_have_churn_date` → przemianowany na `test_static_churn_dates_match_known_roster`, rozszerzony o K03
- `test_order_generator.py::test_customer_count_grows_with_onboarding_schedule` — liczba klientów sierpień 2023: 21→20 (K03 już nieaktywny)
- `test_order_generator.py::test_monthly_orders_use_customer_payment_terms` — data testu przesunięta z 2024-01 na 2022-01 (sprzed churnu K03)
- `test_faza6_market_calibration.py::test_margin_within_safety_threshold_2025_2026` — pasmo 5,5-9% zastąpione sanity floor (margin ≥ 0), z jawnym wyjaśnieniem dlaczego (ten sam wzorzec co niżej)
- `test_faza7b_macro_shock.py::test_macro_shock_does_not_affect_2023_2026` — przepisany na bezpośrednią weryfikację funkcji mnożników (zawsze 1.0 poza 2020) zamiast pełnego backfillu + pasma marży, które nie jest już aktualne dla tych lat z niezwiązanej przyczyny (ta faza) — bardziej odporny test tego samego twierdzenia
- `test_faza7_task4_regression.py::test_fellesferie_reduces_july_ticket_volume` — próg 0,7→0,75 (zmiana bazy klientów przesunęła dokładny stosunek na granicę poprzedniego progu)

**232/232 testów offline** (`pytest -q`).

---

## Audyt dostawców względem Brønnøysundregistrene (2026-09)

Prompt referencjonował "poprzednią sesję" z `scripts/audit_name_collisions.py` (audyt klientów) — **sprawdzone, nie istnieje w tym repo, brak śladu w git ani w tym dokumencie**. Potraktowane jako punkt startowy od zera, udokumentowane wprost (nie milczane) w `docs/DATA_SAFETY.md`. Klienci pozostają nieaudytowani względem Brreg — poza zakresem tej sesji (Zadanie 1/2 promptu dotyczyły wyłącznie dostawców).

**Zadanie 2 (nazwa własnej symulowanej firmy)**: sprawdzone — firma nigdzie w projekcie nie ma nadanej nazwy (ani `roster.py`, ani `DATA_DICTIONARY.md`, ani `raport-site` — wszędzie generyczne "the company"). Nic do zrobienia, czysty wynik.

**Zadanie 1 (audyt 8 dostawców, `scripts/audit_supplier_names.py` → data.brreg.no)**:

| # | Dostawca | Wynik | Decyzja |
|---|---|---|---|
| L01-L04 | Microsoft Norge AS, Telenor Norge AS, Reitan Convenience AS, Statsbygg | Dokładne dopasowania, org.nr potwierdzone | Bez zmian |
| L05 | Sandvik IT Solutions AS | Tylko mała, niezwiązana firma "SANDVIK IT" (Fister) — nie globalny koncern | **Zostaje fikcyjna** (decyzja użytkownika) |
| L06 | ~~Advokatfirma Thommessen~~ | Literówka (brak "et") — realna, znana kancelaria | **Poprawione** na "Advokatfirmaet Thommessen AS", org.nr 957423248 |
| L07 | Avis Norge AS | Niejednoznaczne — API Brreg zwraca tysiące wyników na wieloznaczne słowo "avis" (norw. "gazeta") | **Zostaje bez zmian** (decyzja użytkownika — marka i tak rozpoznawalna) |
| L08 | ~~Nordic Insurance Partners AS~~ | W pełni fikcyjny | **Zastąpione** realną marką "Gjensidige Forsikring ASA", org.nr 995568217 (decyzja użytkownika) |

**Implementacja**: nowe pole `SupplierSeed.real_org_number` (Python, informacyjne) mapowane na **istniejącą** kolumnę `suppliers.organization_number` (standardowe pole schematu Tripletex — nie dodano nowej kolumny, wbrew sugestii promptu, bo już istniała i była niewykorzystana). Przy okazji naprawiony błąd: `seed_reference_data()` dla dostawców używał `ON CONFLICT (id) DO NOTHING` (w przeciwieństwie do `customers`, które ma `DO UPDATE`) — zmiana nazwy w `roster.py` nigdy by się nie propagowała do już istniejących rekordów w bazie. Zmienione na `DO UPDATE SET name, organization_number`, zgodnie ze wzorcem `customers`.

**Zaktualizowano Supabase**: `seed_reference_data()` uruchomiony ręcznie (idempotentny UPSERT metadanych — bezpieczny, nie wymaga `TRUNCATE`/backfillu, bo to nie są dane transakcyjne). Zweryfikowano na żywej bazie: `suppliers.name`/`organization_number` poprawne dla wszystkich 8.

**Znaleziony i naprawiony efekt uboczny**: 121 już istniejących `vouchers.description` zawierało stare nazwy tekstowo (`description` budowany raz przy generowaniu, nie odświeża się przy zmianie referencji — FK do `suppliers.id` był cały czas poprawny, to czysto kosmetyczny rozjazd tekstu). Naprawione jednorazowym skryptem `scripts/fix_stale_supplier_names_in_vouchers.py` (`UPDATE ... REPLACE()` na samym tekście opisu — **zero zmian kwot/kont/dat**, zweryfikowane przed i po). `postings.description` sprawdzone — zawsze `NULL`, nie wymagało naprawy.

**raport-site**: sprawdzone — żadna ze zmienionych nazw (Thommessen, Gjensidige) nigdzie nie występuje w opublikowanym raporcie (widoczna tabela top-dostawców pokazuje tylko Avis/Microsoft/Sandvik/Telenor, bez zmian). **Regeneracja raportu niepotrzebna** dla tego zadania.

**Zadanie 3**: `docs/DATA_SAFETY.md` utworzony (nie istniał) — pełny opis odwrotnej logiki klienci/dostawcy, tabela wyników audytu, znane ograniczenie (brak audytu klientów).

Nowy test regresyjny: `tests/test_seed_roster_payroll.py::test_supplier_names_match_brreg_audit` — zamraża nazwy/`real_org_number` jako regresję, potwierdza że kwoty/konta L08 nietknięte. **233/233 testów offline.**

Kod zacommitowany lokalnie (`98e9c24`) — git odzyskał dostęp (wcześniejszy problem macOS TCC na folderze Desktop ustąpił sam). Niewypchnięty jeszcze na GitHub.

---

## Historia projektu (PROJECT_HISTORY.md) + dostęp demo (2026-09-03)

**README.md NIE zostało zaktualizowane w żadnej "poprzedniej sesji"** — sprawdzone, wciąż miało treść sprzed Fazy 1/2 (16 pracowników, 12 klientów, ~35M NOK, "nie przetestowane end-to-end", 43 testy) — trzeci taki przypadek w tej sesji (po `audit_name_collisions.py` i `DATA_SAFETY.md`). Odnotowane wprost, nie naprawione w całości (poza zakresem tego promptu) — dodane tylko dwie sekcje z linkami ("Project history", "Explore it"), reszta README zostaje nietknięta i **wciąż nieaktualna**. Warto to naprawić osobną sesją.

**`docs/PROJECT_HISTORY.md`** — nowy, chronologia v5.0→obecnie z zweryfikowanymi faktami (nie skopiowanymi na ślepo z szablonu promptu): sekcja "Data safety review" promptu sugerowała tagi v5.15-v5.16, których nie ma — opisana jako "post-v5.13, unreleased" zamiast wymyślać nieistniejące numery wersji.

**Dostęp demo (`demo_reader`)** — osobna rola od `powerbi_reader` (świadomie, uzasadnienie w `scripts/setup_demo_reader.py`): `powerbi_reader` nie miał `statement_timeout`, a rotacja/unieważnienie hasła demo zerwałoby też prawdziwe połączenie właściciela. Utworzona i **zweryfikowana end-to-end na żywej bazie**: `SELECT` działa (50 klientów), `INSERT`/`UPDATE` odrzucone (`InsufficientPrivilege`), `statement_timeout=10s` egzekwowany (`pg_sleep(11)` przerwane), `CONNECTION LIMIT 2` egzekwowany (3. jednoczesne połączenie odrzucone).

**Hasło demo_reader wygenerowane i wypisane w terminalu tej sesji — NIE zapisane w żadnym pliku ani repo.** Do przekazania bezpiecznym kanałem przez użytkownika.

`docs/API_ACCESS.md` — nowy, opisuje proces uzyskania dostępu (host/port/username realne, hasło nigdzie w dokumencie). Zero zmian logiki generatora/cen/kosztów — potwierdzone, 233/233 testów bez zmian.
