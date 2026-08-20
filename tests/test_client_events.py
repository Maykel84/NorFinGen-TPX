"""Faza 7, Zadanie 2 — zdarzenia losowe na poziomie klienta (life events)."""

from datetime import date

from norfingen.generators.client_events import (
    customer_event_state_asof,
    effective_customer_services,
    event_aware_is_customer_active,
    hardship_ticket_multiplier_for,
)
from norfingen.seed.roster import customer_by_number, get_customer_services

# Zdarzenia znalezione deterministycznie przez pełne przejście 2019-2026/07
# (zob. SESSION_HANDOFF.md Faza 7, Zadanie 2) — testy zamrażają te konkretne
# wyniki jako regresję, tak jak reszta pakietu robi z innymi deterministycznymi
# generatorami (np. test_order_generator.py::test_monthly_orders_use_customer_invoice_day).
K12_BANKRUPTCY_MONTH = (2024, 11)  # SMB
K01_LARGE_PROJECT_MONTH = (2020, 5)  # Enterprise
K02_HARDSHIP_MONTH = (2024, 12)  # Mid-market, okno (2024,12)-(2025,1)
K34_REDUCTION_MONTH = (2024, 1)  # Mid-market
K32_EXPANSION_MONTH = (2024, 2)  # Mid-market


def test_deterministic_across_repeated_calls():
    a = customer_event_state_asof("K12", 2024, 11)
    b = customer_event_state_asof("K12", 2024, 11)
    assert a == b


def test_pattern_d_customer_never_gets_events():
    # K06 (consulting, pattern D) — świadomie wykluczony (zob. docstring
    # customer_event_state_asof), brak stałego bundla usług do zmiany.
    for year in range(2019, 2027):
        for month in range(1, 13):
            state = customer_event_state_asof("K06", year, month)
            assert state.triggered_this_month is None
            assert not state.churned


def test_bankruptcy_only_eligible_for_smb():
    # K01 (Enterprise) i K07 (Mid-market) nigdy nie churnują przez BANKRUPTCY
    # (eligible_segments=("SMB",)) — sprawdzone na całej historii.
    for number in ("K01", "K07"):
        for year in range(2019, 2027):
            for month in range(1, 13):
                assert not customer_event_state_asof(number, year, month).churned


def test_bankruptcy_churn_takes_effect_month_after_trigger():
    year, month = K12_BANKRUPTCY_MONTH
    k12 = customer_by_number("K12")
    trigger_state = customer_event_state_asof("K12", year, month)
    assert trigger_state.triggered_this_month == "BANKRUPTCY"
    assert trigger_state.churned is True

    # Miesiąc triggera: klient jeszcze aktywny (ostatnia, odpisana faktura).
    assert event_aware_is_customer_active(k12, date(year, month, 15)) is True
    # Miesiąc kolejny: klient trwale nieaktywny.
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)
    assert event_aware_is_customer_active(k12, date(next_year, next_month, 1)) is False
    # Churn jest trwały — sprawdzone daleko w przyszłości.
    assert event_aware_is_customer_active(k12, date(2026, 6, 1)) is False


def test_hardship_window_has_constant_multiplier_and_expires():
    year, month = K02_HARDSHIP_MONTH
    state = customer_event_state_asof("K02", year, month)
    assert state.triggered_this_month == "TEMPORARY_HARDSHIP"
    assert state.hardship_active_until is not None
    end_year, end_month = state.hardship_active_until

    mult_start = hardship_ticket_multiplier_for("K02", date(year, month, 15))
    mult_end = hardship_ticket_multiplier_for("K02", date(end_year, end_month, 15))
    assert 0.40 <= mult_start <= 0.60
    assert mult_start == mult_end  # stały przez całe okno

    # Miesiąc po wygaśnięciu — z powrotem 1.0 (chyba że coś innego wystrzeli
    # od razu; sprawdzamy tylko że hardship_active_until faktycznie minęło).
    after_year, after_month = (end_year, end_month + 1) if end_month < 12 else (end_year + 1, 1)
    state_after = customer_event_state_asof("K02", after_year, after_month)
    assert state_after.hardship_active_until is None or state_after.hardship_active_until != state.hardship_active_until


def test_offer_reduction_never_removes_s01():
    year, month = K34_REDUCTION_MONTH
    k34 = customer_by_number("K34")
    state = customer_event_state_asof("K34", year, month)
    assert state.triggered_this_month == "OFFER_REDUCTION"
    services = effective_customer_services(k34, state)
    assert "S01" in services
    assert len(services) < len(get_customer_services(k34))


def test_offer_expansion_adds_service_not_in_standard_bundle():
    year, month = K32_EXPANSION_MONTH
    k32 = customer_by_number("K32")
    state = customer_event_state_asof("K32", year, month)
    assert state.triggered_this_month == "OFFER_EXPANSION"
    standard = get_customer_services(k32)
    expanded = effective_customer_services(k32, state)
    assert len(expanded) == len(standard) + 1
    assert set(standard).issubset(expanded)


def test_expansion_service_always_priced_for_segment():
    # Zadanie 2c: regresja przeciw crashowi znalezionemu podczas implementacji
    # (S02/S03 niedostępne cenowo dla części segmentów — zob. SESSION_HANDOFF.md).
    from norfingen.generators.order_generator import build_order_lines

    k32 = customer_by_number("K32")
    order_date = date(*K32_EXPANSION_MONTH, 10)
    lines = build_order_lines(k32, order_date)  # nie może rzucić TypeError (None * float)
    assert len(lines) >= 1


def test_large_project_order_significantly_bigger_than_standard_extra_consulting():
    from norfingen.generators.order_generator import CONSULTING_PRICE_MAX, generate_monthly_orders
    from norfingen.seed.roster import numeric_id

    year, month = K01_LARGE_PROJECT_MONTH
    k01_id = numeric_id("K01")
    orders = generate_monthly_orders(year, month)
    k01_orders = [o for o in orders if o.customer.id == k01_id]
    large_project_lines = [line for o in k01_orders for line in o.orderLines if line.count > 20]
    assert large_project_lines
    total = sum(line.amountExcludingVatCurrency for line in large_project_lines)
    assert total > CONSULTING_PRICE_MAX  # wyraźnie większe niż ryczałt 20-50k standardowego extra-consultingu
