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
