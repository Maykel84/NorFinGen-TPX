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


def test_consulting_pattern_d_within_expected_frequency():
    months_with_order = 0
    for month in range(1, 13):
        orders = generate_monthly_orders(2024, month)
        if any(o.customer.id == 6 for o in orders):
            months_with_order += 1
    assert 2 <= months_with_order <= 4


def test_deterministic_across_calls():
    a = generate_monthly_orders(2024, 6)
    b = generate_monthly_orders(2024, 6)
    assert [o.customer.id for o in a] == [o.customer.id for o in b]
