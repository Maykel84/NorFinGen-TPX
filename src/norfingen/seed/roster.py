"""Single source of truth dla statycznych danych firmy NorFinGen.

Dane przepisane 1:1 z docs/norfingen_warstwa1_schemas.html (Department, Employee,
Customer, Supplier) i docs/norfingen_warstwa2_schemas.html (katalog Product, wzorce
zamówień A/B/C/D, rytm i konta GL dostawców). Wszystkie inne moduły (generatory,
funkcje payroll) czytają stąd — żadne dane firmowe nie są duplikowane gdzie indziej.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from norfingen.models.service import BillingModel, Service, ServiceSegmentAvailability


@dataclass(frozen=True)
class DepartmentSeed:
    number: int
    name: str


@dataclass(frozen=True)
class EmployeeSeed:
    number: str  # "E01" – "E16"
    first_name: str
    last_name: str
    department_number: int  # FK -> DepartmentSeed.number
    start_date: date
    phase: str  # founding / growth1 / growth2 / merger
    role: str
    annual_salary: float  # NOK / rok


@dataclass(frozen=True)
class CustomerSeed:
    number: str  # "K01" – "K12"
    name: str
    segment: str  # Enterprise / Mid-market / SMB
    city: str
    order_pattern: str  # A (IT Support) / B (IT Support + Licencja) / C (Licencja only) / D (Consulting)
    support_product: Optional[str] = None  # numer Product dla linii IT Support
    license_product: Optional[str] = None  # numer Product dla linii Licencja
    invoice_day: Optional[int] = None  # dzień miesiąca wystawienia faktury; None = nieregularny (K06 consulting)
    payment_terms: int = 30  # dni do terminu płatności (net 14/30/45)
    onboarding_date: date = field(kw_only=True)  # data rozpoczęcia współpracy — brak zamówień przed tą datą
    churn_date: Optional[date] = field(default=None, kw_only=True)  # data odejścia — brak zamówień po tej dacie (None = brak churn)


@dataclass(frozen=True)
class SupplierSeed:
    number: str  # "L01" – "L08"
    name: str
    cost_category: str
    gl_account: int  # konto kosztowe DR (6xxx/7xxx)
    rhythm: str  # opis cykliczności faktur
    amount_min: float  # NOK, kwota netto (excl. VAT)
    amount_max: float
    capitalization_threshold: Optional[float] = None  # L05: >= 30 000 -> kapitalizacja
    capitalization_account: Optional[int] = None  # L05: 1200 Maskiner og anlegg


@dataclass(frozen=True)
class ProjectSeed:
    number: str  # "PRJ001" – "PRJ008"
    name: str
    customer_id: int  # numeryczne id klienta (FK -> CustomerSeed, zob. numeric_id)
    start_date: date


@dataclass(frozen=True)
class ProductSeed:
    number: str  # "P01" – "P06"
    name: str
    category: str
    gl_account: int  # 3000 (usługi) / 3100 (licencje)
    service_code: str  # FK -> Service.code (Faza 1) — S01-S04
    default_price: Optional[float] = None  # None = zmienne (P06 consulting)


DEPARTMENTS: list[DepartmentSeed] = [
    DepartmentSeed(number=1, name="Salg"),
    DepartmentSeed(number=2, name="Leveranse"),
    DepartmentSeed(number=3, name="Teknologi"),
    DepartmentSeed(number=4, name="Økonomi"),
]


EMPLOYEES: list[EmployeeSeed] = [
    # --- Założenie firmy: kohorta założycielska rozłożona na 4 miesiące
    # (2019-01 -> 2019-04), nie jednego dnia — realistyczne budowanie zespołu
    # od zera, nie firma "narodzona w pełni ukształtowana".
    EmployeeSeed("E01", "Erik", "Strand", 1, date(2019, 1, 1), "founding", "Sales Manager", 880_000),
    EmployeeSeed("E02", "Marte", "Haugen", 2, date(2019, 2, 1), "founding", "IT Consultant", 720_000),
    EmployeeSeed("E03", "Bjørn", "Dahl", 2, date(2019, 2, 15), "founding", "Senior IT Specialist", 800_000),
    EmployeeSeed("E04", "Kari", "Lund", 2, date(2019, 3, 1), "founding", "IT Support", 620_000),
    EmployeeSeed("E05", "Thomas", "Berg", 3, date(2019, 3, 15), "founding", "System Architect", 860_000),
    EmployeeSeed("E06", "Ingrid", "Moen", 4, date(2019, 4, 1), "founding", "Finance Manager", 820_000),
    # --- Wzrost 1: 2020-03-01 (+2 osoby) ---
    EmployeeSeed("E07", "Lars", "Eriksen", 2, date(2020, 3, 1), "growth1", "IT Consultant", 700_000),
    EmployeeSeed("E08", "Silje", "Voss", 3, date(2020, 3, 1), "growth1", "Developer", 760_000),
    # --- Wzrost 2: 2021-06-01 (+2 osoby) ---
    EmployeeSeed("E09", "Ole", "Pedersen", 2, date(2021, 6, 1), "growth2", "IT Specialist", 680_000),
    EmployeeSeed("E10", "Nina", "Holm", 2, date(2021, 6, 1), "growth2", "Project Coordinator", 700_000),
    # --- Merger: 2022-09-01 (+6 osób) ---
    EmployeeSeed("E11", "Petter", "Nygaard", 1, date(2022, 9, 1), "merger", "Account Manager", 720_000),
    EmployeeSeed("E12", "Hanna", "Kjær", 2, date(2022, 9, 1), "merger", "IT Consultant", 700_000),
    EmployeeSeed("E13", "Rune", "Sæther", 2, date(2022, 9, 1), "merger", "IT Support", 620_000),
    EmployeeSeed("E14", "Camilla", "Bø", 2, date(2022, 9, 1), "merger", "IT Specialist", 680_000),
    EmployeeSeed("E15", "Anders", "Johansen", 3, date(2022, 9, 1), "merger", "Developer", 760_000),
    EmployeeSeed("E16", "Marit", "Sundby", 4, date(2022, 9, 1), "merger", "Admin Coordinator", 640_000),
]


# Stopniowy onboarding — 6 klientów do końca 2019 (rok 1, po zespole 5+ osób),
# +2 w 2020 (rok stabilizacji przy 8 os.), +2 w 2021 (wzrost do 10 os.),
# +2 w 2022 przed/po fuzji do 16 os. Enterprise/Mid-market najpierw, żeby
# przychody rosły szybciej niż przy losowej kolejności.
CUSTOMERS: list[CustomerSeed] = [
    CustomerSeed("K01", "Bergström Industri AS", "Enterprise", "Bergen", "B", "P01", "P04",
                 invoice_day=3, payment_terms=30, onboarding_date=date(2019, 3, 1)),  # pierwszy klient
    CustomerSeed("K02", "Halvorsen & Partnere AS", "Mid-market", "Oslo", "A", "P02", None,
                 invoice_day=7, payment_terms=14, onboarding_date=date(2019, 6, 1)),  # szybki płatnik
    CustomerSeed("K03", "Nordkraft Energi AS", "Enterprise", "Tromsø", "B", "P01", "P04",
                 invoice_day=1, payment_terms=45, onboarding_date=date(2019, 4, 15)),  # duży klient, dłuższy termin
    CustomerSeed("K04", "Solberg Bygg AS", "SMB", "Stavanger", "A", "P03", None,
                 invoice_day=10, payment_terms=30, onboarding_date=date(2020, 8, 1)),  # po ustabilizowaniu zespołu
    CustomerSeed("K05", "Fjord Logistikk AS", "Mid-market", "Bergen", "A", "P02", None,
                 invoice_day=5, payment_terms=30, onboarding_date=date(2019, 9, 1)),
    CustomerSeed("K06", "Telemark Konsult AS", "SMB", "Skien", "D", None, None,
                 invoice_day=None, payment_terms=14, onboarding_date=date(2022, 3, 1)),  # consulting — ostatni, nieregularny
    CustomerSeed("K07", "Østfold Finans AS", "Mid-market", "Fredrikstad", "B", "P02", "P05",
                 invoice_day=15, payment_terms=30, onboarding_date=date(2020, 1, 1)),
    CustomerSeed("K08", "Innlandet Helse AS", "Enterprise", "Hamar", "A", "P01", None,
                 invoice_day=1, payment_terms=45, onboarding_date=date(2019, 7, 15)),
    CustomerSeed("K09", "Vestfold Handel AS", "SMB", "Tønsberg", "A", "P03", None,
                 invoice_day=20, payment_terms=30, onboarding_date=date(2021, 2, 1),  # po wzroście do 10 os.
                 churn_date=date(2024, 11, 30)),  # odchodzi po 3,5 roku współpracy — realistyczny churn SMB
    CustomerSeed("K10", "Kristiansen Gruppen AS", "Mid-market", "Oslo", "C", None, "P05",
                 invoice_day=8, payment_terms=30, onboarding_date=date(2020, 4, 1)),
    CustomerSeed("K11", "Rogaland Teknikk AS", "Enterprise", "Stavanger", "B", "P01", "P04",
                 invoice_day=2, payment_terms=30, onboarding_date=date(2019, 10, 15)),  # komplet 4 Enterprise do końca 2019
    CustomerSeed("K12", "Agder Maritime AS", "SMB", "Kristiansand", "A", "P03", None,
                 invoice_day=12, payment_terms=30, onboarding_date=date(2021, 9, 1)),
]


def _customer_price_multiplier(customer_number: str) -> float:
    """Indywidualny mnożnik ceny per klient — symuluje wynik negocjacji przy
    podpisaniu kontraktu (±8%), ustalony raz i na stałe. Deterministyczny: lokalny
    random.Random zasiany stringiem, NIE wbudowany hash() — hash() na str jest
    solony losowo per proces w Pythonie 3 (bezpieczeństwo), co złamałoby
    powtarzalność backfillu przy każdym kolejnym uruchomieniu."""
    rng = random.Random(f"price-multiplier-{customer_number}")
    return round(rng.uniform(0.92, 1.08), 4)


# Mnożnik jest częścią wyniku negocjacji z klientem, nie osobnym polem
# CustomerSeed — liczony raz przy imporcie modułu z numeru klienta.
CUSTOMER_PRICE_MULTIPLIER: dict[str, float] = {
    c.number: _customer_price_multiplier(c.number) for c in CUSTOMERS
}


SUPPLIERS: list[SupplierSeed] = [
    SupplierSeed("L01", "Microsoft Norge AS", "Licencje software", 6410, "monthly_day_1", 85_000, 85_000),
    SupplierSeed("L02", "Telenor Norge AS", "Telekomunikacja", 6900, "monthly_day_5", 17_100, 18_900),
    SupplierSeed("L03", "Reitan Convenience AS", "Kontor / catering", 6800, "monthly_day_15", 8_000, 14_000),
    SupplierSeed("L04", "Statsbygg", "Wynajem biura", 6300, "monthly_day_1", 45_000, 45_000),
    SupplierSeed(
        "L05",
        "Sandvik IT Solutions AS",
        "Sprzęt IT",
        6540,
        "3_5x_yearly",
        15_000,
        80_000,
        capitalization_threshold=30_000,
        capitalization_account=1200,
    ),
    SupplierSeed("L06", "Advokatfirma Thommessen", "Usługi prawne", 6700, "quarterly_mar_jun_sep_dec", 25_000, 60_000),
    SupplierSeed("L07", "Avis Norge AS", "Wynajem samochodów", 7000, "monthly_day_20", 12_000, 28_000),
    SupplierSeed("L08", "Nordic Insurance Partners AS", "Ubezpieczenia", 7500, "quarterly_jan_apr_jul_oct", 38_000, 38_000),
]


PROJECTS: list[ProjectSeed] = [
    ProjectSeed("PRJ001", "IT Support 2026 — Bergström", 1, date(2026, 1, 1)),
    ProjectSeed("PRJ002", "IT Support 2026 — Nordkraft", 3, date(2026, 1, 1)),
    ProjectSeed("PRJ003", "IT Support 2026 — Innlandet", 8, date(2026, 1, 1)),
    ProjectSeed("PRJ004", "IT Support 2026 — Rogaland", 11, date(2026, 1, 1)),
    ProjectSeed("PRJ005", "Digitalisering — Telemark", 6, date(2026, 3, 1)),
    ProjectSeed("PRJ006", "IT Support 2026 — Halvorsen", 2, date(2026, 1, 1)),
    ProjectSeed("PRJ007", "IT Support 2026 — Fjord", 5, date(2026, 1, 1)),
    ProjectSeed("PRJ008", "IT Support 2026 — Østfold", 7, date(2026, 1, 1)),
]


PRODUCTS: list[ProductSeed] = [
    # Ceny obniżone ~17% (2026-07) w celu domknięcia marży operacyjnej do
    # docelowego przedziału 15-25% (wcześniej ~33% — koszty operacyjne za niskie
    # względem przychodów przy niezmienionych stawkach; koszty pracownicze
    # dominują strukturę kosztów i nie były tu ruszane, patrz notatka w docs/).
    # service_code (Faza 1): P01-P03 (support) -> S01, P04-P05 (licencje/Microsoft)
    # -> S02, P06 (consulting) -> S04, P07 (Faza 2) -> S03 (Cyberbezpieczeństwo).
    #
    # Faza 2: cena faktycznie użyta na fakturze liczy się teraz z
    # Service.base_price_{segment} (build_order_lines/product_for_service w
    # order_generator.py), nie z default_price poniżej — te produkty pozostają
    # jako referencja Tripletex (product_id) i etykieta na fakturze, jeden
    # kanoniczny produkt per usługa niezależnie od segmentu klienta. P02/P03/P05
    # nie są już używane do generowania linii (zastąpione bundlingiem
    # segmentowym), zostają w katalogu dla zgodności wstecznej/FK.
    ProductSeed("P01", "Managed IT Support", "Subskrypcja mies.", 3000, "S01", 183_000),
    ProductSeed("P02", "IT Support — Mid-market", "Subskrypcja mies.", 3000, "S01", 133_000),
    ProductSeed("P03", "IT Support — SMB", "Subskrypcja mies.", 3000, "S01", 62_000),
    ProductSeed("P04", "Zarządzanie infrastrukturą Microsoft", "Subskrypcja mies.", 3100, "S02", 79_000),
    ProductSeed("P05", "Software License — Mid-market", "Licencja mies.", 3100, "S02", 58_000),
    ProductSeed("P06", "Konsulting i digitalizacja", "Projekt / zlecenie", 3000, "S04", None),
    ProductSeed("P07", "Cyberbezpieczeństwo", "Subskrypcja mies.", 3000, "S03", None),
]


# Katalog usług (Faza 1) — niezależny od konkretnych cen per klient (te ustala
# CustomerSeed/CUSTOMER_PRICE_MULTIPLIER). Ceny bazowe z 2019 (rok bazowy
# apply_annual_inflation), per segment.
#
# Faza 2 (rekalibracja): pierwotne base_price_* (S01 Enterprise/Mid/SMB
# 45000/18000/4500, S02 20000/8000, S03 15000) zawaliły marżę operacyjną do
# -70%..-183%/rok (payroll 16-osobowego zespołu, skalibrowany w poprzednich
# sesjach względem starych cen Product, przewyższał cały przychód nawet 2.4x) —
# skorygowane w górę do wartości poniżej, dopasowanych pod OBECNĄ liczbę
# klientów (12), nie docelowe 40-50 z Fazy 4. Świadomy kompromis: cena SMB
# (49 000 NOK/mies. = 588 000 NOK/rok) jest wyższa niż realny rynek dla
# pojedynczego małego klienta (20-40 tys. NOK/rok) — do skorygowania w dół
# w Fazie 4, gdy wolumen klientów SMB pozwoli obniżyć cenę per klient bez
# zawalenia przychodu firmy.
SERVICES: list[Service] = [
    Service(
        code="S01",
        name="Managed IT Support",
        description="Helpdesk, incydenty, monitoring infrastruktury IT",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ALL,
        base_price_enterprise=133_000,
        base_price_mid=84_500,
        base_price_smb=49_000,
    ),
    Service(
        code="S02",
        name="Zarządzanie infrastrukturą Microsoft",
        description="Administracja Azure/M365, zarządzana infrastruktura chmurowa",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ENTERPRISE_MID,
        base_price_enterprise=59_000,
        base_price_mid=37_500,
        base_price_smb=None,
    ),
    Service(
        code="S03",
        name="Cyberbezpieczeństwo",
        description="Monitoring bezpieczeństwa, zgodność NIS2, reagowanie na incydenty",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ENTERPRISE_ONLY,
        base_price_enterprise=44_000,
        base_price_mid=None,
        base_price_smb=None,
    ),
    Service(
        code="S04",
        name="Konsulting i digitalizacja",
        description="Projekty digitalizacyjne, doradztwo IT, wdrożenia",
        billing_model=BillingModel.HOURLY,
        availability=ServiceSegmentAvailability.ALL,
        base_price_enterprise=1_450,
        base_price_mid=1_450,
        base_price_smb=1_450,
    ),
]


# Faza 2 — który klient kupuje jakie usługi, wg segmentu. Niezależne od
# order_pattern/support_product/license_product (Faza 1 i wcześniej) — te pola
# CustomerSeed zostają (m.in. sterują dniem/rytmem fakturowania i wzorcem D
# konsultingowym K06), ale liczba i dobór linii subskrypcyjnych A/B/C liczy się
# teraz z bundlingu per segment, nie z przypisanych produktów.
SEGMENT_SERVICE_BUNDLES: dict[str, tuple[str, ...]] = {
    "Enterprise": ("S01", "S02", "S03"),
    "Mid-market": ("S01", "S02"),
    "SMB": ("S01",),
}


def get_customer_services(customer: CustomerSeed) -> list[str]:
    """Zwraca kody usług, które klient kupuje w standardowej subskrypcji, wg
    segmentu: Enterprise pełny pakiet S01+S02+S03, Mid-market S01+S02, SMB
    tylko S01."""
    return list(SEGMENT_SERVICE_BUNDLES[customer.segment])


def service_base_price(service: Service, segment: str) -> Optional[float]:
    """Cena bazowa usługi (rok 2019, przed inflacją) dla danego segmentu."""
    if segment == "Enterprise":
        return service.base_price_enterprise
    if segment == "Mid-market":
        return service.base_price_mid
    return service.base_price_smb


_PRODUCT_FOR_SERVICE: dict[str, ProductSeed] = {}
for _product in PRODUCTS:
    _PRODUCT_FOR_SERVICE.setdefault(_product.service_code, _product)
del _product


def product_for_service(service_code: str) -> ProductSeed:
    """Produkt kanoniczny (referencja Tripletex/FK) dla danej usługi — jeden
    per service_code niezależnie od segmentu klienta, bo Faza 2 liczy cenę
    bezpośrednio z Service.base_price_* (zob. service_base_price), nie z
    Product.default_price. Zwraca pierwszy produkt w PRODUCTS zmapowany do
    tego kodu (P01 dla S01, P04 dla S02, P07 dla S03, P06 dla S04)."""
    try:
        return _PRODUCT_FOR_SERVICE[service_code]
    except KeyError:
        raise KeyError(f"Brak produktu zmapowanego do usługi: {service_code!r}")


def employee_by_number(number: str) -> EmployeeSeed:
    for e in EMPLOYEES:
        if e.number == number:
            return e
    raise KeyError(f"Nieznany numer pracownika: {number}")


def customer_by_number(number: str) -> CustomerSeed:
    for c in CUSTOMERS:
        if c.number == number:
            return c
    raise KeyError(f"Nieznany numer klienta: {number}")


def customer_by_id(customer_id: int) -> CustomerSeed:
    """Odwrotność numeric_id() dla klientów — customer_id z TripletexRef/bazy
    (1-12) -> CustomerSeed. Potrzebne tam, gdzie mamy tylko numeryczne id
    (np. Order.customer.id), nie kod seed ("K01")."""
    return customer_by_number(f"K{customer_id:02d}")


def supplier_by_number(number: str) -> SupplierSeed:
    for s in SUPPLIERS:
        if s.number == number:
            return s
    raise KeyError(f"Nieznany numer dostawcy: {number}")


def supplier_by_id(supplier_id: int) -> SupplierSeed:
    """Odwrotność numeric_id() dla dostawców — supplier_id z TripletexRef/bazy
    (1-8) -> SupplierSeed."""
    return supplier_by_number(f"L{supplier_id:02d}")


def product_by_number(number: str) -> ProductSeed:
    for p in PRODUCTS:
        if p.number == number:
            return p
    raise KeyError(f"Nieznany numer produktu: {number}")


def service_by_code(code: str) -> Service:
    for s in SERVICES:
        if s.code == code:
            return s
    raise KeyError(f"Nieznany kod usługi: {code}")


def project_by_number(number: str) -> ProjectSeed:
    for p in PROJECTS:
        if p.number == number:
            return p
    raise KeyError(f"Nieznany numer projektu: {number}")


def project_by_id(project_id: int) -> ProjectSeed:
    """Odwrotność numeric_id() dla projektów — project_id (1-8) -> ProjectSeed."""
    return project_by_number(f"PRJ{project_id:03d}")


def numeric_id(code: str) -> int:
    """Konwertuje kod seed (E07, K03, L05, P02, PRJ001) na numeryczne id
    Warstwy 1/2 (Employee 1-16, Customer 1-12, Supplier 1-8, Product 1-6,
    Project 1-8 — przypisywane sekwencyjnie wg kolejności w dokumentacji).
    Obsługuje zarówno jednoliterowe (E/K/L/P), jak i wieloliterowe (PRJ)
    prefiksy."""
    return int(re.sub(r"^[A-Za-z]+", "", code))
