# NorFinGen — Session Handoff

Data sporządzenia: 2026-07-05. Ostatni commit: `290c6f3` (tag `v5.0-faza1-fundament`). Working tree czyste, `main` = `origin/main`.

---

## 1. Co zostało zrobione w tej sesji

Sesja objęła 5 commitów/tagów, od `53d20c5` (Etap 3) do `290c6f3` (Faza 1). Poniżej w kolejności chronologicznej.

### `53d20c5` — feat: etap3 (inflacja, podwyżki, sezonowość, marża, PAID status, export excel)
- **`export_excel.py`** — przychody liczone z `orders/order_lines` (nie z auto-postingów), dodana kolumna `wynik_operacyjny`
- **`supplier_invoice_generator.py`** — auto-status PAID dla faktur >45 dni po terminie; **`scripts/update_paid_status.py`** — migracja jednorazowa
- **`run_daily.py`, `db/repository.py`** — `month_already_generated()`, pomija generację już istniejącego miesiąca
- **`order_generator.py`** — `apply_annual_inflation()` (+3%/rok)
- **`seed/payroll.py`, `salary_generator.py`** — `calc_brutto_with_raises()` (+3%/rok w lipcu)
- **`order_generator.py`, `supplier_invoice_generator.py`** — sezonowość L07 Avis (Q1/Q3) i K06 Consulting (Q2/Q4)
- **`seed/roster.py`** — ceny produktów P01-P05 obniżone ~17%, marża 33,3%→19,8%

### `be1558b` — feat: tier2 (daily generation, bank transactions, hours, projects)
- **`seed/roster.py`** — `invoice_day`/`payment_terms` per klient, `PROJECTS` (8 projektów), `numeric_id()` rozszerzony o prefiksy wieloliterowe
- **`models/bank_transaction.py`, `generators/bank_transaction_generator.py`** — nowy model + generator płatności (DR/CR 1910/1500/2400)
- **`models/hours.py`, `generators/hours_generator.py`** — `HourEntry`/`ActivityType`, timesheet billable/internal/sick
- **`db/schema.sql`** — 3 nowe tabele: `projects`, `bank_transactions`, `hour_entries` (16→19 tabel)
- **`run_daily.py`** — przepisany na rytm dzienny (orders→bank→hours→salary)
- **`run_backfill.py`** — `--mode daily` + retry/reconnect po padach połączenia
- **`db/repository.py`** — `save_orders/save_bank_transactions/save_hour_entries/save_salary`, `get_orders_for_payment_window`, `get_unpaid_supplier_invoices`, `seed_projects`

### `efb0790` — fix: backfill 526 brakujących transakcji OUTGOING
- **`scripts/fix_outgoing_transactions.py`** — jednorazowa migracja uzupełniająca brakujące `BankTransaction(OUTGOING)` dla historycznych faktur zakupu ze statusem PAID nadanym starą heurystyką

### `76c8006` — feat: realistyczny start firmy (progresywne zatrudnienie i onboarding klientów)
- **`seed/roster.py`** — kohorta założycielska E01-E06 rozłożona na 4 miesiące (2019-01→2019-04, nie 1 dzień); `onboarding_date`/`churn_date` dodane do `CustomerSeed`, harmonogram onboardingu 12 klientów (pierwszy K01 marzec 2019, komplet dopiero 2022)
- **`generators/order_generator.py`** — `_is_active()` (onboarding + churn gating) w `generate_monthly_orders`/`generate_daily_orders`
- **`generators/hours_generator.py`** — `_active_projects_for_employee()` respektuje onboarding/churn klienta projektu

