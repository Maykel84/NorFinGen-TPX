"""Order + OrderLine generator (Layer 2) — monthly (backfill) and daily.

Order.invoiceDate = orderDate triggers automatic Voucher (INVOICE) creation
by Tripletex — this module does NOT create Vouchers manually (unlike
supplier_invoice_generator and salary_generator).

Patterns from roster.CUSTOMERS.order_pattern:
  A/B/C — subscription customers (cadence per invoice_day/payment_terms). The
      number and choice of lines no longer depends on the pattern letter
      (Phase 1/earlier: A=1 line, B=2, C=1) — Phase 2 builds lines per
      service purchased based on customer segment
      (build_order_lines/roster.get_customer_services): Enterprise
      S01+S02+S03, Mid-market S01+S02, SMB S01. support_product/license_product
      on CustomerSeed remain as historical fields, unused for building lines.
  D — Consulting (K06), seasonally concentrated in Q2 (April-June) and Q4
      (October-December), rarer in January/July, P06. The only customer
      without a fixed subscription — not part of the segment bundling.

Phase 2 — should_generate_extra_consulting(): Enterprise/Mid-market
customers with an A/B/C subscription can ADDITIONALLY (on top of their
regular Order) get a separate S04 order (an off-contract consulting
project) in Q2/Q4, at low frequency (~15%/~8% chance per month) —
analogous to K06, but as an extra Order on top of the existing
subscription, not instead of it. Like K06, this logic only runs in
generate_monthly_orders (historical backfill) — generate_daily_orders does
not reproduce it, the same limited scope already in place for K06.

The invoice date (orderDate/invoiceDate) and payment terms (invoicesDueIn)
per subscription customer (A/B/C) come from
roster.CustomerSeed.invoice_day / .payment_terms, no longer hardcoded (1st
of the month / net 30).

Customers do not generate orders before their roster.CustomerSeed.onboarding_date
— gradual portfolio onboarding (first customer March 2019, the full 12 only
by 2022), not all existing since 2019-01-01.

generate_monthly_orders(year, month) — one Order per A/B/C customer per
month (+ optional D, + optional extra consulting), used by backfill.py
(historical loop).
generate_daily_orders(year, month, day) — an Order only for customers whose
invoice_day falls on that day; K06 (consulting, invoice_day=None) is
skipped — a separate triggering logic (should_generate_consulting),
unrelated to the day of month.
"""

from __future__ import annotations

import calendar
import random
from datetime import date
from typing import Optional

from norfingen.generators.client_events import (
    LARGE_PROJECT_HOURS_MAX,
    LARGE_PROJECT_HOURS_MIN,
    HARDSHIP_BAD_DEBT_MULTIPLIER,
    customer_event_state_asof,
    effective_customer_services,
    event_aware_is_customer_active,
)
from norfingen.generators.macro_shock import extra_consulting_shock_multiplier, payment_delay_adjusted_bad_debt
from norfingen.generators.seasonality import q4_budget_flush_multiplier
from norfingen.models.base import TripletexRef
from norfingen.models.order import Order, OrderLine, OrderStatus
from norfingen.seed.roster import (
    CUSTOMER_PRICE_MULTIPLIER,
    CUSTOMERS,
    CustomerSeed,
    is_customer_active,
    numeric_id,
    product_by_number,
    product_for_service,
    service_base_price,
    service_by_code_for_customer,
)

SALG_DEPARTMENT_REF = TripletexRef(id=1)
ERIK_STRAND_CONTACT_REF = TripletexRef(id=numeric_id("E01"))

CONSULTING_CUSTOMER_NUMBER = "K06"
CONSULTING_PRICE_MIN = 20_000.0
CONSULTING_PRICE_MAX = 50_000.0
CONSULTING_MONTHS_Q2_Q4 = {4, 5, 6, 10, 11, 12}
CONSULTING_MONTHS_Q1_Q3_RARE = {1, 7}
CONSULTING_PROBABILITY_Q2_Q4 = 0.45
CONSULTING_PROBABILITY_Q1_Q3_RARE = 0.10

