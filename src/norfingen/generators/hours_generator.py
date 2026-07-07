"""HourEntry — dzienny generator timesheet (Warstwa 2/3, Etap 4).

Loguje godziny tylko dla pracowników działów Leveranse/Teknologi (billable —
zob. is_billable_employee), z wyjątkiem E05 (System Architect — rola
techniczno-architektoniczna, nigdy billable, ustalone przed Fazą 4). Każdy
aktywny dzień roboczy: ~5% szans na SICK (0h), inaczej billable (6-7.5h,
przypisane do JEDNEGO z portfela klientów danego konsultanta) + reszta do 7.5h
jako INTERNAL. Jeśli konsultant nie ma przydzielonych klientów w danym
miesiącu (np. brak zdolności — nie powinno się zdarzać, zob.
roster.can_onboard_new_customer), cały dzień loguje się jako INTERNAL.

Faza 4 — zastępuje statyczny EMPLOYEE_PROJECT_MAP (sztywna rotacja 1-2
klientów/konsultanta na zawsze, nierealistyczne przy 45 klientach)
dynamicznym assign_customers_to_consultants(): portfolio przydzielane
proporcjonalnie do obciążenia godzinowego per segment
(roster.SEGMENT_HOURS_PER_MONTH), z rotacją co ~15 miesięcy (zob.
_rotation_id) żeby uniknąć przypisania na zawsze."""

from __future__ import annotations

import random
from datetime import date

from norfingen.models.hours import ActivityType, HourEntry
from norfingen.seed.roster import (
    CustomerSeed,
    EmployeeSeed,
    SEGMENT_HOURS_PER_MONTH,
    UTILIZATION_TARGET,
    HOURS_PER_YEAR_PER_CONSULTANT,
    active_customers,
    employee_by_id,
    project_for_customer,
)

BILLABLE_DEPARTMENTS = {2, 3}  # Leveranse, Teknologi
NON_BILLABLE_OVERRIDES = {5}  # E05 System Architect — nigdy billable (ustalone przed Fazą 4)

FULL_WORKDAY_HOURS = 7.5
SICK_PROBABILITY = 0.05
BILLABLE_HOURS_CHOICES = [6.0, 6.5, 7.0, 7.5]

BASE_YEAR = 2019
ROTATION_PERIOD_QUARTERS = 5  # ~15 miesięcy (widełki 12-18 z zadania)

MAX_CONSULTANT_CAPACITY_HOURS = HOURS_PER_YEAR_PER_CONSULTANT / 12 * UTILIZATION_TARGET


def is_working_day(d: date) -> bool:
    """Pon-Pt, bez norweskich świąt (uproszczone)."""
    return d.weekday() < 5


def is_billable_employee(employee_id: int) -> bool:
    """Pracownik loguje billable godziny — dział Leveranse/Teknologi, poza
    jawnymi wyjątkami (NON_BILLABLE_OVERRIDES). Zastępuje statyczną listę
    BILLABLE_EMPLOYEES sprzed Fazy 4 — teraz działa dla dowolnej liczby
    pracowników (E17+ automatycznie billable, bo są w tych działach)."""
    if employee_id in NON_BILLABLE_OVERRIDES:
        return False
    employee = employee_by_id(employee_id)
    return employee.department_number in BILLABLE_DEPARTMENTS


def _rotation_id(year: int, month: int) -> int:
    """Identyfikator okresu rotacji portfela klient-konsultant (~15 mies.,
    zob. moduł-level docstring, Zadanie 5c) — zmienia się co
    ROTATION_PERIOD_QUARTERS kwartałów, NIE co miesiąc. Świadome odstępstwo od
    pseudokodu zadania (który seedował rng świeżo KAŻDY miesiąc —
    sprzeczne z wymogiem "rotacja co 12-18 miesięcy", bo dawałoby całkowicie
    nowe przypisanie co miesiąc zamiast stabilnego portfela z okresową
    rotacją)."""
    quarter_index = (year - BASE_YEAR) * 4 + (month - 1) // 3
    return quarter_index // ROTATION_PERIOD_QUARTERS


