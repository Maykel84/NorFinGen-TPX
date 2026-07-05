# NorFinGen — Session Handoff

Data sporządzenia: 2026-07-05. Ostatni commit: (do utworzenia w tej sesji, tag `v5.1-faza2-ceny-uslugi`). Working tree: zmiany tej sesji gotowe do commitu.

---

## 1. Co zostało zrobione w tej sesji

Faza 2 z planu 5-fazowego: ceny per usługa/segment, bundling usług per klient, rozbicie kosztu Microsoft na 4 pozycje. Jeden commit obejmujący:

### ZADANIE 1 — Ceny bazowe, bundling, wielolinijkowe faktury
- **`models/service.py`, `seed/roster.py`** — `SERVICES` (Faza 1) z base_price_* per segment. **Ceny bazowe skorygowane DWUKROTNIE w tej sesji** — zob. p. 6 (odstępstwo) i p. 8 (rzeczywiste liczby marży) niżej, to najważniejsza rzecz do zapamiętania z tej sesji.
- **`seed/roster.py`** — `SEGMENT_SERVICE_BUNDLES` + `get_customer_services(customer)`: Enterprise S01+S02+S03, Mid-market S01+S02, SMB S01. `service_base_price(service, segment)`, `product_for_service(service_code)` (jeden kanoniczny produkt per usługa, niezależny od segmentu — cena liczy się z `Service.base_price_*`, nie z `Product.default_price`).
- **`seed/roster.py`** — nowy `ProductSeed("P07", "Cyberbezpieczeństwo", ..., "S03", None)` — S03 miał 0 produktów w Fazie 1 (znane ograniczenie), teraz ma P07. `PRODUCTS` 6→7. Przemianowane P01 ("Managed IT Support"), P04 ("Zarządzanie infrastrukturą Microsoft"), P06 ("Konsulting i digitalizacja") na nazwy zgodne z usługą (były segmentowo-specyficzne, teraz jeden produkt obsługuje wszystkie segmenty). P02/P03/P05 zostają w katalogu (zgodność testów/FK), ale nieużywane do generowania linii.
- **`generators/order_generator.py`** — `build_order_lines(customer, order_date)` zastępuje dawne `_order_lines_for_pattern` (liczba/dobór linii A=1/B=2/C=1 wg litery wzorca) — teraz jedna linia per usługa z bundlingu segmentowego, cena = `service_base_price` × inflacja × `CUSTOMER_PRICE_MULTIPLIER`. `support_product`/`license_product` na `CustomerSeed` zostają jako pola historyczne, nie sterują już liczbą linii.
- **`generators/order_generator.py`** — `should_generate_extra_consulting(customer, month, year)` — klienci Enterprise (~15%/mies.) i Mid-market (~8%/mies.) w Q2/Q4 mogą dostać DODATKOWY Order S04 (projekt poza subskrypcją), niezależnie od stałej faktury miesięcznej. Osobny `order_date` (dzień 25, żaden klient nie ma `invoice_day=25` — brak konfliktu z `UNIQUE(customer_id, order_date)`). **Działa tylko w `generate_monthly_orders` (backfill historyczny)** — `generate_daily_orders` tego nie odtwarza, identyczne ograniczenie jak już istniejące dla K06/wzorca D (świadomie niedomknięte, zob. p. 3).
- **`db/repository.py`** — `seed_reference_data()`: UPSERT `products` rozszerzony o `name`/`number`/`sales_price` (wcześniej tylko `service_code`) — inaczej przemianowane P01/P04/P06 nigdy nie zaktualizowałyby się w Supabase po już wykonanym seedzie z Fazy 1.

