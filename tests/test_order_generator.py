from datetime import date

from norfingen.generators.order_generator import (
    build_order_lines,
    determine_order_status,
    generate_daily_orders,
    generate_monthly_orders,
    should_generate_extra_consulting,
)
from norfingen.models.order import OrderStatus
from norfingen.seed.roster import CUSTOMER_PRICE_MULTIPLIER, customer_by_number, numeric_id, product_for_service


def test_pattern_a_b_c_generated_every_month():
    orders = generate_monthly_orders(2024, 1)
    by_customer = {o.customer.id: o for o in orders}
    # K01 (Enterprise, pattern B) ma 11 klientów A/B/C generujących Order co miesiąc
    # (K06 to pattern D, losowy — może, ale nie musi, wystąpić w danym miesiącu).
    assert len(orders) >= 11

    for order in orders:
        assert order.invoiceDate == order.orderDate
        # orderDate.day = customer.invoice_day (per klient, nie sztywno 1. dzień).
        assert order.department.id == 1
        assert len(order.orderLines) >= 1


def test_monthly_orders_use_customer_invoice_day():
    orders = generate_monthly_orders(2024, 1)
    k02 = next(o for o in orders if o.customer.id == 2)  # invoice_day=7
    k07 = next(o for o in orders if o.customer.id == 7)  # invoice_day=15
    assert k02.orderDate.day == 7
    assert k07.orderDate.day == 15


def test_monthly_orders_use_customer_payment_terms():
    orders = generate_monthly_orders(2024, 1)
    k02 = next(o for o in orders if o.customer.id == 2)  # payment_terms=14
    k03 = next(o for o in orders if o.customer.id == 3)  # payment_terms=45
    assert k02.invoicesDueIn == 14
    assert k03.invoicesDueIn == 45


def test_generate_daily_orders_only_on_invoice_day():
    k02 = customer_by_number("K02")  # invoice_day=7
    orders_on_day = generate_daily_orders(2024, 1, k02.invoice_day)
    assert any(o.customer.id == 2 for o in orders_on_day)

    orders_other_day = generate_daily_orders(2024, 1, k02.invoice_day + 1)
    assert not any(o.customer.id == 2 for o in orders_other_day)


def test_generate_daily_orders_skips_consulting_customer():
    # K06 (consulting, invoice_day=None) nigdy nie pojawia się w generate_daily_orders.
    for day in range(1, 29):
        orders = generate_daily_orders(2024, 1, day)
        assert not any(o.customer.id == 6 for o in orders)


def test_price_multiplier_within_expected_range():
    assert len(CUSTOMER_PRICE_MULTIPLIER) == 12
    for multiplier in CUSTOMER_PRICE_MULTIPLIER.values():
        assert 0.92 <= multiplier <= 1.08


def test_price_multiplier_deterministic_across_calls():
    from norfingen.seed.roster import _customer_price_multiplier
    assert _customer_price_multiplier("K01") == _customer_price_multiplier("K01")
    assert CUSTOMER_PRICE_MULTIPLIER["K01"] == _customer_price_multiplier("K01")


def test_same_segment_customers_pay_different_amounts():
    # K01 i K11 to oboje Enterprise, pattern B, wspólne produkty P01+P04 —
    # bez wariancji byliby identyczni co do grosza.
    k01 = customer_by_number("K01")
    k11 = customer_by_number("K11")
    assert k01.segment == k11.segment == "Enterprise"
    assert k01.support_product == k11.support_product == "P01"

    orders = generate_monthly_orders(2024, 1)
    order_k01 = next(o for o in orders if o.customer.id == 1)
    order_k11 = next(o for o in orders if o.customer.id == 11)

    price_k01 = next(l.unitPriceExcludingVatCurrency for l in order_k01.orderLines if l.product.id == 1)
    price_k11 = next(l.unitPriceExcludingVatCurrency for l in order_k11.orderLines if l.product.id == 1)
    assert price_k01 != price_k11