def assign_customers_to_consultants(
    customers: list[CustomerSeed],
    billable_employees: list[EmployeeSeed],
    year: int,
    month: int,
) -> dict[int, list[CustomerSeed]]:
    """Przydziela klientów do konsultantów tak, żeby suma godzin per
    konsultant nie przekraczała dostępnej pojemności (roster.SEGMENT_HOURS_PER_MONTH,
    MAX_CONSULTANT_CAPACITY_HOURS). Deterministyczne — seed z okresu rotacji
    (zob. _rotation_id), nie z dokładnego (rok, miesiąc), żeby portfolio było
    stabilne przez ~15 miesięcy, a nie zmieniało się co miesiąc (Zadanie 5c)."""
    rng = random.Random(f"consultant-assignment-{_rotation_id(year, month)}")
    sorted_customers = sorted(customers, key=lambda c: SEGMENT_HOURS_PER_MONTH[c.segment], reverse=True)
    shuffled_employees = list(billable_employees)
    rng.shuffle(shuffled_employees)

    assignment: dict[int, list[CustomerSeed]] = {int(e.number[1:]): [] for e in shuffled_employees}
    employee_load: dict[int, float] = {int(e.number[1:]): 0.0 for e in shuffled_employees}

    for customer in sorted_customers:
        hours_needed = SEGMENT_HOURS_PER_MONTH[customer.segment]
        available = [
            e for e in shuffled_employees
            if employee_load[int(e.number[1:])] + hours_needed <= MAX_CONSULTANT_CAPACITY_HOURS
        ]
        if not available:
            continue  # brak wolnej zdolności — klient nieobsłużony ten miesiąc (nie powinno się zdarzać, zob. roster.can_onboard_new_customer)
        chosen = min(available, key=lambda e: employee_load[int(e.number[1:])])
        chosen_id = int(chosen.number[1:])
        assignment[chosen_id].append(customer)
        employee_load[chosen_id] += hours_needed

    return assignment


def generate_daily_hours(year: int, month: int, day: int, active_employee_ids: list[int]) -> list[HourEntry]:
    """Generuje wpisy godzin dla konkretnego dnia roboczego.

    Logika:
    - Każdy aktywny billable pracownik loguje 7.5h
    - ~5% szans na chorobowe (0h billable, wpis SICK)
    - Inaczej: billable (jeden z przydzielonych klientów, 6-7.5h) + reszta do
      7.5h jako INTERNAL
    - Deterministyczne per rok+miesiąc+dzień (lokalny random.Random)."""
    d = date(year, month, day)
    if not is_working_day(d):
        return []

    entries: list[HourEntry] = []
    rng = random.Random(year * 10000 + month * 100 + day)

    billable_ids = [eid for eid in active_employee_ids if is_billable_employee(eid)]
    if not billable_ids:
        return []

    billable_employees = [employee_by_id(eid) for eid in billable_ids]
    customers = active_customers(d)
    assignment = assign_customers_to_consultants(customers, billable_employees, year, month)

    for emp_id in billable_ids:
        if rng.random() < SICK_PROBABILITY:
            entries.append(HourEntry(
                date=d, employee_id=emp_id,
                activity_type=ActivityType.SICK,
                hours=0.0,
                description="Sykefravær",
            ))
            continue

        assigned_customers = assignment.get(emp_id, [])
        if not assigned_customers:
            # Brak przydzielonych klientów ten miesiąc (nowy pracownik przed
            # pierwszą rotacją z klientami, albo portfel pusty) -> cały dzień internal.
            entries.append(HourEntry(
                date=d, employee_id=emp_id,
                activity_type=ActivityType.INTERNAL,
                hours=FULL_WORKDAY_HOURS,
                description="Interne møter / administrasjon (brak przydzielonego klienta)",
            ))
            continue

        customer = rng.choice(assigned_customers)
        project = project_for_customer(customer)
        billable_hours = rng.choice(BILLABLE_HOURS_CHOICES)

        entries.append(HourEntry(
            date=d, employee_id=emp_id,
            # project.customer_id == numer projektu (Faza 4: 1:1 PRJnnn <-> Knnn,
            # zob. roster.PROJECTS) — nie osobne "id" pole na ProjectSeed.
            project_id=project.customer_id,
            activity_type=ActivityType.BILLABLE,
            hours=billable_hours,
            description=f"Konsulentarbeid — prosjekt {project.number}",
        ))

        internal_hours = round(FULL_WORKDAY_HOURS - billable_hours, 1)
        if internal_hours > 0:
            entries.append(HourEntry(
                date=d, employee_id=emp_id,
                activity_type=ActivityType.INTERNAL,
                hours=internal_hours,
                description="Interne møter / administrasjon",
            ))

    return entries
