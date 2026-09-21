import random
from datetime import date, timedelta

from norfingen.generators.hours_generator import (
    assign_customers_to_consultants,
    generate_daily_hours,
    generate_daily_support_hours,
    generate_okonomi_daily_hours,
    generate_salg_daily_hours,
    is_billable_employee,
    is_month_end_closing_period,
    is_working_day,
)
from norfingen.models.hours import ActivityType
from norfingen.seed.roster import active_customers, employee_by_id

ALL_EMPLOYEE_IDS = list(range(1, 18))  # Faza 6: zespół 17 osób (E01-E17)


def test_is_working_day_excludes_weekends():
    assert is_working_day(date(2024, 1, 8)) is True  # poniedziałek
    assert is_working_day(date(2024, 1, 6)) is False  # sobota
    assert is_working_day(date(2024, 1, 7)) is False  # niedziela


def test_generate_daily_hours_empty_on_weekend():
    assert generate_daily_hours(2024, 1, 6, ALL_EMPLOYEE_IDS) == []


def test_generate_daily_hours_excludes_only_e05():
    """Po rozszerzeniu na wszystkie działy (Salg/Okonomi) jedynym stale
    wykluczonym pracownikiem jest E05 (jawny wyjątek, NON_BILLABLE_OVERRIDES).
    Salg loguje nieregularnie (~40% dni), więc sprawdzamy obecność w skali
    miesiąca, nie jednego dnia."""
    seen: set[int] = set()
    d = date(2024, 1, 1)
    while d < date(2024, 2, 1):
        entries = generate_daily_hours(d.year, d.month, d.day, ALL_EMPLOYEE_IDS)
        seen.update(e.employee_id for e in entries)
        d += timedelta(days=1)

    assert 5 not in seen  # jawny wyjątek, nigdy nie loguje
    assert seen == set(ALL_EMPLOYEE_IDS) - {5}  # E01/E06/E11/E16 (Salg/Okonomi) też logują


def test_is_billable_employee_department_rule():
    assert is_billable_employee(2) is True  # Leveranse
    assert is_billable_employee(8) is True  # Teknologi
    assert is_billable_employee(1) is False  # Salg
    assert is_billable_employee(6) is False  # Økonomi
    assert is_billable_employee(5) is False  # jawny wyjątek mimo Teknologi


def test_new_hires_are_billable_by_default():
    # Faza 6: E17 (Leveranse) jest jedynym dociążeniem po fuzji -> billable
    # automatycznie, bo działa w dziale 2 (BILLABLE_DEPARTMENTS).
    assert is_billable_employee(17) is True  # Leveranse


def test_generate_daily_hours_respects_active_employee_filter():
    entries = generate_daily_hours(2024, 1, 8, [2, 3])
    entry_employee_ids = {e.employee_id for e in entries}
    assert entry_employee_ids.issubset({2, 3})


ZERO_HOUR_TYPES = {
    ActivityType.SICK, ActivityType.VACATION, ActivityType.PARENTAL_LEAVE, ActivityType.WELFARE_LEAVE,
    ActivityType.FLEX_LEAVE, ActivityType.CHILD_CARE_LEAVE,
}


def test_billable_and_internal_sum_to_full_workday():
    """Ten pełny-dzień-workday invariant dotyczy tylko Leveranse/Teknologi —
    Salg loguje niepełne, epizodyczne godziny z założenia (Zadanie 2a)."""
    entries = generate_daily_hours(2024, 1, 8, ALL_EMPLOYEE_IDS)
    billable_entries = [e for e in entries if is_billable_employee(e.employee_id)]
    by_employee: dict[int, list] = {}
    for e in billable_entries:
        by_employee.setdefault(e.employee_id, []).append(e)

    for emp_id, emp_entries in by_employee.items():
        types = {e.activity_type for e in emp_entries}
        if types & ZERO_HOUR_TYPES:
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


