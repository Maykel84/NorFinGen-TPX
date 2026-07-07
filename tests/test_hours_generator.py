from datetime import date

from norfingen.generators.hours_generator import (
    assign_customers_to_consultants,
    generate_daily_hours,
    is_billable_employee,
    is_working_day,
)
from norfingen.models.hours import ActivityType
from norfingen.seed.roster import active_customers, employee_by_id

ALL_EMPLOYEE_IDS = list(range(1, 23))


def test_is_working_day_excludes_weekends():
    assert is_working_day(date(2024, 1, 8)) is True  # poniedziałek
    assert is_working_day(date(2024, 1, 6)) is False  # sobota
    assert is_working_day(date(2024, 1, 7)) is False  # niedziela


def test_generate_daily_hours_empty_on_weekend():
    assert generate_daily_hours(2024, 1, 6, ALL_EMPLOYEE_IDS) == []


def test_generate_daily_hours_only_billable_employees():
    entries = generate_daily_hours(2024, 1, 8, ALL_EMPLOYEE_IDS)
    entry_employee_ids = {e.employee_id for e in entries}
    assert all(is_billable_employee(eid) for eid in entry_employee_ids)
    # E01 (Salg), E05 (Teknologi, jawny wyjątek), E06/E16 (Økonomi), E11 (Salg) nigdy nie logują.
    assert 1 not in entry_employee_ids
    assert 5 not in entry_employee_ids
    assert 6 not in entry_employee_ids
    assert 11 not in entry_employee_ids
    assert 16 not in entry_employee_ids


def test_is_billable_employee_department_rule():
    assert is_billable_employee(2) is True  # Leveranse
    assert is_billable_employee(8) is True  # Teknologi
    assert is_billable_employee(1) is False  # Salg
    assert is_billable_employee(6) is False  # Økonomi
    assert is_billable_employee(5) is False  # jawny wyjątek mimo Teknologi


def test_new_hires_are_billable_by_default():
    # Faza 4 (korekta #4, finalna): 20 z 22 nowych pracowników (E17-E38) są w
    # Leveranse/Teknologi -> billable automatycznie. E25 (Salg), E30 (Økonomi)
    # to role wspierające -> nie billable.
    assert is_billable_employee(17) is True  # Leveranse
    assert is_billable_employee(18) is True  # Teknologi
    assert is_billable_employee(37) is True  # Leveranse
    assert is_billable_employee(25) is False  # Salg
    assert is_billable_employee(30) is False  # Økonomi


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
            total = sum(e.hours for e in emp_entries)
            assert total == 7.5


def test_no_billable_hours_before_any_customer_onboarding():
    # Luty 2019: tylko E02 aktywny wśród billable, ale K01 (pierwszy klient)
    # onboarduje się dopiero 2019-03-01 -> brak klientów do przydziału,
    # cały dzień musi być INTERNAL, zero BILLABLE.
    entries = generate_daily_hours(2019, 2, 4, [2])  # poniedziałek
    assert len(entries) == 1
    assert entries[0].activity_type == ActivityType.INTERNAL
    assert entries[0].hours == 7.5
    assert entries[0].project_id is None


def test_billable_hours_only_to_active_customer_projects():
    # Marzec 2019: tylko K01 aktywny (onboarding 2019-03-01) -> jeśli E02
    # loguje BILLABLE, project_id musi odpowiadać K01 (project_id=1).
    for day in (4, 5, 6, 7, 8):  # kilka dni roboczych marca 2019
        entries = generate_daily_hours(2019, 3, day, [2])
        billable = [e for e in entries if e.activity_type == ActivityType.BILLABLE]
        for entry in billable:
            assert entry.project_id == 1


def test_assign_customers_to_consultants_respects_capacity():
    customers = active_customers(date(2026, 6, 30))
    billable_employees = [employee_by_id(i) for i in ALL_EMPLOYEE_IDS if is_billable_employee(i)]
    assignment = assign_customers_to_consultants(customers, billable_employees, 2026, 6)
    # Każdy przydzielony klient musi być w liście wejściowej, żaden konsultant
    # nie może mieć więcej klientów niż jest w customers.
    all_assigned = [c for lst in assignment.values() for c in lst]
    assert len(all_assigned) <= len(customers)
    assert set(assignment.keys()).issubset({int(e.number[1:]) for e in billable_employees})


def test_consultant_portfolio_rotates_over_time():
    """Przypisanie klient-konsultant zmienia się w czasie (rotacja ~15 mies.,
    Zadanie 5c) — 2023 i 2025 to różne okresy rotacji, muszą się różnić."""
    customers_2023 = active_customers(date(2023, 6, 1))
    customers_2025 = active_customers(date(2025, 6, 1))
    billable_2023 = [employee_by_id(i) for i in ALL_EMPLOYEE_IDS if is_billable_employee(i)
                     and employee_by_id(i).start_date <= date(2023, 6, 1)]
    billable_2025 = [employee_by_id(i) for i in ALL_EMPLOYEE_IDS if is_billable_employee(i)
                      and employee_by_id(i).start_date <= date(2025, 6, 1)]

    assignment_2023 = assign_customers_to_consultants(customers_2023, billable_2023, 2023, 6)
    assignment_2025 = assign_customers_to_consultants(customers_2025, billable_2025, 2025, 6)
    assert assignment_2023 != assignment_2025


def test_deterministic_across_calls():
    a = generate_daily_hours(2024, 3, 12, ALL_EMPLOYEE_IDS)
    b = generate_daily_hours(2024, 3, 12, ALL_EMPLOYEE_IDS)
    assert [(e.employee_id, e.activity_type, e.hours, e.project_id) for e in a] == \
           [(e.employee_id, e.activity_type, e.hours, e.project_id) for e in b]