### ZADANIE 2 — Rozbicie kosztu Microsoft
- **`generators/supplier_invoice_generator.py`** — `MICROSOFT_COST_LINES` (4 pozycje: M365 E3 licencje 6100, Azure hosting 35000, Visual Studio 4000, Wsparcie CSP/Premier 8000 NOK/mies., baza 2019 = 53 100 NOK, niżej niż poprzednie płaskie 85 000 — zamierzone). L01 generuje **4 osobne `SupplierInvoice`/miesiąc** (nie jedną pozycję) — model `SupplierInvoice` nie ma multi-line (`SupplierInvoiceLine` nie istnieje), więc wybrano wariant "4 osobne faktury" z zadania zamiast dodawać nowy model. `invoice_number` format `L01-{rok}-{miesiąc:02d}-{1..4}`. Inflacja +3%/rok (`apply_annual_inflation`, import z `order_generator.py`) zastosowana TYLKO do L01 — pozostali dostawcy (L02-L08) pozostają płascy/z szumem, poza zakresem tej fazy.
- Azure hosting **NIE** powiązany dynamicznie z liczbą klientów S02 — uproszczenie świadome (zadanie explicite pozwalało odłożyć), prosta inflacja wystarczyła na tę fazę. Do zrobienia w Fazie 4, gdy portfel faktycznie rośnie.

### ZADANIE 3 — Testy i weryfikacja
- 15 nowych/zaktualizowanych testów w `test_order_generator.py`, `test_supplier_invoice_generator.py`, `test_repository.py`, `test_seed_roster_payroll.py` — bundling per segment (3/2/1 linii), S03 generuje przychód > 0, rozbicie Microsoft na 4 faktury, ceny per segment (nie per produkt).
- Stare testy oparte o literę wzorca (`test_pattern_b_has_two_lines`, `test_pattern_c_license_only`) **zastąpione** nowymi (segment-based) — zamierzona zmiana semantyki, nie regresja.

---

## 2. Aktualny stan testów

**128/128 testów przechodzi** (`python -m pytest tests/ -v`), wzrost ze 121 na początku tej sesji. Bez `xfail`/`skip`.

---

## 3. Co zostało z prompta niewykonane / świadomie ograniczone

- **ZADANIE 1d (extra consulting S04 dla Enterprise/Mid) zaimplementowane, ale tylko w `generate_monthly_orders`** — `generate_daily_orders` go nie odtwarza (ten sam ograniczony zakres, który już istniał dla K06/wzorca D przed tą sesją — K06 też nigdy nie pojawia się w generacji dziennej, zob. `test_generate_daily_orders_skips_consulting_customer`). Skutek: dla danych **od dzisiaj wzwyż** (produkcyjny rytm dzienny `run_daily.py`/cron), nowe zamówienia consultingowe (K06 i extra S04) nie będą już powstawać — tylko historyczny backfill miesięczny je generuje. Nie jest to regresja tej sesji, to już istniejące zachowanie rozszerzone symetrycznie na nowy przypadek.
- **ZADANIE 2a (Azure hosting powiązany z liczbą klientów S02) NIE zrobione w pełnej wersji** — zaimplementowana prosta inflacja +3%/rok, zgodnie z jawnym przyzwoleniem zadania ("jeśli czas pozwoli... jeśli nie, prosta inflacja wystarczy, dokładniejsze powiązanie odłóż do Fazy 4").
- **Nic innego z zadań Fazy 2 nie zostało pominięte.**

---

## 4. Następne kroki

1. **Faza 3/4/5** (kolejne fazy planu 5-fazowego) — treść jeszcze nie podana w tej sesji. Faza 4 ma dotyczyć skalowania liczby klientów (40-50) — wtedy warto zrewidować cenę SMB (zob. p. 8, świadomy kompromis do skorygowania).
2. **Rozważyć pełne powiązanie Azure hosting z liczbą klientów S02** (odłożone z Zadania 2a tej sesji) — najbardziej naturalny moment to Faza 4, gdy portfel faktycznie rośnie i koszt Azure przestaje być płaską linią.
3. **Pamiętać o `scripts/fix_outgoing_transactions.py`** po każdym kolejnym pełnym `TRUNCATE` — uruchomiony 2x w tej sesji (raz po każdym backfillu, bo ceny zostały skorygowane w trakcie sesji i wymagały drugiego pełnego resetu, zob. p. 8).
4. Rola `analyst` nadal `NOLOGIN` — bez zmian względem Fazy 1.

---

## 5. Backfill / migracje — czy uruchomione i z jakim wynikiem

