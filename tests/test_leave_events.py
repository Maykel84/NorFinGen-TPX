from datetime import date, timedelta

from norfingen.generators.leave_events import (
    FATHER_QUOTA_MAX_WEEKS,
    FATHER_QUOTA_MIN_WEEKS,
    LONG_SICK_LEAVE_MAX_DAYS,
    MIN_TENURE_BEFORE_LEAVE_DAYS,
    PARENTAL_LEAVE_COOLDOWN_YEARS,
    PARENTAL_LEAVE_MAX_WEEKS,
    PARENTAL_LEAVE_MIN_WEEKS,
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
    # A PARENTAL_LEAVE period is either a primary block (PARENTAL_LEAVE_MIN/MAX_WEEKS)
    # or a received father's-quota block (FATHER_QUOTA_MIN/MAX_WEEKS, shorter) —
    # the two ranges don't overlap, so the combined bound spans both.
    parental_min_days = FATHER_QUOTA_MIN_WEEKS * 7
    parental_max_days = PARENTAL_LEAVE_MAX_WEEKS * 7
    for emp_id in ALL_EMPLOYEE_IDS:
        for period in employee_leave_periods(emp_id):
            length = (period.end - period.start).days + 1
            if period.activity_type == ActivityType.SICK:
                assert 1 <= length <= LONG_SICK_LEAVE_MAX_DAYS
            elif period.activity_type == ActivityType.PARENTAL_LEAVE:
                assert parental_min_days <= length <= parental_max_days
            elif period.activity_type == ActivityType.WELFARE_LEAVE:
                assert 1 <= length <= WELFARE_LEAVE_MAX_DAYS


def test_parental_leave_primary_events_respect_the_cooldown():
    """No employee's OWN primary-triggered PARENTAL_LEAVE events (length >=
    PARENTAL_LEAVE_MIN_WEEKS) start less than PARENTAL_LEAVE_COOLDOWN_YEARS
    apart. Received father's-quota blocks (shorter, triggered by a DIFFERENT
    employee's event) are excluded — they aren't subject to this employee's
    own cooldown at all."""
    min_primary_days = PARENTAL_LEAVE_MIN_WEEKS * 7
    for emp_id in ALL_EMPLOYEE_IDS:
        primary_starts = [
            p.start for p in employee_leave_periods(emp_id)
            if p.activity_type == ActivityType.PARENTAL_LEAVE
            and (p.end - p.start).days + 1 >= min_primary_days
        ]
        for a, b in zip(primary_starts, primary_starts[1:]):
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


def test_father_quota_assigned_to_a_different_employee_right_after_primary():
    # E06's own primary PARENTAL_LEAVE ends 2025-09-04; E16 deterministically
    # receives a ~3-month father's-quota block starting the very next day.
    e06_periods = [p for p in employee_leave_periods(6) if p.activity_type == ActivityType.PARENTAL_LEAVE]
    assert any(p.end == date(2025, 9, 4) for p in e06_periods)

    e16_periods = [p for p in employee_leave_periods(16) if p.activity_type == ActivityType.PARENTAL_LEAVE]
    father_block = next((p for p in e16_periods if p.start == date(2025, 9, 5)), None)
    assert father_block is not None
    length_weeks = ((father_block.end - father_block.start).days + 1) / 7
    assert FATHER_QUOTA_MIN_WEEKS <= length_weeks <= FATHER_QUOTA_MAX_WEEKS


def test_at_least_one_employee_receives_a_father_quota_block():
    """Sanity check that the company-wide assignment mechanism actually
    produces some cross-employee blocks across the whole roster (not just
    the one deterministic pairing asserted above)."""
    min_primary_days = PARENTAL_LEAVE_MIN_WEEKS * 7
    received_count = 0
    for emp_id in ALL_EMPLOYEE_IDS:
        for p in employee_leave_periods(emp_id):
            if p.activity_type == ActivityType.PARENTAL_LEAVE and (p.end - p.start).days + 1 < min_primary_days:
                received_count += 1
    assert received_count > 0
