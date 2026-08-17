import random
from datetime import date, timedelta

from norfingen.generators.backfill import DEFAULT_START_DATE, run_backfill
from norfingen.generators.hours_generator import (
    client_lifecycle_phase,
    generate_daily_support_hours,
    select_active_onboarding_clients,
)
from norfingen.generators.voucher import Voucher
from norfingen.models.hours import ActivityType
from norfingen.models.order import Order
from norfingen.seed.roster import (
    EMPLOYEES,
    calc_azure_cogs_monthly,
    calc_s01_cogs_monthly,
    customer_by_number,
)

# Próg bezpieczeństwa z promptu Fazy 6 — jeśli marża 2025/2026 wyjdzie poza
# ten zakres, backfill NIE powinien być uruchamiany bez ponownej kalibracji.
MARGIN_SAFETY_LOW = 0.055
MARGIN_SAFETY_HIGH = 0.09


def last_fully_closed_month_end(today: date) -> date:
    """Ostatni dzień poprzedniego miesiąca kalendarzowego — gwarantuje, że
    payroll dla tego miesiąca już zdążył się zaksięgować.

    DLACZEGO to ograniczenie istnieje (nie usuwać / nie zastępować
    `date.today()` z powrotem): lista płac księguje się JEDNORAZOWO, na
    ostatni dzień roboczy miesiąca (`should_generate_monthly_salary`) —
    trwający, jeszcze niezakończony miesiąc ma więc payroll=0, mimo że jego
    opex/COGS (księgowane 1. dnia miesiąca) i część przychodu już istnieją.
    To tymczasowo, sztucznie ZAWYŻA marżę tego miesiąca (brakuje mu
    największej pojedynczej pozycji kosztowej) i ciągnie w górę całoroczną
    marżę kumulatywną — niezależnie od tego, czy cokolwiek w kalibracji się
    zmieniło. Zaobserwowane na żywo 2026-08-17: marża 2026 przez lipiec
    (miesiące w pełni zamknięte) = 7,47% (w progu), ale z doliczonym
    trwającym sierpniem (payroll=0, ale pełny COGS/opex + połowa przychodu)
    skoczyła do 9,12%+ (poza górną granicą) — czysty artefakt dnia
    uruchomienia testu, nie regresja modelu finansowego."""
    first_of_this_month = today.replace(day=1)
    return first_of_this_month - timedelta(days=1)


def test_azure_cogs_scales_with_s02_clients():
    """COGS S02 (Azure) rośnie z liczbą klientów Enterprise/Mid, nie jest płaski."""
    few = calc_azure_cogs_monthly([customer_by_number("K01")])  # 1 Enterprise
    many = [customer_by_number(f"K{n:02d}") for n in (1, 3, 11, 13, 16, 20, 23, 26)]  # kilku Enterprise
    assert calc_azure_cogs_monthly(many) > few * 5


def test_s01_cogs_scales_with_all_clients_including_smb():
    """COGS S01 rośnie z WSZYSTKIMI segmentami (w przeciwieństwie do S02,
    który pomija SMB) — zob. roster.calc_s01_cogs_monthly."""
    smb_only = [customer_by_number("K04")]  # SMB
    mixed = [customer_by_number(n) for n in ("K01", "K02", "K04")]  # Ent+Mid+SMB
    cogs_smb_only = calc_s01_cogs_monthly(smb_only)
    cogs_mixed = calc_s01_cogs_monthly(mixed)
    assert cogs_smb_only > 0  # SMB sam w sobie generuje COGS (w odróżnieniu od Azure/S02)
    assert cogs_mixed > cogs_smb_only


def test_headcount_matches_realistic_target():
    """Faza 6 — zespół skalibrowany top-down względem realnych danych
    rynkowych (Garnes Data AS: 17 pracowników) ląduje w rozsądnym przedziale,
    nie w poprzednim 38-osobowym (Faza 4)."""
    active = [e for e in EMPLOYEES]
    assert 14 <= len(active) <= 20


