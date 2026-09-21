"""Long-absence periods per employee — certified (long) sick leave, parental
leave, and welfare/occasional leave, Norwegian-style.

Same pattern as client_events.py/company_events.py: state as a pure,
memoized function (employee_id) -> a fixed tuple of periods, not a mutable
ledger — the backfill runs as several separate OS processes and the live
cron is a third, none of which share memory, so the result must be
identical every time it's (re)computed from the same input (see the
client_events.py docstring for the full rationale).

PARENTAL_LEAVE is deliberately NOT gender-based: EmployeeSeed carries no
gender field (and adding one just to pick "maternity vs paternity" would be
a whole new dimension of data for one feature). Every employee has the same
independent, symmetric chance of the event each year they're employed. A
triggered event places a primary block (20-39 weeks) for that employee AND
a separate ~3-month "fedrekvote" block for a DIFFERENT, randomly chosen
employee — together capped at the statutory 52 weeks — simulating the
second parent without asserting who's the mother and who's the father (see
_father_quota_assignments(), a company-wide pass, not a per-employee one,
since it writes into someone ELSE's periods).

This only affects hour_entries for employees who log hours at all — see
hours_generator.py's NON_BILLABLE_OVERRIDES (E05 stays fully excluded, as
before this feature existed) and, since the "all departments" prompt,
Salg/Okonomi too (vacation.py + hours_generator.py wire this up).

Salary is untouched by any of this — salary_generator computes pay from
annual_salary/employment status only, independent of hours (see
hours_generator.py's Phase 6 note), which matches Norwegian practice: the
employer keeps paying salary through sick leave and parental leave (and
reclaims part of it from NAV) rather than the employee going unpaid. VACATION
is the one exception — it's covered by feriepenger, not ordinary salary; see
models/hours.py's ActivityType.VACATION comment and seed/payroll.py's
calc_june_salary, which already models this independently of hour_entries."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from norfingen.models.hours import ActivityType
from norfingen.seed.roster import employee_by_id

# Long-term *certified* sick leave (on top of hours_generator.SICK_PROBABILITY,
# which models short, self-certified single-day absences) — rolled once over
# an employee's whole tenure horizon, not per year (a certified long absence
# is rare enough that "at most one in ~8 years" is a reasonable model; the
# per-day short-absence roll already covers the common case).
LONG_SICK_LEAVE_PROBABILITY = 0.12
LONG_SICK_LEAVE_MIN_DAYS = 21  # ~3 weeks
LONG_SICK_LEAVE_MAX_DAYS = 84  # ~12 weeks

# Parental leave (foreldrepermisjon) — rolled independently EVERY year an
# employee is active, not once per tenure, per the spec ("~1 case/year across
# a 17-person team"). A 2-year cooldown after a triggered event prevents the
# same employee going on leave again immediately. Total statutory cap is 52
# weeks; the primary block below is capped at 39 (52 - the 13-week father's
# quota placed separately, see FATHER_QUOTA_*).
PARENTAL_LEAVE_ANNUAL_PROBABILITY = 0.06
PARENTAL_LEAVE_MIN_WEEKS = 20
PARENTAL_LEAVE_MAX_WEEKS = 39
PARENTAL_LEAVE_COOLDOWN_YEARS = 2

# "Fedrekvote" — ~3 months reserved for the second parent, at a different
# employee, placed right after the primary block ends (see
# _father_quota_assignments()).
FATHER_QUOTA_MIN_WEEKS = 12
FATHER_QUOTA_MAX_WEEKS = 14

# Welfare/occasional leave (velferdspermisjon — a death in the family, a
# house move, a child's first day of school, etc.) — short, and unlike
# parental leave, can recur most years without a cooldown.
WELFARE_LEAVE_ANNUAL_PROBABILITY = 0.15
WELFARE_LEAVE_MIN_DAYS = 1
WELFARE_LEAVE_MAX_DAYS = 3

# Don't place any leave block in an employee's first ~3 months (unrealistic
# to go on long leave immediately after starting). How far into the future
# we precompute periods for — a plausible planning horizon, not tied to
# "today" (see module docstring for why: no wall-clock input allowed here).
MIN_TENURE_BEFORE_LEAVE_DAYS = 90
TENURE_HORIZON_YEARS = 8


@dataclass(frozen=True)
class LeavePeriod:
    start: date
    end: date  # inclusive
    activity_type: ActivityType

    def covers(self, on_date: date) -> bool:
        return self.start <= on_date <= self.end


@lru_cache(maxsize=None)
def _own_periods(employee_id: int) -> tuple[LeavePeriod, ...]:
    """This employee's OWN rolled periods (long SICK, primary PARENTAL_LEAVE,
    WELFARE_LEAVE) — everything derivable from just their own start_date, no
    wall-clock/"today" input (see module docstring). Deliberately excludes
    father's-quota blocks assigned to them by someone ELSE's parental-leave
    event (see _father_quota_assignments()) — employee_leave_periods() below
    merges those in. Kept separate to avoid a circular dependency: the
    company-wide father-quota pass needs to read every employee's OWN
    primary periods without triggering the merge itself."""
    employee = employee_by_id(employee_id)
    periods: list[LeavePeriod] = []

    tenure_start = employee.start_date + timedelta(days=MIN_TENURE_BEFORE_LEAVE_DAYS)
    horizon_end = employee.start_date + timedelta(days=365 * TENURE_HORIZON_YEARS)

    _roll_long_sick_leave(employee_id, tenure_start, horizon_end, periods)
    _roll_parental_leave(employee_id, tenure_start, horizon_end, periods)
    _roll_welfare_leave(employee_id, employee.start_date, horizon_end, periods)

    return tuple(sorted(periods, key=lambda p: p.start))


@lru_cache(maxsize=None)
def _father_quota_assignments() -> dict[int, tuple[LeavePeriod, ...]]:
    """Company-wide pass (not per-employee — it writes into OTHER employees'
    periods): for every employee's own, already-rolled primary PARENTAL_LEAVE
    block, assigns a ~3-month "fedrekvote" block, starting right after it
    ends, to a different, randomly chosen employee active at that time.
    E05 is excluded as a candidate (same permanent exclusion as everywhere
    else in hour tracking — duplicated locally since this module can't
    import hours_generator without creating a cycle)."""
    from norfingen.seed.roster import EMPLOYEES

    assignments: dict[int, list[LeavePeriod]] = {}
    for source in EMPLOYEES:
        source_id = int(source.number[1:])
        for period in _own_periods(source_id):
            if period.activity_type != ActivityType.PARENTAL_LEAVE:
                continue
            candidates = [
                e for e in EMPLOYEES
                if int(e.number[1:]) not in (source_id, 5) and e.start_date <= period.start
            ]
            if not candidates:
                continue
            rng = random.Random(f"LEAVE-FATHER-{source_id}-{period.start.isoformat()}")
            father = rng.choice(candidates)
            father_id = int(father.number[1:])
            weeks = rng.randint(FATHER_QUOTA_MIN_WEEKS, FATHER_QUOTA_MAX_WEEKS)
            length = weeks * 7
            father_start = period.end + timedelta(days=1)
            father_period = LeavePeriod(father_start, father_start + timedelta(days=length - 1), ActivityType.PARENTAL_LEAVE)
            assignments.setdefault(father_id, []).append(father_period)

    return {emp_id: tuple(periods) for emp_id, periods in assignments.items()}


@lru_cache(maxsize=None)
def employee_leave_periods(employee_id: int) -> tuple[LeavePeriod, ...]:
    """This employee's full set of long-absence periods: their own (long
    SICK, primary PARENTAL_LEAVE, WELFARE_LEAVE) plus any father's-quota
    block assigned to them by a different employee's parental-leave event.
    A father's-quota block that collides with something already in this
    employee's own periods is dropped (not shifted) — a missed assignment is
    harmless, same policy as _random_start()'s give-up-after-retries."""
    own = _own_periods(employee_id)
    incoming = _father_quota_assignments().get(employee_id, ())

    merged = list(own)
    for candidate in incoming:
        if not any(candidate.start <= p.end and candidate.end >= p.start for p in merged):
            merged.append(candidate)

    return tuple(sorted(merged, key=lambda p: p.start))


