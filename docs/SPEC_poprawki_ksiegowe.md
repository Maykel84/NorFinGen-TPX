# SPEC: Poprawki księgowe w generatorze NorFinGen

Wersja 1.0 · 2026-10-30 · autor: Michał Moleda
Źródło: test A/B agentów na eksporcie z 2026-10-30 (pliki `Postingi_GL.csv`, `Faktury_sprzedazy.csv`, `Faktury_zakupu.csv`, `PL_miesiecznie.csv`, `Payroll_*.csv`)

---

## 0. Instrukcje dla Claude Code (przeczytaj najpierw)

1. **Zanim cokolwiek zmienisz**, zrób inwentaryzację repozytorium: gdzie powstają dokumenty księgowe (voucher types: `INCOMING_INVOICE`, `SALARY`, `BANK`, `OPERATING_COST`, `MANUAL`), gdzie jest plan kont, gdzie eksport do CSV/API. Pokaż mi listę plików i funkcji. **Stop — czekaj na moje „ok”.**
2. Pracuj **fazami** (sekcja 3). Po każdej fazie: uruchom testy z `tests/gl_checks.sql`, pokaż wyniki, **stop — czekaj na „ok”**.
3. **Nie uruchamiaj** `git init/add/commit/push`. Na koniec każdej fazy zaproponuj komendy git (ja je wykonuję).
4. Nie zmieniaj logiki sprzedaży (kwot, klientów, dat faktur) ani payrollu brutto — zmieniamy **księgowanie**, nie biznes. Test regresji: suma przychodu bez MVA na snapshot 2026-10-30 = **211 624 547 NOK** (± 1 NOK).
5. Każda zmiana w planie kont musi być zgodna z **NS 4102**.
6. Jeśli coś w tej specyfikacji jest sprzeczne z kodem albo niejasne — zapytaj, nie zgaduj.

---

## 1. Stan obecny (zdiagnozowany)

| # | Problem | Dowód (snapshot 2026-10-30) |
|---|---|---|
| A | Księga się nie bilansuje | `SUM(amount)` = **−3 718 734,13 NOK**; cała różnica w `INCOMING_INVOICE`; równa sumie MVA z faktur zakupu. Linia VAT naliczonego istnieje tylko w kolumnie `vat_amount`, nie jako posting |
| B | Brak sprzedaży w GL | Brak kont 3xxx, brak Wn 1500, brak VAT należnego. Saldo 1500 = **−185 064 336** (same wpłaty) |
| C | Konta płacowe na kontach VAT | `SALARY`: netto → 2710, podatek → 2740, AGA → 2700. W NS 4102 to konta MVA |
| D | Wpłaty klientów | Tylko 1 315 z 1 885 faktur ma wpłatę (~70%), również faktury z 2019–2020 |
| E | Zobowiązania z COGS | `OPERATING_COST` księguje Ma 2400 = **88 478 143 NOK**, nigdy nie zapłacone |
| F | Bieżący miesiąc | Październik 2026: przychód częściowy, `cogs` = 0, `operating_cost` = 0, brak faktur zakupu po 2026-09-27; **brakuje faktur 13 klientów**, których stałe dni fakturowania już minęły |
| G | Typy / puste kolumny | `count` ma wartości ułamkowe (8 wierszy), `postal_code` w fakturach zakupu 100% pusta, `employee_id` w GL 100% pusta; brak numeru dokumentu w eksporcie GL |

### Świadome założenie — NIE ZMIENIAĆ
**Czerwiec / feriepenger:** w czerwcu nie wypłaca się zwykłego wynagrodzenia, tylko feriepenger naliczone w roku poprzednim (uproszczenie praktyki norweskiej: ferietrekk zastępuje pensję czerwcową). Koszt feriepenger jest naliczany co miesiąc rezerwą, więc niski koszt pracy w czerwcu w P&L jest poprawny. Udokumentuj to w README (faza 6) i dodaj test regresji (T9), żeby nikt tego nie „naprawił”.