### `6923216` — fix: feriepenger zastępuje a nie dubluje pensję, wariancja cen klientów, churn
- **`seed/payroll.py`** — `JuneSalary`/`calc_june_salary()` — feriepenger **zastępuje** pensję czerwcową (nie dodaje się), naprawiony błąd narastającego podwojenia kosztu
- **`generators/salary_generator.py`** — usunięte 2 zbędne vouchery (zawsze 2/miesiąc, nie 4 w czerwcu)
- **`seed/roster.py`** — `CUSTOMER_PRICE_MULTIPLIER` (±8%, deterministyczny per klient — `random.Random(string)`, **nie** `hash()` wbudowany, bo ten jest solony losowo per proces)
- **`models/order.py`** — `OrderStatus` (PAID/OVERDUE/WRITTEN_OFF), `determine_order_status()` w `order_generator.py` — bad debt (~2%, 0,4% nieściągalne), deterministyczny per zamówienie (nie zależny od `today`)
- **`generators/bank_transaction_generator.py`** — WRITTEN_OFF nigdy nie generuje wpłaty, OVERDUE płaci +90 dni później
- **`db/schema.sql`, `repository.py`** — `orders.status`, poszerzone okno wyszukiwania płatności (45→135 dni)

### `290c6f3` — feat: Faza 1 (katalog usług S01-S04, metadane klientów w Supabase, RLS)
- **`models/service.py`** — `Service`, `BillingModel`, `ServiceSegmentAvailability`
- **`seed/roster.py`** — `SERVICES` (4 usługi), `ProductSeed.service_code` (P01-P03→S01, P04-P05→S02, P06→S04)
- **`db/schema.sql`** — tabela `services`, `ALTER` dla `customers` (`onboarding_date`/`churn_date`/`segment`/`price_multiplier`) i `products.service_code` (FK)
- **`db/repository.py`** — `seed_services()`, `DO UPDATE SET` zamiast `DO NOTHING` dla customers/products (metadane odświeżają się przy każdym seedzie)
- **`scripts/migrate_customer_metadata.py`** — jednorazowa migracja metadanych
- **RLS włączone na 14 tabelach** + rola `analyst` (read-only, 14 polityk `SELECT`) — zweryfikowane bezpieczne (połączenie jako `postgres`, `rolbypassrls=true`, generator zapisuje bez przeszkód)
- **`docs/DATA_DICTIONARY.md`** — pełny opis 20 tabel + sekcja "znane ograniczenia"

---

## 2. Aktualny stan testów

**121/121 testów przechodzi** (`python -m pytest tests/ -v`), wzrost ze 107 na początku tej sesji. Bez żadnych `xfail`/`skip`.

---

## 3. Co zostało z prompta niewykonane

- **Nic z podanych zadań nie zostało pominięte** — każde ZADANIE/podpunkt z serii promptów tej sesji (Etap 3, Tier 2, "realistyczny start firmy", "urealnienie danych", Faza 1 Zadania 1-4) zostało zaimplementowane, przetestowane i (gdzie wymagane) zweryfikowane na żywej bazie.
- **Faza 2** ("zmiany cenowe i skalowanie liczby klientów") — zapowiedziana w kontekście Fazy 1, ale **nie rozpoczęta** — czeka na treść kolejnych zadań.
- Drobne świadome odstępstwa od podanych fragmentów kodu (nie "niewykonane", tylko celowo poprawione — patrz p. 6 tej notatki i uzasadnienia w commitach).

---

## 4. Następne kroki

1. **Faza 2** (zapowiedziana, brak treści) — zmiany cenowe i skalowanie liczby klientów.
2. **Rozważyć backfill dla S03 (Cyberbezpieczeństwo)** — usługa istnieje w katalogu, ale nie ma żadnego powiązanego produktu/przychodu (`docs/DATA_DICTIONARY.md`, sekcja `services`).
3. **Pamiętać o `scripts/fix_outgoing_transactions.py`** po każdym kolejnym pełnym `TRUNCATE` — reset zawsze zeruje `bank_transactions`, trzeba dogenerować brakujące OUTGOING.
4. Jeśli pojawi się potrzeba klienckiego dostępu do danych (dashboard/BI) — rozważyć nadanie roli `analyst` realnemu użytkownikowi logującemu się (`GRANT analyst TO <rola_z_LOGIN>`), bo obecnie `analyst` jest `NOLOGIN` (czysto techniczna rola do przyszłego przypisania).

---

## 5. Backfill / migracje — czy uruchomione i z jakim wynikiem

