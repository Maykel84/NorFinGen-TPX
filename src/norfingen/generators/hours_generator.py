"""HourEntry — dzienny generator timesheet (Warstwa 2/3, Etap 4).

Loguje godziny tylko dla pracowników działów Leveranse/Teknologi (per
EMPLOYEE_PROJECT_MAP) — Salg i Økonomi nie raportują czasu projektowego.
Każdy aktywny dzień roboczy: ~5% szans na SICK (0h), inaczej billable (6-7.5h,
przypisane do jednego z dwóch projektów pracownika, ale TYLKO jeśli klient
danego projektu ma już onboarding_date <= dzisiaj — konsultant nie loguje
godzin do klienta, który jeszcze nie istnieje) + reszta do 7.5h jako INTERNAL.
Jeśli żaden z przypisanych projektów pracownika nie ma jeszcze aktywnego
klienta, cały dzień loguje się jako INTERNAL (brak zlecenia do fakturowania).
"""

from __future__ import annotations

import random
from datetime import date

from norfingen.models.hours import ActivityType, HourEntry
from norfingen.seed.roster import customer_by_id, project_by_id

# Pracownicy którzy logują godziny (Leveranse + Teknologi, E02-E15 z wyjątkiem E05).
BILLABLE_EMPLOYEES = [2, 3, 4, 7, 8, 9, 10, 12, 13, 14, 15]

# Mapowanie pracownik → projekty (rotacja między dwoma stałymi projektami klienta).
EMPLOYEE_PROJECT_MAP: dict[int, list[int]] = {
    2: [1, 6],  # Marte → Bergström + Halvorsen
    3: [1, 2],  # Bjørn → Bergström + Nordkraft
    4: [6, 7],  # Kari → Halvorsen + Fjord
    7: [2, 8],  # Lars → Nordkraft + Østfold
    8: [3, 4],  # Silje → Innlandet + Rogaland
    9: [3, 7],  # Ole → Innlandet + Fjord
    10: [4, 8],  # Nina → Rogaland + Østfold
    12: [1, 3],  # Hanna → Bergström + Innlandet
    13: [6, 2],  # Rune → Halvorsen + Nordkraft
    14: [7, 4],  # Camilla → Fjord + Rogaland
    15: [5, 8],  # Anders → Telemark + Østfold
}

FULL_WORKDAY_HOURS = 7.5
SICK_PROBABILITY = 0.05
BILLABLE_HOURS_CHOICES = [6.0, 6.5, 7.0, 7.5]


def is_working_day(d: date) -> bool:
    """Pon-Pt, bez norweskich świąt (uproszczone)."""
    return d.weekday() < 5


def _active_projects_for_employee(emp_id: int, on_date: date) -> list[int]:
    """Projekty przypisane pracownikowi, których klient ma już
    onboarding_date <= on_date i (jeśli ma churn_date) jeszcze nie odszedł —
    konsultant nie loguje godzin do klienta, który jeszcze nie istnieje albo
    już zrezygnował ze współpracy."""
    projects = EMPLOYEE_PROJECT_MAP.get(emp_id, [1])
    active = []
    for project_id in projects:
        project = project_by_id(project_id)
        customer = customer_by_id(project.customer_id)
        if customer.onboarding_date <= on_date and (customer.churn_date is None or on_date <= customer.churn_date):
            active.append(project_id)
    return active


def generate_daily_hours(year: int, month: int, day: int, active_employee_ids: list[int]) -> list[HourEntry]:
    """Generuje wpisy godzin dla konkretnego dnia roboczego.

    Logika:
    - Każdy aktywny pracownik z BILLABLE_EMPLOYEES loguje 7.5h
    - ~5% szans na chorobowe (0h billable, wpis SICK)
    - Inaczej: billable (projekt klienta, 6-7.5h) + reszta do 7.5h jako INTERNAL
    - Deterministyczne per rok+miesiąc+dzień (lokalny random.Random)."""
    d = date(year, month, day)
    if not is_working_day(d):
        return []

    entries: list[HourEntry] = []
    rng = random.Random(year * 10000 + month * 100 + day)

    billable_active = [e for e in active_employee_ids if e in BILLABLE_EMPLOYEES]

    for emp_id in billable_active:
        if rng.random() < SICK_PROBABILITY:
            entries.append(HourEntry(
                date=d, employee_id=emp_id,
                activity_type=ActivityType.SICK,
                hours=0.0,
                description="Sykefravær",
            ))
            continue

        active_projects = _active_projects_for_employee(emp_id, d)
        if not active_projects:
            # Żaden przypisany klient jeszcze nie istnieje (onboarding w przyszłości)
            # -> brak zlecenia do fakturowania, cały dzień internal.
            entries.append(HourEntry(
                date=d, employee_id=emp_id,
                activity_type=ActivityType.INTERNAL,
                hours=FULL_WORKDAY_HOURS,
                description="Interne møter / administrasjon (brak aktywnego klienta)",
            ))
            continue

        project_id = rng.choice(active_projects)
        billable_hours = rng.choice(BILLABLE_HOURS_CHOICES)

        entries.append(HourEntry(
            date=d, employee_id=emp_id,
            project_id=project_id,
            activity_type=ActivityType.BILLABLE,
            hours=billable_hours,
            description=f"Konsulentarbeid — prosjekt PRJ{project_id:03d}",
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
