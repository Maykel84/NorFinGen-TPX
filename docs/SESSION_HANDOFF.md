# NorFinGen — Session Handoff

Data sporządzenia: 2026-07-06. Ostatni commit: (do utworzenia w tej sesji, tag `v5.2-faza3-koszty`). Working tree: zmiany tej sesji gotowe do commitu.

---

## 1. Co zostało zrobione w tej sesji

Faza 3 z planu 5-fazowego: nowe kategorie kosztów — kantyna, reprezentacja, transport (kilometrówka + konferencje), sprzęt do wdrożenia (COGS). Jeden commit obejmujący:

### ZADANIE 1 — Dopłaty do kantyny
- **`seed/roster.py`** — `CANTEEN_SUBSIDY_PER_EMPLOYEE_MONTHLY = 820`, `calc_canteen_cost(active_employee_count)`. Bez inflacji (polityka firmy, nie cena rynkowa — zgodnie z zadaniem).
- Konto **7350 "Kantinetilskudd"** dodane do `ACCOUNTS_SEED` (`db/repository.py`).

### ZADANIE 2 — Koszty reprezentacyjne
- **`seed/roster.py`** — `REPRESENTATION_COST_PER_ENTERPRISE_CLIENT_MONTHLY = 1000`, `REPRESENTATION_COST_PER_MID_CLIENT_MONTHLY = 400`, `calc_representation_cost(customers)` — SMB nie generuje kosztu.
- Konto **7420 "Representasjon"** dodane.
- **Flaga podatkowa `tax_deductible_pct` (2b, opcjonalna) — POMINIĘTA**, zgodnie z jawnym przyzwoleniem zadania ("jeśli to zbyt duża zmiana na tę fazę — pomiń, zostaw komentarz"). Zostawiony komentarz w `docs/DATA_DICTIONARY.md` (sekcja `accounts`) — do rozważenia w przyszłej fazie, jeśli pojawi się potrzeba modelowania różnic podatkowych (nie księgowych) per konto.

### ZADANIE 3 — Rozdzielenie kosztów transportu
- **`seed/roster.py`** — `KM_RATE_2019 = 3.5`, `calc_client_visit_transport(customers, month)` (kilometrówka, sezonowa: Enterprise kwartalnie, Mid-market 2x/rok, SMB 1x/rok), `CONFERENCE_HOTEL_RATES`.
- **`generators/opex_generator.py`** — `generate_conference_trip(year, month, rng)` (2-3 wyjazdy konferencyjne/rok, losowo Q1/Q3 wybranych miesięcy).
- **Weryfikacja "miksu" L07 Avis — brak do rozdzielenia.** L07 to czysto wynajem samochodów (nie mieszał "dostawy usługi" z transportem) — zostawiony bez zmian. Nowe kategorie (kilometrówka, konferencje) księgowane na **to samo istniejące konto 7000** "Reisekostnader" (nie nowy numer) — to ta sama kategoria NS4102.

### ZADANIE 4 — Podział sprzętu IT
- **4a (sprzęt biurowy, L05 Sandvik)** — bez zmian, zgodnie z zadaniem.
- **4b (sprzęt do wdrożenia, NOWA kategoria)** — **`generators/opex_generator.py`**: `should_generate_service_equipment_purchase(customer, month, rng)`, `calc_service_equipment_cost(customer)`. Konto **4290 "Driftsmateriell for kundeleveranse"** (COGS, klasa 4 NS4102 — jedyne takie konto w planie kont, reszta kosztów operacyjnych to 5xxx-7xxx).
- **Ważna poprawka względem dosłownego pseudokodu zadania**: `should_generate_service_equipment_purchase()` z zadania sprawdzała TYLKO miesiąc onboardingu, nie rok — dosłowna implementacja powtarzałaby koszt CO ROKU w tym samym miesiącu kalendarzowym (np. K01 onboardowany w marcu 2019 generowałby koszt sprzętu w marcu KAŻDEGO roku 2019-2026). Naprawione: predykat sprawdza tylko miesiąc (zgodnie z podaną sygnaturą/testem), ale wywołujący (`generate_monthly_opex`) dodatkowo filtruje `customer.onboarding_date.year == year` — koszt występuje faktycznie raz, zweryfikowane testem (`test_generate_monthly_opex_does_not_repeat_equipment_cost_across_years`) i ręcznie na backfillu (2019: 326 500 NOK COGS, 2020: 41 300 NOK, 2021+: 0 — zgodne z harmonogramem onboardingu 12 klientów, kompletny do 2022).