| Operacja | Status | Wynik |
|---|---|---|
| Backfill miesięczny (×3 w tej sesji, po zmianach w logice zatrudnienia/onboardingu/feriepenger) | ✅ Uruchomiony, ostatni czysto | 853 zamówienia, 545 faktur zakupu, 91 list płac, 0 duplikatów, 0 zamówień przed onboardingiem pierwszego klienta |
| Backfill dzienny (×4, kilka przerwań po drodze) | ✅ Uruchomiony, ostatni czysto (0 tracebacków) | 26 859 wpisów godzin (do 2026-07-03), 1132 transakcje bankowe |
| `scripts/fix_outgoing_transactions.py` | ✅ Uruchomiony po każdym backfillu | 532 OUTGOING / 600 INCOMING (ostatni stan) |
| `scripts/migrate_customer_metadata.py` | ✅ Uruchomiony (Faza 1) | 12 klientów, 4 usługi |
| `ensure_schema()` (RLS, `services`, kolumny) | ✅ Uruchomiony bezpośrednio na Supabase | 14 tabel z `rowsecurity=true`, rola `analyst` + 14 polityk, zweryfikowana idempotencja (2x z rzędu bez błędu) |
| `run_daily.py` (smoke test po włączeniu RLS) | ✅ Uruchomiony | Zapisał dane za 2026-07-05 bez błędu dostępu |

**Napotkane i naprawione awarie backfillu w trakcie sesji** (3 różne przyczyny, wszystkie rozwiązane):
1. Zawieszona sesja `idle in transaction` (pozostałość po zerwanym połączeniu) blokująca insercje — naprawione ręcznie (`pg_terminate_backend`), potem trwale: **`terminate_stale_sessions()`** w `repository.py`, wpięta automatycznie w retry `run_backfill_daily()`
2. Realny zanik sieci/DNS po uśpieniu maszyny, natychmiastowy retry bez efektu — dodane rosnące opóźnienie retry (10/20/30s)
3. Duplikaty zamówień po wprowadzeniu `invoice_day` bez przebudowy starych danych (dzień 1 vs `invoice_day`) — naprawione pełnym resetem + przebudową w poprawnej kolejności

---

## 6. Świadome odstępstwa od podanych fragmentów kodu (dla przyszłej sesji)

- **`random.Random(string)` zamiast `hash()`** wszędzie, gdzie proponowany kod używał wbudowanego `hash()` na stringu do seedowania (mnożnik cen, status zamówienia) — `hash()` na `str` jest solony losowo per proces w Pythonie 3 (bezpieczeństwo), co złamałoby powtarzalność backfillu między uruchomieniami.
- **Status zamówienia (`OrderStatus`) i status faktury zakupu ustalane raz, deterministycznie, przy tworzeniu rekordu** — nie na podstawie `today`/wall-clock w momencie generowania płatności, żeby uniknąć błędu, który już raz naprawialiśmy (stara heurystyka PAID dla `supplier_invoices` zależna od czasu uruchomienia skryptu).
- **`CREATE ROLE`/`CREATE POLICY` opakowane w idempotentne konstrukcje** (`DO $$ IF NOT EXISTS ... $$`, `DROP POLICY IF EXISTS` + `CREATE POLICY`) — surowe wersje z zadania nie są idempotentne, a `ensure_schema()` wykonuje `schema.sql` przy każdym starcie `run_backfill.py`/`run_daily.py`.
- **`ON CONFLICT DO UPDATE SET` zamiast `DO NOTHING`** dla metadanych `customers`/`products`/`services` — inaczej nowe kolumny (Faza 1) nigdy nie zostałyby wypełnione na już istniejących wierszach w Supabase.

---

## 7. Stan bazy Supabase (migawka na koniec sesji)

| Tabela | Liczba wierszy |
|---|---|
| orders | 853 |
| order_lines | 1189 |
| supplier_invoices | 545 |
| salary_transactions | 91 |
| vouchers | 1860 |
| postings | 3808 |
| bank_transactions | 1132 (532 OUTGOING / 600 INCOMING) |
| hour_entries | 26 859 (do 2026-07-03) |
| projects | 8 |
| services | 4 |

Zakres historyczny: 2019-01-01 → 2026-07-05 (dziś).
