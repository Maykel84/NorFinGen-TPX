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


def determine_order_status(customer_number: str, order_date: date, bad_debt_probability: float = BAD_DEBT_PROBABILITY,
                            written_off_share: float = WRITTEN_OFF_SHARE_OF_BAD_DEBT) -> OrderStatus:
    """Ustala los faktury sprzedaży (bad debt) — domyślnie ~2% opóźnionych
    >90 dni, z czego ~20% (0.4% wszystkich) nieściągalnych.

    Deterministyczne per zamówienie (seed z tożsamości: klient + data), NIE
    zależne od "dzisiaj"/wall-clock w momencie generowania płatności — inaczej
    ten sam historyczny rekord zmieniałby wynik zależnie od tego, kiedy
    uruchomiono backfill (dokładnie ten błąd naprawiliśmy już raz dla starej
    heurystyki statusu supplier_invoices). Status jest więc stałą właściwością
    zamówienia od chwili utworzenia, a nie czymś ocenianym później względem
    bieżącej daty.

    Faza 7, Zadanie 2c — `bad_debt_probability` opcjonalnie nadpisywany przez
    wywołującego (generate_monthly_orders) podczas aktywnego
    TEMPORARY_HARDSHIP klienta (zob. client_events.HARDSHIP_BAD_DEBT_MULTIPLIER).

    Faza 7b, Zadanie 1e — `written_off_share` opcjonalnie nadpisywany podczas
    MACRO_SHOCK (COVID_2020): oba parametry razem pochodzą z
    macro_shock.payment_delay_adjusted_bad_debt(), które podnosi P(OVERDUE)
    zachowując P(WRITTEN_OFF) DOKŁADNIE na normalnym poziomie — opóźnienie
    płatności ≠ fala bankructw."""
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
    """Buduje OrderLines dla klientów subskrypcyjnych (A/B/C, cykl miesięczny) —
    jedna linia per usługa którą klient kupuje wg segmentu (Faza 2:
    roster.get_customer_services), cena z katalogu usług
    (roster.service_base_price, NIE Product.default_price) po inflacji
    (apply_annual_inflation) i indywidualnym mnożniku negocjacyjnym klienta
    (±8%, roster.CUSTOMER_PRICE_MULTIPLIER) — dwaj klienci tego samego
    segmentu płacą różne kwoty, tak jak przy realnych negocjacjach B2B.
    Zastępuje dawny podział wg litery wzorca (A=1/B=2/C=1 linia) —
    support_product/license_product nie sterują już liczbą/doborem linii.
    Wzorzec D (K06 consulting) ma osobną logikę — nie jest tu obsługiwany.

    Faza 7, Zadanie 2c — lista usług przechodzi przez
    client_events.effective_customer_services(), która dokłada/usuwa
    usługę wg trwałych efektów OFFER_EXPANSION/OFFER_REDUCTION (no-op gdy
    klient nigdy takiego zdarzenia nie miał — identyczny wynik jak dawne
    roster.get_customer_services())."""
    multiplier = CUSTOMER_PRICE_MULTIPLIER[customer.number]
    event_state = customer_event_state_asof(customer.number, order_date.year, order_date.month)
    lines: list[OrderLine] = []
    for code in effective_customer_services(customer, event_state):
        # service_by_code_for_customer (nie service_by_code) — Faza 4,
        # rekalibracja #3: respektuje kohortę cenową klienta (LEGACY_SERVICES
        # dla K01-K12 + fuzja 2022-09, SCALE_SERVICES dla klientów 2023+),
        # zob. roster.get_service_price_table.
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
    """Klienci Enterprise/Mid-market mogą occasionally (dodatkowo do
    standardowej subskrypcji) zamówić projekt S04 — symuluje to dodatkowe
    projekty digitalizacyjne poza umową abonamentową. SMB nie zamawia
    dodatkowego consultingu (jedyny SMB z consultingiem to K06/wzorzec D,
    osobna logika). ~15% szans w Q2/Q4 dla Enterprise, ~8% dla Mid-market.
    Deterministyczne per klient+rok+miesiąc (random.Random(string), nie
    wbudowany hash() — zob. SESSION_HANDOFF.md pkt 6).

    Faza 7, Zadanie 1b — budsjettflukt Q4: próg dodatkowo mnożony przez
    q4_budget_flush_multiplier (listopad/grudzień, Enterprise/Mid-market),
    zamiast równoległego mechanizmu — istniejący próg EXTRA_CONSULTING_MONTHS
    (Q2/Q4) już ogranicza miesiące, mnożnik tylko podbija częstotliwość w
    Q4 ponad to, co jest w Q2.

    Faza 7b, Zadanie 1d — MACRO_SHOCK (COVID_2020): próg dodatkowo × 0,3
    w marcu-czerwcu 2020 (extra_consulting_shock_multiplier) — klienci nie
    zamawiają dodatkowych projektów digitalizacyjnych w środku lockdownu.
    min(..., 1.0) — czysto obronne, przy obecnych stałych nigdy nie
    osiąga 1.0."""
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