def test_margin_within_safety_threshold_2025_2026():
    """Regresja kalibracji Fazy 6 (2. próba, COGS S01+S02) — offline
    sanity-check wykonany PRZED backfillem wykazał marżę 2025 (pełny rok) i
    2026 (do ostatniego W PEŁNI zamkniętego miesiąca) w zakresie 5,5-9%. Ten
    test zamraża tamten wynik jako regresję: jeśli ktoś zmieni ceny/COGS/
    headcount bez ponownej kalibracji, test się wywali zamiast cichego
    rozjazdu marży.

    end_date ograniczony do last_fully_closed_month_end() — NIE
    `date.today()` — zob. docstring tamtej funkcji: trwający miesiąc zawsze
    tymczasowo zawyża marżę (payroll księguje się dopiero na jego koniec),
    co dawało fałszywe alarmy zależne wyłącznie od dnia uruchomienia testu,
    nie od faktycznego stanu kalibracji."""
    revenue: dict[int, float] = {}
    payroll: dict[int, float] = {}
    opex: dict[int, float] = {}
    cogs: dict[int, float] = {}

    def collect(obj):
        if isinstance(obj, Order):
            year = obj.orderDate.year
            revenue[year] = revenue.get(year, 0.0) + sum(
                l.count * l.unitPriceExcludingVatCurrency for l in obj.orderLines
            )
        elif isinstance(obj, Voucher):
            year = obj.date.year
            for p in obj.postings:
                if p.amount <= 0:
                    continue
                n = p.account.number
                if 5000 <= n <= 5999:
                    payroll[year] = payroll.get(year, 0.0) + p.amount
                elif 6000 <= n <= 7999:
                    opex[year] = opex.get(year, 0.0) + p.amount
                elif 4000 <= n <= 4999:
                    cogs[year] = cogs.get(year, 0.0) + p.amount

    run_backfill(
        start_date=DEFAULT_START_DATE,
        end_date=last_fully_closed_month_end(date.today()),
        persist_fn=collect,
    )

    for year in (2025, 2026):
        r = revenue[year]
        total_cost = payroll.get(year, 0.0) + opex.get(year, 0.0) + cogs.get(year, 0.0)
        margin = (r - total_cost) / r
        assert MARGIN_SAFETY_LOW <= margin <= MARGIN_SAFETY_HIGH, (
            f"{year}: margin={margin:.3f} poza progiem bezpieczeństwa "
            f"[{MARGIN_SAFETY_LOW}, {MARGIN_SAFETY_HIGH}] "
            f"(revenue={r:.0f} payroll={payroll.get(year, 0):.0f} "
            f"opex={opex.get(year, 0):.0f} cogs={cogs.get(year, 0):.0f})"
        )


def test_leveranse_consultant_serves_multiple_clients_per_day():
    """Zadanie 3/6 — konsultant Leveranse obsługuje kilku klientów dziennie
    (model ticketowy), nie jednego jak w Fazie 4."""
    customers = [
        customer_by_number(n) for n in ("K01", "K02", "K03", "K05", "K07", "K08", "K11")
    ]
    entries = generate_daily_support_hours(2, customers, date(2026, 3, 10), random.Random(1))
    billable = [e for e in entries if e.activity_type == ActivityType.BILLABLE]
    assert len(billable) >= 2
    total_billable_hours = sum(e.hours for e in billable)
    assert 0 < total_billable_hours <= 7.0  # dąży do 5,5-7,0h, nie zawsze trafia dokładnie (zob. pseudokod Zadania 3)
    total_hours = sum(e.hours for e in entries)
    assert abs(total_hours - 7.5) < 0.01


def test_teknologi_full_day_during_client_onboarding():
    """Zadanie 4 — klient tuż po onboarding_date jest w fazie ONBOARDING;
    Teknologi pracuje u niego pełny dzień, nie rozproszone tickety."""
    k01 = customer_by_number("K01")  # onboarding 2019-03-01, Enterprise -> 6 tygodni ONBOARDING
    assert client_lifecycle_phase(k01, date(2019, 3, 5)) == "ONBOARDING"
    assert client_lifecycle_phase(k01, date(2019, 6, 1)) == "MAINTENANCE"

    active = select_active_onboarding_clients([k01], date(2019, 3, 5))
    assert active == [k01]
