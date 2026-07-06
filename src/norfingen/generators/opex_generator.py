"""Generator dodatkowych kosztów operacyjnych (Faza 3): kantyna, reprezentacja,
transport (kilometrówka + konferencje), sprzęt do wdrożenia u klienta (COGS).

W przeciwieństwie do supplier_invoice_generator (faktury od zewnętrznych
dostawców L01-L08, z VAT i dokumentem SupplierInvoice) te koszty NIE mają
odpowiadającej faktury zakupu — to bezpośrednie koszty gotówkowe firmy,
księgowane wprost: Voucher z 2 postingami (DR konto kosztowe / CR 1910
Bankinnskudd), bez VAT, zgodnie z wzorcem podanym w zadaniu ("prosty koszt
gotówkowy, bez VAT").

Kwoty (roster.CANTEEN_SUBSIDY_PER_EMPLOYEE_MONTHLY,
REPRESENTATION_COST_PER_*_CLIENT_MONTHLY, KM_RATE_2019,
CONFERENCE_HOTEL_RATES) są celowo skromne — lekcja z Fazy 2 (dosłowne
przepisanie cen bez weryfikacji marży zawaliło wynik do -183%). Sprzęt do
wdrożenia (Zadanie 4b) to jedyny nowy koszt COGS (konto 4290) — jednorazowy
przy onboardingu klienta Enterprise/Mid-market, nie powtarzający się.
"""

from __future__ import annotations

import random
from datetime import date

from norfingen.generators.order_generator import apply_annual_inflation
from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid
from norfingen.seed.payroll import active_employees
from norfingen.seed.roster import (
    CONFERENCE_HOTEL_RATES,
    CUSTOMERS,
    CustomerSeed,
    active_customers,
    calc_canteen_cost,
    calc_client_visit_transport,
    calc_representation_cost,
)

ACCOUNT_BANK = 1910
ACCOUNT_CANTEEN = 7350  # Kantinetilskudd
ACCOUNT_REPRESENTATION = 7420  # Representasjon
ACCOUNT_TRANSPORT = 7000  # Reisekostnader — istniejące konto (dzielone z L07 Avis,
# zob. moduł-level docstring supplier_invoice_generator: brak "miksu" do rozdzielenia,
# kilometrówka/konferencje to po prostu nowe podkategorie tej samej pozycji NS4102)
ACCOUNT_SERVICE_EQUIPMENT = 4290  # Driftsmateriell for kundeleveranse (COGS)

CONFERENCE_MONTHS = {3, 9, 11}
CONFERENCE_PROBABILITY = 0.6
CONFERENCE_TICKET_MIN = 3_000.0
CONFERENCE_TICKET_MAX = 8_000.0
CONFERENCE_PER_DIEM_PER_NIGHT = 750.0

SERVICE_EQUIPMENT_COST_RANGE = {
    "Enterprise": (45_000.0, 90_000.0),
    "Mid-market": (15_000.0, 35_000.0),
}

MONTH_NAMES_NO = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]


def _simple_cost_voucher(on_date: date, account_number: int, description: str, amount: float) -> Voucher:
    """Voucher 2-postingowy: DR konto kosztowe / CR 1910 Bankinnskudd, bez VAT
    (koszt gotówkowy płacony bezpośrednio, bez pośredniego dokumentu SupplierInvoice)."""
    amount = round(amount, 2)
    voucher = Voucher(
        date=on_date,
        description=description,
        voucherType=VoucherType.OPERATING_COST,
        postings=[
            Posting(date=on_date, account=acct(account_number), amount=amount),
            Posting(date=on_date, account=acct(ACCOUNT_BANK), amount=-amount),
        ],
    )
    assert_voucher_valid(voucher)
    return voucher


def generate_conference_trip(year: int, month: int, rng: random.Random) -> dict | None:
    """2-3 wyjazdy konferencyjne rocznie (np. NKUL, Sikkerhetsfestivalen,
    Microsoft Ignite Tour Norway). Bilety + hotel + diety. Deterministyczne —
    rng lokalny przekazany przez wywołującego (random.Random(string), nie
    globalny random ani wbudowany hash())."""
    if month not in CONFERENCE_MONTHS:
        return None
    if rng.random() > CONFERENCE_PROBABILITY:
        return None
    city = rng.choice(["Oslo", "Bergen", "Trondheim"])
    nights = rng.choice([1, 2])
    hotel_cost = CONFERENCE_HOTEL_RATES[city] * nights
    ticket_cost = rng.uniform(CONFERENCE_TICKET_MIN, CONFERENCE_TICKET_MAX)
    per_diem = CONFERENCE_PER_DIEM_PER_NIGHT * nights
    return {
        "description": f"Konferansereise {city}",
        "amount": round(hotel_cost + ticket_cost + per_diem, 2),
    }


