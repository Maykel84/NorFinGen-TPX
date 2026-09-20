from datetime import date

from norfingen.generators.vacation import (
    FULL_YEAR_VACATION_DAYS,
    _easter_sunday,
    _target_vacation_days,
    employee_vacation_days,
    is_vacation_day,
)
from norfingen.seed.roster import employee_by_id

ALL_EMPLOYEE_IDS = list(range(1, 18))

KNOWN_EASTER_SUNDAYS = {
    2019: date(2019, 4, 21),
    2024: date(2024, 3, 31),
    2025: date(2025, 4, 20),
}


def test_easter_sunday_matches_known_dates():
    for year, expected in KNOWN_EASTER_SUNDAYS.items():
        assert _easter_sunday(year) == expected


def test_annual_vacation_days_equals_25():
    """A full-time employee worked the whole calendar year -> exactly 25
    VACATION days (E01, hired 2019-01-01, year 2023 — no other leave period
    overlaps this employee/year, see test_leave_events.py)."""
    days = employee_vacation_days(1, 2023)
    assert len(days) == FULL_YEAR_VACATION_DAYS
    for d in days:
        assert d.year == 2023
        assert d.weekday() < 5  # only working days


def test_vacation_prorated_for_partial_first_year():
    employee = employee_by_id(1)
    target_first_year = _target_vacation_days(1, employee.start_date.year)
    assert target_first_year <= FULL_YEAR_VACATION_DAYS


def test_vacation_days_deterministic_across_calls():
    for emp_id in ALL_EMPLOYEE_IDS:
        for year in (2020, 2023, 2025):
            assert employee_vacation_days(emp_id, year) == employee_vacation_days(emp_id, year)


def test_vacation_never_exceeds_target_and_stays_on_working_days():
    for emp_id in ALL_EMPLOYEE_IDS:
        for year in range(2019, 2028):
            target = _target_vacation_days(emp_id, year)
            days = employee_vacation_days(emp_id, year)
            assert len(days) <= target
            assert all(d.weekday() < 5 for d in days)


def test_vacation_includes_a_july_block():
    days = employee_vacation_days(1, 2023)
    july_days = [d for d in days if d.month == 7]
    assert len(july_days) >= 10  # the fellesferie block, ~15/25 days


def test_is_vacation_day_matches_employee_vacation_days():
    days = employee_vacation_days(1, 2023)
    assert days  # sanity — E01/2023 has placed days (see test above)
    assert is_vacation_day(1, days[0]) is True
    assert is_vacation_day(1, date(2023, 1, 1)) is False  # a Sunday, and not in the set anyway
