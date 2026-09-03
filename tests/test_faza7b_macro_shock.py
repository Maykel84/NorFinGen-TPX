"""Faza 7b — szok makroekonomiczny 2020 (COVID_2020), Zadanie 2.

Testy z promptu zaadaptowane do rzeczywistego API: CUSTOMERS to lista
CustomerSeed (dataclass, `.onboarding_date` typu date), nie listy dictów
z "onboarding_date" jako string ISO. Porównanie ticketów kwiecień 2020 vs
kwiecień 2019/2021 zamienione na porównanie WEWNĄTRZ 2020 (miesiące COVID
vs pozostałe) — cross-rok jest silnie zaburzone wzrostem bazy klientów
(2 aktywnych w kwietniu 2019, 8 w 2020, 10 w 2021), więc surowe liczby
ticketów rosłyby z roku na rok niezależnie od COVID; porównanie
wewnątrzroczne izoluje efekt szoku przy tej samej bazie klientów/pracowników."""

from datetime import date, timedelta

from norfingen.generators.hours_generator import generate_daily_hours, is_working_day
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.models.hours import ActivityType
from norfingen.models.order import OrderStatus
from norfingen.seed.roster import CUSTOMERS


def _monthly_ticket_count(year: int, month: int) -> int:
    count = 0
    day = date(year, month, 1)
    while day.month == month:
        if is_working_day(day):
            entries = generate_daily_hours(day.year, day.month, day.day, list(range(1, 18)))
            count += sum(
                1 for e in entries
                if e.activity_type == ActivityType.BILLABLE and e.description and e.description.startswith("Support")
            )
        day += timedelta(days=1)
    return count


def test_macro_shock_reduces_2020_covid_window_ticket_volume():
    covid_months = (3, 4, 5, 6)
    non_covid_months = (1, 2, 7, 8)  # ta sama baza klientów/pracowników w 2020 co okno COVID
    covid_avg = sum(_monthly_ticket_count(2020, m) for m in covid_months) / len(covid_months)
    non_covid_avg = sum(_monthly_ticket_count(2020, m) for m in non_covid_months) / len(non_covid_months)
    assert covid_avg < non_covid_avg


def test_macro_shock_does_not_affect_2023_2026():
    """MACRO_SHOCK (COVID_2020) samo w sobie nie dotyka lat dojrzałych w
    żaden sposób — wszystkie trzy mnożniki wracają do 1.0 (no-op) poza
    oknem marzec-czerwiec 2020.

    NAPRAWA (Faza 7c): pierwotnie ten test uruchamiał pełny backfill i
    sprawdzał margin 2023-2026 w paśmie 5,5-9% — ale to pasmo NIE jest już
    aktualne dla tych lat po Fazie 7c (MAJOR_INCIDENT_2023, świadomy,
    udokumentowany wieloletni wyjątek, zob. SESSION_HANDOFF.md i
    test_faza6_market_calibration.py). Test przez to fałszywie sugerowałby
    regresję MACRO_SHOCK, mimo że przyczyna leży całkowicie gdzie indziej
    (późniejsza, niezwiązana faza). Bezpośrednia weryfikacja funkcji
    mnożników jest właściwym, odpornym na takie sprzężenia sposobem
    sprawdzenia TEGO konkretnego twierdzenia."""
    from norfingen.generators.macro_shock import (
        apply_macro_shock_multiplier,
        extra_consulting_shock_multiplier,
    )

    for year in (2023, 2024, 2025, 2026):
        for month in range(1, 13):
            assert apply_macro_shock_multiplier(year, month, 1.0) == 1.0
            assert extra_consulting_shock_multiplier(year, month) == 1.0


def test_no_onboarding_during_covid_window():
    """Żaden klient nie ma onboarding_date w marcu-czerwcu 2020."""
    for c in CUSTOMERS:
        onboarding = c.onboarding_date
        if onboarding.year == 2020:
            assert not (3 <= onboarding.month <= 6), f"{c.number} ma onboarding_date {onboarding} w oknie COVID"


def test_written_off_rate_2020_not_elevated():
    """WRITTEN_OFF w 2020 pozostaje blisko normalnego poziomu (~0,4%), mimo
    podniesionego OVERDUE w oknie COVID — to opóźnienie, nie fala bankructw."""
    written_off = 0
    total = 0
    for month in range(1, 13):
        for order in generate_monthly_orders(2020, month):
            total += 1
            if order.status == OrderStatus.WRITTEN_OFF:
                written_off += 1
    assert total > 0
    rate = written_off / total
    assert rate < 0.02  # wyraźnie poniżej podniesionego OVERDUE, blisko bazowych ~0.4%
