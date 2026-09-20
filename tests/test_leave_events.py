from datetime import date, timedelta

from norfingen.generators.leave_events import (
    LONG_SICK_LEAVE_MAX_DAYS,
    MIN_TENURE_BEFORE_LEAVE_DAYS,
    PARENTAL_LEAVE_COOLDOWN_YEARS,
    PARENTAL_LEAVE_MAX_WEEKS,
    WELFARE_LEAVE_MAX_DAYS,
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
    # WELFARE_LEAVE deliberately has no minimum-tenure requirement — a
    # family emergency doesn't wait for your 90th day on the job.
    for emp_id in ALL_EMPLOYEE_IDS:
        start_date = employee_by_id(emp_id).start_date
        for period in employee_leave_periods(emp_id):
            assert period.end >= period.start
            if period.activity_type != ActivityType.WELFARE_LEAVE:
                assert period.start >= start_date + timedelta(days=MIN_TENURE_BEFORE_LEAVE_DAYS)


def test_periods_never_overlap_for_the_same_employee():
    for emp_id in ALL_EMPLOYEE_IDS:
        periods = employee_leave_periods(emp_id)
        for a, b in zip(periods, periods[1:]):
            assert a.end < b.start


def test_periods_use_only_the_expected_activity_types():
    allowed = {ActivityType.SICK, ActivityType.PARENTAL_LEAVE, ActivityType.WELFARE_LEAVE}
    for emp_id in ALL_EMPLOYEE_IDS:
        for period in employee_leave_periods(emp_id):
            assert period.activity_type in allowed


def test_period_lengths_within_declared_bounds():
    max_weeks_days = PARENTAL_LEAVE_MAX_WEEKS * 7
    for emp_id in ALL_EMPLOYEE_IDS:
        for period in employee_leave_periods(emp_id):
            length = (period.end - period.start).days + 1
            if period.activity_type == ActivityType.SICK:
                assert 1 <= length <= LONG_SICK_LEAVE_MAX_DAYS
            elif period.activity_type == ActivityType.PARENTAL_LEAVE:
                assert 1 <= length <= max_weeks_days
            elif period.activity_type == ActivityType.WELFARE_LEAVE:
                assert 1 <= length <= WELFARE_LEAVE_MAX_DAYS


def test_parental_leave_respects_the_cooldown():
    """No employee gets two PARENTAL_LEAVE events with start dates less than
    PARENTAL_LEAVE_COOLDOWN_YEARS apart."""
    for emp_id in ALL_EMPLOYEE_IDS:
        parental_starts = [
            p.start for p in employee_leave_periods(emp_id) if p.activity_type == ActivityType.PARENTAL_LEAVE
        ]
        for a, b in zip(parental_starts, parental_starts[1:]):
            assert (b.year - a.year) >= PARENTAL_LEAVE_COOLDOWN_YEARS


def test_parental_leave_not_gender_assigned():
    """EmployeeSeed carries no gender field at all — PARENTAL_LEAVE can only
    ever be assigned independent of gender, by construction. This test just
    confirms the model has no such field to accidentally key off of."""
    employee = employee_by_id(1)
    assert not hasattr(employee, "gender")
    assert not hasattr(employee, "sex")


def test_active_leave_period_matches_a_known_deterministic_case():
    # E03, seed "LEAVE-PARENTAL-3-2021" -> a fixed PARENTAL_LEAVE block.
    period = active_leave_period(3, date(2021, 6, 1))
    assert period is not None
    assert period.activity_type == ActivityType.PARENTAL_LEAVE
    assert period.start == date(2021, 4, 22)
    assert period.end == date(2021, 9, 15)

    assert active_leave_period(3, date(2021, 4, 21)) is None
    assert active_leave_period(3, date(2021, 9, 16)) is None


def test_active_leave_period_none_outside_any_period():
    assert active_leave_period(4, date(2019, 1, 10)) is None
