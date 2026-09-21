"""Two more annual day-budgets, beyond the statutory VACATION —

- FLEX_LEAVE ("dager til avspasering" / dni na żądanie): 12 days/year,
  taken in blocks of at most 3 consecutive working days, with a mandatory
  16-day gap before the next block starts.
- CHILD_CARE_LEAVE ("omsorgsdager", sick-child care): 10 days/year, shorter
  blocks (1-2 days), no mandated gap — a sick child doesn't wait 16 days
  for the next one.

Same pattern as vacation.py: deterministic, memoized per (employee_id,
year), placed on days not already claimed by another leave type for the
same employee — checked in the order VACATION -> FLEX_LEAVE ->
CHILD_CARE_LEAVE, each avoiding everything placed before it."""

from __future__ import annotations

import random
from datetime import date, timedelta
from functools import lru_cache

from norfingen.generators.leave_events import employee_leave_periods
from norfingen.generators.vacation import employee_vacation_days

FLEX_LEAVE_ANNUAL_DAYS = 12
FLEX_LEAVE_MAX_CONSECUTIVE_DAYS = 3
FLEX_LEAVE_MIN_GAP_DAYS = 16

CHILD_CARE_LEAVE_ANNUAL_DAYS = 10
CHILD_CARE_LEAVE_MAX_CONSECUTIVE_DAYS = 2


def _is_working_day(d: date) -> bool:
    return d.weekday() < 5


def _place_day_budget(
    employee_id: int,
    year: int,
    seed_prefix: str,
    annual_days: int,
    max_consecutive_days: int,
    gap_days: int,
    is_free,
) -> tuple[date, ...]:
    """Walks forward through the year placing blocks of at most
    `max_consecutive_days` on free working days, jumping `gap_days` past
    the end of each placed block before looking for the next one. Stops
    early if the budget is exhausted or the year runs out — a shortfall
    (fewer than `annual_days` placed) is accepted, not worked around.

    `gap_days` is clamped to at least 1 here — a caller passing 0 (no
    *mandated* gap, e.g. CHILD_CARE_LEAVE) would otherwise let two
    back-to-back blocks silently merge into one longer run in the rendered
    calendar output, quietly breaking `max_consecutive_days`."""
    rng = random.Random(f"{seed_prefix}-{employee_id}-{year}")
    gap_days = max(gap_days, 1)
    placed: list[date] = []
    remaining = annual_days
    cursor = date(year, 1, 1)
    year_end = date(year, 12, 31)

    while remaining > 0 and cursor <= year_end:
        if not is_free(cursor):
            cursor += timedelta(days=1)
            continue

        block_len = min(rng.randint(1, max_consecutive_days), remaining)
        block: list[date] = []
        probe = cursor
        while len(block) < block_len and probe <= year_end and is_free(probe):
            block.append(probe)
            probe += timedelta(days=1)

        placed.extend(block)
        remaining -= len(block)
        cursor = block[-1] + timedelta(days=1 + gap_days)

    return tuple(placed)


@lru_cache(maxsize=None)
def employee_flex_leave_days(employee_id: int, year: int) -> tuple[date, ...]:
    other_leave = employee_leave_periods(employee_id)
    vacation = employee_vacation_days(employee_id, year)

    def is_free(d: date) -> bool:
        return _is_working_day(d) and d not in vacation and not any(p.covers(d) for p in other_leave)

    return _place_day_budget(
        employee_id, year, "FLEX",
        FLEX_LEAVE_ANNUAL_DAYS, FLEX_LEAVE_MAX_CONSECUTIVE_DAYS, FLEX_LEAVE_MIN_GAP_DAYS,
        is_free,
    )


@lru_cache(maxsize=None)
def employee_child_care_leave_days(employee_id: int, year: int) -> tuple[date, ...]:
    other_leave = employee_leave_periods(employee_id)
    vacation = employee_vacation_days(employee_id, year)
    flex = employee_flex_leave_days(employee_id, year)

    def is_free(d: date) -> bool:
        return (
            _is_working_day(d)
            and d not in vacation
            and d not in flex
            and not any(p.covers(d) for p in other_leave)
        )

    return _place_day_budget(
        employee_id, year, "CHILDCARE",
        CHILD_CARE_LEAVE_ANNUAL_DAYS, CHILD_CARE_LEAVE_MAX_CONSECUTIVE_DAYS, 0,
        is_free,
    )


def is_flex_leave_day(employee_id: int, on_date: date) -> bool:
    return on_date in employee_flex_leave_days(employee_id, on_date.year)


def is_child_care_leave_day(employee_id: int, on_date: date) -> bool:
    return on_date in employee_child_care_leave_days(employee_id, on_date.year)
