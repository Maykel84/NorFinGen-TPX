"""Phase 7, Task 3 — random company-level events.

The same pattern as client_events.py (Task 2): state as a pure, memoized
function (year, month) -> cumulative state, not a mutable ledger — for the
same reasons (the backfill is two separate processes, the live cron is a
third, see the client_events.py docstring). Here the only element that
actually needs memory beyond one month is SUPPLIER_RENEGOTIATION
("permanent from this month on") — EQUIPMENT_INVESTMENT and
UNPROFITABLE_QUARTER are both fully derivable from roll_company_events(year)
alone (Task 3b), with no state at all."""

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

# "a one-off opex cost increase" (Task 3c) — no amount was given in the task
# (only a magnitude_range assigned to tickets/volume, see below), calibrated
# independently: the order of magnitude of one "rough month" of an unusual
# cost, not destabilizing to annual margin (~2.2M NOK opex/year across ~9
# accounts — see SESSION_HANDOFF.md).
UNPROFITABLE_QUARTER_COST_SPIKE_MIN = 40_000.0
UNPROFITABLE_QUARTER_COST_SPIKE_MAX = 120_000.0
ACCOUNT_UNEXPECTED_COST = 7790  # NS4102 "Annen driftskostnad" — a new account, unused elsewhere in this repo


def roll_company_events(year: int) -> list[dict]:
    """Task 3b — exactly per the given pseudocode."""
    rng = random.Random(f"COMPANY-{year}-events")
    triggered = []
    for event_code, event_def in COMPANY_LIFE_EVENTS.items():
        if rng.random() < event_def["yearly_probability"]:
            month = rng.randint(1, 12)
            triggered.append({"code": event_code, "year": year, "month": month})
    return triggered


@lru_cache(maxsize=None)
def _year_triggers(year: int) -> dict[str, int]:
    """code -> month (1-12), a memoized wrapper around roll_company_events —
    avoids re-rolling (and the resulting unnecessary work) on every query
    for a single month of this year."""
    return {ev["code"]: ev["month"] for ev in roll_company_events(year)}


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


@dataclass(frozen=True)
class CompanyEventState:
    """supplier_number -> cumulative cost multiplier (1.0 = unchanged) after
    all SUPPLIER_RENEGOTIATION events through (year, month) inclusive.
    Successive renegotiations of the SAME supplier in different years
    compound (successive contract negotiations) — a deliberate choice, the
    task doesn't specify."""

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
    """Task 3c — a supplier's cost multiplier after any renegotiations
    (1.0 = unchanged). Wired into supplier_invoice_generator BEFORE the net
    amount is rounded."""
    return company_event_state_asof(year, month).supplier_multipliers.get(supplier_number, 1.0)


def equipment_investment_trigger(year: int, month: int) -> Optional[float]:
    """Task 3c — returns the rolled amount (80k-250k) if EQUIPMENT_INVESTMENT
    fired in (year, month) of this year, otherwise None."""
    if _year_triggers(year).get("EQUIPMENT_INVESTMENT") != month:
        return None
    rng = random.Random(f"COMPANY-{year}-EQUIPMENT_INVESTMENT-effect")
    amount_min, amount_max = COMPANY_LIFE_EVENTS["EQUIPMENT_INVESTMENT"]["amount_range"]
    return round(rng.uniform(amount_min, amount_max), 2)


def unprofitable_quarter_ticket_multiplier(year: int, month: int) -> float:
    """Task 3c — the ticket-volume multiplier (hours_generator), active for
    the WHOLE quarter containing the rolled UNPROFITABLE_QUARTER month (not
    just that one month) — 1.0 outside the window."""
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
    """Task 3c — "a one-off opex cost increase": returns the rolled amount
    (UNPROFITABLE_QUARTER_COST_SPIKE_MIN..MAX) if (year, month) is EXACTLY
    the rolled trigger month (not the whole quarter — this is one-off,
    unlike the ticket reduction), otherwise None."""
    if _year_triggers(year).get("UNPROFITABLE_QUARTER") != month:
        return None
    rng = random.Random(f"COMPANY-{year}-UNPROFITABLE_QUARTER-cost-spike")
    return round(rng.uniform(UNPROFITABLE_QUARTER_COST_SPIKE_MIN, UNPROFITABLE_QUARTER_COST_SPIKE_MAX), -2)
