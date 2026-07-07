# NorFinGen — Session Handoff

Data sporządzenia: 2026-07-07. Ostatni commit: (do utworzenia w tej sesji, tag `v5.4a-future-date-fix`). Working tree: zmiany tej sesji gotowe do commitu.

**To jest hotfix PO zamknięciu 5-fazowego planu (`v5.4-faza5-final`)** — naprawa krytycznego błędu wykrytego w świeżym eksporcie danych, nie kolejna faza zmian architektonicznych.

---

## 1. Opis błędu i źródło

**Znaleziony błąd (2026-07-07, analiza eksportu `norfingen_export.xlsx`)**: baza zawierała transakcje z datami do 20 dni w przyszłość względem rzeczywistej daty systemowej (2026-07-07):
- 33 zamówienia sprzedaży z `order_date`/`invoice_date` do 2026-07-27
- 2 faktury zakupu z datami do 2026-07-20
- 1 lista płac za lipiec 2026 (`Lønnskjøring juli 2026`, `Arbeidsgiveravgift juli 2026`) zaksięgowana z datą 2026-07-31 — wypłacona z góry, 24 dni przed końcem miesiąca
- 4 vouchery z datą w przyszłości (odpowiadające powyższym)
- `bank_transactions` i `hour_entries`: **0 rekordów w przyszłości** (te generatory już były bezpieczne, zob. niżej)

**Źródło (potwierdzone przeglądem kodu)**: `generators/backfill.py::generate_and_persist_month(year, month, ...)` — wywoływana raz per `(rok, miesiąc)` z `months_range()`, generowała **CAŁY** miesiąc kalendarzowy (wszystkie zamówienia wg `invoice_day` klienta, wszystkie faktury dostawców wg ich rytmu, cała lista płac na `last_working_day(year, month)`) **bez sprawdzenia, czy poszczególne dni tego miesiąca faktycznie już minęły** względem `date.today()`. Gdy `run_backfill.py --start 2019-01-01` (bez `--end`) dotarł do bieżącego miesiąca (lipiec 2026), `months_range()` włączył `(2026, 7)` jako ostatni miesiąc do przetworzenia — i cały ten miesiąc został wygenerowany na raz, tak jakby już się zakończył.

**Dlaczego `bank_transactions`/`hour_entries` NIE ucierpiały**: te dwa generatory są wywoływane wyłącznie przez `run_daily.py` (dzień-po-dniu, w pętli `run_backfill_daily()` ograniczonej do `[start_date, end_date]` przekazanego jawnie), nie przez `generate_and_persist_month()` — więc nigdy nie miały tego samego błędu strukturalnego. Błąd był **wyizolowany do trybu miesięcznego backfillu** (`run_backfill.py` bez `--mode daily`).

---

## 2. Naprawa źródłowa

- **`seed/payroll.py`** — nowe funkcje: `get_generation_cutoff_date()` (= `date.today()`), `is_date_generatable(target_date, cutoff=None)`, `should_generate_monthly_salary(year, month, cutoff=None)` (payroll tylko gdy `last_working_day(year, month) <= cutoff`).
- **`generators/backfill.py`**:
  - `run_backfill()` — `end_date` (jawny lub domyślny) jest zawsze dodatkowo przycięty do `get_generation_cutoff_date()`, niezależnie od tego, co poda wywołujący.
  - `generate_and_persist_month(year, month, persist_fn, cutoff=None)` — każdy wygenerowany `Order`/`SupplierInvoice`/opex `Voucher` jest filtrowany po dacie względem `cutoff` PRZED zapisem i PRZED policzeniem do stats; lista płac generuje się tylko jeśli `should_generate_monthly_salary()` zwróci `True`.
- **`run_daily.py`** — dodany twardy bezpiecznik: `run_daily(target_date=<data w przyszłości>)` zwraca `{"skipped": True, ...}` bez dotykania bazy (wcześniej to wywołanie było teoretycznie bezpieczne tylko dzięki temu, że nic go nigdy nie wołało z przyszłą datą — teraz jest to zagwarantowane jawnie). Payroll w `run_daily.py` dodatkowo strzeżony przez `should_generate_monthly_salary()`.

---

## 3. Czyszczenie danych i weryfikacja

**Migracja ukierunkowana (NIE pełny TRUNCATE)** — `scripts/fix_future_dated_records.py`:

| Tabela | Usunięto rekordów |
|---|---|
| orders | 33 |
| supplier_invoices | 2 |
| salary_transactions | 1 |
| vouchers | 4 |
| bank_transactions | 0 (nic nie odwoływało się do przyszłych dat) |
| hour_entries | 0 |

Po migracji: `python run_daily.py` uruchomiony ręcznie dla 2026-07-07 — wygenerował **tylko dzisiejsze dane** (2 zamówienia, 56 wpisów godzin, 0 listy płac — miesiąc się nie zakończył, 0 transakcji bankowych), zero rekordów w przyszłości. `scripts/fix_outgoing_transactions.py` uruchomiony ponownie (0 nowych — nic nie wymagało naprawy, bo błąd nie dotyczył `bank_transactions`).

