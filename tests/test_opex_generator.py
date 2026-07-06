import random

from norfingen.generators.opex_generator import (
    ACCOUNT_CANTEEN,
    ACCOUNT_SERVICE_EQUIPMENT,
    calc_service_equipment_cost,
    generate_conference_trip,
    generate_monthly_opex,
    should_generate_service_equipment_purchase,
)
from norfingen.seed.roster import (
    CANTEEN_SUBSIDY_PER_EMPLOYEE_MONTHLY,
    calc_canteen_cost,
    calc_client_visit_transport,
    calc_representation_cost,
    customer_by_number,
)


def test_canteen_cost_scales_with_employee_count():
    cost_16 = calc_canteen_cost(16)
    cost_20 = calc_canteen_cost(20)
    assert cost_20 > cost_16
    assert cost_16 == 16 * CANTEEN_SUBSIDY_PER_EMPLOYEE_MONTHLY


def test_representation_cost_only_enterprise_and_mid():
    smb_customer = customer_by_number("K04")  # SMB
    enterprise_customer = customer_by_number("K01")  # Enterprise
    assert calc_representation_cost([smb_customer]) == 0
    assert calc_representation_cost([enterprise_customer]) > 0


def test_representation_cost_mid_lower_than_enterprise():
    enterprise_customer = customer_by_number("K01")
    mid_customer = customer_by_number("K02")
    assert calc_representation_cost([mid_customer]) < calc_representation_cost([enterprise_customer])


def test_client_visit_transport_zero_outside_seasonal_months():
    enterprise_customer = customer_by_number("K01")
    # Enterprise ma spotkania tylko w lutym/maju/sierpniu/listopadzie.
    assert calc_client_visit_transport([enterprise_customer], 1) == 0
    assert calc_client_visit_transport([enterprise_customer], 2) > 0


def test_service_equipment_only_at_onboarding_month():
    """Koszt sprzętu do wdrożenia pojawia się tylko w miesiącu onboardingu."""
    customer = customer_by_number("K01")
    onboarding_month = customer.onboarding_date.month
    assert should_generate_service_equipment_purchase(customer, onboarding_month, random.Random(1))
    other_month = (onboarding_month % 12) + 1
    assert not should_generate_service_equipment_purchase(customer, other_month, random.Random(1))


def test_service_equipment_not_generated_for_smb():
    smb_customer = customer_by_number("K04")  # SMB
    assert not should_generate_service_equipment_purchase(
        smb_customer, smb_customer.onboarding_date.month, random.Random(1),
    )


def test_service_equipment_cost_within_segment_range():
    enterprise_customer = customer_by_number("K01")
    mid_customer = customer_by_number("K02")
    assert 45_000 <= calc_service_equipment_cost(enterprise_customer) <= 90_000
    assert 15_000 <= calc_service_equipment_cost(mid_customer) <= 35_000


def test_service_equipment_cost_deterministic():
    customer = customer_by_number("K01")
    assert calc_service_equipment_cost(customer) == calc_service_equipment_cost(customer)


def test_generate_monthly_opex_does_not_repeat_equipment_cost_across_years():
    """K01 onboarduje się 2019-03-01 — koszt sprzętu wdrożeniowego może
    wystąpić tylko w marcu 2019, nie w marcu 2020/2021/... (zabezpieczenie
    przed powtarzającym się co roku kosztem jednorazowym)."""
    onboarding_year_vouchers = generate_monthly_opex(2019, 3)
    other_year_vouchers = generate_monthly_opex(2020, 3)

    def has_equipment_cost(vouchers):
        return any(
            p.account.number == ACCOUNT_SERVICE_EQUIPMENT
            for v in vouchers for p in v.postings
        )

    assert has_equipment_cost(onboarding_year_vouchers)
    assert not has_equipment_cost(other_year_vouchers)


def test_generate_monthly_opex_includes_canteen_every_month():
    vouchers = generate_monthly_opex(2024, 1)
    canteen = [v for v in vouchers if v.postings[0].account.number == ACCOUNT_CANTEEN]
    assert len(canteen) == 1


def test_generate_monthly_opex_vouchers_balance():
    for year, month in [(2019, 1), (2019, 3), (2024, 3), (2024, 9)]:
        for voucher in generate_monthly_opex(year, month):
            assert voucher.validate_balance(), f"Niezbalansowany voucher: {voucher.description}"


def test_conference_trip_only_in_allowed_months():
    for month in range(1, 13):
        trip = generate_conference_trip(2024, month, random.Random(f"test-{month}"))
        if trip is not None:
            assert month in (3, 9, 11)


def test_conference_trip_deterministic():
    rng1 = random.Random("conference-2024-3")
    rng2 = random.Random("conference-2024-3")
    assert generate_conference_trip(2024, 3, rng1) == generate_conference_trip(2024, 3, rng2)
