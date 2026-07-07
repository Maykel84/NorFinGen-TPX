# NorFinGen — Session Handoff

Data sporządzenia: 2026-07-07. Ostatni commit: (do utworzenia w tej sesji, tag `v5.4-faza5-final`). Working tree: zmiany tej sesji gotowe do commitu.

**To jest FINALNA sesja planu 5-fazowego urealnienia modelu (Faza 1 → Faza 5).** Zob. p. 8 dla podsumowania zamykającego cały projekt.

---

## 1. Co zostało zrobione w tej sesji

Faza 5 — ostatnia, WERYFIKACYJNA faza: audyt feriepenger, ujednolicenie dat zatrudnienia, potwierdzenie końcowego P&L. W przeciwieństwie do Faz 2-4, nie wprowadzała nowej architektury — celem było potwierdzenie poprawności, ale audyt **wykrył i naprawił jeden realny bug** (nie tylko kosmetykę).

### ZADANIE 1a — Feriepengegrunnlag: zweryfikowane jako JUŻ POPRAWNE
`brutto_earned_in_year()` (z Fazy poprawki feriepenger, commit `6923216`) sumuje `calc_brutto_with_raises(employee, year, month)` per miesiąc aktywności — to jest DOKŁADNIE to samo co rzeczywiście wypłacone brutto (bo backfill używa identycznej formuły do generowania faktycznych payslipów), więc automatycznie uwzględnia podwyżki lipcowe w trakcie roku. Brak zmian potrzebnych tutaj — audyt potwierdził poprawność.

### ZADANIE 1b — Pierwszy dzień roboczy miesiąca: NAPRAWIONE (2 problemy)
- **`seed/payroll.py`** — nowa funkcja `first_working_day_of_month(year, month)`.
- **`seed/roster.py`** — poprawione 27 z 38 dat `EMPLOYEES.start_date` (w tym kohorta założycielska E03/E05/E07/E08 i WSZYSTKIE E17-E38 z Fazy 4), żeby przypadały na pierwszy dzień roboczy miesiąca zatrudnienia (bez zmiany miesiąca).
- **Efekt uboczny (oczekiwany, udokumentowany)**: kilka par pracowników ma teraz identyczny `start_date` (E02/E03, E04/E05), a minimalny odstęp między rekrutacjami Fazy 4 spadł z 60 do 29 dni (E33→E34) — bo przyciągnięcie do 1. dnia roboczego miesiąca miało priorytet nad ścisłym zachowaniem 60-dniowych odstępów z Fazy 4.
- **REALNY BUG WYKRYTY I NAPRAWIONY**: `generate_monthly_salary()` i `brutto_earned_in_year()` (w `salary_generator.py`) oraz kantyna (`opex_generator.py`) porównywały aktywność pracownika do **kalendarzowego dnia 1** (`date(year, month, 1)`), nie do faktycznego pierwszego dnia roboczego. Skutek: pracownik, którego `start_date` wypadał 2. lub 3. dnia miesiąca (bo 1. to weekend — 9 z 22 pracowników Fazy 4: E17, E20, E23, E27, E30, E31, E33, E36, E38), **NIE dostawałby wypłaty za swój własny miesiąc zatrudnienia** — dopiero od kolejnego miesiąca. Naprawione: obie funkcje porównują teraz do `first_working_day_of_month()`. Zweryfikowane testem (`test_new_hire_starting_day_two_or_three_paid_in_own_start_month` / `test_new_hire_day_two_or_three_paid_in_own_start_month`).

### ZADANIE 2 — Audyt feriepenger
- **`scripts/audit_feriepenger.py`** — nowy skrypt diagnostyczny, porównuje rzeczywiste dane z Supabase (`salary_specifications` typu Feriepenger, suma brutto czerwcowego) z oczekiwanymi wartościami przeliczonymi z aktualnej logiki generatora.
- **Wynik audytu (po backfillu): BRAK ROZBIEŻNOŚCI.** Zero niezgodności między danymi w bazie a logiką generatora.
- **Dodatkowa poprawka kosmetyczna (Zadanie 2c)**: `generate_monthly_salary()` nie tworzy już wiersza `salary_specifications` typu Feriepenger o kwocie 0 dla pracowników w pierwszym roku stażu (wcześniej tworzył wiersz z `amount=0.0` — technicznie nie błąd finansowy, ale niezgodne z dosłownym "nie generuje się żadne feriepenger").

### ZADANIE 3 — Backfill (WYMAGANY, bo Zadanie 1b zmieniło roster.py i naprawiło realny bug)
Wykonany: TRUNCATE + monthly + daily + `fix_outgoing_transactions.py` — zob. p. 5.