LARGE_PROJECT_ORDER_DAY = 26  # odrębny od EXTRA_CONSULTING_ORDER_DAY (25) i invoice_day klientów


def _build_large_project_order(customer: CustomerSeed, year: int, month: int) -> Order:
    """Faza 7, Zadanie 2c — ONE_OFF_LARGE_PROJECT: jedna, znacząco większa
    linia S04 (80-200h wg stawki godzinowej usługi, zamiast standardowego
    ryczałtu 20-50k NOK w should_generate_extra_consulting) — duży,
    jednorazowy projekt, nie kolejny "zwykły" dodatkowy consulting."""
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
    """Generuje po jednym Order per klient subskrypcyjny (A/B/C) w danym
    miesiącu — używana przez backfill (pętla historyczna). Data faktury =
    customer.invoice_day (nie sztywno 1. dzień miesiąca).

    Faza 7, Zadanie 2 — zdarzenia klienckie (client_events) wpływają tu na:
    aktywność (event_aware_is_customer_active — BANKRUPTCY), próg bad-debt
    (podwyższony podczas TEMPORARY_HARDSHIP), status ostatniej faktury
    (wymuszony WRITTEN_OFF w miesiącu bankructwa) i dodatkowe zamówienie
    (ONE_OFF_LARGE_PROJECT). Jak extra-consulting/K06 — ten sam, świadomie
    ograniczony zakres: tylko backfill miesięczny, nie generate_daily_orders
    (poza samą aktywnością/BANKRUPTCY, zob. niżej)."""
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
            # Faza 7b, Zadanie 1e — MACRO_SHOCK (COVID_2020): podnosi OVERDUE,
            # zachowuje WRITTEN_OFF na poziomie sprzed tej korekty (czy to
            # normalnym, czy już podniesionym przez TEMPORARY_HARDSHIP powyżej).
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
                continue  # ostatnia faktura już wystawiona (odpisana) — klient znika od przyszłego miesiąca

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
            raise ValueError(f"Nieznany order_pattern: {pattern!r} dla klienta {customer.number}")

    return orders


def generate_daily_orders(year: int, month: int, day: int) -> list[Order]:
    """Generuje zamówienia dla konkretnego dnia — wystawia fakturę tylko tym
    klientom, dla których dzisiaj wypada ich invoice_day i którzy są już
    onboardowani (order_date >= onboarding_date). K06 (consulting,
    invoice_day=None) jest tu pomijany — ma osobną logikę wyzwalania
    (should_generate_consulting), nierozłożoną na konkretny dzień miesiąca.

    Faza 7, Zadanie 2 — używa event_aware_is_customer_active (nie samego
    roster.is_customer_active), żeby żywy cron/tryb daily przestał
    wystawiać faktury klientowi, którego BANKRUPTCY wystrzeliło podczas
    backfillu miesięcznego — reszta efektów zdarzeń (extra order,
    podwyższony bad-debt) zostaje świadomie tylko w generate_monthly_orders,
    zob. tamten docstring."""
    orders: list[Order] = []

    for customer in CUSTOMERS:
        if customer.invoice_day is None:
            continue  # K06 consulting — osobna logika
        if customer.invoice_day != day:
            continue

        order_date = date(year, month, day)
        if not event_aware_is_customer_active(customer, order_date):
            continue

        lines = build_order_lines(customer, order_date)
        orders.append(_build_order(customer, year, month, day, lines))

    return orders
