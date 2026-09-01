"""Faza 7b — szok makroekonomiczny 2020 (COVID-19).

RÓŻNICA ARCHITEKTONICZNA względem client_events.py/company_events.py/
seasonality.py: to zdarzenie jest **DETERMINISTYCZNIE WSTAWIONE na konkretny
rok**, nie losowane. `random.Random(string)` NIE jest tu w ogóle używane —
nie ma czego losować, bo to jest świadomie zaszyty fakt historyczny
(realny szok COVID-19 w Norwegii, marzec-czerwiec 2020), nie przestrzeń
prawdopodobieństw. Zamierzone rozróżnienie od reszty katalogu Fazy 7 —
zob. też SESSION_HANDOFF.md, Faza 7b.

Zakres świadomie ograniczony do 2020 — nie dotyka lat dojrzałych
(2023-2026, próg bezpieczeństwa 5,5-9%) w żaden sposób."""

from __future__ import annotations

MACRO_SHOCK_EVENTS: dict[str, dict] = {
    "COVID_2020": {
        "year": 2020,
        "months_affected": (3, 4, 5, 6),
        "effect": "broad_slowdown",
        "ticket_volume_multiplier": 0.65,
        "new_client_onboarding_freeze": True,
        "extra_consulting_suppression": 0.3,
        "payment_delay_multiplier": 1.8,
    }
}


def _is_covid_window(year: int, month: int) -> bool:
    shock = MACRO_SHOCK_EVENTS["COVID_2020"]
    return year == shock["year"] and month in shock["months_affected"]


def apply_macro_shock_multiplier(year: int, month: int, base_multiplier: float) -> float:
    """Zadanie 1b — nakłada szok makro na już istniejące mnożniki (fellesferie,
    UNPROFITABLE_QUARTER), mnożnikowo, nie zastępując. Dotyczy WSZYSTKICH
    aktywnych klientów jednocześnie (nie per-klient losowanie jak
    TEMPORARY_HARDSHIP) — kluczowa różnica: MACRO_SHOCK to szok rynkowy,
    nie sytuacja pojedynczej firmy."""
    if _is_covid_window(year, month):
        return base_multiplier * MACRO_SHOCK_EVENTS["COVID_2020"]["ticket_volume_multiplier"]
    return base_multiplier


def extra_consulting_shock_multiplier(year: int, month: int) -> float:
    """Zadanie 1d — tłumienie should_generate_extra_consulting (Faza 2) w
    oknie COVID: próg × 0.3 (tylko 30% zwykłej szansy). 1.0 poza oknem —
    mnoży się z q4_budget_flush_multiplier (Faza 7a), nie zastępuje."""
    if _is_covid_window(year, month):
        return MACRO_SHOCK_EVENTS["COVID_2020"]["extra_consulting_suppression"]
    return 1.0


def payment_delay_adjusted_bad_debt(base_probability: float, base_written_off_share: float,
                                     year: int, month: int) -> tuple[float, float]:
    """Zadanie 1e — podnosi prawdopodobieństwo OVERDUE (payment_delay_multiplier),
    ale zachowuje ABSOLUTNE prawdopodobieństwo WRITTEN_OFF dokładnie na
    normalnym poziomie (opóźnienie płatności ≠ fala bankructw). Zwraca
    (bad_debt_probability, written_off_share) do przekazania bezpośrednio
    do order_generator.determine_order_status.

    Matematyka: normalny P(WRITTEN_OFF) = base_probability * base_written_off_share
    zostaje NIETKNIĘTY; tylko P(OVERDUE) = base_probability*(1-base_written_off_share)
    rośnie ×payment_delay_multiplier. Oba przeliczone z powrotem na
    (bad_debt_probability, written_off_share), bo determine_order_status
    operuje w tej parametryzacji (jeden rng.random() < bad_debt_probability,
    potem drugi rng.random() < written_off_share)."""
    if not _is_covid_window(year, month):
        return base_probability, base_written_off_share

    multiplier = MACRO_SHOCK_EVENTS["COVID_2020"]["payment_delay_multiplier"]
    normal_written_off_abs = base_probability * base_written_off_share
    normal_overdue_abs = base_probability * (1 - base_written_off_share)
    elevated_overdue_abs = normal_overdue_abs * multiplier

    adjusted_bad_debt_probability = elevated_overdue_abs + normal_written_off_abs
    adjusted_written_off_share = normal_written_off_abs / adjusted_bad_debt_probability
    return adjusted_bad_debt_probability, adjusted_written_off_share
