"""Faza 7, Zadanie 3 — zdarzenia losowe na poziomie firmy.

Ten sam wzorzec co client_events.py (Zadanie 2): stan jako czysta,
memoizowana funkcja (rok, miesiąc) -> skumulowany stan, nie mutowalny
ledger — z tych samych powodów (backfill to dwa osobne procesy, żywy cron
to trzeci, zob. docstring client_events.py). Tu jedyny element, który
faktycznie wymaga pamięci ponad jeden miesiąc, to SUPPLIER_RENEGOTIATION
("trwale od tego miesiąca") — EQUIPMENT_INVESTMENT i UNPROFITABLE_QUARTER
są w pełni wyprowadzalne z samego roll_company_events(year) (Zadanie 3b),
bez żadnego stanu."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from norfingen.seed.roster import SUPPLIERS

FOUNDING_YEAR = 2019
FOUNDING_MONTH = 1

COMPANY_LIFE_EVENTS: dict[str, dict] = {
    "EQUIPMENT_INVESTMENT": {
        "yearly_probability": 0.35,
        "effect": "capex_office_equipment",
        "amount_range": (80_000, 250_000),
    },
    "UNPROFITABLE_QUARTER": {
        "yearly_probability": 0.25,
        "effect": "temporary_cost_spike_or_revenue_dip",
        "magnitude_range": (0.85, 0.95),
    },
    "SUPPLIER_RENEGOTIATION": {
        "yearly_probability": 0.3,
        "effect": "one_time_cost_change",
        "amount_range_pct": (-15, 10),
    },
}

# "jednorazowy wzrost kosztu opex" (Zadanie 3c) — kwota nie podana w zadaniu
# (tylko magnitude_range przypisany do ticketów/wolumenu, zob. niżej),
# skalibrowana samodzielnie: rząd wielkości jednego "trudnego miesiąca"
# nietypowego kosztu, nie destabilizujący marży rocznej (~2,2M NOK opex/rok
# na ~9 kont — zob. SESSION_HANDOFF.md).
UNPROFITABLE_QUARTER_COST_SPIKE_MIN = 40_000.0
UNPROFITABLE_QUARTER_COST_SPIKE_MAX = 120_000.0
ACCOUNT_UNEXPECTED_COST = 7790  # NS4102 "Annen driftskostnad" — nowe konto, nieużywane dotąd w tym repo


def roll_company_events(year: int) -> list[dict]:
    """Zadanie 3b — dokładnie wg podanego pseudokodu."""
    rng = random.Random(f"COMPANY-{year}-events")
    triggered = []
    for event_code, event_def in COMPANY_LIFE_EVENTS.items():
        if rng.random() < event_def["yearly_probability"]:
            month = rng.randint(1, 12)
            triggered.append({"code": event_code, "year": year, "month": month})
    return triggered


@lru_cache(maxsize=None)
def _year_triggers(year: int) -> dict[str, int]:
    """code -> miesiąc (1-12), memoizowany wrapper wokół roll_company_events —
    unika ponownego losowania (i przez to niepotrzebnej pracy) przy każdym
    zapytaniu o pojedynczy miesiąc tego roku."""
    return {ev["code"]: ev["month"] for ev in roll_company_events(year)}


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


@dataclass(frozen=True)
class CompanyEventState:
    """supplier_number -> skumulowany mnożnik kosztu (1.0 = bez zmian) po
    wszystkich SUPPLIER_RENEGOTIATION do (year, month) włącznie. Kolejne
    renegocjacje TEGO SAMEGO dostawcy w różnych latach się mnożą (kolejne
    negocjacje kontraktu) — świadomy wybór, zadanie nie precyzuje."""

    supplier_multipliers: dict[str, float] = field(default_factory=dict)


_EMPTY_COMPANY_STATE = CompanyEventState()


@lru_cache(maxsize=None)
def company_event_state_asof(year: int, month: int) -> CompanyEventState:
    if (year, month) < (FOUNDING_YEAR, FOUNDING_MONTH):
        return _EMPTY_COMPANY_STATE

    if (year, month) == (FOUNDING_YEAR, FOUNDING_MONTH):
        prev_multipliers: dict[str, float] = {}
    else:
        prev_year, prev_month = _prev_month(year, month)
        prev_multipliers = dict(company_event_state_asof(prev_year, prev_month).supplier_multipliers)

    if _year_triggers(year).get("SUPPLIER_RENEGOTIATION") == month:
        effect_rng = random.Random(f"COMPANY-{year}-SUPPLIER_RENEGOTIATION-effect")
        supplier_number = effect_rng.choice([s.number for s in SUPPLIERS])
        pct_min, pct_max = COMPANY_LIFE_EVENTS["SUPPLIER_RENEGOTIATION"]["amount_range_pct"]
        pct = effect_rng.uniform(pct_min, pct_max)
        current = prev_multipliers.get(supplier_number, 1.0)
        prev_multipliers[supplier_number] = current * (1 + pct / 100)

    return CompanyEventState(supplier_multipliers=prev_multipliers)


def supplier_cost_multiplier(supplier_number: str, year: int, month: int) -> float:
    """Zadanie 3c — mnożnik kosztu dostawcy po ewentualnych renegocjacjach
    (1.0 = bez zmian). Podłączane w supplier_invoice_generator PRZED
    zaokrągleniem kwoty netto."""
    return company_event_state_asof(year, month).supplier_multipliers.get(supplier_number, 1.0)


def equipment_investment_trigger(year: int, month: int) -> Optional[float]:
    """Zadanie 3c — zwraca wylosowaną kwotę (80k-250k) jeśli EQUIPMENT_INVESTMENT
    wystrzeliło w (year, month) tego roku, inaczej None."""
    if _year_triggers(year).get("EQUIPMENT_INVESTMENT") != month:
        return None
    rng = random.Random(f"COMPANY-{year}-EQUIPMENT_INVESTMENT-effect")
    amount_min, amount_max = COMPANY_LIFE_EVENTS["EQUIPMENT_INVESTMENT"]["amount_range"]
    return round(rng.uniform(amount_min, amount_max), 2)


def unprofitable_quarter_ticket_multiplier(year: int, month: int) -> float:
    """Zadanie 3c — mnożnik wolumenu ticketów (hours_generator), aktywny przez
    CAŁY kwartał zawierający wylosowany miesiąc UNPROFITABLE_QUARTER (nie tylko
    ten jeden miesiąc) — 1.0 poza oknem."""
    triggered_month = _year_triggers(year).get("UNPROFITABLE_QUARTER")
    if triggered_month is None:
        return 1.0
    quarter_start = ((triggered_month - 1) // 3) * 3 + 1
    if not (quarter_start <= month < quarter_start + 3):
        return 1.0
    rng = random.Random(f"COMPANY-{year}-UNPROFITABLE_QUARTER-effect")
    magnitude_min, magnitude_max = COMPANY_LIFE_EVENTS["UNPROFITABLE_QUARTER"]["magnitude_range"]
    return rng.uniform(magnitude_min, magnitude_max)


def unprofitable_quarter_cost_spike(year: int, month: int) -> Optional[float]:
    """Zadanie 3c — "jednorazowy wzrost kosztu opex": zwraca wylosowaną kwotę
    (UNPROFITABLE_QUARTER_COST_SPIKE_MIN..MAX) jeśli (year, month) to
    DOKŁADNIE wylosowany miesiąc triggera (nie cały kwartał — to jest
    jednorazowe, w przeciwieństwie do redukcji ticketów), inaczej None."""
    if _year_triggers(year).get("UNPROFITABLE_QUARTER") != month:
        return None
    rng = random.Random(f"COMPANY-{year}-UNPROFITABLE_QUARTER-cost-spike")
    return round(rng.uniform(UNPROFITABLE_QUARTER_COST_SPIKE_MIN, UNPROFITABLE_QUARTER_COST_SPIKE_MAX), -2)
