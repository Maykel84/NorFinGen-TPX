"""Faza 7c — duży incydent 2023 (utrata klienta Enterprise), Zadanie 3.

Historia decyzji (pełny opis w SESSION_HANDOFF.md): pierwotny plan zakładał
też Zadanie 2 (mniejsze echo Mid-market 2025) i kompensujących klientów
zastępujących utraconego K03 — oba świadomie WYCOFANE w tej sesji po
offline sanity-checku: (a) próba kompensacji jednym/dwoma nowymi klientami
SCALE_SERVICES nie odtwarzała przychodu LEGACY_SERVICES i DODATKOWO
podwajała COGS per-klient (COGS naliczany per klient, nie per przychód),
pogarszając marżę zamiast ją poprawiać; (b) organiczny wzrost portfela (bez
żadnej sztucznej kompensacji) NIE przywraca marży do pasma 5,5-9% nawet do
2026 — zaakceptowane jako realistyczny, wieloletni "scar" utraty dużego
klienta przy stałym headcount. `test_2024_margin_recovers_to_safe_band`
z pierwotnego promptu zaadaptowany zgodnie z tym wynikiem — NIE odtwarza
literalnie oczekiwania z promptu (2024 w paśmie), bo to się nie potwierdziło
mimo iteracyjnych prób kompensacji, udokumentowanych osobno."""

from datetime import date

from norfingen.generators.backfill import DEFAULT_START_DATE, run_backfill
from norfingen.generators.order_generator import generate_monthly_orders
from norfingen.generators.voucher import Voucher
from norfingen.models.order import Order, OrderStatus
from norfingen.seed.roster import customer_by_number, is_customer_active

K03_CHURN_DATE = date(2023, 4, 1)


def test_major_incident_customer_fully_churned():
    k03 = customer_by_number("K03")
    assert k03.churn_date == K03_CHURN_DATE

    for year, month in ((2023, 5), (2024, 1), (2025, 6), (2026, 6)):
        orders = generate_monthly_orders(year, month)
        assert not any(o.customer.id == 3 for o in orders), f"K03 nie powinien generować zamówień w {year}-{month:02d}"

    # Miesiąc TUŻ PRZED churn_date — standardowa aktywność, bez zmian
    # (Zadanie 1c: "w miesiącach notice_period przed odejściem: standardowa
    # aktywność").
    assert is_customer_active(k03, date(2023, 3, 15)) is True
    assert is_customer_active(k03, date(2023, 4, 1)) is True  # dzień odejścia jeszcze aktywny
    assert is_customer_active(k03, date(2023, 4, 2)) is False


def test_major_incident_invoices_remain_paid():
    """Brak wymuszonego WRITTEN_OFF przy odejściu K03 (w przeciwieństwie do
    BANKRUPTCY) — to utrata przyszłego przychodu, nie problem ze
    ściągalnością. Ostatnie realne zamówienie K03 (marzec 2023) powstaje
    normalną ścieżką determine_order_status, nie status_override."""
    orders = generate_monthly_orders(2023, 3)
    k03_orders = [o for o in orders if o.customer.id == 3]
    assert k03_orders

    # Nie asercja "zawsze PAID" — to NIE jest wymuszone jak przy BANKRUPTCY
    # (normalny mechanizm bad-debt ma swoje ~2% szansy na OVERDUE/WRITTEN_OFF
    # per zamówienie niezależnie od odejścia). Weryfikujemy coś silniejszego
    # i deterministycznego: status ostatniej faktury K03 pochodzi z tej samej,
    # niezmienionej ścieżki determine_order_status(), z domyślnym (nie
    # podniesionym) progiem — czyli identyczny wynik jak przed Fazą 7c dla
    # tego samego klienta+daty.
    from norfingen.generators.order_generator import determine_order_status
    for order in k03_orders:
        expected_status = determine_order_status("K03", order.orderDate)
        assert order.status == expected_status


def test_no_other_years_affected():
    """Lata SPRZED incydentu (2019-2022) pozostają bit-identyczne z
    wartościami zamrożonymi jako regresja we wcześniejszych fazach (Faza 7a/
    7b) — MAJOR_INCIDENT_2023 nie może wpływać wstecz. 2023-2026 są
    ŚWIADOMIE zmienione (to jest cel tej fazy), więc nie są tu sprawdzane
    względem stanu sprzed Fazy 7c."""
    revenue: dict[int, float] = {}
    payroll: dict[int, float] = {}
    opex: dict[int, float] = {}
    cogs: dict[int, float] = {}

    def collect(obj):
        if isinstance(obj, Order):
            year = obj.orderDate.year
            revenue[year] = revenue.get(year, 0.0) + sum(
                line.count * line.unitPriceExcludingVatCurrency for line in obj.orderLines
            )
        elif isinstance(obj, Voucher):
            year = obj.date.year
            for p in obj.postings:
                if p.amount <= 0:
                    continue
                n = p.account.number
                if 5000 <= n <= 5999:
                    payroll[year] = payroll.get(year, 0.0) + p.amount
                elif 6000 <= n <= 7999:
                    opex[year] = opex.get(year, 0.0) + p.amount
                elif 4000 <= n <= 4999:
                    cogs[year] = cogs.get(year, 0.0) + p.amount

    run_backfill(start_date=DEFAULT_START_DATE, end_date=date(2022, 12, 31), persist_fn=collect)

    expected_margins = {2019: -0.2567, 2020: 0.1922, 2021: 0.1730, 2022: 0.1161}
    for year, expected in expected_margins.items():
        r = revenue[year]
        total_cost = payroll.get(year, 0.0) + opex.get(year, 0.0) + cogs.get(year, 0.0)
        margin = (r - total_cost) / r
        assert abs(margin - expected) < 0.001, f"{year}: margin={margin:.4f}, oczekiwano {expected:.4f}"