def _roll_long_sick_leave(
    employee_id: int, tenure_start: date, horizon_end: date, periods: list[LeavePeriod]
) -> None:
    if tenure_start >= horizon_end:
        return
    rng = random.Random(f"LEAVE-SICK-{employee_id}")
    if rng.random() < LONG_SICK_LEAVE_PROBABILITY:
        length = rng.randint(LONG_SICK_LEAVE_MIN_DAYS, LONG_SICK_LEAVE_MAX_DAYS)
        start = _random_start(rng, tenure_start, horizon_end, length, periods)
        if start is not None:
            periods.append(LeavePeriod(start, start + timedelta(days=length - 1), ActivityType.SICK))


def _roll_parental_leave(
    employee_id: int, tenure_start: date, horizon_end: date, periods: list[LeavePeriod]
) -> None:
    last_start_year: int | None = None
    for year in range(tenure_start.year, horizon_end.year + 1):
        year_start = max(date(year, 1, 1), tenure_start)
        year_end = min(date(year, 12, 31), horizon_end)
        if year_start > year_end:
            continue
        if last_start_year is not None and year - last_start_year < PARENTAL_LEAVE_COOLDOWN_YEARS:
            continue

        rng = random.Random(f"LEAVE-PARENTAL-{employee_id}-{year}")
        if rng.random() < PARENTAL_LEAVE_ANNUAL_PROBABILITY:
            weeks = rng.randint(PARENTAL_LEAVE_MIN_WEEKS, PARENTAL_LEAVE_MAX_WEEKS)
            length = weeks * 7
            start = _random_start(rng, year_start, year_end, length, periods)
            if start is not None:
                periods.append(LeavePeriod(start, start + timedelta(days=length - 1), ActivityType.PARENTAL_LEAVE))
                last_start_year = year


def _roll_welfare_leave(
    employee_id: int, employee_start: date, horizon_end: date, periods: list[LeavePeriod]
) -> None:
    for year in range(employee_start.year, horizon_end.year + 1):
        year_start = max(date(year, 1, 1), employee_start)
        year_end = min(date(year, 12, 31), horizon_end)
        if year_start > year_end:
            continue

        rng = random.Random(f"LEAVE-WELFARE-{employee_id}-{year}")
        if rng.random() < WELFARE_LEAVE_ANNUAL_PROBABILITY:
            length = rng.randint(WELFARE_LEAVE_MIN_DAYS, WELFARE_LEAVE_MAX_DAYS)
            start = _random_start(rng, year_start, year_end, length, periods)
            if start is not None:
                periods.append(LeavePeriod(start, start + timedelta(days=length - 1), ActivityType.WELFARE_LEAVE))


def _random_start(
    rng: random.Random,
    window_start: date,
    window_end: date,
    length: int,
    avoid: list[LeavePeriod],
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
