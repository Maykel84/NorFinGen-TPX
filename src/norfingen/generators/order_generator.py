"""Generator miesięcznych Order + OrderLine (Warstwa 2).

Order.invoiceDate = orderDate wyzwala automatyczne utworzenie Vouchera (INVOICE)
przez Tripletex — ten moduł NIE tworzy Voucherów ręcznie (w przeciwieństwie do
supplier_invoice_generator i salary_generator).

Wzorce z roster.CUSTOMERS.order_pattern:
  A — 1 OrderLine, IT Support (P01/P02/P03 per segment)
  B — 2 OrderLines, IT Support + Licencja (P0x + P04/P05)
  C — 1 OrderLine, tylko licencja (P05)
  D — Consulting (K06), 2-4x rocznie w losowych miesiącach, P06
"""

from __future__ import annotations

import calendar
import random
from datetime import date

from norfingen.models.base import TripletexRef
from norfingen.models.order import Order, OrderLine
from norfingen.seed.roster import CUSTOMERS, CustomerSeed, numeric_id, product_by_number

SALG_DEPARTMENT_REF = TripletexRef(id=1)
ERIK_STRAND_CONTACT_REF = TripletexRef(id=numeric_id("E01"))

CONSULTING_CUSTOMER_NUMBER = "K06"
CONSULTING_MIN_PER_YEAR = 2
CONSULTING_MAX_PER_YEAR = 4
CONSULTING_PRICE_MIN = 20_000.0
CONSULTING_PRICE_MAX = 50_000.0

MONTH_NAMES_NO = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]


def _consulting_months_for_year(year: int) -> set[int]:
    """Losowe 2-4 miesiące w roku dla K06 — deterministyczne per rok (seed),
    żeby backfill dawał powtarzalne wyniki przy ponownym uruchomieniu."""
    rng = random.Random(f"{CONSULTING_CUSTOMER_NUMBER}-{year}")
    count = rng.randint(CONSULTING_MIN_PER_YEAR, CONSULTING_MAX_PER_YEAR)
    return set(rng.sample(range(1, 13), count))


def _order_line_for_product(product_number: str, count: float = 1.0, unit_price: float | None = None) -> OrderLine:
    product = product_by_number(product_number)
    price = unit_price if unit_price is not None else (product.default_price or 0.0)
    return OrderLine(
        product=TripletexRef(id=numeric_id(product.number)),
        count=count,
        unitPriceExcludingVatCurrency=price,
    )


def _build_order(customer: CustomerSeed, year: int, month: int, order_lines: list[OrderLine]) -> Order:
    order_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    delivery_date = date(year, month, last_day)
    month_label = f"{MONTH_NAMES_NO[month - 1]} {year}"
    return Order(
        customer=TripletexRef(id=numeric_id(customer.number)),
        orderDate=order_date,
        deliveryDate=delivery_date,
        invoiceDate=order_date,
        orderLines=order_lines,
        department=SALG_DEPARTMENT_REF,
        comment=f"Månedlig faktura — {month_label}",
        ourContact=ERIK_STRAND_CONTACT_REF,
    )


def generate_monthly_orders(year: int, month: int) -> list[Order]:
    orders: list[Order] = []
    consulting_months = _consulting_months_for_year(year)

    for customer in CUSTOMERS:
        pattern = customer.order_pattern

        if pattern == "A":
            line = _order_line_for_product(customer.support_product)
            orders.append(_build_order(customer, year, month, [line]))

        elif pattern == "B":
            support_line = _order_line_for_product(customer.support_product)
            license_line = _order_line_for_product(customer.license_product)
            orders.append(_build_order(customer, year, month, [support_line, license_line]))

        elif pattern == "C":
            line = _order_line_for_product(customer.license_product)
            orders.append(_build_order(customer, year, month, [line]))

        elif pattern == "D":
            if month in consulting_months:
                rng = random.Random(f"{customer.number}-{year}-{month}")
                price = rng.uniform(CONSULTING_PRICE_MIN, CONSULTING_PRICE_MAX)
                line = _order_line_for_product("P06", count=1.0, unit_price=round(price, 2))
                orders.append(_build_order(customer, year, month, [line]))

        else:
            raise ValueError(f"Nieznany order_pattern: {pattern!r} dla klienta {customer.number}")

    return orders
