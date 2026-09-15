"""Phase 7, Task 2 — random client-level events (life events).

A DELIBERATE ARCHITECTURE CHANGE relative to Task 2d: the prompt assumed
"in-memory state during the backfill, a single sequential run is enough —
check whether the backfill actually runs sequentially month by month."
Checked — NOT quite: the backfill in this repo is in practice TWO SEPARATE
process runs invoked manually one after the other (`run_backfill.py --mode
monthly`, then `--mode daily`, see SESSION_HANDOFF.md section 5), and
`--mode daily` and the live cron (`run_daily.py`,
`.github/workflows/daily.yml`) share the very same `run_daily()` function,
called once per process/day — no mutable state object passed in "from
outside" would survive between these runs.

Solution: `customer_event_state_asof()` is a PURE, memoized function
(customer, year, month) -> cumulative state — it recursively advances month
by month from onboarding, cached via functools.lru_cache (each
(customer, year, month) triple is computed once for the entire lifetime of
the process, regardless of who asks for it and when). This makes it work
correctly and identically in all three call sites (the monthly loop, the
daily loop, the live cron) with no explicit state hand-off between them and
no new column/table in Supabase (Task 2d) — a stronger version of the same
determinism requirement, not a violation of it."""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from norfingen.seed.roster import CustomerSeed, customer_by_number, get_customer_services

CLIENT_LIFE_EVENTS: dict[str, dict] = {
    "OFFER_EXPANSION": {
        "monthly_probability": 0.004,
        "eligible_segments": ("Mid-market", "SMB"),
        "effect": "add_service",
        "duration_months": None,
    },
    "OFFER_REDUCTION": {
        "monthly_probability": 0.003,
        "eligible_segments": ("Enterprise", "Mid-market"),
        "effect": "remove_service",
        "duration_months": None,
    },
    "TEMPORARY_HARDSHIP": {
        "monthly_probability": 0.004,
        "eligible_segments": ("Enterprise", "Mid-market", "SMB"),
        "effect": "reduced_volume_and_late_payment",
        "duration_months": (2, 4),
    },
    "BANKRUPTCY": {
        "monthly_probability": 0.0008,
        "eligible_segments": ("SMB",),
        "effect": "immediate_churn_and_writeoff",
        "duration_months": None,
    },
    "ONE_OFF_LARGE_PROJECT": {
        "monthly_probability": 0.005,
        "eligible_segments": ("Enterprise", "Mid-market"),
        "effect": "large_s04_order",
        "duration_months": None,
    },
}

# OFFER_EXPANSION — a service "one tier up" from the standard segment bundle
# (roster.SEGMENT_SERVICE_BUNDLES). Enterprise already has the full
# S01+S02+S03 package — deliberately absent here, consistent with
# eligible_segments above.
#
# A DELIBERATE CORRECTION relative to the naive "next tier up" (SMB->S02,
# Mid-market->S03): S02 has roster.Service.availability=ENTERPRISE_MID (no
# base_price_smb — would crash when pricing for SMB), S03 has
# availability=ENTERPRISE_ONLY (no base_price_mid) — both would violate
# existing service-catalog constraints. S04 (Consulting and digitalization)
# has availability=ALL and pricing for every segment — the only service
# both segments can actually legally "buy up" as a permanent, additional
# subscription line, independent of the occasional
# should_generate_extra_consulting/ONE_OFF_LARGE_PROJECT orders.
EXPANSION_SERVICE_BY_SEGMENT: dict[str, str] = {
    "SMB": "S04",
    "Mid-market": "S04",
}

# OFFER_REDUCTION — services eligible for removal, never S01 (Task 2c).
# Mid-market has only one sensible option (S02); Enterprise picks
# deterministically between S02/S03 with a separate rng (see
# _advance_one_month).
REDUCIBLE_SERVICES_BY_SEGMENT: dict[str, tuple[str, ...]] = {
    "Mid-market": ("S02",),
    "Enterprise": ("S02", "S03"),
}

HARDSHIP_TICKET_REDUCTION_MIN = 0.40  # "reduce volume by 40-60%" — multiplier on remaining hours: 1-0.6=0.40 .. 1-0.4=0.60
HARDSHIP_TICKET_REDUCTION_MAX = 0.60

