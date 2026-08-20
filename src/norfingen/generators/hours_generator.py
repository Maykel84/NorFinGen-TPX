"""HourEntry — dzienny generator timesheet (Warstwa 2/3, Etap 4).

Loguje godziny tylko dla pracowników działów Leveranse/Teknologi (billable —
zob. is_billable_employee), z wyjątkiem E05 (System Architect — rola
techniczno-architektoniczna, nigdy billable, ustalone przed Fazą 4).

Faza 6, Zadania 3/4 — zastępuje wzorzec "jeden klient dziennie" (Faza 4)
dwoma modelami zależnymi od działu, bo w małym (17-osobowym) zespole
obsługującym 48 aktywnych klientów jeden konsultant fizycznie MUSI serwisować
wielu klientów dziennie:
  - Leveranse (support, wszyscy klienci) — model ticketowy
    (generate_daily_support_hours): kilku klientów dziennie, krótkie bloki
    godzin proporcjonalne do segmentu (TICKET_AVG_HOURS).
  - Teknologi (projekty/wdrożenia) — model cyklu życia klienta
    (client_lifecycle_phase): pełny dzień u klienta w fazie ONBOARDING
    (pierwsze tygodnie po onboarding_date), rozproszona konserwacja u kilku
    klientów w fazie MAINTENANCE poza tym.

Ta zmiana dotyczy WYŁĄCZNIE realizmu hour_entries — nie ma wpływu na przychód
(order_generator) ani payroll (salary_generator, niezależny od godzin), więc
nie zmienia wyniku offline sanity-checku marży (zob. SESSION_HANDOFF.md,
Faza 6).

Portfolio klient-konsultant nadal przydzielane przez
assign_customers_to_consultants(), z rotacją co ~15 miesięcy (zob.
_rotation_id) — teraz wywoływane osobno dla puli Leveranse (wszyscy klienci)
i puli Teknologi (tylko klienci w fazie MAINTENANCE, klienci w ONBOARDING
mają dedykowany zespół, zob. select_active_onboarding_clients)."""

from __future__ import annotations

import random
from datetime import date, timedelta

from norfingen.generators.client_events import event_aware_is_customer_active, hardship_ticket_multiplier_for
from norfingen.generators.company_events import unprofitable_quarter_ticket_multiplier
from norfingen.generators.seasonality import fellesferie_activity_multiplier
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
LEVERANSE_DEPARTMENT = 2
TEKNOLOGI_DEPARTMENT = 3

FULL_WORKDAY_HOURS = 7.5
SICK_PROBABILITY = 0.05

BASE_YEAR = 2019
ROTATION_PERIOD_QUARTERS = 5  # ~15 miesięcy (widełki 12-18 z zadania)

MAX_CONSULTANT_CAPACITY_HOURS = HOURS_PER_YEAR_PER_CONSULTANT / 12 * UTILIZATION_TARGET

# Faza 6, Zadanie 3 — model ticketowy Leveranse: konsultant obsługuje kilku
# klientów dziennie zamiast jednego. Średni czas ticketu rośnie z segmentem
# (Enterprise: bardziej złożone incydenty/infrastruktura).
TICKET_AVG_HOURS: dict[str, float] = {
    "Enterprise": 1.2,
    "Mid-market": 0.9,
    "SMB": 0.6,
}
TICKET_TARGET_BILLABLE_MIN = 5.5
TICKET_TARGET_BILLABLE_MAX = 7.0
TICKET_CLIENTS_PER_DAY_MIN = 2
TICKET_CLIENTS_PER_DAY_MAX = 5

# Faza 6, Zadanie 4 — cykl życia klienta dla Teknologi: pełny dzień u klienta
# podczas wdrożenia (ONBOARDING), potem rozproszona konserwacja (MAINTENANCE).
# CONCURRENT_ONBOARDING_CAPACITY=1 — mały (2-osobowy) zespół Teknologi
# prowadzi jeden aktywny projekt wdrożeniowy naraz, nie równolegle wiele.
ONBOARDING_DURATION_WEEKS: dict[str, int] = {
    "Enterprise": 6,
    "Mid-market": 4,
    "SMB": 2,
}
DEVELOPERS_PER_ONBOARDING: dict[str, int] = {
    "Enterprise": 2,
    "Mid-market": 1,
    "SMB": 1,
}
CONCURRENT_ONBOARDING_CAPACITY = 1


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


