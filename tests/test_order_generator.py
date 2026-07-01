from datetime import date

from norfingen.generators.order_generator import generate_monthly_orders


def test_pattern_a_b_c_generated_every_month():
    orders = generate_monthly_orders(2024, 1)
    by_customer = {o.customer.id: o for o in orders}
    # K01 (Enterprise, pattern B) ma 11 klientów A/B/C generujących Order co miesiąc
    # (K06 to pattern D, losowy — może, ale nie musi, wystąpić w danym miesiącu).
    assert len(orders) >= 11

    for order in orders:
        assert order.invoiceDate == order.orderDate
        assert order.orderDate.day == 1
        assert order.department.id == 1
        assert len(order.orderLines) >= 1


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


def test_deterministic_across_calls():
    a = generate_monthly_orders(2024, 6)
    b = generate_monthly_orders(2024, 6)
    assert [o.customer.id for o in a] == [o.customer.id for o in b]
