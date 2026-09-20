from datetime import date, timedelta

from norfingen.generators.leave_events import (
    LONG_SICK_LEAVE_MAX_DAYS,
    MATERNITY_LEAVE_MAX_DAYS,
    MIN_TENURE_BEFORE_LEAVE_DAYS,
    PATERNITY_LEAVE_MAX_DAYS,
    active_leave_period,
    employee_leave_periods,
)
from norfingen.models.hours import ActivityType
from norfingen.seed.roster import employee_by_id

ALL_EMPLOYEE_IDS = list(range(1, 18))


def test_deterministic_across_calls():
    for emp_id in ALL_EMPLOYEE_IDS:
        assert employee_leave_periods(emp_id) == employee_leave_periods(emp_id)


def test_periods_start_after_minimum_tenure():
    for emp_id in ALL_EMPLOYEE_IDS:
        start_date = employee_by_id(emp_id).start_date
        for period in employee_leave_periods(emp_id):
            assert period.start >= start_date + timedelta(days=MIN_TENURE_BEFORE_LEAVE_DAYS)
            assert period.end >= period.start


def test_periods_never_overlap_for_the_same_employee():
    for emp_id in ALL_EMPLOYEE_IDS:
        periods = employee_leave_periods(emp_id)
        for a, b in zip(periods, periods[1:]):
            assert a.end < b.start


def test_periods_use_only_the_expected_activity_types():
    allowed = {ActivityType.SICK, ActivityType.MATERNITY_LEAVE, ActivityType.PATERNITY_LEAVE}
    for emp_id in ALL_EMPLOYEE_IDS:
        for period in employee_leave_periods(emp_id):
            assert period.activity_type in allowed


def test_period_lengths_within_declared_bounds():
    max_by_type = {
        ActivityType.SICK: LONG_SICK_LEAVE_MAX_DAYS,
        ActivityType.MATERNITY_LEAVE: MATERNITY_LEAVE_MAX_DAYS,
        ActivityType.PATERNITY_LEAVE: PATERNITY_LEAVE_MAX_DAYS,
    }
    for emp_id in ALL_EMPLOYEE_IDS:
        for period in employee_leave_periods(emp_id):
            length = (period.end - period.start).days + 1
            assert 1 <= length <= max_by_type[period.activity_type]


def test_active_leave_period_matches_a_known_deterministic_case():
    # E04, seed "LEAVE-4" -> a fixed PATERNITY_LEAVE block, 2019-09-15..2019-12-19.
    period = active_leave_period(4, date(2019, 10, 1))
    assert period is not None
    assert period.activity_type == ActivityType.PATERNITY_LEAVE
    assert period.start == date(2019, 9, 15)
    assert period.end == date(2019, 12, 19)

    assert active_leave_period(4, date(2019, 9, 14)) is None
    assert active_leave_period(4, date(2019, 12, 20)) is None


def test_active_leave_period_none_when_no_periods():
    # E01, seed "LEAVE-1" -> no leave events in this deterministic run.
    assert employee_leave_periods(1) == ()
    assert active_leave_period(1, date(2024, 6, 1)) is None