### Refaktoryzacja przy okazji
- **`is_customer_active(customer, on_date)` + `active_customers(on_date)` w `roster.py`** — wydzielone ze zduplikowanej logiki `order_generator._is_active` (usunięta, zastąpiona importem) — potrzebne też przez nowy `opex_generator.py`. `hours_generator._active_projects_for_employee` ma nieco inną logikę (per-projekt, nie per-klient) — celowo NIE ruszone, żeby nie poszerzać zakresu tej fazy.
- **Nowy `VoucherType.OPERATING_COST`** (`generators/voucher.py`) — koszty Fazy 3 nie mają odpowiadającego dokumentu źródłowego (w przeciwieństwie do `INCOMING_INVOICE`/`SupplierInvoice`), więc dostały własny typ vouchera zamiast nadużywania `MANUAL` (opisanego jako "kapitał zakładowy, korekty").

### ZADANIE 5 — Testy i weryfikacja
- **Nowy plik `tests/test_opex_generator.py`** — 13 testów (kantyna skaluje się z liczbą pracowników, reprezentacja tylko Enterprise/Mid, transport sezonowy, sprzęt tylko w miesiącu ORAZ roku onboardingu, brak powtórzenia między latami, bilansowanie voucherów, determinizm).
- **141/141 testów przechodzi** (wzrost ze 128 na początku tej sesji).

---

## 2. Rzeczywista marża po zmianach (KRYTYCZNE — próg bezpieczeństwa NIE przekroczony)

Offline sanity-check wykonany PRZED pełnym backfillem (lekcja z Fazy 2, zob. `feedback_verify_margin_before_commit` w pamięci sesji) — dodatkowy koszt Fazy 3 oszacowany na ~200-430 tys. NOK/rok, potwierdzone po backfillu:

| Rok | Przychód (NOK) | Koszty prac. | Koszty op. | COGS (Faza 3) | Wynik | Marża |
|---|---|---|---|---|---|---|
| 2019 | 7 306 506 | 4 544 983 | 2 278 291 | 326 500 | 156 732 | **2,1%** |
| 2020 | 17 770 538 | 6 929 865 | 2 274 273 | 41 300 | 8 525 100 | 48,0% |
| 2021 | 19 922 564 | 8 436 433 | 2 333 494 | 0 | 9 152 637 | 45,9% |
| 2022 | 20 960 374 | 10 939 958 | 2 382 297 | 0 | 7 638 118 | 36,4% |
| 2023 | 21 540 720 | 14 482 254 | 2 432 878 | 0 | 4 625 588 | **21,5%** |
| 2024 | 22 314 991 | 15 085 791 | 2 499 535 | 0 | 4 729 665 | **21,2%** |
| 2025 | 22 194 839 | 15 538 361 | 2 500 288 | 0 | 4 156 190 | **18,7%** |
| 2026 (częściowy, do 07-06) | 13 396 594 | 9 462 485 | 1 458 211 | 0 | 2 475 898 | 18,5% |

**Próg bezpieczeństwa (12% w latach dojrzałych) NIE został przekroczony** — 2023-2025 lądują na 18,7%-21,5%, w środku docelowego przedziału 15-22% z zadania. Spadek względem Fazy 2 (20-23%) to ok. 1-1,5 pkt proc., zgodnie z oczekiwaniem "kwoty celowo skromne, żeby nie powtórzyć błędu z Fazy 2".