BAD_DEBT_PROBABILITY = 0.02  # ~2% of invoices are >90 days overdue
WRITTEN_OFF_SHARE_OF_BAD_DEBT = 0.20  # of which ~20% (0.4% of all) become uncollectible

# Phase 2 — S04 projects on top of the subscription (Enterprise/Mid-market).
EXTRA_CONSULTING_MONTHS = {4, 5, 6, 10, 11, 12}  # Q2/Q4, like K06 (without the rare Jan/Jul)
EXTRA_CONSULTING_PROBABILITY = {"Enterprise": 0.15, "Mid-market": 0.08}
EXTRA_CONSULTING_PRODUCT_NUMBER = "P06"  # product_for_service("S04").number
EXTRA_CONSULTING_ORDER_DAY = 25  # separate from each subscription customer's invoice_day

INFLATION_BASE_YEAR = 2019
INFLATION_RATE = 0.03

MONTH_NAMES_NO = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]


def should_generate_consulting(month: int, year: int) -> bool:
    """K06: consulting mostly concentrated in Q2 (April-June) and Q4
    (October-December) — ~45% chance; rarer in January/July — ~10% chance;
    none in the remaining months. Deterministic per year+month (a local
    random.Random, not the global random.seed() — so as not to disturb the
    determinism of other generators sharing the process)."""
    rng = random.Random(f"{CONSULTING_CUSTOMER_NUMBER}-{year}-{month}-trigger")
    if month in CONSULTING_MONTHS_Q2_Q4:
        return rng.random() < CONSULTING_PROBABILITY_Q2_Q4
    if month in CONSULTING_MONTHS_Q1_Q3_RARE:
        return rng.random() < CONSULTING_PROBABILITY_Q1_Q3_RARE
    return False


def apply_annual_inflation(base_price: float, year: int, base_year: int = INFLATION_BASE_YEAR,
                            rate: float = INFLATION_RATE) -> float:
    """Applies +rate% inflation per year since base_year."""
    years_elapsed = max(0, year - base_year)
    return round(base_price * ((1 + rate) ** years_elapsed), 2)


def _order_line_for_product(product_number: str, year: int, count: float = 1.0, unit_price: float | None = None,
                             price_multiplier: float = 1.0) -> OrderLine:
    product = product_by_number(product_number)
    if unit_price is not None:
        price = unit_price
    else:
        price = round(apply_annual_inflation(product.default_price or 0.0, year) * price_multiplier, 2)
    return OrderLine(
        product=TripletexRef(id=numeric_id(product.number)),
        count=count,
        unitPriceExcludingVatCurrency=price,
    )


def _clamp_day(year: int, month: int, day: int) -> int:
    last_day = calendar.monthrange(year, month)[1]
    return min(day, last_day)


def determine_order_status(customer_number: str, order_date: date, bad_debt_probability: float = BAD_DEBT_PROBABILITY,
                            written_off_share: float = WRITTEN_OFF_SHARE_OF_BAD_DEBT) -> OrderStatus:
    """Determines the fate of a sales invoice (bad debt) — by default ~2%
    are >90 days overdue, of which ~20% (0.4% of all) become uncollectible.

    Deterministic per order (seeded from identity: customer + date), NOT
    dependent on "today"/wall-clock at the moment the payment is generated —
    otherwise the same historical record would change outcome depending on
    when the backfill was run (exactly the bug we already fixed once for the
    old supplier_invoices status heuristic). The status is therefore a fixed
    property of the order from the moment it's created, not something
    re-evaluated later against the current date.

    Phase 7, Task 2c — `bad_debt_probability` is optionally overridden by the
    caller (generate_monthly_orders) during a customer's active
    TEMPORARY_HARDSHIP (see client_events.HARDSHIP_BAD_DEBT_MULTIPLIER).

    Phase 7b, Task 1e — `written_off_share` is optionally overridden during
    MACRO_SHOCK (COVID_2020): both parameters together come from
    macro_shock.payment_delay_adjusted_bad_debt(), which raises P(OVERDUE)
    while keeping P(WRITTEN_OFF) EXACTLY at the normal level — payment delay
    != a wave of bankruptcies."""
    rng = random.Random(f"bad-debt-{customer_number}-{order_date.isoformat()}")
    if rng.random() < bad_debt_probability:
        if rng.random() < written_off_share:
            return OrderStatus.WRITTEN_OFF
        return OrderStatus.OVERDUE
    return OrderStatus.PAID


