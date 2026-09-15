"""Norwegian B2B seasonal patterns (Phase 7, Task 1) — company-wide level.

Pure multipliers with no randomness (deterministic functions of
month/segment), used by other generators to modulate already-existing
randomness (hours_generator.generate_daily_support_hours,
order_generator.should_generate_extra_consulting) instead of adding parallel
mechanisms.

There is no state or RNG here — these functions don't roll anything
themselves, they only scale existing thresholds/ranges at the call site.
This preserves determinism (random.Random(string) in the calling code)
unchanged."""

from __future__ import annotations


def fellesferie_activity_multiplier(month: int) -> float:
    """July: ~50% of the normal volume of new support tickets and pace of
    purchasing decisions. Does not affect already-signed S01/S02/S03
    subscriptions (they invoice normally — see order_generator, A/B/C
    subscriptions are not scaled by this multiplier at all)."""
    if month == 7:
        return 0.5
    return 1.0


def q4_budget_flush_multiplier(month: int, customer_segment: str) -> float:
    """November-December: elevated probability of extra S04 orders for
    Enterprise/Mid-market, on top of the standard seasonality already
    present in the Phase 2 extra-consulting mechanism (Q2/Q4 in
    order_generator.EXTRA_CONSULTING_MONTHS)."""
    if month in (11, 12) and customer_segment in ("Enterprise", "Mid-market"):
        return 1.4
    return 1.0


def january_new_initiative_boost(month: int) -> float:
    """January: a slightly elevated probability of new S02 projects (new IT
    initiatives for the new budget year).

    NOTE — deliberately NOT WIRED UP yet (Phase 7, Task 1c): the codebase
    currently has no discrete "new S02 project" mechanism analogous to
    should_generate_extra_consulting (S02 is sold exclusively as part of the
    fixed segment bundle — roster.get_customer_services — not as a separate
    order). Wiring up this multiplier would first require designing such a
    mechanism, which is out of scope for Task 1 — see SESSION_HANDOFF.md."""
    return 1.2 if month == 1 else 1.0