# Elevated bad-debt/OVERDUE threshold during an active customer crisis — the
# task didn't give a concrete value ("raise the threshold"), calibrated to a
# clearly elevated but not absurd level: 5x the normal
# order_generator.BAD_DEBT_PROBABILITY (0.02 -> 0.10).
HARDSHIP_BAD_DEBT_MULTIPLIER = 5.0

LARGE_PROJECT_HOURS_MIN = 80.0
LARGE_PROJECT_HOURS_MAX = 200.0


@dataclass(frozen=True)
class CustomerEventState:
    """A customer's cumulative state at the end of a given (year, month) —
    see customer_event_state_asof(). Frozen — _advance_one_month always
    returns a NEW instance instead of mutating, so the result cached by
    lru_cache can never accidentally be modified by the caller."""

    added_service: Optional[str] = None
    removed_service: Optional[str] = None
    hardship_active_until: Optional[tuple[int, int]] = None  # (year, month) — the last month of the crisis, inclusive
    hardship_ticket_multiplier: Optional[float] = None  # 0.40-0.60, rolled once at the start of the window, fixed for its whole duration
    churned: bool = False
    churn_year_month: Optional[tuple[int, int]] = None
    triggered_this_month: Optional[str] = None  # the event code, if something fired EXACTLY in the (year, month) of this state


_EMPTY_STATE = CustomerEventState()


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + n
    return total // 12, total % 12 + 1


def roll_client_events(customer: CustomerSeed, year: int, month: int, prev_state: CustomerEventState) -> Optional[str]:
    """Deterministic roll — a single rng seeded with
    customer_number+year+month, iterated in catalog order (as in Task 2b).
    A deliberate deviation from the given pseudocode: instead of checking
    `active_event == event_code` (a single String field that doesn't capture
    "permanent" OFFER_EXPANSION/REDUCTION changes coexisting with a later
    crisis), permanent effects (with no duration_months) are ruled out once
    and for all by the state itself (added_service/removed_service already
    set -> ineligible for future months), and the only truly "active,
    blocking-new-rolls" state is TEMPORARY_HARDSHIP (the only one with a
    defined duration_months) — checked BEFORE calling this function, see
    _advance_one_month. The first hit in catalog order wins (a customer goes
    through one event per month)."""
    rng = random.Random(f"{customer.number}-{year}-{month}-events")
    for event_code, event_def in CLIENT_LIFE_EVENTS.items():
        if customer.segment not in event_def["eligible_segments"]:
            continue
        if event_code == "OFFER_EXPANSION" and prev_state.added_service is not None:
            continue
        if event_code == "OFFER_REDUCTION" and prev_state.removed_service is not None:
            continue
        if rng.random() < event_def["monthly_probability"]:
            return event_code
    return None


def _advance_one_month(customer: CustomerSeed, year: int, month: int, prev_state: CustomerEventState) -> CustomerEventState:
    if prev_state.churned:
        return CustomerEventState(
            added_service=prev_state.added_service, removed_service=prev_state.removed_service,
            churned=True, churn_year_month=prev_state.churn_year_month, triggered_this_month=None,
        )

    hardship_until = prev_state.hardship_active_until
    if hardship_until is not None and (year, month) > hardship_until:
        hardship_until = None  # the crisis expired before this month

    if hardship_until is not None:
        # customer in the middle of an active crisis — don't roll new events
        # (2d: one "active" state at a time)
        return CustomerEventState(
            added_service=prev_state.added_service, removed_service=prev_state.removed_service,
            hardship_active_until=hardship_until, hardship_ticket_multiplier=prev_state.hardship_ticket_multiplier,
            triggered_this_month=None,
        )

    code = roll_client_events(customer, year, month, prev_state)
    if code is None:
        return CustomerEventState(added_service=prev_state.added_service, removed_service=prev_state.removed_service)

    effect_rng = random.Random(f"{customer.number}-{year}-{month}-{code}-effect")

    if code == "OFFER_EXPANSION":
        new_service = EXPANSION_SERVICE_BY_SEGMENT[customer.segment]
        return CustomerEventState(added_service=new_service, removed_service=prev_state.removed_service, triggered_this_month=code)

    if code == "OFFER_REDUCTION":
        options = REDUCIBLE_SERVICES_BY_SEGMENT[customer.segment]
        removed = effect_rng.choice(options)
        return CustomerEventState(added_service=prev_state.added_service, removed_service=removed, triggered_this_month=code)

    if code == "TEMPORARY_HARDSHIP":
        duration_min, duration_max = CLIENT_LIFE_EVENTS[code]["duration_months"]
        duration = effect_rng.randint(duration_min, duration_max)
        end_year, end_month = _add_months(year, month, duration - 1)
        reduction_multiplier = effect_rng.uniform(HARDSHIP_TICKET_REDUCTION_MIN, HARDSHIP_TICKET_REDUCTION_MAX)
        return CustomerEventState(
            added_service=prev_state.added_service, removed_service=prev_state.removed_service,
            hardship_active_until=(end_year, end_month), hardship_ticket_multiplier=reduction_multiplier,
            triggered_this_month=code,
        )

    if code == "BANKRUPTCY":
        return CustomerEventState(
            added_service=prev_state.added_service, removed_service=prev_state.removed_service,
            churned=True, churn_year_month=(year, month), triggered_this_month=code,
        )

    if code == "ONE_OFF_LARGE_PROJECT":
        return CustomerEventState(added_service=prev_state.added_service, removed_service=prev_state.removed_service, triggered_this_month=code)

    raise AssertionError(f"Unhandled event code: {code!r}")  # pragma: no cover


