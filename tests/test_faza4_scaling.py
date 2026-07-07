from datetime import date

from norfingen.generators.hours_generator import is_billable_employee
from norfingen.generators.opex_generator import generate_monthly_opex
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.supplier_invoice_generator import generate_monthly_supplier_invoices
from norfingen.seed.roster import EMPLOYEES, active_customers, calc_target_headcount


def _billable_employees_at(year: int, month: int) -> list:
    on_date = date(year, month, 1)
    return [e for e in EMPLOYEES if e.start_date <= on_date and is_billable_employee(int(e.number[1:]))]


def _employees_at(year: int, month: int) -> list:
    on_date = date(year, month, 1)
    return [e for e in EMPLOYEES if e.start_date <= on_date]


def test_customer_count_reaches_target():
    """Docelowo 50 klientów onboardowanych do 2026 (48 aktywni po 2 churnach SMB)."""
    all_active_2026 = active_customers(date(2026, 6, 30))
    assert 40 <= len(all_active_2026) <= 50


def test_target_headcount_tracks_actual_hiring_within_tolerance():
    """Zespół faktycznie zatrudniony (EMPLOYEES) nie powinien odbiegać od
    calc_target_headcount() (rachunek top-down z celu marży, korekta #4)
    o więcej niż ~25% w żadnym roku 2023-2026 — to nie twardy warunek co do
    joty (harmonogram rekrutacji ustalony wcześniej niż dokładny przychód
    danego miesiąca), ale zgrubna kontrola sanity, żeby wychwycić rażące
    niedopasowanie w przyszłych sesjach."""
    for year in (2023, 2024, 2025, 2026):
        month = 7 if year == 2026 else 12
        revenue = sum(
            l.amountExcludingVatCurrency
            for o in generate_monthly_orders(year, month)
            for l in o.orderLines
        ) * 12  # przybliżenie roczne z jednego miesiąca (sezonowość uśredniona w teście offline)
        opex_cogs = sum(
            p.amount
            for v in generate_monthly_opex(year, month)
            for p in v.postings if p.amount > 0
        ) * 12
        supplier_cost = sum(
            inv.amountExcludingVatCurrency for inv in generate_monthly_supplier_invoices(year, month)
        ) * 12
        target = calc_target_headcount(revenue, opex_cogs + supplier_cost)
        actual = len(_employees_at(year, month))
        assert abs(actual - target) <= max(8, target * 0.25), \
            f"{year}: actual={actual} target={target} (revenue={revenue:.0f})"


def test_new_hires_individually_staggered():
    """Nowi pracownicy (E17+) mają różne, pojedyncze daty startu — nie grupowe
    (w przeciwieństwie do fuzji 2022-09, gdzie 6 osób startowało tego samego dnia)."""
    new_hire_dates = [e.start_date for e in EMPLOYEES if int(e.number[1:]) >= 17]
    assert len(new_hire_dates) == 22
    assert len(set(new_hire_dates)) == len(new_hire_dates)  # wszystkie unikalne


def test_new_hires_spaced_at_least_two_months_apart():
    new_hire_dates = sorted(e.start_date for e in EMPLOYEES if int(e.number[1:]) >= 17)
    for earlier, later in zip(new_hire_dates, new_hire_dates[1:]):
        gap_days = (later - earlier).days
        assert gap_days >= 60, f"Rekrutacje zbyt blisko siebie: {earlier} -> {later} ({gap_days} dni)"


def test_new_hires_include_billable_and_support_roles():
    # Faza 4 korekta #4 (finalna): 20 billable (Leveranse/Teknologi) + 2 role
    # wspierające (Salg/Økonomi) — 22 rekrutacje to maksimum mieszczące się
    # przy odstępach >=60 dni w oknie 2022-10 -> 2026-03 (fizyczne
    # ograniczenie okna czasowego, nie wybór).
    new_hires = [e for e in EMPLOYEES if int(e.number[1:]) >= 17]
    billable = [e for e in new_hires if e.department_number in (2, 3)]
    support = [e for e in new_hires if e.department_number in (1, 4)]
    assert len(billable) == 20
    assert len(support) == 2