---

## 2. Docelowy plan kont (NS 4102) — zakres zmian

| Konto | Nazwa (NO) | Użycie po zmianie |
|---|---|---|
| 1500 | Kundefordringer | Wn: faktura sprzedaży (brutto); Ma: wpłata klienta |
| 1910 / 1920 | Bank | bez zmian (zostaw konto, którego generator używa; zanotuj w README, że NS 4102 standardowo ma 1920) |
| 2400 | Leverandørgjeld | Ma: faktura zakupu i koszt COGS; Wn: płatność |
| 2600 | Forskuddstrekk | Ma: podatek pobrany od pensji; Wn: przelew do Skatteetaten |
| 2700 | Utgående merverdiavgift | Ma: VAT należny ze sprzedaży (25%) |
| 2710 | Inngående merverdiavgift | Wn: VAT naliczony z faktur zakupu |
| 2740 | Oppgjørskonto merverdiavgift | rozliczenie VAT per termin (faza 5, opcjonalnie) |
| 2770 | Skyldig arbeidsgiveravgift | Ma: AGA od wynagrodzeń; Wn: przelew |
| 2780 | Påløpt arbeidsgiveravgift på feriepenger | Ma: AGA od rezerwy feriepenger (jeśli generator nalicza AGA od rezerwy; jeśli nie — pomiń) |
| 2930 | Skyldig lønn | Ma: wynagrodzenie netto do wypłaty; Wn: wypłata |
| 2940 | Skyldige feriepenger | Ma: comiesięczna rezerwa; Wn: wypłata w czerwcu |
| 3000 | Salgsinntekt, avgiftspliktig | Ma: przychód netto |
| 5000 / 5099 / 5400 | koszty wynagrodzeń | bez zmian (opcjonalnie 5099 → 5180 „Feriepenger” — zapytaj mnie) |

---

## 3. Fazy pracy

### Faza 1 — Konta płacowe (C) — musi być PRZED fazą 2
- `SALARY`: netto Ma 2710 → **Ma 2930**; podatek Ma 2740 → **Ma 2600**; AGA Ma 2700 → **Ma 2770**; rezerwa feriepenger Ma 2930 → **Ma 2940**; wypłata feriepenger w czerwcu Wn 2930 → **Wn 2940**.
- `BANK`: płatności rozliczające te zobowiązania przenieś na te same nowe konta.
- **Akceptacja:** T1 (SALARY i BANK bilansują się do 0), T7 (żadnego postingu SALARY na 2700/2710/2740), T9 (wypłata feriepenger z 2940 w każdym czerwcu od 2020).
- Uwaga: pensja (5000) w czerwcu 2019–2023 u nowych pracowników bez pełnej rezerwy feriepenger jest **poprawna** — nie usuwaj jej.

### Faza 2 — VAT naliczony na fakturach zakupu (A)
- Każdy `INCOMING_INVOICE`: Wn koszt (netto) + **Wn 2710 (VAT)** / Ma 2400 (brutto).
- Faktury z zerowym VAT — bez linii 2710.
- **Akceptacja:** T1 (cała księga = 0,00), T2 (każdy dokument = 0,00), T6.

### Faza 3 — Faktury sprzedaży w GL (B) + wpłaty (D)
- Nowy voucher **`OUTGOING_INVOICE`** na datę `invoice_date`: Wn 1500 (brutto) / Ma 3000 (netto) / Ma 2700 (VAT 25%).
- Wpłaty klientów: każda faktura dostaje wpłatę w dacie `invoice_date + termin płatności + opóźnienie` (rozkład z seedem, np. 70% w terminie, 25% do 30 dni po terminie, 5% zaległe). Zaległe faktury oznacz flagą (`is_overdue` lub status w eksporcie), żeby były **celową pułapką testową**, a nie błędem.
- Nie zmieniaj kwot ani dat faktur.
- **Akceptacja:** T3, T4, T5, regresja 211 624 547.