def _build_order(customer: CustomerSeed, year: int, month: int, day: int, order_lines: list[OrderLine],
                  bad_debt_probability: float = BAD_DEBT_PROBABILITY, written_off_share: float = WRITTEN_OFF_SHARE_OF_BAD_DEBT,
                  status_override: Optional[OrderStatus] = None) -> Order:
    order_date = date(year, month, _clamp_day(year, month, day))
    last_day = calendar.monthrange(year, month)[1]
    delivery_date = date(year, month, last_day)
    month_label = f"{MONTH_NAMES_NO[month - 1]} {year}"
    status = status_override if status_override is not None else determine_order_status(customer.number, order_date, bad_debt_probability, written_off_share)
    return Order(
        customer=TripletexRef(id=numeric_id(customer.number)),
        orderDate=order_date,
        deliveryDate=delivery_date,
        invoiceDate=order_date,
        invoicesDueIn=customer.payment_terms,
        status=status,
        orderLines=order_lines,
        department=SALG_DEPARTMENT_REF,
        comment=f"Månedlig faktura — {month_label}",
        ourContact=ERIK_STRAND_CONTACT_REF,
    )


def build_order_lines(customer: CustomerSeed, order_date: date) -> list[OrderLine]:
    """Builds OrderLines for subscription customers (A/B/C, monthly cycle) —
    one line per service the customer buys based on segment (Phase 2:
    roster.get_customer_services), priced from the service catalog
    (roster.service_base_price, NOT Product.default_price) after inflation
    (apply_annual_inflation) and the customer's individual negotiation
    multiplier (±8%, roster.CUSTOMER_PRICE_MULTIPLIER) — two customers in
    the same segment pay different amounts, just like in real B2B
    negotiations. Replaces the old split by pattern letter (A=1/B=2/C=1
    line) — support_product/license_product no longer drive the
    number/choice of lines. Pattern D (K06 consulting) has separate logic —
    not handled here.

    Phase 7, Task 2c — the service list goes through
    client_events.effective_customer_services(), which adds/removes a
    service per the permanent effects of OFFER_EXPANSION/OFFER_REDUCTION
    (a no-op when the customer never had such an event — identical result
    to the old roster.get_customer_services())."""
    multiplier = CUSTOMER_PRICE_MULTIPLIER[customer.number]
    event_state = customer_event_state_asof(customer.number, order_date.year, order_date.month)
    lines: list[OrderLine] = []
    for code in effective_customer_services(customer, event_state):
        # service_by_code_for_customer (not service_by_code) — Phase 4,
        # recalibration #3: respects the customer's pricing cohort
        # (LEGACY_SERVICES for K01-K12 + the 2022-09 merger, SCALE_SERVICES
        # for 2023+ customers), see roster.get_service_price_table.
        service = service_by_code_for_customer(customer, code)
        base_price = service_base_price(service, customer.segment)
        product = product_for_service(code)
        price = round(apply_annual_inflation(base_price, order_date.year) * multiplier, 2)
        lines.append(OrderLine(
            product=TripletexRef(id=numeric_id(product.number)),
            count=1.0,
            unitPriceExcludingVatCurrency=price,
        ))
    return lines


