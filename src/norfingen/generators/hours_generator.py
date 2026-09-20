"""HourEntry — daily timesheet generator (Layer 2/3, Tier 4).

Logs hours only for employees in the Leveranse/Teknologi departments
(billable — see is_billable_employee), except E05 (System Architect — a
technical/architectural role, never billable, set before Phase 4).

Phase 6, Tasks 3/4 — replaces the "one customer per day" pattern (Phase 4)
with two department-dependent models, because in a small (17-person) team
serving 48 active customers, one consultant physically MUST service
multiple customers per day:
  - Leveranse (support, all customers) — a ticketing model
    (generate_daily_support_hours): several customers per day, short hour
    blocks proportional to segment (TICKET_AVG_HOURS).
  - Teknologi (projects/implementations) — a customer lifecycle model
    (client_lifecycle_phase): a full day at the customer during the
    ONBOARDING phase (the first weeks after onboarding_date), otherwise
    dispersed maintenance across several customers in the MAINTENANCE phase.

This change is PURELY about hour_entries realism — it has no effect on
revenue (order_generator) or payroll (salary_generator, independent of
hours), so it does not change the result of the offline margin sanity-check
(see SESSION_HANDOFF.md, Phase 6).

The customer-consultant portfolio is still assigned by
assign_customers_to_consultants(), rotating every ~15 months (see
_rotation_id) — now called separately for the Leveranse pool (all
customers) and the Teknologi pool (only customers in the MAINTENANCE phase,
customers in ONBOARDING have a dedicated team, see
select_active_onboarding_clients)."""

from __future__ import annotations

import random
from datetime import date, timedelta

from norfingen.generators.client_events import event_aware_is_customer_active, hardship_ticket_multiplier_for
from norfingen.generators.company_events import unprofitable_quarter_ticket_multiplier
from norfingen.generators.leave_events import active_leave_period
from norfingen.generators.macro_shock import apply_macro_shock_multiplier
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
NON_BILLABLE_OVERRIDES = {5}  # E05 System Architect — never billable (set before Phase 4)
LEVERANSE_DEPARTMENT = 2
TEKNOLOGI_DEPARTMENT = 3

FULL_WORKDAY_HOURS = 7.5
SICK_PROBABILITY = 0.05  # short, self-certified single-day sick leave

LEAVE_DESCRIPTIONS = {
    ActivityType.SICK: "Sykefravær",
    ActivityType.MATERNITY_LEAVE: "Foreldrepermisjon",
    ActivityType.PATERNITY_LEAVE: "Foreldrepermisjon (fedrekvote)",
}

BASE_YEAR = 2019
ROTATION_PERIOD_QUARTERS = 5  # ~15 months (the 12-18 range from the task)

MAX_CONSULTANT_CAPACITY_HOURS = HOURS_PER_YEAR_PER_CONSULTANT / 12 * UTILIZATION_TARGET

# Phase 6, Task 3 — Leveranse ticketing model: a consultant serves several
# customers per day instead of one. Average ticket duration increases with
# segment (Enterprise: more complex incidents/infrastructure).
TICKET_AVG_HOURS: dict[str, float] = {
    "Enterprise": 1.2,
    "Mid-market": 0.9,
    "SMB": 0.6,
}
TICKET_TARGET_BILLABLE_MIN = 5.5
TICKET_TARGET_BILLABLE_MAX = 7.0
TICKET_CLIENTS_PER_DAY_MIN = 2
TICKET_CLIENTS_PER_DAY_MAX = 5

# Phase 6, Task 4 — customer lifecycle for Teknologi: a full day at the
# customer during implementation (ONBOARDING), then dispersed maintenance
# (MAINTENANCE). CONCURRENT_ONBOARDING_CAPACITY=1 — the small (2-person)
# Teknologi team runs one active implementation project at a time, not
# several in parallel.
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
    """Mon-Fri, without Norwegian holidays (simplified)."""
    return d.weekday() < 5


def is_billable_employee(employee_id: int) -> bool:
    """Whether an employee logs billable hours — Leveranse/Teknologi
    department, minus explicit exceptions (NON_BILLABLE_OVERRIDES). Replaces
    the static BILLABLE_EMPLOYEES list from before Phase 4 — now works for
    any number of employees (E17+ is automatically billable, since they're
    in these departments)."""
    if employee_id in NON_BILLABLE_OVERRIDES:
        return False
    employee = employee_by_id(employee_id)
    return employee.department_number in BILLABLE_DEPARTMENTS