**Ta sesja wymagała DWÓCH pełnych cykli reset+backfill** — pierwszy z pierwotnymi cenami z zadania (`S01` Enterprise/Mid/SMB 45000/18000/4500, `S02` 20000/8000, `S03` 15000) zawalił marżę operacyjną do -70%..-183%/rok (payroll 16-osobowego zespołu, skalibrowany w poprzednich sesjach względem starych cen `Product`, przewyższał cały przychód nawet 2,4×). Zatrzymano się, zgłoszono użytkownikowi, otrzymano skorygowane ceny (zob. p. 8), wykonano DRUGI pełny reset+backfill z poprawionymi cenami — wynik zweryfikowany jako zdrowy.

| Operacja | Status | Wynik |
|---|---|---|
| Backfill miesięczny (×2, pierwotne i skorygowane ceny) | ✅ Uruchomiony, ostatni czysto | 879 zamówień, 1885 linii, 818 faktur zakupu, 91 list płac |
| Backfill dzienny (×2, po każdym backfillu miesięcznym) | ✅ Uruchomiony, ostatni czysto (0 tracebacków) | 1959 dni roboczych przetworzonych (2019-01-01 → 2026-07-05), 26 859 wpisów godzin (bez zmian — Faza 2 nie dotyka godzin), 1414 transakcji bankowych |
| `scripts/fix_outgoing_transactions.py` | ✅ Uruchomiony 2× (po każdym backfillu) | Ostatni stan: 616 INCOMING / 798 OUTGOING |
| `ensure_schema()`/`seed_reference_data()` | ✅ Uruchomiony automatycznie na starcie `run_backfill.py` (2×) | `products` UPSERT rozszerzony o name/number/sales_price (ta sesja) — P01/P04/P06 przemianowane poprawnie w Supabase, P07 dodany |

**Napotkana awaria w trakcie sesji**: brak błędów technicznych (backfill/reconnect/duplikaty) — jedyny problem to **błąd modelowania biznesowego** (ceny z zadania zbyt niskie względem istniejącej struktury kosztów), opisany szczegółowo w p. 8.

---

## 6. Świadome odstępstwa od podanych fragmentów kodu (dla przyszłej sesji)

Kontynuacja listy z poprzednich sesji (zob. commity Etap 3 → Faza 1):

- **Ceny bazowe `SERVICES` skorygowane w górę względem dosłownej treści zadania** (p. 8) — jedyne odstępstwo tej sesji od literalnego kodu podanego w prompcie, wymuszone przez katastrofalny wynik finansowy (-70%..-183% marży/rok) przy dosłownym zastosowaniu podanych liczb. Zgłoszone użytkownikowi przed commitem, nie zdecydowane samodzielnie.
- **`product_for_service()` (jeden kanoniczny produkt per usługa, niezależny od segmentu)** zamiast dosłownego `product_service_code` na `OrderLine`/`order_lines` z pseudokodu zadania — schemat `order_lines.product_id` (FK do `products`) już istniał i jest zgodny z rzeczywistym Tripletex API (`OrderLine.product: TripletexRef`); dodanie nowej kolumny `product_service_code` byłoby denormalizacją nadmiarową względem `products.service_code`, które już istnieje od Fazy 1. Kod usługi danej linii wynika z joina `order_lines.product_id → products.service_code`.
- **4 osobne `SupplierInvoice` dla L01 (Microsoft)** zamiast `SupplierInvoiceLine` (multi-line) — model `SupplierInvoice` nie ma linii (w przeciwieństwie do `Order`/`OrderLine`), a zadanie explicite dopuszczało ten wariant jako fallback ("4 osobne faktury w tym samym dniu, jeśli [multi-line] nie wspiera").
- **`apply_annual_inflation` zaimportowana z `order_generator.py` do `supplier_invoice_generator.py`** (nie zduplikowana) — DRY, brak cyklu importu (order_generator nie importuje supplier_invoice_generator).
- Kontynuacja wcześniejszych zasad: `random.Random(string)` nie `hash()`, statusy/ceny deterministyczne przy tworzeniu rekordu nie względem `today`, `ON CONFLICT DO UPDATE` dla metadanych.

---

## 7. Stan bazy Supabase (migawka na koniec sesji, PO korekcie cen)

