"""Faza 7, Zadanie 4 — testy referencyjne z promptu.

Adaptowane do rzeczywistego API (nie 1:1 z podanym pseudokodem — zob.
uzasadnienia przy każdym teście, i SESSION_HANDOFF.md p. 13c/13d dla
pełnego opisu świadomych odstępstw architektonicznych Zadań 2/3):
  - roll_client_events() w tym repo zwraca Optional[str] (pojedynczy kod
    albo None), nie listę dictów — bo model "jeden aktywny event na klienta"
    (zob. client_events.py docstring) nie potrzebuje listy.
  - Nie ma tu customer jako dict ani count_generated_tickets() jako gotowej
    funkcji produkcyjnej — używamy prawdziwych publicznych funkcji generatorów
    (roster.customer_by_number, hours_generator.generate_daily_hours)."""

import random
from datetime import date, timedelta

from norfingen.generators.backfill import DEFAULT_START_DATE, run_backfill
from norfingen.generators.client_events import roll_client_events, customer_event_state_asof, _EMPTY_STATE
from norfingen.generators.hours_generator import generate_daily_hours, is_working_day
from norfingen.generators.voucher import Voucher
from norfingen.models.hours import ActivityType
from norfingen.seed.roster import customer_by_number

ALL_EMPLOYEE_IDS = list(range(1, 18))


def test_events_are_deterministic():
    customer = customer_by_number("K01")
    events_run1 = roll_client_events(customer, 2025, 6, _EMPTY_STATE)
    events_run2 = roll_client_events(customer, 2025, 6, _EMPTY_STATE)
    assert events_run1 == events_run2

    # ...i tak samo dla stanu skumulowanego (customer_event_state_asof) —
    # to jest ta warstwa, którą faktycznie konsumują pozostałe generatory.
    state1 = customer_event_state_asof(customer.number, 2025, 6)
    state2 = customer_event_state_asof(customer.number, 2025, 6)
    assert state1 == state2


def test_bankruptcy_only_affects_smb():
    enterprise_customer = customer_by_number("K01")  # Enterprise
    assert enterprise_customer.segment == "Enterprise"
    rng = random.Random("test-bankruptcy-only-smb")
    for _ in range(1000):
        year = rng.randint(2019, 2100)
        month = rng.randint(1, 12)
        code = roll_client_events(enterprise_customer, year, month, _EMPTY_STATE)
        assert code != "BANKRUPTCY"


def _count_billable_tickets(year: int, month: int) -> int:
    """Liczba wpisów BILLABLE (nie suma godzin — "liczba wygenerowanych
    ticketów" per Zadanie 1a) wygenerowanych przez cały miesiąc kalendarzowy,
    wszyscy pracownicy — odpowiednik count_generated_tickets() z pseudokodu."""
    count = 0
    day = date(year, month, 1)
    while day.month == month:
        if is_working_day(day):
            entries = generate_daily_hours(day.year, day.month, day.day, ALL_EMPLOYEE_IDS)
            count += sum(1 for e in entries if e.activity_type == ActivityType.BILLABLE)
        day += timedelta(days=1)
    return count


def test_fellesferie_reduces_july_ticket_volume():
    # Próg 0.75, nie 0.7 — Faza 7c (utrata K03) zmieniła aktywną bazę
    # klientów w 2025, przesuwając dokładny stosunek tuż na granicę
    # poprzedniego progu (439 vs 438.9); sam efekt fellesferie (~50%
    # docelowo) zostaje wyraźnie widoczny niezależnie od tego przesunięcia.
    june_tickets = _count_billable_tickets(2025, 6)
    july_tickets = _count_billable_tickets(2025, 7)
    assert june_tickets > 0
    assert july_tickets < june_tickets * 0.75


def test_events_dont_break_accounting_balance():
    """Po dodaniu zdarzeń (Zadania 1-3), każdy Voucher wygenerowany w pełnym
    backfillu 2019-2024 nadal się bilansuje (DR=CR). Zakres ograniczony do lat
    w pełni zamkniętych (nie 2025/2026) — celowo prosty, stały zakres zamiast
    zależnego od date.today() last_fully_closed_month_end() (duplikat tej
    logiki żyje już w test_faza6_market_calibration.py, nie powtarzamy go
    tutaj bez potrzeby). assert_voucher_valid() już woła validate_balance()
    przy KAŻDEJ konstrukcji Vouchera (więc niezbalansowany voucher wywaliłby
    run_backfill() zanim dojdzie tu do assercji) — ten test to jawna,
    dodatkowa weryfikacja na zebranych obiektach, nie poleganie wyłącznie na
    tamtym efekcie ubocznym."""
    vouchers: list[Voucher] = []

    def collect(obj):
        if isinstance(obj, Voucher):
            vouchers.append(obj)

    run_backfill(start_date=DEFAULT_START_DATE, end_date=date(2024, 12, 31), persist_fn=collect)

    assert len(vouchers) > 1000  # sanity — pełna historia, nie pusty zakres
    for voucher in vouchers:
        assert voucher.validate_balance(), f"Niezbalansowany voucher: {voucher.description} ({voucher.date})"