def client_lifecycle_phase(customer: CustomerSeed, on_date: date) -> str:
    """Faza 6, Zadanie 4 — faza cyklu życia klienta z perspektywy Teknologi:
    "ONBOARDING" przez ONBOARDING_DURATION_WEEKS[segment] tygodni od
    onboarding_date (pełny dzień u klienta), potem "MAINTENANCE"
    (rozproszona konserwacja). Nie modeluje osobnej fazy STABILIZATION —
    uproszczenie świadome, bo zadanie nie podaje jej konkretnego czasu
    trwania (w przeciwieństwie do ONBOARDING)."""
    onboarding_end = customer.onboarding_date + timedelta(weeks=ONBOARDING_DURATION_WEEKS[customer.segment])
    if customer.onboarding_date <= on_date < onboarding_end:
        return "ONBOARDING"
    return "MAINTENANCE"


def select_active_onboarding_clients(customers: list[CustomerSeed], on_date: date) -> list[CustomerSeed]:
    """Klienci aktualnie we wdrożeniu, ograniczeni do CONCURRENT_ONBOARDING_CAPACITY
    (najwcześniej onboardowani mają pierwszeństwo — deterministyczne, bez
    losowości) — mały zespół Teknologi prowadzi jeden projekt wdrożeniowy
    naraz, nawet jeśli kalendarzowo kilku klientów jest w swoim oknie
    onboardingu jednocześnie."""
    onboarding_now = [c for c in customers if client_lifecycle_phase(c, on_date) == "ONBOARDING"]
    onboarding_now.sort(key=lambda c: c.onboarding_date)
    return onboarding_now[:CONCURRENT_ONBOARDING_CAPACITY]


def generate_daily_support_hours(
    employee_id: int,
    assigned_customers: list[CustomerSeed],
    on_date: date,
    rng: random.Random,
) -> list[HourEntry]:
    """Faza 6, Zadanie 3 — model ticketowy: konsultant obsługuje kilku
    (TICKET_CLIENTS_PER_DAY_MIN..MAX) klientów ze swojego portfela dziennie,
    zamiast jednego bloku 6-7.5h u jednego klienta (Faza 4). Suma billable
    dąży do losowego celu (5.5-7.0h), reszta do 7.5h loguje się jako
    INTERNAL. Używane zarówno dla Leveranse (support wszystkich klientów),
    jak i Teknologi w fazie MAINTENANCE (konserwacja rozproszona) —
    zob. moduł-level docstring."""
    if not assigned_customers:
        return [HourEntry(
            date=on_date, employee_id=employee_id,
            activity_type=ActivityType.INTERNAL,
            hours=FULL_WORKDAY_HOURS,
            description="Interne møter / administrasjon (brak przydzielonego klienta)",
        )]

    entries: list[HourEntry] = []
    total_hours = 0.0
    # Faza 7, Zadanie 1a — fellesferie: ~50% normalnego wolumenu ticketów w
    # lipcu (uwolnione godziny trafiają do INTERNAL, zob. internal_hours
    # niżej). Czysto realizm hour_entries — jak reszta tego modelu, nie ma
    # wpływu na przychód/payroll (zob. docstring modułu).
    # Faza 7, Zadanie 3c — UNPROFITABLE_QUARTER: dodatkowy, firmowy (nie
    # per-klient jak TEMPORARY_HARDSHIP) mnożnik 0,85-0,95 przez cały
    # kwartał — mnoży się z fellesferie, jeśli oba akurat trafią ten sam
    # miesiąc (niezależne zdarzenia, brak przesłanki żeby się wykluczały).
    target_billable = (
        rng.uniform(TICKET_TARGET_BILLABLE_MIN, TICKET_TARGET_BILLABLE_MAX)
        * fellesferie_activity_multiplier(on_date.month)
        * unprofitable_quarter_ticket_multiplier(on_date.year, on_date.month)
    )
    n_clients_today = min(len(assigned_customers), rng.randint(TICKET_CLIENTS_PER_DAY_MIN, TICKET_CLIENTS_PER_DAY_MAX))
    todays_clients = rng.sample(assigned_customers, n_clients_today)

    for customer in todays_clients:
        if total_hours >= target_billable:
            break
        avg_hours = TICKET_AVG_HOURS[customer.segment]
        hours = round(rng.uniform(avg_hours * 0.6, avg_hours * 1.6) * 4) / 4  # zaokrąglone do 0.25h
        # Faza 7, Zadanie 2c — TEMPORARY_HARDSHIP: redukcja 40-60% wolumenu
        # ticketów TEGO klienta (nie całego dnia konsultanta — inni klienci
        # w tym samym dniu nie są dotknięci).
        hours = round(hours * hardship_ticket_multiplier_for(customer.number, on_date) * 4) / 4
        hours = min(hours, round(target_billable - total_hours, 2))
        if hours < 0.25:
            continue
        project = project_for_customer(customer)
        entries.append(HourEntry(
            date=on_date, employee_id=employee_id,
            project_id=project.customer_id,
            activity_type=ActivityType.BILLABLE,
            hours=hours,
            description=f"Support — {customer.name}",
        ))
        total_hours += hours

    internal_hours = round(FULL_WORKDAY_HOURS - total_hours, 2)
    if internal_hours > 0:
        entries.append(HourEntry(
            date=on_date, employee_id=employee_id,
            activity_type=ActivityType.INTERNAL,
            hours=internal_hours,
            description="Interne møter / administrasjon",
        ))

    return entries