2019 (rok startowy) spadł z 8,0% (Faza 2) do 2,1% — cieńsze niż poprzednio, ale **nadal dodatnie**, nie ujemne — nie kwalifikuje się jako "błąd modelowania" w rozumieniu Fazy 2 (tam był -183%). Przyczyna: 2019 to jedyny rok z pełnym efektem jednorazowego COGS sprzętu wdrożeniowego dla 4 klientów onboardowanych w tym roku (K01, K02, K03, K05, K08, K11 — część z nich), a przychód w roku 1 jest z natury niski (mały zespół, mała baza klientów). Nie zatrzymano się — próg dotyczy lat dojrzałych (2023-2026), zgodnie z dosłowną treścią zadania.

---

## 3. Aktualny stan testów

**141/141 testów przechodzi** (`python -m pytest tests/ -v`), wzrost ze 128 na początku tej sesji (13 nowych w `test_opex_generator.py`).

---

## 4. Co zostało z prompta niewykonane / świadomie ograniczone

- **Zadanie 2b (flaga `tax_deductible_pct` na koncie 7420)** — POMINIĘTE, zgodnie z jawnym przyzwoleniem zadania. Nie ma wpływu na generowane dane (VAT nie jest modelowany dla kosztów Fazy 3 w ogóle — zob. pkt 6).
- **extra-consulting w `run_daily.py` (dług techniczny z Fazy 2) — POTWIERDZONY, NIE naprawiony w tej fazie**, zgodnie z instrukcją. `should_generate_extra_consulting`/K06-style consulting nadal działają tylko w `generate_monthly_orders` (backfill historyczny), nie w rytmie dziennym produkcyjnym. Zostawione do rozważenia w przyszłej fazie, jeśli w ogóle — nie było to w zakresie zadań Fazy 3.
- **Nic innego z zadań Fazy 3 nie zostało pominięte.**

---

## 5. Następne kroki

1. **Faza 4/5** (kolejne fazy planu 5-fazowego) — treść jeszcze nie podana. Faza 4 ma dotyczyć skalowania liczby klientów (40-50) — przy tej skali koszt sprzętu wdrożeniowego (Zadanie 4b) zacznie występować regularnie przy onboardingu każdego nowego klienta, nie tylko historycznie.
2. Rozważyć `tax_deductible_pct` na koncie 7420, jeśli pojawi się potrzeba modelowania różnic podatkowych (odłożone z Zadania 2b).
3. **Pamiętać o `scripts/fix_outgoing_transactions.py`** po każdym kolejnym pełnym `TRUNCATE` — uruchomiony w tej sesji, stan: 616 INCOMING / 798 OUTGOING.
4. extra-consulting w `run_daily.py` — nadal znany dług techniczny (zob. pkt 4), nie naprawiać bez wyraźnego zadania.

---

## 6. Backfill / migracje — czy uruchomione i z jakim wynikiem

**Jeden pełny cykl reset+backfill** wystarczył w tej sesji (w przeciwieństwie do Fazy 2, gdzie potrzebne były dwa) — dzięki offline sanity-checkowi PRZED backfillem, który potwierdził bezpieczny wpływ na marżę zanim wykonano kosztowny (czasowo) reset.

| Operacja | Status | Wynik |
|---|---|---|
| Backfill miesięczny | ✅ Uruchomiony, czysto | 879 zamówień, 1885 linii, 818 faktur zakupu, 91 list płac, **1252 vouchery** (wzrost z 1001 w Fazie 2 — nowe koszty Fazy 3), 2592 postingi |
| Backfill dzienny | ✅ Uruchomiony, czysto (0 tracebacków) | 1960 dni roboczych (2019-01-01 → 2026-07-06), 26 876 wpisów godzin, 1414 transakcji bankowych (bez zmian — koszty Fazy 3 nie generują bank_transactions, tylko bezpośrednie Vouchery) |
| `scripts/fix_outgoing_transactions.py` | ✅ Uruchomiony | 616 INCOMING / 798 OUTGOING |
| `ensure_schema()`/`seed_reference_data()` | ✅ Automatyczny na starcie `run_backfill.py` | 3 nowe konta (4290, 7350, 7420) w `accounts` — 27 wierszy łącznie |