def test_price_reflects_customer_multiplier():
    from norfingen.generators.order_generator import apply_annual_inflation
    from norfingen.seed.roster import service_by_code

    orders = generate_monthly_orders(2024, 1)
    order_k01 = next(o for o in orders if o.customer.id == 1)  # Enterprise -> S01 = product P01 (id=1)
    line = next(l for l in order_k01.orderLines if l.product.id == 1)

    s01 = service_by_code("S01")
    expected_base_price = apply_annual_inflation(s01.base_price_enterprise, 2024)
    expected_price = round(expected_base_price * CUSTOMER_PRICE_MULTIPLIER["K01"], 2)
    assert line.unitPriceExcludingVatCurrency == expected_price


def test_customer_price_variance():
    # Wszyscy 4 klienci Enterprise muszą mieć różne łączne przychody na
    # przestrzeni historii — mnożnik ceny per klient (±8%) gwarantuje, że nawet
    # ci z identycznym wzorcem zamówień i produktami nie płacą co do grosza tyle samo.
    enterprise_ids = {1: "K01", 3: "K03", 8: "K08", 11: "K11"}
    totals: dict[int, float] = {cid: 0.0 for cid in enterprise_ids}
    for year in range(2019, 2027):
        for month in range(1, 13):
            for order in generate_monthly_orders(year, month):
                if order.customer.id in totals:
                    totals[order.customer.id] += sum(l.amountExcludingVatCurrency for l in order.orderLines)

    values = list(totals.values())
    assert len(set(values)) == len(values), f"Klienci Enterprise mają identyczne przychody: {totals}"


def test_determine_order_status_deterministic():
    assert determine_order_status("K12", date(2019, 1, 2)) == OrderStatus.OVERDUE
    assert determine_order_status("K11", date(2019, 2, 22)) == OrderStatus.WRITTEN_OFF
    # Wywołanie ponowne z tymi samymi argumentami musi dać ten sam wynik
    # (deterministyczne, żeby backfill był powtarzalny).
    assert determine_order_status("K12", date(2019, 1, 2)) == OrderStatus.OVERDUE


def test_bad_debt_ratios_within_expected_bounds():
    # ~2% opóźnionych, z czego ~20% (0.4% wszystkich) nieściągalnych — na dużej
    # próbie (12 klientów x ~8 lat x ~28 dni) stosunki powinny być w rozsądnym
    # zakresie wokół oczekiwanych wartości.
    customers = ["K01", "K02", "K03", "K04", "K05", "K07", "K08", "K09", "K10", "K11", "K12"]
    total = overdue = written_off = 0
    for year in range(2019, 2027):
        for month in range(1, 13):
            for day in range(1, 29):
                for cust in customers:
                    status = determine_order_status(cust, date(year, month, day))
                    total += 1
                    if status == OrderStatus.OVERDUE:
                        overdue += 1
                    elif status == OrderStatus.WRITTEN_OFF:
                        written_off += 1

    bad_debt_share = (overdue + written_off) / total
    written_off_share = written_off / total
    assert 0.01 < bad_debt_share < 0.03  # ~2%
    assert 0.001 < written_off_share < 0.01  # ~0.4%


def test_order_status_defaults_to_paid_for_generated_orders():
    orders = generate_monthly_orders(2024, 8)  # sierpień, poza sezonem K06
    statuses = {o.status for o in orders}
    # Nie każdy Order jest PAID (bad debt), ale zdecydowana większość powinna być.
    paid_count = sum(1 for o in orders if o.status == OrderStatus.PAID)
    assert paid_count >= len(orders) - 1


def test_enterprise_customer_has_three_service_lines():
    # K01 (Enterprise) -> pełny pakiet S01+S02+S03 (Faza 2 bundling per segment,
    # zastępuje dawne liczenie linii wg litery order_pattern).
    k01 = customer_by_number("K01")
    order_date = date(2025, 1, k01.invoice_day)
    lines = build_order_lines(k01, order_date)
    assert len(lines) == 3
    expected_product_ids = {numeric_id(product_for_service(code).number) for code in ("S01", "S02", "S03")}
    assert {line.product.id for line in lines} == expected_product_ids