def generate_daily_hours(year: int, month: int, day: int, active_employee_ids: list[int]) -> list[HourEntry]:
    """Generuje wpisy godzin dla konkretnego dnia roboczego.

    Logika (Faza 6, Zadania 3/4):
    - Każdy aktywny billable pracownik: ~5% szans na chorobowe (0h billable, wpis SICK).
    - Leveranse: model ticketowy (generate_daily_support_hours) na portfelu
      obejmującym wszystkich aktywnych klientów.
    - Teknologi: pełny dzień (7.5h billable) u klienta w aktywnym onboardingu
      (zob. select_active_onboarding_clients, DEVELOPERS_PER_ONBOARDING
      określa którzy konsultanci są przydzieleni), inaczej model ticketowy na
      portfelu klientów w fazie MAINTENANCE.
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
    # Faza 7, Zadanie 2c — active_customers() zna tylko statyczny churn_date;
    # dokładamy event_aware_is_customer_active, żeby klient po BANKRUPTCY
    # (client_events) zniknął z portfela wsparcia od następnego miesiąca,
    # tak samo jak z order_generator.
    customers = [c for c in active_customers(d) if event_aware_is_customer_active(c, d)]

    leveranse_employees = [e for e in billable_employees if e.department_number == LEVERANSE_DEPARTMENT]
    teknologi_employees = [e for e in billable_employees if e.department_number == TEKNOLOGI_DEPARTMENT]

    support_assignment = assign_customers_to_consultants(customers, leveranse_employees, year, month)

    active_onboarding = select_active_onboarding_clients(customers, d)
    onboarding_employee_ids: set[int] = set()
    if active_onboarding and teknologi_employees:
        onboarding_client = active_onboarding[0]
        n_devs = min(DEVELOPERS_PER_ONBOARDING[onboarding_client.segment], len(teknologi_employees))
        assigned_devs = sorted(teknologi_employees, key=lambda e: e.number)[:n_devs]
        onboarding_employee_ids = {int(e.number[1:]) for e in assigned_devs}

    maintenance_customers = [c for c in customers if client_lifecycle_phase(c, d) == "MAINTENANCE"]
    maintenance_assignment = assign_customers_to_consultants(maintenance_customers, teknologi_employees, year, month)

    for emp_id in billable_ids:
        if rng.random() < SICK_PROBABILITY:
            entries.append(HourEntry(
                date=d, employee_id=emp_id,
                activity_type=ActivityType.SICK,
                hours=0.0,
                description="Sykefravær",
            ))
            continue

        employee = employee_by_id(emp_id)

        if employee.department_number == LEVERANSE_DEPARTMENT:
            entries.extend(generate_daily_support_hours(emp_id, support_assignment.get(emp_id, []), d, rng))
        elif emp_id in onboarding_employee_ids:
            onboarding_client = active_onboarding[0]
            project = project_for_customer(onboarding_client)
            entries.append(HourEntry(
                date=d, employee_id=emp_id,
                project_id=project.customer_id,
                activity_type=ActivityType.BILLABLE,
                hours=FULL_WORKDAY_HOURS,
                description=f"Prosjektarbeid (onboarding) — {project.number}",
            ))
        else:
            entries.extend(generate_daily_support_hours(emp_id, maintenance_assignment.get(emp_id, []), d, rng))

    return entries
