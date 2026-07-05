"""Generator Order + OrderLine (Warstwa 2) — miesięczny (backfill) i dzienny.

Order.invoiceDate = orderDate wyzwala automatyczne utworzenie Vouchera (INVOICE)
przez Tripletex — ten moduł NIE tworzy Voucherów ręcznie (w przeciwieństwie do
supplier_invoice_generator i salary_generator).

Wzorce z roster.CUSTOMERS.order_pattern:
  A/B/C — klienci subskrypcyjni (rytm wg invoice_day/payment_terms). Liczba i
      dobór linii NIE zależy już od litery wzorca (Faza 1/wcześniej: A=1 linia,
      B=2, C=1) — Faza 2 buduje linie per usługa kupowaną wg segmentu klienta
      (build_order_lines/roster.get_customer_services): Enterprise S01+S02+S03,
      Mid-market S01+S02, SMB S01. support_product/license_product na
      CustomerSeed zostają jako pola historyczne, nieużywane do budowy linii.
  D — Consulting (K06), sezonowo skupiony w Q2 (kwiecień-czerwiec) i Q4
      (październik-grudzień), rzadziej w styczniu/lipcu, P06. Jedyny klient bez
      stałej subskrypcji — nie wchodzi w bundling segmentowy.

Faza 2 — should_generate_extra_consulting(): klienci Enterprise/Mid-market z
subskrypcją A/B/C mogą DODATKOWO (poza swoim stałym Order) dostać osobne
zamówienie S04 (projekt konsultingowy poza umową) w Q2/Q4, niska częstotliwość
(~15%/~8% szans na miesiąc) — analogicznie do K06, ale jako Order dodatkowy do
istniejącej subskrypcji, nie zamiast niej. Jak K06, ta logika działa tylko w
generate_monthly_orders (backfill historyczny) — generate_daily_orders jej nie
odtwarza, ten sam ograniczony zakres co już istniejący dla K06.

Data faktury (orderDate/invoiceDate) i termin płatności (invoicesDueIn) per
klient subskrypcyjny (A/B/C) pochodzą z roster.CustomerSeed.invoice_day /
.payment_terms, nie są już sztywne (1. dzień miesiąca / net 30).

Klienci nie generują zamówień przed swoją roster.CustomerSeed.onboarding_date —
stopniowy onboarding portfela (pierwszy klient marzec 2019, komplet 12 dopiero
w 2022), nie wszyscy istniejący od 2019-01-01.

generate_monthly_orders(year, month) — jeden Order per klient A/B/C w miesiącu
(+ ewentualny D, + ewentualny extra consulting), używana przez backfill.py
(pętla historyczna).
generate_daily_orders(year, month, day) — Order tylko dla klientów, których
invoice_day wypada danego dnia; K06 (consulting, invoice_day=None) pomijany —
osobna logika wyzwalania (should_generate_consulting), niezwiązana z dniem.
"""

from __future__ import annotations

import calendar
import random
from datetime import date

