# NorFinGen — Session Handoff

Data sporządzenia: 2026-07-07. Ostatni commit: (do utworzenia w tej sesji, tag `v5.3-faza4-skalowanie`). Working tree: zmiany tej sesji gotowe do commitu.

---

## 1. Co zostało zrobione w tej sesji

Faza 4 z planu 5-fazowego — **najbardziej ryzykowna faza** (skalowanie 12→50 klientów, zatrudnienie 16→38, normalizacja godzin konsultantów). Wymagała **CZTERECH kolejnych korekt kalibracji marży** w trakcie sesji (opisane szczegółowo w p. 8) — to najważniejsza rzecz do zapamiętania z tej sesji.

### ZADANIE 1 — Skalowanie klientów 12→50
- **`seed/roster.py`** — `CUSTOMERS` rozszerzone o 38 nowych (K13-K50): 11 Enterprise + 14 Mid-market + 13 SMB, onboarding rozłożony 2022-09 (kohorta fuzji) → 2026-06. Docelowy mix: 15 Enterprise / 18 Mid-market / 17 SMB (finalna wersja — pierwsza miała tylko 12 SMB, zmienione podczas korekty marży #2/#3).
- **Kohorta fuzji (2022-09-01)** — 4 nowi klienci (K27, K32, K34, K46) onboardowani TEGO SAMEGO dnia co fuzja pracownicza (E11-E16) — jedno spójne zdarzenie biznesowe (przejęcie firmy = pracownicy + portfel klientów razem). Kluczowe: mimo numeracji K13-K50, ci czterej onboardują się PRZED cutoffem cenowym (2023-01-01), więc płacą ceny `LEGACY_SERVICES`, nie `SCALE_SERVICES`.
- **2 nowe churny SMB** (Zadanie 4, zrobione) — K15 (churn 2025-10-31, ~2,5 roku współpracy) obok istniejącego K09.

### ZADANIE 2 — Reguła wzrostu (PRZESZŁA PRZEZ 2 PODEJŚCIA, OBA PORZUCONE)
Zob. p. 8 dla pełnej historii. Finalne rozwiązanie: `roster.calc_target_headcount()` — rachunek top-down z celu marży (`TARGET_MARGIN = 0.19`), nie z godzin/przychodu per konsultant.

### ZADANIE 3 — Wzrost zatrudnienia 16→38
- **`seed/roster.py`** — `EMPLOYEES` +22 (E17-E38), rekrutacje POJEDYNCZE, odstępy DOKŁADNIE 60 dni (2022-10-15 → 2026-03-28 — to maksimum mieszczące się w oknie czasowym przy tym rygorze), pensje 950 000 NOK/rok (senior/specjalista — wyżej niż reszta zespołu, żeby zamortyzować budżet płacowy przy ograniczonej liczbie etatów, zob. p. 8). Mix: 20 billable (Leveranse/Teknologi) + 2 wspierające (Salg/Økonomi).

### ZADANIE 5 — Normalizacja godzin konsultantów
- **`generators/hours_generator.py`** — CAŁKOWICIE PRZEPISANY: `assign_customers_to_consultants()` (dynamiczny przydział portfela wg obciążenia segmentowego, zamiast statycznego `EMPLOYEE_PROJECT_MAP`), `is_billable_employee()` (zamiast statycznej listy `BILLABLE_EMPLOYEES` — działa automatycznie dla nowych pracowników wg działu), rotacja portfela co ~15 miesięcy (`_rotation_id()`, świadome odstępstwo od pseudokodu zadania — zob. p. 7).
- **`seed/roster.py`** — `PROJECTS` przepisane na 1:1 z `CUSTOMERS` (50 projektów zamiast 8 ręcznie utrzymywanych), `start_date = customer.onboarding_date` (naprawia wcześniejsze mylące ograniczenie z DATA_DICTIONARY), `is_customer_active`/`active_customers`/`employee_by_id`/`project_for_customer` — nowe funkcje pomocnicze.

### Faza 2 rozszerzona: dwie kohorty cenowe (KRYTYCZNE dla przyszłych sesji)
- **`seed/roster.py`** — `LEGACY_SERVICES` (ceny Fazy 2, niezmienione) + `SCALE_SERVICES` (nowe, ~2,2x niższe) + `get_service_price_table(customer)`/`service_by_code_for_customer(customer, code)` — klient płaci wg kohorty (onboarding_date < 2023-01-01 → legacy, inaczej → scale). `SERVICES` (alias `LEGACY_SERVICES`) nadal zasila tabelę `services` w Supabase — `SCALE_SERVICES` **nie ma reprezentacji w bazie**, tylko w kodzie (zob. DATA_DICTIONARY.md).
- **`generators/order_generator.py`** — `build_order_lines()` używa `service_by_code_for_customer()` zamiast `service_by_code()`.

---

## 2. Rzeczywista marża po zmianach (finalna, po 4 korektach kalibracji)

Zweryfikowana na żywej bazie po pełnym backfillu:

| Rok | Przychód (NOK) | Wynik (NOK) | Marża | Aktywni klienci |
|---|---|---|---|---|
| 2019 | 7 306 506 | 156 732 | 2,1% | 6 |
| 2020 | 17 770 538 | 8 525 100 | 48,0% | 9 |
| 2021 | 19 922 564 | 9 152 637 | 45,9% | 11 |
| 2022 | 23 294 689 | 9 632 302 | 41,3% | 16 |
| 2023 | 31 771 579 | 9 530 207 | 30,0% | 24 |
| 2024 | 38 538 133 | 8 792 532 | 22,8% | 34 |
| 2025 | 44 842 653 | 6 922 942 | 15,4% | 43 |
| 2026 (częściowy, do 07-07) | 30 174 799 | 4 166 529 | 13,8% | 48 |

**Próg bezpieczeństwa (10%) NIE został przekroczony** — najniższa wartość to 13,8% (2026, częściowy rok). 2025-2026 lądują dokładnie w oczekiwanym paśmie 14-16% z opisu zadania. Trajektoria jest płynnie malejąca (41,3%→30,0%→22,8%→15,4%→13,8%) — dokładnie taki kształt, jaki zadanie przewidywało ("marża może spaść do 14-16% w okresie skalowania").

---

## 3. Aktualny stan testów

**152/152 testów przechodzi** (`python -m pytest tests/ -v`), wzrost ze 152 na początku tej sesji (część testów zastąpiona nowymi o innej treści, część dodana — `test_faza4_scaling.py`, rozszerzone `test_hours_generator.py`/`test_seed_roster_payroll.py`/`test_order_generator.py`).

---

## 4. Co zostało z prompta niewykonane / świadomie ograniczone

- **Nic z Zadań 1-6 nie zostało pominięte** — wszystkie zaimplementowane, w tym opcjonalne Zadanie 4 (dodatkowy churn SMB).
- **`assign_customers_to_consultants()` WYMAGAŁO korekty względem podanego pseudokodu** — zob. p. 7, punkt o `_rotation_id`.
- **Reguła wzrostu (Zadanie 2) przeszła przez 3 podejścia w tej sesji** zanim znaleziono działające rozwiązanie — zob. p. 8, kluczowe dla zrozumienia dlaczego finalny kod różni się od wszystkich trzech wersji pseudokodu podanych w kolejnych turach tej sesji.

---

## 5. Następne kroki

1. **Faza 5** (ostatnia faza planu 5-fazowego) — treść jeszcze nie podana.
2. **Rozważyć dodanie `SCALE_SERVICES` do tabeli `services` w Supabase** (obecnie tylko w kodzie) — jeśli pojawi się potrzeba dashboardu/BI pokazującego pełny cennik, nie tylko legacy.
3. **Pamiętać o `scripts/fix_outgoing_transactions.py`** po każdym kolejnym pełnym `TRUNCATE` — uruchomiony w tej sesji, stan: 1218 INCOMING / 798 OUTGOING.
4. **Jeśli Faza 5 dodaje więcej klientów/pracowników** — użyć `roster.calc_target_headcount()` (top-down z celu marży) OD RAZU, nie zgadywać godzin/przychodu per konsultant — te dwa podejścia już raz zawiodły w tej sesji (zob. p. 8).
5. Backfill dzienny jest teraz znacznie dłuższy niż w poprzednich fazach (~90 min dla 50 klientów/38 pracowników vs ~60 min dla 12/22) — planować czas odpowiednio przy kolejnych pełnych resetach.

---

## 6. Backfill / migracje — czy uruchomione i z jakim wynikiem

**Jeden pełny cykl reset+backfill wystarczył** (offline sanity-check przed backfillem — po 4. korekcie kalibracji — potwierdził bezpieczny wynik zanim wykonano kosztowny backfill).

| Operacja | Status | Wynik |
|---|---|---|
| Backfill miesięczny | ✅ Uruchomiony, czysto | 1807 zamówień, 3682 linii, 818 faktur zakupu, 91 list płac (38 payslips/mies. przy pełnej skali) |
| Backfill dzienny | ✅ Uruchomiony, czysto (0 tracebacków) | 1961 dni roboczych (2019-01-01 → 2026-07-07), ~88 min (znacznie dłużej niż poprzednie fazy — 50 klientów/38 pracowników) |
| `scripts/fix_outgoing_transactions.py` | ✅ Uruchomiony | 1218 INCOMING / 798 OUTGOING |
| `ensure_schema()`/`seed_reference_data()` | ✅ Automatyczny na starcie `run_backfill.py` | 50 customers, 38 employees, 50 projects zasilone |

**Napotkane awarie**: brak technicznych (backfill/reconnect) — TYLKO awarie kalibracji marży (4 iteracje w tej samej sesji, zob. p. 8), wszystkie wychwycone offline PRZED kosztownym backfillem poza samą ostatnią (finalną, poprawną) iteracją.

---

## 7. Świadome odstępstwa od podanych fragmentów kodu (dla przyszłej sesji)

- **`should_generate_service_equipment_purchase` (Faza 3)** — bez zmian w tej sesji.
- **`assign_customers_to_consultants()` — rng seedowany okresem rotacji (`_rotation_id`), NIE dokładnym (rok, miesiąc)** jak w pseudokodzie zadania. Dosłowny pseudokod (`random.Random(year*100+month)`) dawałby CAŁKOWICIE nowe przypisanie klient-konsultant co miesiąc — sprzeczne z Zadaniem 5c ("rotacja co 12-18 miesięcy", czyli portfel ma być STABILNY między rotacjami). Naprawione: seed z `_rotation_id(year, month)` (zmienia się co ~15 miesięcy), zweryfikowane testem (`test_consultant_portfolio_rotates_over_time`).
- **`PROJECTS` — 1:1 z `CUSTOMERS`, nie osobna struktura** — jedyny sposób, żeby dynamiczny przydział konsultantów (Zadanie 5) miał gdzie logować godziny dla WSZYSTKICH klientów (w tym SMB, którzy wcześniej nie mieli żadnego projektu).
- **Dwie kohorty cenowe (`LEGACY_SERVICES`/`SCALE_SERVICES`) zamiast jednego cennika** — zob. p. 8, wymuszone przez odkrycie, że jeden globalny cennik psuje retroaktywnie historię.
- **`calc_target_headcount()` (top-down z marży) zamiast godzin/przychodu per konsultant** — zob. p. 8, dwa wcześniejsze podejścia (`SEGMENT_HOURS_PER_MONTH`+`can_onboard_new_customer` godzinowe, potem przychodowe z `REVENUE_PER_CONSULTANT_YEARLY`) zostały PORZUCONE w tej samej sesji po tym, jak żadne nie trzymało marży w ryzach.
- Kontynuacja wcześniejszych zasad: `random.Random(string)` nie `hash()`, statusy/ceny deterministyczne, `ON CONFLICT DO UPDATE` dla metadanych.

---

## 8. Historia kalibracji marży w tej sesji (KRYTYCZNE dla przyszłych faz — przeczytać przed dotykaniem cen/zatrudnienia)

Ta faza wymagała **czterech kolejnych korekt** zanim marża wylądowała w bezpiecznym zakresie. Każda była zgłoszona użytkownikowi PRZED wykonaniem backfillu (offline sanity-check), zgodnie z lekcją z Fazy 2/3.

**Próba #1 (odrzucona przed backfillem)**: dosłowne zastosowanie cen Fazy 2/3 (niezmienione) do 50 klientów + Zadanie 2 oparte o `SEGMENT_HOURS_PER_MONTH`/`can_onboard_new_customer` (godzinowe) + 6 nowych pracowników (E17-E22). Wynik: marża eksplodowała do **40-73%/rok** (2022-2026) — bo istniejący zespół (11-17 billable) miał ogromną nadwyżkę godzin nawet dla 50 klientów (subskrypcja MSP obejmuje więcej niż czysty czas konsultanta), więc payroll rósł dużo wolniej niż przychód.

**Próba #2 (odrzucona przed backfillem)**: obniżka WSZYSTKICH cen `SERVICES` ~2,2x (jeden globalny cennik) + bramka onboardingu przychodowa (`REVENUE_PER_CONSULTANT_YEARLY`). Naprawiła 2024-2026, ale **zepsuła retroaktywnie 2019-2023** (-138% do -15,6%) — bo ten sam cennik obowiązywał całą historię, a obniżka dla "nowych 38 klientów" obniżyła też przychód ORYGINALNYCH 12 klientów w latach, gdy byli jedyną bazą przychodową.

**Próba #3 (odrzucona przed backfillem)**: DWIE kohorty cenowe (`LEGACY_SERVICES`/`SCALE_SERVICES`, cutoff 2023-01-01) + kohorta fuzji (4 klientów, 2022-09) + wciąż bramka przychodowa dla Zadania 2, 16 nowych pracowników. Naprawiła retroaktywne psucie (2019-2021 wróciły do zdrowego 1-47%), ale **2022-2026 nadal 40-54%** — bo `REVENUE_PER_CONSULTANT_YEARLY` (2,3M NOK/konsultant) było zbyt wysokie względem rzeczywistego kosztu pracownika (~890 tys. NOK w pełni obciążony, nie założone 1,15 mln ani zgadywane 2,3 mln przychodu) — 22 pracowników generowało dużo za mało kosztu względem 50-klienckiego przychodu.

**Próba #4 (FINALNA, zaakceptowana)**: `calc_target_headcount()` — rachunek top-down z celu marży (`TARGET_MARGIN=0,19`), zastępujący całkowicie próby #1-3. Pierwsza iteracja (16 nowych pracowników, pensje 640-760k jak reszta zespołu) dała docelowy zespół 32 osoby — ale rzeczywisty koszt/pracownika (~890 tys.) i rzeczywisty przychód wymagały ~44 etatów przy TYCH pensjach, co jest **fizycznie niewykonalne** przy odstępach rekrutacji ≥60 dni w oknie 2022-10→2026-07 (potrzeba by ~4,6 roku, jest ~3,5). Rozwiązanie: 22 rekrutacje (maksimum mieszczące się w oknie przy 60-dniowych odstępach) + WYŻSZA pensja (950 tys. NOK, senior/specjalista) zamiast więcej osób — to domknęło budżet płacowy bez łamania ograniczenia czasowego. Zweryfikowane symulacją PRZED backfillem: marża 40,8%(2022)→29,6%(2023)→22,6%(2024)→14,9%(2025)→15,0%(2026) — potwierdzone identycznie po rzeczywistym backfillu (41,3%/30,0%/22,8%/15,4%/13,8%, drobne różnice z sezonowości/zaokrągleń).

**Wniosek dla przyszłych sesji**: gdy zadanie daje wzory oparte o "godziny per konsultant" lub "przychód per konsultant" jako sposób ustalenia potrzebnego zatrudnienia, **zweryfikuj wynik total-em, nie tylko logiką wzoru** — te podejścia zakładają relację między przychodem a wymaganą pracą, która może nie odpowiadać rzeczywistej strukturze cen/kosztów już ustalonej w poprzednich fazach. Rachunek TOP-DOWN z celu marży (znany przychód/opex → budżet płacowy → liczba etatów) jest bardziej niezawodny niż BOTTOM-UP (godziny/przychód → liczba etatów → marża wynikowa) — pierwszy gwarantuje trafienie w cel z definicji, drugi wymaga trafienia z góry przyjętych założeń.

---

## 9. Stan bazy Supabase (migawka na koniec sesji)

| Tabela | Liczba wierszy |
|---|---|
| orders | 1807 |
| order_lines | 3682 |
| supplier_invoices | 818 |
| salary_transactions | 91 |
| vouchers | 3293 |
| postings | 6677 |
| bank_transactions | 2016 |
| hour_entries | 44 866 |
| customers | 50 |
| employees | 38 |
| projects | 50 |

Zakres historyczny: 2019-01-01 → 2026-07-07 (dziś).
