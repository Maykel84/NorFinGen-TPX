"""Phase 7b — the 2020 macroeconomic shock (COVID-19).

ARCHITECTURAL DIFFERENCE relative to client_events.py/company_events.py/
seasonality.py: this event is **DETERMINISTICALLY PLANTED in a specific
year**, not rolled. `random.Random(string)` is NOT used here at all —
there's nothing to roll, because this is a deliberately hardcoded historical
fact (the real COVID-19 shock in Norway, March-June 2020), not a probability
space. A deliberate distinction from the rest of the Phase 7 catalog — see
also SESSION_HANDOFF.md, Phase 7b.

The scope is deliberately limited to 2020 — it does not touch the mature
years (2023-2026, the 5.5-9% safety threshold) in any way."""

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
    """Task 1b — applies the macro shock on top of already-existing
    multipliers (fellesferie, UNPROFITABLE_QUARTER), multiplicatively, not
    replacing them. Applies to ALL active customers simultaneously (not a
    per-customer roll like TEMPORARY_HARDSHIP) — the key difference:
    MACRO_SHOCK is a market-wide shock, not a single company's situation."""
    if _is_covid_window(year, month):
        return base_multiplier * MACRO_SHOCK_EVENTS["COVID_2020"]["ticket_volume_multiplier"]
    return base_multiplier


def extra_consulting_shock_multiplier(year: int, month: int) -> float:
    """Task 1d — suppresses should_generate_extra_consulting (Phase 2)
    within the COVID window: threshold x 0.3 (only 30% of the usual
    chance). 1.0 outside the window — multiplies with
    q4_budget_flush_multiplier (Phase 7a), does not replace it."""
    if _is_covid_window(year, month):
        return MACRO_SHOCK_EVENTS["COVID_2020"]["extra_consulting_suppression"]
    return 1.0


def payment_delay_adjusted_bad_debt(base_probability: float, base_written_off_share: float,
                                     year: int, month: int) -> tuple[float, float]:
    """Task 1e — raises the probability of OVERDUE (payment_delay_multiplier),
    but keeps the ABSOLUTE probability of WRITTEN_OFF exactly at its normal
    level (payment delay != a wave of bankruptcies). Returns
    (bad_debt_probability, written_off_share) to pass straight into
    order_generator.determine_order_status.

    The math: the normal P(WRITTEN_OFF) = base_probability *
    base_written_off_share stays UNTOUCHED; only P(OVERDUE) =
    base_probability*(1-base_written_off_share) grows by
    xpayment_delay_multiplier. Both are converted back into
    (bad_debt_probability, written_off_share), because
    determine_order_status operates in that parametrization (one
    rng.random() < bad_debt_probability, then a second
    rng.random() < written_off_share)."""
    if not _is_covid_window(year, month):
        return base_probability, base_written_off_share

    multiplier = MACRO_SHOCK_EVENTS["COVID_2020"]["payment_delay_multiplier"]
    normal_written_off_abs = base_probability * base_written_off_share
    normal_overdue_abs = base_probability * (1 - base_written_off_share)
    elevated_overdue_abs = normal_overdue_abs * multiplier

    adjusted_bad_debt_probability = elevated_overdue_abs + normal_written_off_abs
    adjusted_written_off_share = normal_written_off_abs / adjusted_bad_debt_probability
    return adjusted_bad_debt_probability, adjusted_written_off_share