@lru_cache(maxsize=None)
def customer_event_state_asof(customer_number: str, year: int, month: int) -> CustomerEventState:
    """A customer's cumulative event state at the end of (year, month) — a
    pure function, cached (see the module docstring). Takes customer_number
    (str), not CustomerSeed — the dataclass is frozen, but lru_cache still
    requires hashable arguments, and the number is the natural key.

    Phase 7, Task 2 — pattern D (K06, the only consulting customer without a
    fixed service bundle, see roster.py/order_generator.py "separate
    logic") is deliberately excluded: OFFER_EXPANSION/REDUCTION have nothing
    to apply to (K06 never goes through build_order_lines at all), and
    BANKRUPTCY would be dead code (the pattern=="D" branch in
    generate_monthly_orders doesn't check event_aware_is_customer_active) —
    wiring this up would require redesigning K06's separate logic, out of
    scope for this task. K06 never rolls any event."""
    customer = customer_by_number(customer_number)
    if customer.order_pattern not in ("A", "B", "C"):
        return _EMPTY_STATE
    onboarding = customer.onboarding_date
    if (year, month) < (onboarding.year, onboarding.month):
        return _EMPTY_STATE

    if (year, month) == (onboarding.year, onboarding.month):
        prev_state = _EMPTY_STATE
    else:
        prev_year, prev_month = _prev_month(year, month)
        prev_state = customer_event_state_asof(customer_number, prev_year, prev_month)

    return _advance_one_month(customer, year, month, prev_state)


def effective_customer_services(customer: CustomerSeed, state: CustomerEventState) -> list[str]:
    """get_customer_services(), but with the permanent effects of
    OFFER_EXPANSION/OFFER_REDUCTION applied (Task 2c)."""
    services = list(get_customer_services(customer))
    if state.added_service and state.added_service not in services:
        services.append(state.added_service)
    if state.removed_service and state.removed_service in services:
        services.remove(state.removed_service)
    return services


def event_aware_is_customer_active(customer: CustomerSeed, on_date) -> bool:
    """roster.is_customer_active(), extended with BANKRUPTCY — a customer
    stops being active starting the month AFTER the one in which the event
    fired (the trigger month still generates its final, written-off
    invoice, see order_generator)."""
    from norfingen.seed.roster import is_customer_active  # local import — avoids a module-level cycle

    if not is_customer_active(customer, on_date):
        return False
    state = customer_event_state_asof(customer.number, on_date.year, on_date.month)
    if state.churned and state.churn_year_month != (on_date.year, on_date.month):
        return False
    return True


def hardship_ticket_multiplier_for(customer_number: str, on_date) -> float:
    """Phase 7, Task 2c — the support-ticket-volume multiplier
    (hours_generator) for a customer in an active TEMPORARY_HARDSHIP window
    on a given date; 1.0 (no reduction) outside the crisis window."""
    state = customer_event_state_asof(customer_number, on_date.year, on_date.month)
    if state.hardship_active_until is None:
        return 1.0
    return state.hardship_ticket_multiplier
