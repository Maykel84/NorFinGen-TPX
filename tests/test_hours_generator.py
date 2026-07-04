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


def test_no_billable_hours_before_any_assigned_customer_onboarding():
    # E02 (Marte): projekty [1=K01 onboarding 2019-03-01, 6=K02 onboarding 2019-06-01].
    # W lutym 2019 (dzień po jej starcie 2019-02-01) żaden klient jeszcze nie istnieje
    # -> cały dzień musi być INTERNAL, zero BILLABLE.
    entries = generate_daily_hours(2019, 2, 4, [2])  # poniedziałek
    assert len(entries) == 1
    assert entries[0].activity_type == ActivityType.INTERNAL
    assert entries[0].hours == 7.5
    assert entries[0].project_id is None


def test_billable_hours_only_to_onboarded_customer_project():
    # Od 2019-03-01 K01 (projekt 1) jest aktywny, ale K02 (projekt 6) nie
    # (onboarding dopiero 2019-06-01) -> jeśli E02 loguje BILLABLE, musi to być
    # zawsze projekt 1, nigdy 6.
    for day in (4, 5, 6, 7, 8):  # kilka dni roboczych marca 2019
        entries = generate_daily_hours(2019, 3, day, [2])
        billable = [e for e in entries if e.activity_type == ActivityType.BILLABLE]
        for entry in billable:
            assert entry.project_id == 1


def test_deterministic_across_calls():
    a = generate_daily_hours(2024, 3, 12, ALL_EMPLOYEE_IDS)
    b = generate_daily_hours(2024, 3, 12, ALL_EMPLOYEE_IDS)
    assert [(e.employee_id, e.activity_type, e.hours, e.project_id) for e in a] == \
           [(e.employee_id, e.activity_type, e.hours, e.project_id) for e in b]