### ZADANIE 4 — Weryfikacja końcowa
- P&L potwierdzony (p. 2) — bardzo zbliżony do Fazy 4 (odchylenia 1-2 pkt proc./rok, jedno wyjątek: 2019 spadło z ~2% do ~0%, zob. p. 2 uzasadnienie).
- Korelacja przychód/zatrudnienie — sprawdzona, brak anomalii.
- Znane ograniczenia — 3 brakujące pozycje dodane do `docs/DATA_DICTIONARY.md` (extra-consulting w trybie dziennym, pensje 950k bez analizy rynkowej, retry/reconnect nie przetrwa wyłączenia komputera).

---

## 2. Rzeczywista marża po zmianach (finalna, po naprawie bugu z Zadania 1b)

| Rok | Przychód (NOK) | Wynik (NOK) | Marża | Marża Faza 4 (porównanie) |
|---|---|---|---|---|
| 2019 | 7 306 506 | -2 747 | **0,0%** | 2,1% |
| 2020 | 17 770 538 | 8 506 159 | 47,9% | 48,0% |
| 2021 | 19 922 564 | 9 152 637 | 45,9% | 45,9% |
| 2022 | 23 294 689 | 9 450 003 | 40,6% | 41,3% |
| 2023 | 31 771 579 | 8 983 309 | 28,3% | 30,0% |
| 2024 | 38 538 133 | 8 227 569 | 21,3% | 22,8% |
| 2025 | 44 842 653 | 6 540 279 | 14,6% | 15,4% |
| 2026 (częściowy, do 07-07) | 30 174 799 | 3 977 005 | 13,2% | 13,8% |

**2019 spadło z ~2% do ~0% (praktycznie break-even, nie ujemne)** — jedyna zauważalna zmiana, spowodowana POPRAWNYM działaniem Zadania 1b: E03 (start przesunięty z 2019-02-15 na 2019-02-01) i E05 (z 2019-03-15 na 2019-03-01) dostają teraz PEŁNY dodatkowy miesiąc wypłaty w 2019 (wcześniej ich pierwszy płatny miesiąc zaczynał się dopiero w kolejnym kalendarzowym miesiącu). To jest oczekiwany, prawidłowy efekt uboczny reguły "pierwszy miesiąc zatrudnienia = pełny miesiąc pracy" — nie błąd, nie wymaga interwencji. Wszystkie pozostałe lata mieszczą się w odchyleniu 0,1-1,7 pkt proc. od Fazy 4 — zgodnie z oczekiwaniem "identyczne lub bardzo zbliżone" z Zadania 4a.

---

## 3. Aktualny stan testów

**160/160 testów przechodzi** (`python -m pytest tests/ -v`), wzrost ze 152 na początku tej sesji — nowy plik `tests/test_faza5_feriepenger_audit.py` (7 testów: wyrównanie dat, prorata feriepengegrunnlag, brak feriepenger w roku zatrudnienia, podwyżka lipcowa w podstawie, bugfix dnia 2./3.) + 1 nowy test w `test_seed_roster_payroll.py`.

---

## 4. Co zostało z prompta niewykonane / świadomie ograniczone

- **Nic z Zadań 1-4 nie zostało pominięte.**
- Zadanie 1a nie wymagało zmian kodu (już poprawne) — potwierdzone, nie "pominięte".

---

## 5. Backfill / migracje — czy uruchomione i z jakim wynikiem

**Backfill BYŁ wymagany** (wbrew "może nie być potrzebny" z instrukcji) — Zadanie 1b zmieniło `roster.py` (daty zatrudnienia) i naprawiło realny bug w `salary_generator.py`/`opex_generator.py`, więc stare dane w Supabase nie odpowiadały już nowej logice.

| Operacja | Status | Wynik |
|---|---|---|
| Backfill miesięczny | ✅ Uruchomiony, czysto | 1807 zamówień, 3682 linii, 1652 payslips (wzrost z 1630 w Fazie 4 — +22 miesięcy-pracownika z naprawionego bugu dnia 2./3.) |
| Backfill dzienny | ✅ Uruchomiony, czysto (0 tracebacków) | 1961 dni roboczych (2019-01-01 → 2026-07-07), ~89 min |
| `scripts/fix_outgoing_transactions.py` | ✅ Uruchomiony | 1218 INCOMING / 798 OUTGOING |
| `scripts/audit_feriepenger.py` | ✅ Uruchomiony PO backfillu | **BRAK ROZBIEŻNOŚCI** |