def _rotation_id(year: int, month: int) -> int:
    """Identifier of the customer-consultant portfolio rotation period
    (~15 months, see the module-level docstring, Task 5c) — changes every
    ROTATION_PERIOD_QUARTERS quarters, NOT every month. A deliberate
    deviation from the task's pseudocode (which reseeded the rng fresh EVERY
    month — contradicting the "rotate every 12-18 months" requirement, since
    that would give a completely new assignment every month instead of a
    stable portfolio with periodic rotation)."""
    quarter_index = (year - BASE_YEAR) * 4 + (month - 1) // 3
    return quarter_index // ROTATION_PERIOD_QUARTERS


def assign_customers_to_consultants(
    customers: list[CustomerSeed],
    billable_employees: list[EmployeeSeed],
    year: int,
    month: int,
) -> dict[int, list[CustomerSeed]]:
    """Assigns customers to consultants so that the sum of hours per
    consultant doesn't exceed available capacity
    (roster.SEGMENT_HOURS_PER_MONTH, MAX_CONSULTANT_CAPACITY_HOURS).
    Deterministic — seeded from the rotation period (see _rotation_id), not
    from the exact (year, month), so the portfolio stays stable for ~15
    months instead of changing every month (Task 5c)."""
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
            continue  # no free capacity — customer unserved this month (shouldn't happen, see roster.can_onboard_new_customer)
        chosen = min(available, key=lambda e: employee_load[int(e.number[1:])])
        chosen_id = int(chosen.number[1:])
        assignment[chosen_id].append(customer)
        employee_load[chosen_id] += hours_needed

    return assignment


def client_lifecycle_phase(customer: CustomerSeed, on_date: date) -> str:
    """Phase 6, Task 4 — the customer's lifecycle phase from Teknologi's
    perspective: "ONBOARDING" for ONBOARDING_DURATION_WEEKS[segment] weeks
    from onboarding_date (a full day at the customer), then "MAINTENANCE"
    (dispersed maintenance). Does not model a separate STABILIZATION phase —
    a deliberate simplification, since the task doesn't give it a concrete
    duration (unlike ONBOARDING)."""
    onboarding_end = customer.onboarding_date + timedelta(weeks=ONBOARDING_DURATION_WEEKS[customer.segment])
    if customer.onboarding_date <= on_date < onboarding_end:
        return "ONBOARDING"
    return "MAINTENANCE"


def select_active_onboarding_clients(customers: list[CustomerSeed], on_date: date) -> list[CustomerSeed]:
    """Customers currently in implementation, capped at
    CONCURRENT_ONBOARDING_CAPACITY (the earliest onboarded take priority —
    deterministic, no randomness) — the small Teknologi team runs one
    implementation project at a time, even if several customers happen to be
    in their onboarding window simultaneously by the calendar."""
    onboarding_now = [c for c in customers if client_lifecycle_phase(c, on_date) == "ONBOARDING"]
    onboarding_now.sort(key=lambda c: c.onboarding_date)
    return onboarding_now[:CONCURRENT_ONBOARDING_CAPACITY]