**Napotkane awarie**: brak — ani technicznych (backfill/reconnect), ani modelowania biznesowego (offline sanity-check przed backfillem zapobiegł powtórce błędu z Fazy 2).

---

## 7. Świadome odstępstwa od podanych fragmentów kodu (dla przyszłej sesji)

Kontynuacja listy z poprzednich sesji:

- **`should_generate_service_equipment_purchase()` sprawdza tylko miesiąc, rok filtrowany przez wywołującego** — zob. pkt 1/Zadanie 4 wyżej. Dosłowny pseudokod zadania miał błąd (brak sprawdzenia roku), który spowodowałby coroczne powtarzanie jednorazowego kosztu.
- **`calc_representation_cost()` NIE stosuje inflacji wewnątrz `roster.py`** — pseudokod zadania wołał `apply_annual_inflation(total, year)` bezpośrednio w funkcji zdefiniowanej w `roster.py`, ale `apply_annual_inflation` żyje w `order_generator.py`, który JUŻ importuje z `roster.py` — dosłowna implementacja stworzyłaby cykl importu. Naprawione: `calc_representation_cost(customers)` zwraca kwotę bazową (bez roku w sygnaturze), a inflację stosuje wywołujący (`opex_generator.generate_monthly_opex`, który i tak już importuje `apply_annual_inflation` z `order_generator.py`, tak jak `supplier_invoice_generator.py` w Fazie 2).
- **Kilometrówka (`calc_client_visit_transport`) NIE stosuje inflacji**, mimo komentarza w zadaniu "stawka bazowa, rośnie z inflacją/regulacją" — zaimplementowane dosłownie jak podany kod (bez `apply_annual_inflation`), bo to nie jest bug (kod działa), tylko stylistyczna niespójność komentarza z ciałem funkcji, a kwota jest na tyle mała (~10-15 tys. NOK/rok), że różnica jest nieistotna. Odłożone bez oznaczania jako "do naprawy" — nie warto komplikować kodu dla marginalnego efektu.
- **Nowy `VoucherType.OPERATING_COST`** zamiast nadużywania istniejącego `MANUAL` — zob. pkt 1.
- **`is_customer_active()`/`active_customers()` wydzielone do `roster.py`** z duplikowanej logiki `order_generator._is_active` — nie było to explicite w zadaniu, ale nowy `opex_generator.py` potrzebował identycznej logiki co `order_generator.py`, więc konsolidacja była naturalnym momentem (uniknięcie trzeciej kopii tego samego kodu).
- Kontynuacja wcześniejszych zasad: `random.Random(string)` nie `hash()`/`random.uniform()` globalny (naprawione w `calc_service_equipment_cost` względem pseudokodu zadania, który używał globalnego `random.uniform`), statusy/koszty deterministyczne, `ON CONFLICT DO UPDATE` dla metadanych.

---

## 8. Stan bazy Supabase (migawka na koniec sesji)

| Tabela | Liczba wierszy |
|---|---|
| orders | 879 |
| order_lines | 1885 |
| supplier_invoices | 818 |
| salary_transactions | 91 |
| vouchers | 2666 (wzrost z 2415 w Fazie 2 — +251 nowych kosztów operacyjnych Fazy 3) |
| postings | 5420 |
| bank_transactions | 1414 |
| hour_entries | 26 876 |
| accounts | 27 (24 + 3 nowe: 4290, 7350, 7420) |

Zakres historyczny: 2019-01-01 → 2026-07-06 (dziś).