def test_mid_market_customer_has_two_service_lines():
    # K10 (Mid-market) -> S01+S02.
    k10 = customer_by_number("K10")
    order_date = date(2025, 1, k10.invoice_day)
    lines = build_order_lines(k10, order_date)
    assert len(lines) == 2


def test_smb_customer_has_one_service_line():
    # K04 (SMB) -> tylko S01.
    k04 = customer_by_number("K04")
    order_date = date(2025, 1, k04.invoice_day)
    lines = build_order_lines(k04, order_date)
    assert len(lines) == 1
    assert lines[0].product.id == numeric_id(product_for_service("S01").number)


def test_s03_generates_revenue_for_enterprise_customer():
    # Cyberbezpieczeństwo (S03) musi faktycznie generować przychód > 0 dla
    # klientów Enterprise (Faza 1 ograniczenie: usługa istniała bez przychodu).
    k01 = customer_by_number("K01")
    order_date = date(2025, 1, k01.invoice_day)
    lines = build_order_lines(k01, order_date)
    s03_product_id = numeric_id(product_for_service("S03").number)
    s03_lines = [l for l in lines if l.product.id == s03_product_id]
    assert len(s03_lines) == 1
    assert s03_lines[0].amountExcludingVatCurrency > 0


def test_should_generate_extra_consulting_smb_never():
    k04 = customer_by_number("K04")  # SMB
    for year in range(2019, 2027):
        for month in range(1, 13):
            assert should_generate_extra_consulting(k04, month, year) is False


def test_should_generate_extra_consulting_only_in_q2_q4():
    k01 = customer_by_number("K01")  # Enterprise
    for month in (1, 2, 3, 7, 8, 9):
        for year in range(2019, 2027):
            assert should_generate_extra_consulting(k01, month, year) is False


def test_extra_consulting_orders_occasionally_appear_for_enterprise():
    hits = 0
    for year in range(2019, 2035):
        for month in (4, 5, 6, 10, 11, 12):
            orders = generate_monthly_orders(year, month)
            k01_orders = [o for o in orders if o.customer.id == 1]
            if len(k01_orders) > 1:
                hits += 1
    assert hits > 0


def test_consulting_pattern_d_only_in_allowed_months():
    # K06 (Q2 kwi-cze, Q4 paź-gru, rzadko sty/lip) — nigdy w pozostałych miesiącach.
    allowed_months = {1, 4, 5, 6, 7, 10, 11, 12}
    for year in range(2019, 2027):
        for month in range(1, 13):
            orders = generate_monthly_orders(year, month)
            if any(o.customer.id == 6 for o in orders):
                assert month in allowed_months


def test_consulting_pattern_d_seasonal_bias_towards_q2_q4():
    # Na przestrzeni wielu lat Q2/Q4 (45% szans/miesiąc) powinno dominować nad
    # rzadkim Q1/Q3 (10% szans, tylko styczeń/lipiec).
    q2_q4_hits = q1_q3_hits = 0
    for year in range(2019, 2040):
        for month in range(1, 13):
            has_order = any(o.customer.id == 6 for o in generate_monthly_orders(year, month))
            if month in (4, 5, 6, 10, 11, 12):
                q2_q4_hits += has_order
            elif month in (1, 7):
                q1_q3_hits += has_order
    assert q2_q4_hits > q1_q3_hits


def test_customer_churn_stops_orders_after_churn_date():
    # K09 (Vestfold Handel): churn_date=2024-11-30, invoice_day=20.
    k09 = customer_by_number("K09")
    assert k09.churn_date == date(2024, 11, 30)

    orders_november = generate_monthly_orders(2024, 11)  # 2024-11-20 <= churn -> aktywny
    orders_december = generate_monthly_orders(2024, 12)  # 2024-12-20 > churn -> odszedł

    assert any(o.customer.id == 9 for o in orders_november)
    assert not any(o.customer.id == 9 for o in orders_december)


