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

from norfingen.generators.backfill import DEFAULT_START_DATE, run_backfill
from norfingen.generators.hours_generator import generate_daily_hours, is_working_day
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.voucher import Voucher
from norfingen.models.hours import ActivityType
from norfingen.models.order import Order, OrderStatus
from norfingen.seed.roster import CUSTOMERS

MARGIN_SAFETY_LOW = 0.055
MARGIN_SAFETY_HIGH = 0.09


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
    """Próg bezpieczeństwa marży 5,5-9% dla lat dojrzałych pozostaje
    nienaruszony — MACRO_SHOCK jest ograniczony do 2020, nie dotyka
    późniejszych lat w żaden sposób (ani przez stan, ani przez efekt
    uboczny)."""
    revenue: dict[int, float] = {}
    payroll: dict[int, float] = {}
    opex: dict[int, float] = {}
    cogs: dict[int, float] = {}

    def collect(obj):
        if isinstance(obj, Order):
            year = obj.orderDate.year
            revenue[year] = revenue.get(year, 0.0) + sum(
                line.count * line.unitPriceExcludingVatCurrency for line in obj.orderLines
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

    run_backfill(start_date=DEFAULT_START_DATE, end_date=date(2026, 7, 31), persist_fn=collect)

    for year in (2023, 2024, 2025, 2026):
        r = revenue[year]
        total_cost = payroll.get(year, 0.0) + opex.get(year, 0.0) + cogs.get(year, 0.0)
        margin = (r - total_cost) / r
        assert MARGIN_SAFETY_LOW <= margin <= MARGIN_SAFETY_HIGH, f"{year}: margin={margin:.4f} poza progiem"


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