def should_generate_extra_consulting(customer: CustomerSeed, month: int, year: int) -> bool:
    """Enterprise/Mid-market customers may occasionally (on top of their
    standard subscription) order an S04 project — this simulates extra
    digitalization projects outside the subscription agreement. SMB never
    orders extra consulting (the only SMB with consulting is K06/pattern D,
    separate logic). ~15% chance in Q2/Q4 for Enterprise, ~8% for
    Mid-market. Deterministic per customer+year+month (random.Random(string),
    not the built-in hash() — see SESSION_HANDOFF.md item 6).

    Phase 7, Task 1b — Q4 budget flush: the threshold is additionally
    multiplied by q4_budget_flush_multiplier (November/December,
    Enterprise/Mid-market), instead of a parallel mechanism — the existing
    EXTRA_CONSULTING_MONTHS gate (Q2/Q4) already restricts the months, the
    multiplier just boosts the frequency in Q4 beyond what's in Q2.

    Phase 7b, Task 1d — MACRO_SHOCK (COVID_2020): the threshold is
    additionally ×0.3 in March-June 2020 (extra_consulting_shock_multiplier)
    — customers don't order extra digitalization projects in the middle of
    lockdown. min(..., 1.0) is purely defensive, never reached at the
    current constants."""
    if customer.segment not in EXTRA_CONSULTING_PROBABILITY:
        return False
    if month not in EXTRA_CONSULTING_MONTHS:
        return False
    rng = random.Random(f"extra-consulting-{customer.number}-{year}-{month}")
    threshold = (
        EXTRA_CONSULTING_PROBABILITY[customer.segment]
        * q4_budget_flush_multiplier(month, customer.segment)
        * extra_consulting_shock_multiplier(year, month)
    )
    return rng.random() < min(threshold, 1.0)


LARGE_PROJECT_ORDER_DAY = 26  # separate from EXTRA_CONSULTING_ORDER_DAY (25) and customers' invoice_day


def _build_large_project_order(customer: CustomerSeed, year: int, month: int) -> Order:
    """Phase 7, Task 2c — ONE_OFF_LARGE_PROJECT: one, significantly larger
    S04 line (80-200h at the service's hourly rate, instead of the standard
    20-50k NOK flat fee in should_generate_extra_consulting) — a large,
    one-off project, not another "regular" extra consulting engagement."""
    rng = random.Random(f"large-project-{customer.number}-{year}-{month}")
    service = service_by_code_for_customer(customer, "S04")
    base_price = service_base_price(service, customer.segment)
    hourly_rate = round(apply_annual_inflation(base_price, year) * CUSTOMER_PRICE_MULTIPLIER[customer.number], 2)
    hours = round(rng.uniform(LARGE_PROJECT_HOURS_MIN, LARGE_PROJECT_HOURS_MAX), 1)
    product = product_for_service("S04")
    line = OrderLine(
        product=TripletexRef(id=numeric_id(product.number)),
        count=hours,
        unitPriceExcludingVatCurrency=hourly_rate,
    )
    return _build_order(customer, year, month, LARGE_PROJECT_ORDER_DAY, [line])


