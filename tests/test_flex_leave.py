from datetime import date, timedelta

from norfingen.generators.flex_leave import (
    CHILD_CARE_LEAVE_ANNUAL_DAYS,
    CHILD_CARE_LEAVE_MAX_CONSECUTIVE_DAYS,
    FLEX_LEAVE_ANNUAL_DAYS,
    FLEX_LEAVE_MAX_CONSECUTIVE_DAYS,
    FLEX_LEAVE_MIN_GAP_DAYS,
    employee_child_care_leave_days,
    employee_flex_leave_days,
    is_child_care_leave_day,
    is_flex_leave_day,
)

ALL_EMPLOYEE_IDS = list(range(1, 18))


def _blocks(days: tuple[date, ...]) -> list[list[date]]:
    blocks: list[list[date]] = []
    current: list[date] = []
    for d in days:
        if current and (d - current[-1]).days == 1:
            current.append(d)
        else:
            if current:
                blocks.append(current)
            current = [d]
    if current:
        blocks.append(current)
    return blocks


def test_flex_leave_deterministic_across_calls():
    for emp_id in ALL_EMPLOYEE_IDS:
        assert employee_flex_leave_days(emp_id, 2023) == employee_flex_leave_days(emp_id, 2023)


def test_flex_leave_days_are_working_days():
    for emp_id in ALL_EMPLOYEE_IDS:
        for d in employee_flex_leave_days(emp_id, 2023):
            assert d.weekday() < 5
            assert d.year == 2023


def test_flex_leave_blocks_respect_max_length_and_gap():
    for emp_id in ALL_EMPLOYEE_IDS:
        for year in (2021, 2023, 2025):
            blocks = _blocks(employee_flex_leave_days(emp_id, year))
            for block in blocks:
                assert len(block) <= FLEX_LEAVE_MAX_CONSECUTIVE_DAYS
            for a, b in zip(blocks, blocks[1:]):
                gap = (b[0] - a[-1]).days - 1
                assert gap >= FLEX_LEAVE_MIN_GAP_DAYS


def test_flex_leave_does_not_exceed_annual_budget():
    for emp_id in ALL_EMPLOYEE_IDS:
        for year in range(2019, 2028):
            assert len(employee_flex_leave_days(emp_id, year)) <= FLEX_LEAVE_ANNUAL_DAYS


def test_child_care_leave_does_not_exceed_annual_budget_and_max_block():
    for emp_id in ALL_EMPLOYEE_IDS:
        for year in range(2019, 2028):
            days = employee_child_care_leave_days(emp_id, year)
            assert len(days) <= CHILD_CARE_LEAVE_ANNUAL_DAYS
            for block in _blocks(days):
                assert len(block) <= CHILD_CARE_LEAVE_MAX_CONSECUTIVE_DAYS


def test_flex_and_child_care_never_collide_for_the_same_employee():
    for emp_id in ALL_EMPLOYEE_IDS:
        for year in (2021, 2023, 2025):
            flex = set(employee_flex_leave_days(emp_id, year))
            child_care = set(employee_child_care_leave_days(emp_id, year))
            assert flex.isdisjoint(child_care)


def test_is_flex_leave_day_matches_employee_flex_leave_days():
    days = employee_flex_leave_days(1, 2023)
    assert days
    assert is_flex_leave_day(1, days[0]) is True
    assert is_flex_leave_day(1, date(2023, 6, 15)) in (True, False)  # no crash either way


def test_is_child_care_leave_day_matches_employee_child_care_leave_days():
    days = employee_child_care_leave_days(1, 2023)
    assert days
    assert is_child_care_leave_day(1, days[0]) is True
