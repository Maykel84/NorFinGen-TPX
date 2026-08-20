"""Faza 7, Zadanie 3 — zdarzenia losowe na poziomie firmy."""

from norfingen.generators.company_events import (
    COMPANY_LIFE_EVENTS,
    UNPROFITABLE_QUARTER_COST_SPIKE_MAX,
    UNPROFITABLE_QUARTER_COST_SPIKE_MIN,
    equipment_investment_trigger,
    roll_company_events,
    supplier_cost_multiplier,
    unprofitable_quarter_cost_spike,
    unprofitable_quarter_ticket_multiplier,
)

# Zdarzenia znalezione deterministycznie na 2019-2026 (zob. SESSION_HANDOFF.md
# Faza 7, Zadanie 3) — zamrożone jako regresja, tak jak test_client_events.py.
UNPROFITABLE_2020 = (2020, 4)
EQUIPMENT_2022 = (2022, 1)
UNPROFITABLE_2022 = (2022, 4)
RENEGOTIATION_2025 = (2025, 9)


def test_roll_company_events_deterministic():
    assert roll_company_events(2020) == roll_company_events(2020)


def test_equipment_investment_only_in_exact_triggered_month():
    year, month = EQUIPMENT_2022
    amount = equipment_investment_trigger(year, month)
    amount_min, amount_max = COMPANY_LIFE_EVENTS["EQUIPMENT_INVESTMENT"]["amount_range"]
    assert amount is not None
    assert amount_min <= amount <= amount_max
    assert equipment_investment_trigger(year, month + 1) is None
    assert equipment_investment_trigger(year - 1, month) is None


def test_unprofitable_quarter_ticket_multiplier_covers_whole_quarter():
    year, month = UNPROFITABLE_2020  # kwiecień -> Q2 (kwi-cze)
    q2_months = (4, 5, 6)
    assert month in q2_months
    for m in q2_months:
        mult = unprofitable_quarter_ticket_multiplier(year, m)
        assert 0.85 <= mult <= 0.95
    # miesiące spoza kwartału — bez zmian
    assert unprofitable_quarter_ticket_multiplier(year, 3) == 1.0
    assert unprofitable_quarter_ticket_multiplier(year, 7) == 1.0


def test_unprofitable_quarter_cost_spike_only_exact_month():
    year, month = UNPROFITABLE_2022
    spike = unprofitable_quarter_cost_spike(year, month)
    assert spike is not None
    assert UNPROFITABLE_QUARTER_COST_SPIKE_MIN <= spike <= UNPROFITABLE_QUARTER_COST_SPIKE_MAX
    # sąsiednie miesiące tego samego kwartału NIE dostają kosztu (jednorazowy)
    assert unprofitable_quarter_cost_spike(year, month + 1) is None


def test_supplier_renegotiation_permanent_from_trigger_month():
    year, month = RENEGOTIATION_2025
    before_year, before_month = (year, month - 1)
    multipliers_before = {s: supplier_cost_multiplier(s, before_year, before_month) for s in
                           ("L01", "L02", "L03", "L04", "L05", "L06", "L07", "L08")}
    multipliers_after = {s: supplier_cost_multiplier(s, year, month) for s in multipliers_before}
    assert multipliers_before != multipliers_after  # dokładnie jeden dostawca się zmienił

    changed = [s for s in multipliers_before if multipliers_before[s] != multipliers_after[s]]
    assert len(changed) == 1

    # trwałe — zostaje zmienione miesiąc, rok i więcej lat później
    assert supplier_cost_multiplier(changed[0], year, month + 1) == multipliers_after[changed[0]]
    assert supplier_cost_multiplier(changed[0], year + 1, 1) == multipliers_after[changed[0]]


def test_equipment_investment_invoice_appears_in_trigger_month():
    from norfingen.generators.supplier_invoice_generator import generate_monthly_supplier_invoices

    year, month = EQUIPMENT_2022
    invoices = generate_monthly_supplier_invoices(year, month)
    equip_invoices = [i for i in invoices if i.invoiceNumber.endswith("-EQUIP")]
    assert len(equip_invoices) == 1
    assert equip_invoices[0].account.id == 1200  # skapitalizowane — kwota zawsze > progu 30k


def test_full_history_no_crash():
    from norfingen.generators.hours_generator import generate_daily_hours
    from norfingen.generators.opex_generator import generate_monthly_opex
    from norfingen.generators.supplier_invoice_generator import generate_monthly_supplier_invoices

    for year in range(2019, 2027):
        for month in range(1, 13):
            if (year, month) > (2026, 7):
                continue
            generate_monthly_supplier_invoices(year, month)
            generate_monthly_opex(year, month)
    generate_daily_hours(2022, 4, 15, list(range(1, 18)))  # miesiąc UNPROFITABLE_QUARTER 2022
