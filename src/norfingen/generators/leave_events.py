"""Long-absence periods per employee — certified (long) sick leave and
parental leave, Norwegian-style (foreldrepermisjon: a longer
primary-caregiver leave plus a shorter "fedrekvote" secondary-caregiver
quota).

Same pattern as client_events.py/company_events.py: state as a pure,
memoized function (employee_id) -> a fixed tuple of periods, not a mutable
ledger — the backfill runs as several separate OS processes and the live
cron is a third, none of which share memory, so the result must be
identical every time it's (re)computed from the same input (see the
client_events.py docstring for the full rationale).

Deliberately NOT gender-based: EmployeeSeed carries no gender field (and
adding one just to pick "maternity vs paternity" would be adding a whole
new dimension of data for one feature). Instead, every employee has an
independent, symmetric chance of drawing either leave archetype — this
models the two real Norwegian leave shapes (a long primary-caregiver leave,
a short secondary-caregiver quota) without asserting anything about a
specific (fictional) person's gender.

This only affects hour_entries (via hours_generator.generate_daily_hours)
for BILLABLE employees — the only ones who log hours at all (see
hours_generator.py's module docstring). Non-billable staff (Salg/Økonomi)
have no hour-level tracking in this project already; extending that is a
separate, bigger change, not attempted here.

Salary is untouched by any of this — salary_generator computes pay from
annual_salary/employment status only, independent of hours (see
hours_generator.py's Phase 6 note), which matches Norwegian practice:
the employer keeps paying salary through sick leave and parental leave
(and reclaims part of it from NAV) rather than the employee going unpaid."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from norfingen.models.hours import ActivityType
from norfingen.seed.roster import employee_by_id

# Chance a given employee experiences one long-term *certified* sick-leave
# block at some point during their tenure (on top of the short, self-certified
# single-day chance already rolled per-day in hours_generator.SICK_PROBABILITY).
LONG_SICK_LEAVE_PROBABILITY = 0.12
LONG_SICK_LEAVE_MIN_DAYS = 21  # ~3 weeks
LONG_SICK_LEAVE_MAX_DAYS = 84  # ~12 weeks

# Chance of one parental-leave event during tenure. Real-world uptake over a
# multi-year window for a small, mixed-age workforce is roughly this order of
# magnitude — not fitted to any specific statistic, just plausible.
PARENTAL_LEAVE_PROBABILITY = 0.18
MATERNITY_LEAVE_MIN_DAYS = 30 * 7  # ~30 weeks
MATERNITY_LEAVE_MAX_DAYS = 49 * 7  # ~49 weeks (100% dekningsgrad default)
PATERNITY_LEAVE_MIN_DAYS = 10 * 7  # ~10 weeks
PATERNITY_LEAVE_MAX_DAYS = 15 * 7  # ~15 weeks (fedrekvote)

# Don't place a leave block in an employee's first ~3 months (unrealistic to
# go on long leave immediately after starting), and cap how far into the
# future we place one so it stays within a plausible planning horizon.
MIN_TENURE_BEFORE_LEAVE_DAYS = 90
TENURE_HORIZON_DAYS = 365 * 8


@dataclass(frozen=True)
class LeavePeriod:
    start: date
    end: date  # inclusive
    activity_type: ActivityType

    def covers(self, on_date: date) -> bool:
        return self.start <= on_date <= self.end


@lru_cache(maxsize=None)
def employee_leave_periods(employee_id: int) -> tuple[LeavePeriod, ...]:
    """Deterministically derives 0-2 long-absence periods for one employee
    from their start_date alone (no wall-clock/"today" input — see module
    docstring for why). Seeded via random.Random(f"LEAVE-{employee_id}")
    (string seed, never hash() — see roster.py/company_events.py convention)."""
    employee = employee_by_id(employee_id)
    rng = random.Random(f"LEAVE-{employee_id}")

    window_start = employee.start_date + timedelta(days=MIN_TENURE_BEFORE_LEAVE_DAYS)
    window_end = employee.start_date + timedelta(days=TENURE_HORIZON_DAYS)
    if window_start >= window_end:
        return ()

    periods: list[LeavePeriod] = []

    if rng.random() < LONG_SICK_LEAVE_PROBABILITY:
        length = rng.randint(LONG_SICK_LEAVE_MIN_DAYS, LONG_SICK_LEAVE_MAX_DAYS)
        start = _random_start(rng, window_start, window_end, length)
        if start is not None:
            periods.append(LeavePeriod(start, start + timedelta(days=length - 1), ActivityType.SICK))

    if rng.random() < PARENTAL_LEAVE_PROBABILITY:
        if rng.random() < 0.5:
            activity_type = ActivityType.MATERNITY_LEAVE
            length = rng.randint(MATERNITY_LEAVE_MIN_DAYS, MATERNITY_LEAVE_MAX_DAYS)
        else:
            activity_type = ActivityType.PATERNITY_LEAVE
            length = rng.randint(PATERNITY_LEAVE_MIN_DAYS, PATERNITY_LEAVE_MAX_DAYS)
        start = _random_start(rng, window_start, window_end, length, avoid=periods)
        if start is not None:
            periods.append(LeavePeriod(start, start + timedelta(days=length - 1), activity_type))

    return tuple(sorted(periods, key=lambda p: p.start))


def _random_start(
    rng: random.Random,
    window_start: date,
    window_end: date,
    length: int,
    avoid: list[LeavePeriod] = (),
) -> date | None:
    """Picks a start date for a `length`-day block inside [window_start,
    window_end], retrying a few times if it collides with an already-placed
    period in `avoid`. Gives up (returns None) rather than looping forever —
    a missed leave event is harmless, an infinite loop isn't."""
    latest_start = window_end - timedelta(days=length - 1)
    if latest_start < window_start:
        return None
    span_days = (latest_start - window_start).days
    for _ in range(8):
        start = window_start + timedelta(days=rng.randint(0, span_days))
        end = start + timedelta(days=length - 1)
        if not any(start <= p.end and end >= p.start for p in avoid):
            return start
    return None


def active_leave_period(employee_id: int, on_date: date) -> LeavePeriod | None:
    """The one leave period (if any) covering `on_date` for this employee."""
    for period in employee_leave_periods(employee_id):
        if period.covers(on_date):
            return period
    return None