### Faza 4 — Płatności COGS (E)
- `OPERATING_COST` z Ma 2400: generuj `BANK` Wn 2400 / Ma 1910 w terminie płatności (np. +30 dni), z tym samym rozkładem opóźnień co dostawcy.
- **Akceptacja:** T8.

### Faza 5 — Bieżący miesiąc (F) + rozliczenie VAT (opcjonalnie)
- Zbadaj, dlaczego w październiku 2026 brakuje faktur 13 klientów (stałe dni 3., 4., 10., 11., 17., 18., 24. już minęły). Pokaż przyczynę, zanim poprawisz.
- Koszty miesięczne (COGS, operating cost, faktury zakupu): wybierz razem ze mną jedną opcję:
  - **A (zalecana):** generuj koszty w ich realnych datach w trakcie miesiąca,
  - **B:** dodaj tabelę `period_status` (`open` / `closed`) i eksportuj ją, żeby raporty mogły odfiltrować otwarty miesiąc.
- **Opcjonalnie (zapytaj):** rozliczenie MVA per termin (6 terminów rocznie): przeniesienie sald 2700 i 2710 na 2740 i przelew do/z Skatteetaten.
- **Akceptacja:** T10.

### Faza 6 — Typy, eksport, dokumentacja (G)
- `count` → typ dziesiętny.
- `postal_code` w fakturach zakupu: uzupełnij z danych dostawcy albo usuń kolumnę z eksportu (zapytaj).
- `employee_id` w GL: wypełniaj dla postingów `SALARY` per pracownik albo usuń z eksportu (zapytaj).
- **Dodaj `voucher_number`** do eksportu GL (potrzebny do T2).
- README: plan kont, model feriepenger w czerwcu (świadome założenie), celowe pułapki testowe (zaległe faktury), sposób regeneracji historii.
- **Akceptacja:** T11 + wszystkie testy T1–T10 zielone na pełnej regeneracji 8 lat z tym samym seedem.

---

## 4. Migracja danych
- Poprawki dotyczą całej historii → **pełna regeneracja od 2019-01-01** z tym samym seedem.
- Przed regeneracją: eksport „przed” do `snapshots/before_<data>/`. Po: eksport „po” i raport różnic (przychód, payroll brutto, liczba faktur muszą być identyczne; zmieniają się tylko postingi GL).
- Supabase: migracja schematu (nowe kolumny, nowe konta) jako osobny plik migracji; pokaż mi SQL migracji przed uruchomieniem.

## 5. Definition of Done
- [ ] T1–T11 przechodzą na pełnej historii
- [ ] Regresja: przychód 211 624 547 NOK (snapshot 2026-10-30), payroll brutto bez zmian
- [ ] README zaktualizowane (plan kont, feriepenger, pułapki testowe)
- [ ] Raport różnic before/after
- [ ] Zaproponowane komendy git per faza (wykonuję sam)

## 6. Stan wyjściowy testów (snapshot 2026-10-30, przed zmianami)

| Test | Wynik | Uwagi |
|---|---|---|
| T1 bilans księgi | FAIL | −3 718 734,13 |
| T2 bilans dokumentów | brak kolumny | wymaga `voucher_number` (faza 6) |
| T3 należności 1500 | FAIL | −185 064 335,56 |
| T4 przychód GL = faktury | FAIL | brak kont 3xxx |
| T5 VAT należny | FAIL | brak przychodu w GL |
| T6 VAT naliczony | FAIL | 2710 zajęte przez płace |
| T7 płace na kontach VAT | FAIL | 2700/2710/2740 |
| T8 saldo dostawców | FAIL | −88 540 822 vs −62 680 |
| T9 feriepenger z 2940 | FAIL | dziś księgowane na 2930 |
| T10 koszty w bieżącym miesiącu | FAIL | ostatni koszt 2026-09-20 |
| T11 puste kolumny | FAIL | postal_code, employee_id |
| REG przychód | PASS | 211 624 547 |