**Zapytanie weryfikacyjne (Zadanie 5) — wszystkie wartości = 0**, potwierdzone na żywej bazie po naprawie.

---

## 4. Testy

**167/167 testów przechodzi** (wzrost ze 160 przed tą naprawą) — nowy plik `tests/test_future_date_regression.py` (7 testów): `is_date_generatable`/`get_generation_cutoff_date`/`should_generate_monthly_salary` jako jednostki, `generate_and_persist_month()` dla bieżącego miesiąca nigdy nie przekracza cutoff, lista płac pomija niezakończony miesiąc, `run_backfill()` przycina `end_date` nawet gdy podano datę w przyszłości, `run_daily()` odrzuca przyszłą `target_date`.

---

## 5. Stan bazy Supabase (po naprawie)

| Tabela | Liczba wierszy (przed naprawą → po) |
|---|---|
| orders | 1807 → 1774 |
| order_lines | 3682 → 3627 |
| supplier_invoices | 818 → 816 |
| salary_transactions | 91 → 90 |
| payslips | 1652 → 1614 |
| salary_specifications | 3216 → 3140 |
| vouchers | 3293 → 3289 |
| postings | 6677 → 6668 |
| bank_transactions | 2016 → 2016 (bez zmian) |
| hour_entries | 45 190 → 45 268 (+78 z dzisiejszego `run_daily.py`) |

---

## 6. Ustalona kolejność dalszych faz

Decyzja z rozmowy z użytkownikiem, do zachowania w dokumentacji projektu:

```
Ustalona kolejność po naprawie błędu dat:
1. Ta naprawa (v5.4a-future-date-fix)
2. Kalibracja Fazy 6 względem realnych danych branżowych
   (Brønnøysundregistrene, NACE 62.020) zamiast wyłącznie szacunków
3. Faza 6 — redukcja zespołu do realnego wolumenu pracy
4. Dodatek NACE (kody branżowe firmy i klientów)
5. Domknięcie API (Supabase REST już działa, RLS z Fazy 1) —
   rate limiting, nadanie roli analyst realnemu loginowi, dokumentacja

Ważne zastrzeżenie: Tripletex API NIE udostępnia żadnych publicznych
danych innych firm (system autoryzowany, dostęp tylko do własnego
konta/klientów księgowych). Realnym źródłem publicznych danych
finansowych norweskich firm do kalibracji modelu jest
Brønnøysundregistrene (Regnskapsregisteret), nie Tripletex.
```

---

## 7. Co zostało z prompta niewykonane / świadomie ograniczone

- **Zadanie 2d** (`order_generator.py`/`bank_transaction_generator.py` — dodanie `is_date_generatable()` bezpośrednio w tych modułach) — **nie było potrzebne**: te generatory są wywoływane wyłącznie przez `run_daily.py` z konkretnym, już-bezpiecznym `target_date` (nigdy przez `generate_and_persist_month()`), więc dodawanie tam kontroli cutoff byłoby podwójnym zabezpieczeniem bez realnej luki do załatania. Naprawiono w jedynym rzeczywistym źródle błędu (`generate_and_persist_month`/`run_backfill`) + dodano niezależny bezpiecznik w `run_daily()` dla obrony w głąb.
- Nic innego nie zostało pominięte.

---

## 8. Świadome odstępstwa od podanych fragmentów kodu

- **`is_date_generatable`/`get_generation_cutoff_date`/`should_generate_monthly_salary` umieszczone w `seed/payroll.py`**, nie w nowym osobnym module — `seed/payroll.py` już zawiera `last_working_day()` (blisko powiązane), a `generators/backfill.py` już zależy od `seed/payroll.py` pośrednio (przez `salary_generator.py`) — dodanie bezpośredniej zależności nie tworzy cyklu. Uniknięto tworzenia nowego modułu dla 3 małych funkcji.
- **Filtrowanie zamiast wczesnego `return`/asercji w generatorach** — `generate_and_persist_month()` generuje CAŁY miesiąc (jak wcześniej), ale filtruje wynik po dacie przed zapisem/zliczeniem, zamiast przerywać generowanie w połowie miesiąca — prostsze, mniej inwazyjne zmiany w `order_generator.py`/`supplier_invoice_generator.py`, które nie musiały w ogóle być dotykane.

---

## 9. Kontekst poprzednich faz (dla ciągłości)

Ta naprawa następuje bezpośrednio po zamknięciu 5-fazowego planu urealnienia modelu (`v5.0-faza1-fundament` → `v5.4-faza5-final`, zob. commit `069ca6b` i wcześniejsza wersja tego dokumentu w historii git dla pełnych szczegółów każdej fazy). Kluczowa lekcja z tamtego planu (offline sanity-check marży przed backfillem, top-down kalibracja zatrudnienia) pozostaje aktualna dla Fazy 6.