def generate_daily_support_hours(
    employee_id: int,
    assigned_customers: list[CustomerSeed],
    on_date: date,
    rng: random.Random,
) -> list[HourEntry]:
    """Phase 6, Task 3 — the ticketing model: a consultant serves several
    (TICKET_CLIENTS_PER_DAY_MIN..MAX) customers from their portfolio per day,
    instead of one 6-7.5h block at a single customer (Phase 4). The billable
    total aims for a random target (5.5-7.0h), the remainder up to 7.5h is
    logged as INTERNAL. Used both for Leveranse (support for all customers)
    and for Teknologi in the MAINTENANCE phase (dispersed maintenance) —
    see the module-level docstring."""
    if not assigned_customers:
        return [HourEntry(
            date=on_date, employee_id=employee_id,
            activity_type=ActivityType.INTERNAL,
            hours=FULL_WORKDAY_HOURS,
            description="Interne møter / administrasjon (no assigned customer)",
        )]

    entries: list[HourEntry] = []
    total_hours = 0.0
    # Phase 7, Tasks 1a/3c — fellesferie (July, ~50%) and UNPROFITABLE_QUARTER
    # (company-wide, 0.85-0.95, whole quarter) reduce ticket volume.
    #
    # FIX (Task 4 — test_fellesferie_reduces_july_ticket_volume caught this
    # as a regression): the multiplier originally (Task 1) scaled ONLY
    # target_billable. In practice that almost never changed the outcome —
    # the loop below is usually actually bound by n_clients_today (a ceiling
    # of TICKET_CLIENTS_PER_DAY_MAX=5 x ~1h/ticket ≈ 5h, already below the
    # unreduced target_billable of 5.5-7h), so reducing target_billable
    # rarely mattered. The multiplier now also scales n_clients_today (the
    # actual, binding ceiling) — target_billable remains as an extra
    # safeguard in case of large customers/segments.
    #
    # Phase 7b, Task 1b — MACRO_SHOCK (COVID_2020, March-June 2020): stacks
    # multiplicatively on top of the above (apply_macro_shock_multiplier),
    # applies to ALL active customers simultaneously (a market-wide shock),
    # not randomly rolled like TEMPORARY_HARDSHIP — a deterministically
    # inserted historical fact for 2020, see macro_shock.py.
    activity_multiplier = fellesferie_activity_multiplier(on_date.month) * unprofitable_quarter_ticket_multiplier(on_date.year, on_date.month)
    activity_multiplier = apply_macro_shock_multiplier(on_date.year, on_date.month, activity_multiplier)
    target_billable = rng.uniform(TICKET_TARGET_BILLABLE_MIN, TICKET_TARGET_BILLABLE_MAX) * activity_multiplier
    n_clients_today = min(len(assigned_customers), rng.randint(TICKET_CLIENTS_PER_DAY_MIN, TICKET_CLIENTS_PER_DAY_MAX))
    n_clients_today = max(1, round(n_clients_today * activity_multiplier))
    todays_clients = rng.sample(assigned_customers, n_clients_today)

    for customer in todays_clients:
        if total_hours >= target_billable:
            break
        avg_hours = TICKET_AVG_HOURS[customer.segment]
        hours = round(rng.uniform(avg_hours * 0.6, avg_hours * 1.6) * 4) / 4  # rounded to 0.25h
        # Phase 7, Task 2c — TEMPORARY_HARDSHIP: reduces THIS customer's
        # ticket volume by 40-60% (not the consultant's whole day — other
        # customers on the same day are unaffected).
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
    """Generates hour entries for a specific working day.

    Logic (Phase 6, Tasks 3/4; leave periods added later, see leave_events.py):
    - Every active billable employee first checked against
      leave_events.active_leave_period — if they're inside a precomputed
      long-term SICK/MATERNITY_LEAVE/PATERNITY_LEAVE block, that's the whole
      day (0h billable, one entry), nothing else below applies to them.
    - Otherwise: ~5% chance of a short, self-certified sick day (0h billable,
      a SICK entry).
    - Leveranse: the ticketing model (generate_daily_support_hours) over a
      portfolio covering all active customers.
    - Teknologi: a full day (7.5h billable) at a customer in active
      onboarding (see select_active_onboarding_clients,
      DEVELOPERS_PER_ONBOARDING determines which consultants are assigned),
      otherwise the ticketing model over the portfolio of customers in the
      MAINTENANCE phase.
    - Deterministic per year+month+day (a local random.Random)."""
    d = date(year, month, day)
    if not is_working_day(d):
        return []

    entries: list[HourEntry] = []
    rng = random.Random(year * 10000 + month * 100 + day)

    billable_ids = [eid for eid in active_employee_ids if is_billable_employee(eid)]
    if not billable_ids:
        return []

    billable_employees = [employee_by_id(eid) for eid in billable_ids]
    # Phase 7, Task 2c — active_customers() only knows the static churn_date;
    # we additionally apply event_aware_is_customer_active, so a customer
    # that went through BANKRUPTCY (client_events) disappears from the
    # support portfolio starting next month, same as with order_generator.
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
        leave = active_leave_period(emp_id, d)
        if leave is not None:
            entries.append(HourEntry(
                date=d, employee_id=emp_id,
                activity_type=leave.activity_type,
                hours=0.0,
                description=LEAVE_DESCRIPTIONS[leave.activity_type],
            ))
            continue

        if rng.random() < SICK_PROBABILITY:
            entries.append(HourEntry(
                date=d, employee_id=emp_id,
                activity_type=ActivityType.SICK,
                hours=0.0,
                description=LEAVE_DESCRIPTIONS[ActivityType.SICK],
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
