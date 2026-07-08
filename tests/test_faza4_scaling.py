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


def test_only_one_new_hire_after_merger():
    """Faza 6 (2. kalibracja) ZASTĘPUJE Fazę 4 — zespół przestaje rosnąć z
    portfelem klientów po jednym dociążeniu tuż po fuzji (E17). Poprzednie 21
    dalsze rekrutacje (E18-E38) usunięte: kalibracja rynkowa (Brønnøysundregistrene)
    pokazała, że porównywalne firmy IT drift/support obsługują duży portfel
    małym zespołem, bo koszt obsługi jest głównie kosztem materiałowym (COGS
    pass-through S01/S02), nie osobowym — zob. roster.py, komentarz przy
    calc_s01_cogs_monthly."""
    new_hires = [e for e in EMPLOYEES if int(e.number[1:]) >= 17]
    assert len(new_hires) == 1
    assert new_hires[0].number == "E17"
    assert new_hires[0].department_number == 2  # Leveranse, billable
