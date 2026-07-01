"""Single source of truth dla statycznych danych firmy NorFinGen.

Dane przepisane 1:1 z docs/norfingen_warstwa1_schemas.html (Department, Employee,
Customer, Supplier) i docs/norfingen_warstwa2_schemas.html (katalog Product, wzorce
zamówień A/B/C/D, rytm i konta GL dostawców). Wszystkie inne moduły (generatory,
funkcje payroll) czytają stąd — żadne dane firmowe nie są duplikowane gdzie indziej.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


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
class ProductSeed:
    number: str  # "P01" – "P06"
    name: str
    category: str
    gl_account: int  # 3000 (usługi) / 3100 (licencje)
    default_price: Optional[float] = None  # None = zmienne (P06 consulting)


DEPARTMENTS: list[DepartmentSeed] = [
    DepartmentSeed(number=1, name="Salg"),
    DepartmentSeed(number=2, name="Leveranse"),
    DepartmentSeed(number=3, name="Teknologi"),
    DepartmentSeed(number=4, name="Økonomi"),
]


EMPLOYEES: list[EmployeeSeed] = [
    # --- Założenie firmy: 2019-01-02 (6 osób) ---
    EmployeeSeed("E01", "Erik", "Strand", 1, date(2019, 1, 2), "founding", "Sales Manager", 880_000),
    EmployeeSeed("E02", "Marte", "Haugen", 2, date(2019, 1, 2), "founding", "IT Consultant", 720_000),
    EmployeeSeed("E03", "Bjørn", "Dahl", 2, date(2019, 1, 2), "founding", "Senior IT Specialist", 800_000),
    EmployeeSeed("E04", "Kari", "Lund", 2, date(2019, 1, 2), "founding", "IT Support", 620_000),
    EmployeeSeed("E05", "Thomas", "Berg", 3, date(2019, 1, 2), "founding", "System Architect", 860_000),
    EmployeeSeed("E06", "Ingrid", "Moen", 4, date(2019, 1, 2), "founding", "Finance Manager", 820_000),
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


CUSTOMERS: list[CustomerSeed] = [
    CustomerSeed("K01", "Bergström Industri AS", "Enterprise", "Bergen", "B", "P01", "P04"),
    CustomerSeed("K02", "Halvorsen & Partnere AS", "Mid-market", "Oslo", "A", "P02", None),
    CustomerSeed("K03", "Nordkraft Energi AS", "Enterprise", "Tromsø", "B", "P01", "P04"),
    CustomerSeed("K04", "Solberg Bygg AS", "SMB", "Stavanger", "A", "P03", None),
    CustomerSeed("K05", "Fjord Logistikk AS", "Mid-market", "Bergen", "A", "P02", None),
    CustomerSeed("K06", "Telemark Konsult AS", "SMB", "Skien", "D", None, None),
    CustomerSeed("K07", "Østfold Finans AS", "Mid-market", "Fredrikstad", "B", "P02", "P05"),
    CustomerSeed("K08", "Innlandet Helse AS", "Enterprise", "Hamar", "A", "P01", None),
    CustomerSeed("K09", "Vestfold Handel AS", "SMB", "Tønsberg", "A", "P03", None),
    CustomerSeed("K10", "Kristiansen Gruppen AS", "Mid-market", "Oslo", "C", None, "P05"),
    CustomerSeed("K11", "Rogaland Teknikk AS", "Enterprise", "Stavanger", "B", "P01", "P04"),
    CustomerSeed("K12", "Agder Maritime AS", "SMB", "Kristiansand", "A", "P03", None),
]


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


PRODUCTS: list[ProductSeed] = [
    # Ceny obniżone ~17% (2026-07) w celu domknięcia marży operacyjnej do
    # docelowego przedziału 15-25% (wcześniej ~33% — koszty operacyjne za niskie
    # względem przychodów przy niezmienionych stawkach; koszty pracownicze
    # dominują strukturę kosztów i nie były tu ruszane, patrz notatka w docs/).
    ProductSeed("P01", "IT Support — Enterprise", "Subskrypcja mies.", 3000, 183_000),
    ProductSeed("P02", "IT Support — Mid-market", "Subskrypcja mies.", 3000, 133_000),
    ProductSeed("P03", "IT Support — SMB", "Subskrypcja mies.", 3000, 62_000),
    ProductSeed("P04", "Software License — Enterprise", "Licencja mies.", 3100, 79_000),
    ProductSeed("P05", "Software License — Mid-market", "Licencja mies.", 3100, 58_000),
    ProductSeed("P06", "IT Consulting", "Projekt / zlecenie", 3000, None),
]


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


def supplier_by_number(number: str) -> SupplierSeed:
    for s in SUPPLIERS:
        if s.number == number:
            return s
    raise KeyError(f"Nieznany numer dostawcy: {number}")


def product_by_number(number: str) -> ProductSeed:
    for p in PRODUCTS:
        if p.number == number:
            return p
    raise KeyError(f"Nieznany numer produktu: {number}")


def numeric_id(code: str) -> int:
    """Konwertuje kod seed (E07, K03, L05, P02) na numeryczne id Warstwy 1
    (Employee 1-16, Customer 1-12, Supplier 1-8, Product 1-6 — przypisywane
    sekwencyjnie wg kolejności w dokumentacji)."""
    return int(code[1:])
