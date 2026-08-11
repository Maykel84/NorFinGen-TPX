# Podłączenie NorFingen do Power BI

Zob. `DATA_DICTIONARY.md` (sekcja "Dostęp read-only") dla pełnego opisu roli `powerbi_reader`, GRANT-ów i widoków — ten dokument to tylko instrukcja podłączenia.

## Dane połączenia

W Power BI Desktop: **Pobierz dane → Więcej → Baza danych → PostgreSQL database**

- **Serwer**: `aws-1-eu-central-1.pooler.supabase.com:5432` (Session pooler — zweryfikowane, ten port; Transaction pooler na 6543 też istnieje w Supabase, ale nie był testowany z tą rolą w tym projekcie)
- **Baza danych**: `postgres`
- **Tryb łączności danych**: Import (zalecane) lub DirectQuery (live, ale wolniejsze odświeżanie raportów)
- **Uwierzytelnianie**: Baza danych
  - **Użytkownik**: `powerbi_reader.<project_ref>` — **UWAGA**: to NIE jest sam `powerbi_reader`. Supabase Pooler wymaga kwalifikowanej nazwy użytkownika w formacie `<rola>.<project_ref>` (np. `powerbi_reader.zijotdnqunkwqztpxhiv`). Bez tego sufiksu logowanie się nie powiedzie. Dokładny, gotowy do wklejenia username wypisuje `scripts/setup_powerbi_reader.py` przy każdym uruchomieniu.
  - **Hasło**: [przekazane bezpiecznie, nie w tym dokumencie — zob. `scripts/setup_powerbi_reader.py`]
- **Encrypt connection**: włączone (Supabase wymaga SSL — bez tego połączenie się nie nawiąże)

## Zalecane tabele/widoki do połączenia

Dla podstawowej analityki finansowej wystarczą 3 widoki (zob. `DATA_DICTIONARY.md`, "Widoki BI"):
- **`v_sales_flat`** — sprzedaż z pełnym kontekstem klienta (segment, miasto, kod pocztowy, NACE)
- **`v_pl_monthly`** — P&L miesięczny (revenue, labor_cost, operating_cost, cogs, operating_result) gotowy do wykresu
- **`v_headcount_monthly`** — trend zatrudnienia — **uwaga**: liczy tylko pracowników billable logujących godziny (Leveranse/Teknologi), nie pełny headcount kadrowy (role wspierające Salg/Økonomi nigdy nie logują `hour_entries`). Jeśli potrzebny prawdziwy headcount, połącz się do `employments`/`employees` zamiast tego widoku.

Dla głębszej analizy — połącz się bezpośrednio do tabel źródłowych:
`orders`, `order_lines`, `supplier_invoices`, `customers`, `suppliers`, `employees`, `hour_entries`, `bank_transactions`, `vouchers`, `postings`.

## Odświeżanie danych

- **Power BI Desktop**: ręczne "Refresh" lub zaplanowane w Power BI Service
- Dane w Supabase aktualizują się przyrostowo — GitHub Actions (`.github/workflows/daily.yml`) uruchamia generator 3x/dzień w dni robocze: **07:00, 11:00, 16:00 UTC = 08:00, 12:00, 17:00 CET** (w okresie zimowym; latem CEST przesunie efektywne godziny lokalne o godzinę do przodu — cron GitHub Actions liczy zawsze w UTC, bez DST)
- Zalecany scheduled refresh w Power BI Service: **18:00 CET/CEST** (godzina po ostatnim uruchomieniu generatora), żeby mieć pewność że dane z danego dnia już są w bazie
- **Power BI Service ≠ Power BI Desktop**: scheduled refresh w chmurze (Power BI Service) wymaga skonfigurowania danych logowania do źródła w ustawieniach datasetu PO publikacji raportu — Supabase Postgres jest źródłem chmurowym, więc **nie jest potrzebny on-premises data gateway** (ten jest wymagany tylko dla źródeł lokalnych/za firewallem)

## Limity i bezpieczeństwo

- Rola `powerbi_reader` ma dostęp **wyłącznie do odczytu** (`SELECT`) — zweryfikowane end-to-end (`scripts/test_powerbi_connection.py`): `INSERT`/`UPDATE`/`DELETE` wszystkie poprawnie odrzucane (`InsufficientPrivilege`)
- Limit **3 jednoczesnych połączeń** (`CONNECTION LIMIT 3`) — chroni bazę przed przeciążeniem przy kilku równoległych odświeżeniach (np. kilka raportów Power BI Service naraz)
- **Nie udostępniaj hasła w publicznych repozytoriach ani dokumentach** — hasło NIE jest nigdzie zapisane w tym repo; generowane losowo przez `scripts/setup_powerbi_reader.py`, wypisywane tylko raz na stdout. Zapisz je w menedżerze haseł od razu po wygenerowaniu. Każde ponowne uruchomienie skryptu rotuje hasło i unieważnia poprzednie.

## Weryfikacja połączenia przed podłączeniem Power BI

```bash
python scripts/test_powerbi_connection.py powerbi_reader.<project_ref>
```

Hasło podaj przez zmienną środowiskową `POWERBI_READER_PASSWORD` albo interaktywnie (skrypt zapyta, bez echo) — **nie jako argument wiersza poleceń** (trafiłoby do historii powłoki i byłoby widoczne w liście procesów innym użytkownikom tej samej maszyny). Skrypt sprawdza `SELECT` na 3 widokach BI + 3 tabelach źródłowych, i potwierdza że `INSERT`/`UPDATE`/`DELETE` są zablokowane.