from norfingen.models.base import TripletexRef
from norfingen.models.order import Order, OrderLine, OrderStatus
from norfingen.seed.roster import (
    CUSTOMER_PRICE_MULTIPLIER,
    CUSTOMERS,
    CustomerSeed,
    get_customer_services,
    numeric_id,
    product_by_number,
    product_for_service,
    service_base_price,
    service_by_code,
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

BAD_DEBT_PROBABILITY = 0.02  # ~2% faktur ma opóźnienie >90 dni
WRITTEN_OFF_SHARE_OF_BAD_DEBT = 0.20  # z tego ~20% (0.4% wszystkich) staje się nieściągalne

# Faza 2 — projekty S04 dodatkowe do subskrypcji (Enterprise/Mid-market).
EXTRA_CONSULTING_MONTHS = {4, 5, 6, 10, 11, 12}  # Q2/Q4, jak K06 (bez rzadkiego sty/lip)
EXTRA_CONSULTING_PROBABILITY = {"Enterprise": 0.15, "Mid-market": 0.08}
EXTRA_CONSULTING_PRODUCT_NUMBER = "P06"  # product_for_service("S04").number
EXTRA_CONSULTING_ORDER_DAY = 25  # dzień odrębny od invoice_day każdego klienta subskrypcyjnego

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


def _is_active(customer: CustomerSeed, on_date: date) -> bool:
    """Klient nie generuje zamówień przed swoją onboarding_date (stopniowy
    onboarding portfela, nie wszyscy istniejący od 2019-01-01) ani po swojej
    churn_date, jeśli ma (niski, realistyczny churn — głównie SMB, K09)."""
    if on_date < customer.onboarding_date:
        return False
    if customer.churn_date is not None and on_date > customer.churn_date:
        return False
    return True


def determine_order_status(customer_number: str, order_date: date) -> OrderStatus:
    """Ustala los faktury sprzedaży (bad debt) — ~2% opóźnionych >90 dni, z czego
    ~20% (0.4% wszystkich) nieściągalnych.

    Deterministyczne per zamówienie (seed z tożsamości: klient + data), NIE
    zależne od "dzisiaj"/wall-clock w momencie generowania płatności — inaczej
    ten sam historyczny rekord zmieniałby wynik zależnie od tego, kiedy
    uruchomiono backfill (dokładnie ten błąd naprawiliśmy już raz dla starej
    heurystyki statusu supplier_invoices). Status jest więc stałą właściwością
    zamówienia od chwili utworzenia, a nie czymś ocenianym później względem
    bieżącej daty."""
    rng = random.Random(f"bad-debt-{customer_number}-{order_date.isoformat()}")
    if rng.random() < BAD_DEBT_PROBABILITY:
        if rng.random() < WRITTEN_OFF_SHARE_OF_BAD_DEBT:
            return OrderStatus.WRITTEN_OFF
        return OrderStatus.OVERDUE
    return OrderStatus.PAID


def _build_order(customer: CustomerSeed, year: int, month: int, day: int, order_lines: list[OrderLine]) -> Order:
    order_date = date(year, month, _clamp_day(year, month, day))
    last_day = calendar.monthrange(year, month)[1]
    delivery_date = date(year, month, last_day)
    month_label = f"{MONTH_NAMES_NO[month - 1]} {year}"
    return Order(
        customer=TripletexRef(id=numeric_id(customer.number)),
        orderDate=order_date,
        deliveryDate=delivery_date,
        invoiceDate=order_date,
        invoicesDueIn=customer.payment_terms,
        status=determine_order_status(customer.number, order_date),
        orderLines=order_lines,
        department=SALG_DEPARTMENT_REF,
        comment=f"Månedlig faktura — {month_label}",
        ourContact=ERIK_STRAND_CONTACT_REF,
    )


def build_order_lines(customer: CustomerSeed, order_date: date) -> list[OrderLine]:
    """Buduje OrderLines dla klientów subskrypcyjnych (A/B/C, cykl miesięczny) —
    jedna linia per usługa którą klient kupuje wg segmentu (Faza 2:
    roster.get_customer_services), cena z katalogu usług
    (roster.service_base_price, NIE Product.default_price) po inflacji
    (apply_annual_inflation) i indywidualnym mnożniku negocjacyjnym klienta
    (±8%, roster.CUSTOMER_PRICE_MULTIPLIER) — dwaj klienci tego samego
    segmentu płacą różne kwoty, tak jak przy realnych negocjacjach B2B.
    Zastępuje dawny podział wg litery wzorca (A=1/B=2/C=1 linia) —
    support_product/license_product nie sterują już liczbą/doborem linii.
    Wzorzec D (K06 consulting) ma osobną logikę — nie jest tu obsługiwany."""
    multiplier = CUSTOMER_PRICE_MULTIPLIER[customer.number]
    lines: list[OrderLine] = []
    for code in get_customer_services(customer):
        service = service_by_code(code)
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
    """Klienci Enterprise/Mid-market mogą occasionally (dodatkowo do
    standardowej subskrypcji) zamówić projekt S04 — symuluje to dodatkowe
    projekty digitalizacyjne poza umową abonamentową. SMB nie zamawia
    dodatkowego consultingu (jedyny SMB z consultingiem to K06/wzorzec D,
    osobna logika). ~15% szans w Q2/Q4 dla Enterprise, ~8% dla Mid-market.
    Deterministyczne per klient+rok+miesiąc (random.Random(string), nie
    wbudowany hash() — zob. SESSION_HANDOFF.md pkt 6)."""
    if customer.segment not in EXTRA_CONSULTING_PROBABILITY:
        return False
    if month not in EXTRA_CONSULTING_MONTHS:
        return False
    rng = random.Random(f"extra-consulting-{customer.number}-{year}-{month}")
    return rng.random() < EXTRA_CONSULTING_PROBABILITY[customer.segment]


def generate_monthly_orders(year: int, month: int) -> list[Order]:
    """Generuje po jednym Order per klient subskrypcyjny (A/B/C) w danym
    miesiącu — używana przez backfill (pętla historyczna). Data faktury =
    customer.invoice_day (nie sztywno 1. dzień miesiąca)."""
    orders: list[Order] = []

    for customer in CUSTOMERS:
        pattern = customer.order_pattern

        if pattern in ("A", "B", "C"):
            order_date = date(year, month, _clamp_day(year, month, customer.invoice_day))
            if not _is_active(customer, order_date):
                continue
            lines = build_order_lines(customer, order_date)
            orders.append(_build_order(customer, year, month, customer.invoice_day, lines))

            if should_generate_extra_consulting(customer, month, year):
                rng = random.Random(f"extra-consulting-price-{customer.number}-{year}-{month}")
                price = round(rng.uniform(CONSULTING_PRICE_MIN, CONSULTING_PRICE_MAX), 2)
                extra_line = _order_line_for_product(
                    EXTRA_CONSULTING_PRODUCT_NUMBER, year, count=1.0, unit_price=price,
                )
                orders.append(_build_order(customer, year, month, EXTRA_CONSULTING_ORDER_DAY, [extra_line]))

        elif pattern == "D":
            if _is_active(customer, date(year, month, 1)) and should_generate_consulting(month, year):
                rng = random.Random(f"{customer.number}-{year}-{month}")
                price = rng.uniform(CONSULTING_PRICE_MIN, CONSULTING_PRICE_MAX)
                line = _order_line_for_product("P06", year, count=1.0, unit_price=round(price, 2))
                orders.append(_build_order(customer, year, month, 1, [line]))

        else:
            raise ValueError(f"Nieznany order_pattern: {pattern!r} dla klienta {customer.number}")

    return orders


def generate_daily_orders(year: int, month: int, day: int) -> list[Order]:
    """Generuje zamówienia dla konkretnego dnia — wystawia fakturę tylko tym
    klientom, dla których dzisiaj wypada ich invoice_day i którzy są już
    onboardowani (order_date >= onboarding_date). K06 (consulting,
    invoice_day=None) jest tu pomijany — ma osobną logikę wyzwalania
    (should_generate_consulting), nierozłożoną na konkretny dzień miesiąca."""
    orders: list[Order] = []

    for customer in CUSTOMERS:
        if customer.invoice_day is None:
            continue  # K06 consulting — osobna logika
        if customer.invoice_day != day:
            continue

        order_date = date(year, month, day)
        if not _is_active(customer, order_date):
            continue

        lines = build_order_lines(customer, order_date)
        orders.append(_build_order(customer, year, month, day, lines))

    return orders
