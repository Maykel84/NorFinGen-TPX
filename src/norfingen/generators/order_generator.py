"""Generator miesięcznych Order + OrderLine (Warstwa 2).

Order.invoiceDate = orderDate wyzwala automatyczne utworzenie Vouchera (INVOICE)
przez Tripletex — ten moduł NIE tworzy Voucherów ręcznie (w przeciwieństwie do
supplier_invoice_generator i salary_generator).

Wzorce z roster.CUSTOMERS.order_pattern:
  A — 1 OrderLine, IT Support (P01/P02/P03 per segment)
  B — 2 OrderLines, IT Support + Licencja (P0x + P04/P05)
  C — 1 OrderLine, tylko licencja (P05)
  D — Consulting (K06), sezonowo skupiony w Q2 (kwiecień-czerwiec) i Q4
      (październik-grudzień), rzadziej w styczniu/lipcu, P06
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
CONSULTING_PRICE_MIN = 20_000.0
CONSULTING_PRICE_MAX = 50_000.0
CONSULTING_MONTHS_Q2_Q4 = {4, 5, 6, 10, 11, 12}
CONSULTING_MONTHS_Q1_Q3_RARE = {1, 7}
CONSULTING_PROBABILITY_Q2_Q4 = 0.45
CONSULTING_PROBABILITY_Q1_Q3_RARE = 0.10

INFLATION_BASE_YEAR = 2019
INFLATION_RATE = 0.03

MONTH_NAMES_NO = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]


def should_generate_consulting(month: int, year: int) -> bool:
    """K06: consulting skupiony głównie w Q2 (kwiecień-czerwiec) i Q4
    (październik-grudzień) — ~45% szans; rzadziej w styczniu/lipcu — ~10% szans;
    brak w pozostałych miesiącach. Deterministyczne per rok+miesiąc (lokalny
    random.Random, nie globalny random.seed() — żeby nie zaburzać determinizmu
    innych generatorów dzielących proces)."""
    rng = random.Random(f"{CONSULTING_CUSTOMER_NUMBER}-{year}-{month}-trigger")
    if month in CONSULTING_MONTHS_Q2_Q4:
        return rng.random() < CONSULTING_PROBABILITY_Q2_Q4
    if month in CONSULTING_MONTHS_Q1_Q3_RARE:
        return rng.random() < CONSULTING_PROBABILITY_Q1_Q3_RARE
    return False


def apply_annual_inflation(base_price: float, year: int, base_year: int = INFLATION_BASE_YEAR,
                            rate: float = INFLATION_RATE) -> float:
    """Stosuje inflację +rate% rocznie od base_year."""
    years_elapsed = max(0, year - base_year)
    return round(base_price * ((1 + rate) ** years_elapsed), 2)


def _order_line_for_product(product_number: str, year: int, count: float = 1.0, unit_price: float | None = None) -> OrderLine:
    product = product_by_number(product_number)
    if unit_price is not None:
        price = unit_price
    else:
        price = apply_annual_inflation(product.default_price or 0.0, year)
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

    for customer in CUSTOMERS:
        pattern = customer.order_pattern

        if pattern == "A":
            line = _order_line_for_product(customer.support_product, year)
            orders.append(_build_order(customer, year, month, [line]))

        elif pattern == "B":
            support_line = _order_line_for_product(customer.support_product, year)
            license_line = _order_line_for_product(customer.license_product, year)
            orders.append(_build_order(customer, year, month, [support_line, license_line]))

        elif pattern == "C":
            line = _order_line_for_product(customer.license_product, year)
            orders.append(_build_order(customer, year, month, [line]))

        elif pattern == "D":
            if should_generate_consulting(month, year):
                rng = random.Random(f"{customer.number}-{year}-{month}")
                price = rng.uniform(CONSULTING_PRICE_MIN, CONSULTING_PRICE_MAX)
                line = _order_line_for_product("P06", year, count=1.0, unit_price=round(price, 2))
                orders.append(_build_order(customer, year, month, [line]))

        else:
            raise ValueError(f"Nieznany order_pattern: {pattern!r} dla klienta {customer.number}")

    return orders
