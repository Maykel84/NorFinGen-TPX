from datetime import date

from norfingen.generators.hours_generator import (
    BILLABLE_EMPLOYEES,
    EMPLOYEE_PROJECT_MAP,
    generate_daily_hours,
    is_working_day,
)
from norfingen.models.hours import ActivityType

ALL_EMPLOYEE_IDS = list(range(1, 17))


def test_is_working_day_excludes_weekends():
    assert is_working_day(date(2024, 1, 8)) is True  # poniedziałek
    assert is_working_day(date(2024, 1, 6)) is False  # sobota
    assert is_working_day(date(2024, 1, 7)) is False  # niedziela


def test_generate_daily_hours_empty_on_weekend():
    assert generate_daily_hours(2024, 1, 6, ALL_EMPLOYEE_IDS) == []


def test_generate_daily_hours_only_billable_employees():
    entries = generate_daily_hours(2024, 1, 8, ALL_EMPLOYEE_IDS)
    entry_employee_ids = {e.employee_id for e in entries}
    assert entry_employee_ids.issubset(set(BILLABLE_EMPLOYEES))
    # E01 (Salg), E05 (Teknologi, wyłączony), E06/E16 (Økonomi), E11 (Salg) nigdy nie logują.
    assert 1 not in entry_employee_ids
    assert 5 not in entry_employee_ids
    assert 6 not in entry_employee_ids
    assert 11 not in entry_employee_ids
    assert 16 not in entry_employee_ids


def test_generate_daily_hours_respects_active_employee_filter():
    entries = generate_daily_hours(2024, 1, 8, [2, 3])
    entry_employee_ids = {e.employee_id for e in entries}
    assert entry_employee_ids.issubset({2, 3})


def test_billable_and_internal_sum_to_full_workday():
    entries = generate_daily_hours(2024, 1, 8, ALL_EMPLOYEE_IDS)
    by_employee: dict[int, list] = {}
    for e in entries:
        by_employee.setdefault(e.employee_id, []).append(e)

    for emp_id, emp_entries in by_employee.items():
        types = {e.activity_type for e in emp_entries}
        if ActivityType.SICK in types:
            assert len(emp_entries) == 1
            assert emp_entries[0].hours == 0.0
            assert emp_entries[0].project_id is None
        else:
            assert ActivityType.BILLABLE in types
            total = sum(e.hours for e in emp_entries)
            assert total == 7.5
            billable_entry = next(e for e in emp_entries if e.activity_type == ActivityType.BILLABLE)
            assert billable_entry.project_id in EMPLOYEE_PROJECT_MAP[emp_id]


def test_deterministic_across_calls():
    a = generate_daily_hours(2024, 3, 12, ALL_EMPLOYEE_IDS)
    b = generate_daily_hours(2024, 3, 12, ALL_EMPLOYEE_IDS)
    assert [(e.employee_id, e.activity_type, e.hours, e.project_id) for e in a] == \
           [(e.employee_id, e.activity_type, e.hours, e.project_id) for e in b]