def test_churned_customer_no_orders_after_churn_date():
    # Sprawdza cały pozostały zakres historii po churn (nie tylko miesiąc po),
    # żeby wykluczyć jednorazowe pominięcie zamiast trwałego zaprzestania.
    for year in range(2024, 2027):
        for month in range(1, 13):
            if year == 2024 and month <= 11:
                continue
            orders = generate_monthly_orders(year, month)
            assert not any(o.customer.id == 9 for o in orders), f"K09 wygenerował zamówienie w {year}-{month:02d} po churn"


def test_customer_churn_no_daily_orders_after_churn_date():
    k09 = customer_by_number("K09")
    orders_after_churn = generate_daily_orders(2025, 1, k09.invoice_day)
    assert not any(o.customer.id == 9 for o in orders_after_churn)


def test_only_churned_customer_has_churn_date():
    from norfingen.seed.roster import CUSTOMERS
    churned = [c for c in CUSTOMERS if c.churn_date is not None]
    assert len(churned) == 1
    assert churned[0].number == "K09"
    # Enterprise nie mają churnu (długoterminowe kontrakty).
    for c in CUSTOMERS:
        if c.segment == "Enterprise":
            assert c.churn_date is None


def test_no_orders_before_any_customer_onboarding():
    # Pierwszy klient (K01) onboarduje się 2019-03-01 -> styczeń/luty 2019 bez zamówień.
    assert generate_monthly_orders(2019, 1) == []
    assert generate_monthly_orders(2019, 2) == []


def test_customer_count_grows_with_onboarding_schedule():
    # 2019-03: tylko K01. 2019-12: 6 klientów (K01,K02,K03,K05,K08,K11 wg harmonogramu).
    # 2023+: pełny portfel 12 klientów (K06 doszedł 2022-03).
    orders_march_2019 = generate_monthly_orders(2019, 3)
    assert {o.customer.id for o in orders_march_2019} == {1}

    # Sierpień: poza wszystkimi progami K06 (Q2/Q4/sty/lip) -> gwarantowane 0% szans,
    # więc dokładnie 11 klientów A/B/C, bez zależności od losowego wyniku RNG.
    orders_2023 = generate_monthly_orders(2023, 8)
    assert len({o.customer.id for o in orders_2023}) == 11


def test_customer_not_onboarded_yet_generates_no_order():
    k04 = customer_by_number("K04")  # onboarding 2020-08-01
    assert k04.onboarding_date == date(2020, 8, 1)
    orders_before = generate_monthly_orders(2020, 7)
    orders_after = generate_monthly_orders(2020, 8)
    assert not any(o.customer.id == 4 for o in orders_before)
    assert any(o.customer.id == 4 for o in orders_after)


def test_generate_daily_orders_respects_onboarding_date():
    k04 = customer_by_number("K04")  # invoice_day=10, onboarding 2020-08-01
    orders_before = generate_daily_orders(2020, 7, k04.invoice_day)
    orders_after = generate_daily_orders(2020, 8, k04.invoice_day)
    assert not any(o.customer.id == 4 for o in orders_before)
    assert any(o.customer.id == 4 for o in orders_after)


def test_consulting_customer_no_orders_before_onboarding():
    # K06 onboarduje się 2022-03-01 -> nigdy przed tą datą, nawet w sezonie Q2/Q4.
    for year in range(2019, 2022):
        for month in range(1, 13):
            orders = generate_monthly_orders(year, month)
            assert not any(o.customer.id == 6 for o in orders)


def test_deterministic_across_calls():
    a = generate_monthly_orders(2024, 6)
    b = generate_monthly_orders(2024, 6)
    assert [o.customer.id for o in a] == [o.customer.id for o in b]