def generate_monthly_orders(year: int, month: int) -> list[Order]:
    """Generates one Order per subscription customer (A/B/C) for a given
    month — used by the backfill (historical loop). Invoice date =
    customer.invoice_day (no longer hardcoded to the 1st of the month).

    Phase 7, Task 2 — customer events (client_events) affect this in: activity
    (event_aware_is_customer_active — BANKRUPTCY), the bad-debt threshold
    (raised during TEMPORARY_HARDSHIP), the status of the final invoice
    (forced WRITTEN_OFF in the bankruptcy month), and an extra order
    (ONE_OFF_LARGE_PROJECT). Like extra-consulting/K06 — the same,
    deliberately limited scope: monthly backfill only, not
    generate_daily_orders (except for the activity/BANKRUPTCY check itself,
    see below)."""
    orders: list[Order] = []

    for customer in CUSTOMERS:
        pattern = customer.order_pattern

        if pattern in ("A", "B", "C"):
            order_date = date(year, month, _clamp_day(year, month, customer.invoice_day))
            if not event_aware_is_customer_active(customer, order_date):
                continue

            event_state = customer_event_state_asof(customer.number, year, month)
            bad_debt_probability = BAD_DEBT_PROBABILITY
            if event_state.hardship_active_until is not None:
                bad_debt_probability = min(BAD_DEBT_PROBABILITY * HARDSHIP_BAD_DEBT_MULTIPLIER, 1.0)
            # Phase 7b, Task 1e — MACRO_SHOCK (COVID_2020): raises OVERDUE,
            # keeps WRITTEN_OFF at its pre-adjustment level (whether that's
            # normal, or already raised by TEMPORARY_HARDSHIP above).
            bad_debt_probability, written_off_share = payment_delay_adjusted_bad_debt(
                bad_debt_probability, WRITTEN_OFF_SHARE_OF_BAD_DEBT, year, month,
            )
            status_override = OrderStatus.WRITTEN_OFF if event_state.triggered_this_month == "BANKRUPTCY" else None

            lines = build_order_lines(customer, order_date)
            orders.append(_build_order(
                customer, year, month, customer.invoice_day, lines,
                bad_debt_probability=bad_debt_probability, written_off_share=written_off_share,
                status_override=status_override,
            ))

            if event_state.triggered_this_month == "BANKRUPTCY":
                continue  # last invoice already issued (written off) — customer disappears starting next month

            if event_state.triggered_this_month == "ONE_OFF_LARGE_PROJECT":
                orders.append(_build_large_project_order(customer, year, month))

            if should_generate_extra_consulting(customer, month, year):
                rng = random.Random(f"extra-consulting-price-{customer.number}-{year}-{month}")
                price = round(rng.uniform(CONSULTING_PRICE_MIN, CONSULTING_PRICE_MAX), 2)
                extra_line = _order_line_for_product(
                    EXTRA_CONSULTING_PRODUCT_NUMBER, year, count=1.0, unit_price=price,
                )
                orders.append(_build_order(customer, year, month, EXTRA_CONSULTING_ORDER_DAY, [extra_line]))

        elif pattern == "D":
            if is_customer_active(customer, date(year, month, 1)) and should_generate_consulting(month, year):
                rng = random.Random(f"{customer.number}-{year}-{month}")
                price = rng.uniform(CONSULTING_PRICE_MIN, CONSULTING_PRICE_MAX)
                line = _order_line_for_product("P06", year, count=1.0, unit_price=round(price, 2))
                orders.append(_build_order(customer, year, month, 1, [line]))

        else:
            raise ValueError(f"Unknown order_pattern: {pattern!r} for customer {customer.number}")

    return orders


def generate_daily_orders(year: int, month: int, day: int) -> list[Order]:
    """Generates orders for a specific day — issues an invoice only to
    customers whose invoice_day falls today and who are already onboarded
    (order_date >= onboarding_date). K06 (consulting, invoice_day=None) is
    skipped here — it has separate triggering logic
    (should_generate_consulting), not tied to a specific day of the month.

    Phase 7, Task 2 — uses event_aware_is_customer_active (not plain
    roster.is_customer_active), so the live cron/daily mode stops issuing
    invoices to a customer whose BANKRUPTCY fired during the monthly
    backfill — the rest of the event effects (extra order, raised bad-debt)
    deliberately stay only in generate_monthly_orders, see that docstring."""
    orders: list[Order] = []

    for customer in CUSTOMERS:
        if customer.invoice_day is None:
            continue  # K06 consulting — separate logic
        if customer.invoice_day != day:
            continue

        order_date = date(year, month, day)
        if not event_aware_is_customer_active(customer, order_date):
            continue

        lines = build_order_lines(customer, order_date)
        orders.append(_build_order(customer, year, month, day, lines))

    return orders
