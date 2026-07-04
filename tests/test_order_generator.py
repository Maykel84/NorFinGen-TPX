from datetime import date

from norfingen.generators.order_generator import generate_daily_orders, generate_monthly_orders
from norfingen.seed.roster import customer_by_number


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


def test_pattern_b_has_two_lines():
    orders = generate_monthly_orders(2024, 1)
    k01 = next(o for o in orders if o.customer.id == 1)
    assert len(k01.orderLines) == 2


def test_pattern_c_license_only():
    orders = generate_monthly_orders(2024, 1)
    k10 = next(o for o in orders if o.customer.id == 10)
    assert len(k10.orderLines) == 1


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