def test_employee_on_leave_logs_a_single_zero_hour_entry():
    # E03 is deterministically on PARENTAL_LEAVE 2021-04-22..2021-09-15
    # (see test_leave_events.py) — a Tuesday well inside that window.
    entries = generate_daily_hours(2021, 6, 1, [3])
    assert len(entries) == 1
    assert entries[0].employee_id == 3
    assert entries[0].activity_type == ActivityType.PARENTAL_LEAVE
    assert entries[0].hours == 0.0
    assert entries[0].project_id is None


def test_employee_on_flex_leave_logs_a_single_zero_hour_entry():
    # E01, 2023-01-02 — deterministically the first FLEX_LEAVE day (see
    # test_flex_leave.py).
    entries = generate_daily_hours(2023, 1, 2, [1])
    assert len(entries) == 1
    assert entries[0].employee_id == 1
    assert entries[0].activity_type == ActivityType.FLEX_LEAVE
    assert entries[0].hours == 0.0
    assert entries[0].project_id is None


def test_employee_on_child_care_leave_logs_a_single_zero_hour_entry():
    # E01, 2023-01-05 — deterministically the first CHILD_CARE_LEAVE day.
    entries = generate_daily_hours(2023, 1, 5, [1])
    assert len(entries) == 1
    assert entries[0].employee_id == 1
    assert entries[0].activity_type == ActivityType.CHILD_CARE_LEAVE
    assert entries[0].hours == 0.0
    assert entries[0].project_id is None


def test_employee_on_vacation_logs_a_single_zero_hour_entry():
    # E01, 2023 — deterministically 25/25 VACATION days placed (see
    # test_vacation.py), including a fellesferie block in July.
    entries = generate_daily_hours(2023, 7, 12, [1])
    assert len(entries) == 1
    assert entries[0].employee_id == 1
    assert entries[0].activity_type == ActivityType.VACATION
    assert entries[0].hours == 0.0
    assert entries[0].project_id is None


def test_salg_hours_irregular():
    """Dział Salg (E01) NIE loguje godzin każdego dnia roboczego — w skali
    miesiąca powinny być zarówno dni z wpisem, jak i bez."""
    logged_days = 0
    total_days = 0
    d = date(2024, 1, 1)
    while d < date(2024, 4, 1):
        if is_working_day(d):
            total_days += 1
            entries = generate_salg_daily_hours(1, d, random.Random(f"test-{d.isoformat()}"))
            if entries:
                logged_days += 1
        d += timedelta(days=1)
    assert 0 < logged_days < total_days


def test_salg_hours_are_internal_and_within_declared_range():
    rng = random.Random("salg-range-test")
    for _ in range(200):
        entries = generate_salg_daily_hours(1, date(2024, 3, 4), rng)
        for e in entries:
            assert e.activity_type == ActivityType.INTERNAL
            assert 1.5 <= e.hours <= 4.0
            assert e.project_id is None


def test_okonomi_month_end_spike():
    """Ostatnie dni miesiąca mają wyższe godziny Okonomi niż środek miesiąca."""
    def avg_hours(d: date, n: int) -> float:
        rng = random.Random(f"okonomi-test-{d.isoformat()}")
        total = 0.0
        for _ in range(n):
            entries = generate_okonomi_daily_hours(6, d, rng)
            total += sum(e.hours for e in entries)
        return total / n

    assert is_month_end_closing_period(date(2024, 1, 31)) is True
    assert is_month_end_closing_period(date(2024, 1, 15)) is False
    assert avg_hours(date(2024, 1, 31), 100) > avg_hours(date(2024, 1, 15), 100)


def test_fellesferie_reduces_july_billable_ticket_hours():
    """Faza 7, Zadanie 1a — target_billable w lipcu ma być ~połowa
    normalnego, przy tym samym rng.uniform draw (izolujemy efekt miesiąca,
    nie inny seed)."""
    customers = active_customers(date(2024, 6, 15))
    assigned = customers[:5]

    def billable_total(month: int) -> float:
        rng = random.Random("fellesferie-test-fixed-seed")
        entries = generate_daily_support_hours(1, assigned, date(2024, month, 10), rng)
        return sum(e.hours for e in entries if e.activity_type == ActivityType.BILLABLE)

    assert billable_total(7) < billable_total(6)