def should_generate_service_equipment_purchase(customer: CustomerSeed, month: int, rng: random.Random | None = None) -> bool:
    """Sprzęt kupowany do wdrożenia u klienta (routery, serwery, urządzenia
    sieciowe) — tylko Enterprise/Mid-market (SMB ma wyłącznie S01, mniejszy
    zakres wdrożenia bez dedykowanego sprzętu). Sprawdza TYLKO miesiąc — o to
    czy to właściwy ROK onboardingu (żeby koszt nie powtarzał się co roku w
    tym samym miesiącu) decyduje wywołujący (generate_monthly_opex), zob. jego
    docstring. Parametr rng zachowany dla zgodności sygnatury z zadaniem —
    predykat jest w pełni deterministyczny z dat/segmentu, nieużywany."""
    return month == customer.onboarding_date.month and customer.segment in ("Enterprise", "Mid-market")


def calc_service_equipment_cost(customer: CustomerSeed) -> float:
    """Jednorazowy koszt wdrożeniowy przy onboardingu. Deterministyczne
    (random.Random(string) zasiany numerem klienta, NIE globalny random.uniform
    z pseudokodu zadania — złamałoby powtarzalność backfillu między
    uruchomieniami, zob. SESSION_HANDOFF.md pkt 6)."""
    rng = random.Random(f"service-equipment-{customer.number}")
    low, high = SERVICE_EQUIPMENT_COST_RANGE[customer.segment]
    return round(rng.uniform(low, high), -2)


def generate_monthly_opex(year: int, month: int) -> list[Voucher]:
    """Generuje wszystkie nowe koszty operacyjne Fazy 3 dla jednego miesiąca:
    kantyna (co miesiąc), reprezentacja (co miesiąc, per aktywny klient
    Enterprise/Mid), kilometrówka (sezonowa), konferencje (Q1/Q3 wybranych
    miesięcy, losowo), sprzęt wdrożeniowy (tylko w miesiącu I ROKU onboardingu
    klienta — should_generate_service_equipment_purchase sprawdza tylko
    miesiąc, więc dodatkowy warunek `customer.onboarding_date.year == year`
    tutaj zapobiega powtarzaniu kosztu co roku)."""
    on_date = date(year, month, 1)
    month_label = f"{MONTH_NAMES_NO[month - 1]} {year}"
    vouchers: list[Voucher] = []

    employee_count = len(active_employees(on_date))
    if employee_count > 0:
        canteen_cost = calc_canteen_cost(employee_count)
        vouchers.append(_simple_cost_voucher(on_date, ACCOUNT_CANTEEN, f"Kantinetilskudd {month_label}", canteen_cost))

    customers = active_customers(on_date)

    representation_base = calc_representation_cost(customers)
    if representation_base > 0:
        representation_cost = apply_annual_inflation(representation_base, year)
        vouchers.append(_simple_cost_voucher(on_date, ACCOUNT_REPRESENTATION, f"Representasjon {month_label}", representation_cost))

    transport_cost = calc_client_visit_transport(customers, month)
    if transport_cost > 0:
        vouchers.append(_simple_cost_voucher(on_date, ACCOUNT_TRANSPORT, f"Kjøregodtgjørelse — kundebesøk {month_label}", transport_cost))

    conference_rng = random.Random(f"conference-{year}-{month}")
    trip = generate_conference_trip(year, month, conference_rng)
    if trip is not None:
        vouchers.append(_simple_cost_voucher(on_date, ACCOUNT_TRANSPORT, trip["description"], trip["amount"]))

    for customer in CUSTOMERS:
        if customer.onboarding_date.year == year and should_generate_service_equipment_purchase(customer, month):
            equipment_cost = calc_service_equipment_cost(customer)
            vouchers.append(_simple_cost_voucher(
                customer.onboarding_date, ACCOUNT_SERVICE_EQUIPMENT,
                f"Driftsmateriell for kundeleveranse — {customer.number}", equipment_cost,
            ))

    return vouchers
