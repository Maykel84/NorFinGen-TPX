"""Round 4, step 3: natural variability and the margin recalibration (decision D1)."""

from datetime import date

import pytest

from norfingen.generators import opex_extras
from norfingen.generators import order_generator as og
from norfingen.generators.opex_generator import generate_monthly_opex
from norfingen.generators.revenue_variability import NOISE_STD, SEASONALITY, usage_factor
from norfingen.seed.payroll import first_working_day_of_month
from norfingen.seed.roster import EMPLOYEES, cogs_volume_discount

YEARS = range(2019, 2027)


# ------------------------------------------------------------------ revenue variability
@pytest.mark.parametrize("code", ["S01", "S02", "S03"])
def test_the_usage_factors_of_a_year_average_exactly_one(code):
    for year in YEARS:
        factors = [usage_factor(code, year, m) for m in range(1, 13)]
        assert abs(sum(factors) / 12 - 1.0) < 1e-9, (code, year)
        assert all(0.55 < f < 1.45 for f in factors), (code, year, factors)


def test_s04_consulting_and_unknown_services_are_not_modulated():
    assert all(usage_factor("S04", y, m) == 1.0 for y in YEARS for m in range(1, 13))


def test_the_factors_are_deterministic_and_differ_between_years_and_services():
    assert usage_factor("S02", 2024, 5) == usage_factor("S02", 2024, 5)
    assert usage_factor("S02", 2024, 5) != usage_factor("S02", 2025, 5)
    assert usage_factor("S02", 2024, 5) != usage_factor("S03", 2024, 5)


def test_july_is_the_quiet_month_for_usage_and_projects():
    """fellesferie: S02 (Azure consumption) and S03 (security projects) are below their yearly mean in July in most years (noise can
    lift one July, e.g. S02 2021) and clearly below the other months on average."""
    for code in ("S02", "S03"):
        below = sum(usage_factor(code, y, 7) < 1.0 for y in YEARS)
        assert below >= 6, (code, below)
        july_avg = sum(usage_factor(code, y, 7) for y in YEARS) / len(YEARS)
        rest_avg = sum(usage_factor(code, y, m) for y in YEARS for m in (3, 4, 5, 9, 10)) / (len(YEARS) * 5)
        assert july_avg < rest_avg - 0.08, (code, july_avg, rest_avg)
    s01_july = sum(usage_factor("S01", y, 7) for y in YEARS) / len(YEARS)
    s01_rest = sum(usage_factor("S01", y, m) for y in YEARS for m in (3, 4, 5, 9, 10)) / (len(YEARS) * 5)
    assert s01_july < s01_rest


def test_the_configured_variability_is_sane():
    assert set(SEASONALITY) == set(NOISE_STD) == {"S01", "S02", "S03"}
    assert all(0 < std <= 0.15 for std in NOISE_STD.values())


def test_a_subscription_line_carries_the_usage_factor_of_its_service_and_month():
    """K01 (Enterprise) buys S01-S03: the same customer, the same price list, the amount differs only by the factor of the month."""
    jan = {l.product.id: l.unitPriceExcludingVatCurrency for l in next(o for o in og.generate_monthly_orders(2024, 1) if o.customer.id == 1).orderLines}
    jul = {l.product.id: l.unitPriceExcludingVatCurrency for l in next(o for o in og.generate_monthly_orders(2024, 7) if o.customer.id == 1).orderLines}
    for product_id, code in ((1, "S01"), (2, "S02"), (7, "S03")):
        if product_id in jan and product_id in jul:
            ratio = jul[product_id] / jan[product_id]
            expected = usage_factor(code, 2024, 7) / usage_factor(code, 2024, 1)
            assert abs(ratio - expected) < 0.001, (code, ratio, expected)


def test_the_yearly_revenue_stays_what_the_price_list_says(monkeypatch):
    """The factors move revenue between months, they do not create it: the yearly subscription revenue is within 0.5 % of the same
    year without any variability."""
    def year_revenue():
        return sum(l.amountExcludingVatCurrency for m in range(1, 13) for o in og.generate_monthly_orders(2024, m) for l in o.orderLines)

    with_factors = year_revenue()
    monkeypatch.setattr(og, "usage_factor", lambda code, year, month: 1.0)
    without = year_revenue()
    assert abs(with_factors / without - 1) < 0.005, (with_factors, without)


# ------------------------------------------------------------------ opex with spikes
def test_the_extra_costs_of_a_year_add_up_to_its_budget_to_the_cent():
    for year in YEARS:
        total = round(sum(c.net for c in opex_extras.extra_costs_for_year(year)), 2)
        assert total == round(opex_extras.EXTRA_OPEX_NET_BY_YEAR[year], 2), year
    assert opex_extras.extra_costs_for_year(2019) == ()


def test_the_extras_have_the_calendar_of_a_real_company():
    for year in range(2020, 2027):
        items = opex_extras.extra_costs_for_year(year)
        kinds = {c.kind for c in items}
        assert {"licenses", "audit", "marketing", "repairs"} <= kinds
        assert [c.month for c in items if c.kind == "licenses"] == [1]                    # annual licences in January
        assert all(c.month in (4, 5) for c in items if c.kind == "audit")                 # the auditor comes in spring
        assert len([c for c in items if c.kind == "marketing"]) == 4 and all(c.month != 7 for c in items if c.kind == "marketing")
        assert len({c.month for c in items if c.kind == "repairs"}) == 3
        assert all(c.net > 0 for c in items)


def test_every_hire_costs_a_recruitment_fee_the_month_before_the_start():
    hires = [e for e in EMPLOYEES if e.phase == "scaling2"]
    assert len(hires) == 5
    for hire in hires:
        month = hire.start_date.month - 1 or 12
        year = hire.start_date.year if hire.start_date.month > 1 else hire.start_date.year - 1
        fees = [c for c in opex_extras.extra_costs(year, month) if c.kind == "recruitment"]
        assert any(c.net == round(hire.annual_salary * 0.2, -2) for c in fees), hire.number


def test_extras_are_cash_purchases_with_25_percent_vat_in_the_months_they_fall_in():
    vouchers = generate_monthly_opex(2025, 1)                                          # January: the annual licences
    licence = [v for v in vouchers if v.description.startswith("Årslisenser")]
    assert len(licence) == 1
    postings = {p.account.number: p.amount for p in licence[0].postings}
    net = postings[6410]
    assert postings[2710] == round(net * 0.25, 2) and postings[1910] == -round(net * 1.25, 2)
    assert not any(v.description.startswith("Årslisenser") for v in generate_monthly_opex(2025, 3))


# ------------------------------------------------------------------ COGS volume discount and the team
def test_the_cogs_volume_discount_grows_with_scale_and_never_goes_up():
    assert [cogs_volume_discount(y) for y in (2019, 2022)] == [1.0, 1.0]
    values = [cogs_volume_discount(y) for y in range(2022, 2028)]
    assert values == sorted(values, reverse=True) and values[-1] == cogs_volume_discount(2030)
    assert cogs_volume_discount(2026) < cogs_volume_discount(2024) < cogs_volume_discount(2023) < 1.0


def test_the_new_hires_start_on_the_first_working_day_of_their_month():
    for e in EMPLOYEES:
        assert e.start_date == first_working_day_of_month(e.start_date.year, e.start_date.month), e.number