| Tabela | Liczba wierszy |
|---|---|
| orders | 879 |
| order_lines | 1885 |
| supplier_invoices | 818 (364 to L01 Microsoft, 4×91 miesięcy) |
| salary_transactions | 91 |
| vouchers | 2415 |
| postings | 4918 |
| bank_transactions | 1414 (798 OUTGOING / 616 INCOMING) |
| hour_entries | 26 859 (do 2026-07-03, bez zmian vs poprzednia sesja) |
| projects | 8 |
| products | 7 (P07 nowy) |
| services | 4 |

Zakres historyczny: 2019-01-01 → 2026-07-05 (dziś).

---

## 8. Rzeczywiste liczby marży — PRZED i PO korekcie cen (kluczowe dla przyszłej sesji)

**Ceny z pierwotnej treści zadania** (`S01` Enterprise/Mid/SMB = 45000/18000/4500 NOK/mies., `S02` = 20000/8000, `S03` = 15000) dały:

| Rok | Przychód (NOK) | Wynik (NOK) | Marża |
|---|---|---|---|
| 2019 | 2 372 402 | -4 348 484 | -183,3% |
| 2023 | 6 033 074 | -10 627 875 | -176,2% |
| 2025 | 6 416 554 | -11 342 342 | -176,8% |

Payroll sam w sobie (15,5M NOK/rok w 2025) przewyższał **cały przychód firmy 2,4×**. Przyczyna: dawne ceny `Product` (np. P03 SMB = 62 000 NOK/mies.) skalibrowane w poprzednich sesjach względem 16-osobowego zespołu, nowe ceny `Service` z zadania były nawet 13,8× niższe (SMB 4500 vs 62000) — redukcja przychodu nie miała żadnego pokrycia w redukcji kosztów (payroll niezmieniony).

**Zatrzymano się i zgłoszono użytkownikowi przed commitem** (nie zdecydowano samodzielnie o dostosowaniu liczb) — otrzymano skorygowane ceny bazowe:

- `S01`: Enterprise=133 000, Mid=84 500, SMB=49 000 NOK/mies.
- `S02`: Enterprise=59 000, Mid=37 500 NOK/mies.
- `S03`: Enterprise=44 000 NOK/mies.

Po korekcie i **drugim** pełnym reset+backfill, rzeczywista marża:

| Rok | Przychód (NOK) | Wynik (NOK) | Marża |
|---|---|---|---|
| 2019 | 7 306 506 | 585 621 | 8,0% (rok startowy, oczekiwane niżej) |
| 2020 | 17 770 538 | 8 739 263 | 49,2% |
| 2021 | 19 922 564 | 9 348 910 | 46,9% |
| 2022 | 20 960 374 | 7 852 399 | 37,5% |
| 2023 | 21 540 720 | 4 879 771 | 22,7% |
| 2024 | 22 314 991 | 5 003 848 | 22,4% |
| 2025 | 22 194 839 | 4 435 942 | 20,0% |
| 2026 (częściowy) | 13 396 594 | 2 622 669 | 19,6% |

Marża stabilizuje się w docelowym przedziale 15-25% od 2023 (kiedy portfel klientów jest już bliski pełnego). Lata 2020-2022 mają wyższą marżę (37-49%) — zespół rośnie wolniej niż przychód w tym okresie; do ewentualnego dostrojenia w Fazie 5, ale w granicach "rozsądnego zakresu" wymaganego przez zadanie.

**Świadomy kompromis zapisany przez użytkownika**: cena SMB (49 000 NOK/mies. = 588 000 NOK/rok) jest wyższa niż realny rynek dla pojedynczego małego klienta (20-40 tys. NOK/rok) — ceny są skalibrowane pod OBECNĄ liczbę klientów (12), nie docelowe 40-50 z Fazy 4. Do skorygowania w dół w Fazie 4, gdy wolumen klientów SMB pozwoli obniżyć cenę per klient bez zawalenia przychodu firmy.

**Wniosek dla przyszłych sesji**: gdy zadanie podaje dosłowne wartości liczbowe cen/kosztów, warto **zweryfikować wynikową marżę przed commitem**, nie tylko zaimplementować literalnie — ceny nie istnieją w próżni, muszą być spójne z już skalibrowaną strukturą kosztów z poprzednich faz.
