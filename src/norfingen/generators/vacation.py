"""Statutory annual vacation (ferie) — 25 working days/year per full-time
employee, per Norwegian law (ferieloven), placed with a realistic shape:
a long contiguous "fellesferie" block in July, shorter clusters around
Easter and Christmas, the rest scattered through the year.

Deterministic and memoized per (employee_id, year), same pattern as
leave_events.py — a pure function of static inputs, no "today". Does NOT
import from hours_generator.py (hours_generator imports THIS, not the other
way around, to avoid a cycle) — hence the tiny local _is_working_day/
_working_days_in_range helpers instead of reusing hours_generator's.

Placement deliberately avoids days already claimed by
leave_events.employee_leave_periods() for the same employee (you don't
"take vacation" on top of a day you're already on sick/parental leave) — so
an employee who spends most of a year on PARENTAL_LEAVE will end up with
FEWER than their prorated target of placed vacation days that year (there's
nowhere left to put them). This is accepted, not worked around further."""

from __future__ import annotations

import random
from datetime import date, timedelta
from functools import lru_cache

from norfingen.generators.leave_events import employee_leave_periods
from norfingen.seed.roster import employee_by_id

FULL_YEAR_VACATION_DAYS = 25
JULY_BLOCK_SHARE = 0.6  # ~15 of 25 days as one contiguous "fellesferie" block
EASTER_LOOKBACK_DAYS = 7  # the working week immediately before Easter Sunday
CHRISTMAS_WINDOW_START_DAY = 15  # December 15 - 31


def _is_working_day(d: date) -> bool:
    return d.weekday() < 5


def _working_days_in_range(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        if _is_working_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm (computus) — exact for any Gregorian year."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = ((h + m - 7 * n + 114) % 31) + 1
    return date(year, month, day)


def _target_vacation_days(employee_id: int, year: int) -> int:
    """25/year for a full calendar year of employment, prorated by the
    fraction of the year actually employed (this project's EmployeeSeed has
    no termination date, so the only partial-year case is a mid-year hire)."""
    employee = employee_by_id(employee_id)
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    active_from = max(employee.start_date, year_start)
    if active_from > year_end:
        return 0
    active_days = (year_end - active_from).days + 1
    calendar_days = (year_end - year_start).days + 1
    return round(FULL_YEAR_VACATION_DAYS * active_days / calendar_days)


@lru_cache(maxsize=None)
def employee_vacation_days(employee_id: int, year: int) -> tuple[date, ...]:
    """This employee's VACATION days for one calendar year — a tuple of
    dates, sized at most `_target_vacation_days()` (less if long-absence
    periods crowd out the available room, see module docstring)."""
    target = _target_vacation_days(employee_id, year)
    if target <= 0:
        return ()

    other_leave = employee_leave_periods(employee_id)

    def is_free(d: date) -> bool:
        return _is_working_day(d) and not any(p.covers(d) for p in other_leave)

    rng = random.Random(f"VACATION-{employee_id}-{year}")
    placed: set[date] = set()

    # 1) fellesferie — one contiguous block in July
    july_target = round(target * JULY_BLOCK_SHARE)
    july_days = [d for d in _working_days_in_range(date(year, 7, 1), date(year, 7, 31)) if is_free(d)]
    if july_days and july_target > 0:
        block_len = min(july_target, len(july_days))
        max_offset = len(july_days) - block_len
        offset = rng.randint(0, max_offset) if max_offset > 0 else 0
        placed.update(july_days[offset:offset + block_len])

    # 2) a short block the week before Easter
    remaining = target - len(placed)
    if remaining > 0:
        easter = _easter_sunday(year)
        window_start = easter - timedelta(days=EASTER_LOOKBACK_DAYS)
        easter_days = [
            d for d in _working_days_in_range(window_start, easter - timedelta(days=1))
            if is_free(d) and d not in placed
        ]
        block_len = min(rng.randint(2, 4), remaining, len(easter_days))
        if block_len > 0:
            offset = rng.randint(0, len(easter_days) - block_len)
            placed.update(easter_days[offset:offset + block_len])

    # 3) a short block around Christmas
    remaining = target - len(placed)
    if remaining > 0:
        christmas_days = [
            d for d in _working_days_in_range(date(year, 12, CHRISTMAS_WINDOW_START_DAY), date(year, 12, 31))
            if is_free(d) and d not in placed
        ]
        block_len = min(rng.randint(2, 4), remaining, len(christmas_days))
        if block_len > 0:
            offset = rng.randint(0, len(christmas_days) - block_len)
            placed.update(christmas_days[offset:offset + block_len])

    # 4) scatter whatever's left across the rest of the year
    remaining = target - len(placed)
    if remaining > 0:
        pool = [d for d in _working_days_in_range(date(year, 1, 1), date(year, 12, 31)) if is_free(d) and d not in placed]
        rng.shuffle(pool)
        placed.update(pool[:remaining])

    return tuple(sorted(placed))


def is_vacation_day(employee_id: int, on_date: date) -> bool:
    return on_date in employee_vacation_days(employee_id, on_date.year)