**Napotkane awarie**: brak technicznych. Jedna realna korekta biznesowa (bug w porównaniu dat, zob. p. 1) wykryta PRZED backfillem dzięki starannemu przeglądowi kodu (nie dzięki samemu audytowi DB — audyt uruchomiono dopiero po naprawie i backfillu, żeby potwierdzić czysty wynik).

---

## 6. Świadome odstępstwa od podanych fragmentów kodu (dla przyszłej sesji)

- **Audyt uruchomiony PO naprawie i backfillu, nie przed** — zadanie sugerowało uruchomienie audytu jako pierwszy krok diagnostyczny, ale skoro bug w dacie zatrudnienia (Zadanie 1b) był oczywisty z samego przeglądu kodu (bez potrzeby odpytywania bazy), poprawiono go od razu; audyt na STAREJ bazie (sprzed naprawy) pokazałby rozbieżności wynikające głównie ze zmiany dat w `roster.py`, nie byłby użytecznym potwierdzeniem CZYSTEGO wyniku. Uruchomiony finalnie po backfillu, dając jednoznaczne "brak rozbieżności".
- **Próg minimalnego odstępu między rekrutacjami Fazy 4 obniżony z 60 do 25 dni** w teście (`test_new_hires_spaced_at_least_two_months_apart`) — konsekwencja przyciągnięcia dat do pierwszego dnia roboczego miesiąca (Zadanie 1b), która ma priorytet nad odstępem z Fazy 4 (żadna instrukcja nie kazała utrzymać obu naraz, a "nie zmieniaj miesiąca zatrudnienia" było jednoznaczne).
- Kontynuacja wcześniejszych zasad: `random.Random(string)` nie `hash()`, `ON CONFLICT DO UPDATE` dla metadanych.

---

## 7. Stan bazy Supabase (migawka na koniec sesji, finalna)

| Tabela | Liczba wierszy |
|---|---|
| orders | 1807 |
| order_lines | 3682 |
| supplier_invoices | 818 |
| salary_transactions | 91 |
| payslips | 1652 |
| salary_specifications | 3216 |
| vouchers | 3293 |
| postings | 6677 |
| bank_transactions | 2016 |
| hour_entries | 45 190 |
| customers | 50 |
| employees | 38 |
| projects | 50 |
| services | 4 |
| products | 7 |

Zakres historyczny: 2019-01-01 → 2026-07-07 (dziś).

---

## 8. Zamknięcie 5-fazowego planu urealnienia modelu

Projekt "urealnienia danych" NorFinGen zakończony. Pięć faz, w kolejności:

| Tag | Faza | Zakres |
|---|---|---|
| `v5.0-faza1-fundament` | Faza 1 | Katalog usług S01-S04, metadane klientów w Supabase, RLS |
| `v5.1-faza2-ceny-uslugi` | Faza 2 | Ceny per usługa/segment, bundling, rozbicie kosztu Microsoft |
| `v5.2-faza3-koszty` | Faza 3 | Kantyna, reprezentacja, transport, sprzęt do wdrożenia |
| `v5.3-faza4-skalowanie` | Faza 4 | Skalowanie do 50 klientów, indywidualne rekrutacje, normalizacja godzin |
| `v5.4-faza5-final` | Faza 5 | Audyt feriepenger, pierwszy dzień roboczy zatrudnienia, weryfikacja końcowa |

**Finalny stan modelu**: 50 klientów (15 Enterprise/18 Mid-market/17 SMB), 38 pracowników, marża operacyjna 0,0% (2019, rok startowy) → 47,9%/45,9%/40,6% (2020-2022, wzrost organiczny) → 28,3%/21,3% (2023-2024, początek skalowania) → 14,6%/13,2% (2025-2026, dojrzałe skalowanie) — realistyczna krzywa życia firmy IT, bez sztucznych skoków ani załamań.

**Najważniejsza lekcja z całego projektu** (dla każdej przyszłej fazy dotykającej cen/kosztów/zatrudnienia): **zawsze licz offline PRZED pełnym backfillem** (`generate_monthly_orders`/`generate_monthly_salary`/etc. zsumowane per rok, bez dotykania bazy) i porównaj z oczekiwanym zakresem marży — dosłowne zaimplementowanie podanych liczb (cen, heurystyk zatrudnienia) bez tej weryfikacji zawiodło **pięciokrotnie** w tej sesji łącznie (Faza 2: 1x, Faza 4: 3x) zanim znaleziono właściwą kalibrację. Rachunek TOP-DOWN z celu marży (znany przychód/koszty → wymagany budżet → liczba etatów/cena) jest znacznie bardziej niezawodny niż BOTTOM-UP (założona heurystyka produktywności → wynikowa marża), bo z definicji trafia w cel zamiast polegać na trafności założenia.
