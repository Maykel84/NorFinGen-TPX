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
    EmployeeSeed("E03", "Bjørn", "Dahl", 2, date(2019, 2, 1), "founding", "Senior IT Specialist", 800_000),
    EmployeeSeed("E04", "Kari", "Lund", 2, date(2019, 3, 1), "founding", "IT Support", 620_000),
    EmployeeSeed("E05", "Thomas", "Berg", 3, date(2019, 3, 1), "founding", "System Architect", 860_000),
    EmployeeSeed("E06", "Ingrid", "Moen", 4, date(2019, 4, 1), "founding", "Finance Manager", 820_000),
    # --- Wzrost 1: 2020-03-01 (+2 osoby) ---
    EmployeeSeed("E07", "Lars", "Eriksen", 2, date(2020, 3, 2), "growth1", "IT Consultant", 700_000),
    EmployeeSeed("E08", "Silje", "Voss", 3, date(2020, 3, 2), "growth1", "Developer", 760_000),
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
    # --- Faza 6 (druga kalibracja, ZASTĘPUJE Fazę 4): zespół PRZESTAJE rosnąć
    # po jednym dociążeniu tuż po fuzji (E17) — nie skaluje się już liniowo z
    # portfelem klientów (Faza 4: 22 dalsze rekrutacje do 38 osób na 50
    # klientów). Powód: kalibracja względem realnych danych rynkowych
    # (Brønnøysundregistrene, zob. roster.calc_s01_cogs_monthly) pokazała, że
    # porównywalne norweskie firmy IT drift/support (Garnes Data AS: 17
    # pracowników, 48 mln NOK przychodu, marża 5,4%) obsługują duży portfel
    # klientów małym zespołem właśnie DLATEGO, że większość kosztu obsługi
    # (narzędzia RMM/PSA, licencje, sprzęt) jest kosztem materiałowym
    # (COGS pass-through), nie osobową (payroll) — i dlatego, że wsparcie
    # jest modelem ticketowym (jeden konsultant obsługuje wielu klientów
    # dziennie, zob. hours_generator.generate_daily_support_hours), nie 1:1
    # klient-konsultant. Poprzednia próba (Faza 4, 38 etatów) była
    # kalibrowana pod stary, dużo skromniejszy model kosztów (tylko Faza 3:
    # kantyna/reprezentacja/transport/sprzęt) i dawała nierealistycznie
    # wysoki przychód/pracownika względem realnych firm z tego segmentu.
    # E17 (Vegard Lien) zostaje jedynym dociążeniem po fuzji — zweryfikowane
    # symulacją PRZED backfillem (nie szacunkiem, zob. calc_target_headcount
    # niżej): marża 11,5% (2022) -> 7,1% (2023) -> 7,3% (2024) -> 7,0-7,5%
    # (2025) -> 6,9-7,6% (2026, częściowy/pełny rok) — płynny spadek do celu
    # 5,5-9%, nigdy poniżej progu bezpieczeństwa w latach dojrzałych.
    EmployeeSeed("E17", "Vegard", "Lien", 2, date(2022, 10, 3), "scaling", "Senior IT Consultant", 950_000),
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
                 invoice_day=1, payment_terms=45, onboarding_date=date(2019, 4, 15),  # duży klient, dłuższy termin
                 # Faza 7c, Zadanie 1 — MAJOR_INCIDENT_2023 (ENTERPRISE_CONTRACT_LOSS):
                 # utrata kontraktu na rzecz konkurencji przy odnowieniu, nie
                 # BANKRUPTCY (to jest zarezerwowane dla SMB) — firma klienta
                 # nadal istnieje, po prostu przestaje być klientem. Wybrana
                 # spośród 4 największych Enterprise (Bergström Industri,
                 # Nordkraft Energi, Rogaland Teknikk, Innlandet Helse) jako
                 # jedyna (razem z K08) bez żadnych wcześniejszych zdarzeń z
                 # Fazy 7/7b — druga co do wielkości (24,0M NOK), więc realny
                 # ciężar utraty. Ten sam mechanizm co K09/K15 (statyczne
                 # churn_date) — brak wymuszonego WRITTEN_OFF (w
                 # przeciwieństwie do BANKRUPTCY): to utrata przychodu na
                 # przyszłość, nie problem ze ściągalnością należności.
                 churn_date=date(2023, 4, 1)),
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
                 # Faza 7b, Zadanie 1c — MACRO_SHOCK (COVID_2020): pierwotny
                 # onboarding 2020-04-01 wypadał w oknie lockdownu (marzec-
                 # czerwiec) — new_client_onboarding_freeze, przesunięte
                 # deterministycznie na pierwszy miesiąc po oknie (nie losowo,
                 # świadoma korekta historyczna, potwierdzona przez
                 # użytkownika mimo że wymaga pełnego re-backfillu).
                 invoice_day=8, payment_terms=30, onboarding_date=date(2020, 7, 1)),
    CustomerSeed("K11", "Rogaland Teknikk AS", "Enterprise", "Stavanger", "B", "P01", "P04",
                 invoice_day=2, payment_terms=30, onboarding_date=date(2019, 10, 15)),  # komplet 4 Enterprise do końca 2019
    CustomerSeed("K12", "Agder Maritime AS", "SMB", "Kristiansand", "A", "P03", None,
                 invoice_day=12, payment_terms=30, onboarding_date=date(2021, 9, 1)),
]


# Faza 4 — skalowanie z 12 do 50 klientów (K13-K50), onboarding rozłożony
# 2022-09 (fuzja) do 2026-07 (2022 fuzja: +4, 2023: +8, 2024: +10, 2025: +10,
# 2026 do lipca: +6 = 38 nowych). Docelowy segment mix: 15 Enterprise (4+11),
# 18 Mid-market (4+14), 17 SMB (4+13).
#
# Kohorta fuzji (2022-09-01, TA SAMA data co fuzja pracownicza E11-E16,
# rekalibracja #3) — 4 klienci = dokładnie 1/3 z 12 posiadanych w tym
# momencie, przejęci razem z pracownikami przejmowanej firmy (jedno spójne
# zdarzenie biznesowe, nie dwa osobne). Onboardują się PRZED
# CUSTOMER_PRICING_COHORT_CUTOFF (2023-01-01) -> LEGACY_SERVICES, nie
# SCALE_SERVICES (zob. get_service_price_table wyżej).
#
# order_pattern/support_product/license_product NIE mają już znaczenia dla
# generowania linii zamówień od Fazy 2 (zob. order_generator.build_order_lines)
# — wszyscy nowi klienci dostają "A" / None / None, bo jedyne co ten wzorzec
# jeszcze robi to odróżnienie "zwykły abonament" (A/B/C) od "tylko konsulting,
# nieregularny" (D, tylko K06). Tabela poniżej (nie w pełni literalne
# CustomerSeed jak K01-K12 — przy 38 nowych rekordach czytelniejsza) zasila
# listę przez comprehension.
#
# (number_suffix, name, segment, city, onboarding_date, invoice_day, payment_terms, churn_date)
_NEW_CUSTOMER_SEED_DATA: list[tuple[int, str, str, str, date, int, int, Optional[date]]] = [
    # --- Fuzja 2022-09-01: +4 (1 Enterprise, 2 Mid-market, 1 SMB) — LEGACY_SERVICES ---
    (27, "Grenland Energi AS", "Enterprise", "Porsgrunn", date(2022, 9, 1), 4, 45, None),
    (32, "Harstad Finans AS", "Mid-market", "Harstad", date(2022, 9, 1), 10, 30, None),
    (34, "Kristiansund Transport AS", "Mid-market", "Kristiansund", date(2022, 9, 1), 15, 14, None),
    (46, "Lillestrøm Verksted AS", "SMB", "Lillestrøm", date(2022, 9, 1), 16, 30, None),
    # --- 2023: +8 (3 Enterprise, 3 Mid-market, 2 SMB) ---
    (13, "Trøndelag Industri AS", "Enterprise", "Trondheim", date(2023, 1, 16), 4, 45, None),
    (14, "Sørlandet Rådgivning AS", "Mid-market", "Arendal", date(2023, 2, 27), 9, 30, None),
    (15, "Moss Elektro AS", "SMB", "Moss", date(2023, 4, 10), 14, 30, date(2025, 10, 31)),  # churn po ~2,5 roku — Zadanie 4
    (16, "Vestland Maritime AS", "Enterprise", "Haugesund", date(2023, 5, 22), 6, 45, None),
    (17, "Drammen Eiendom AS", "Mid-market", "Drammen", date(2023, 7, 3), 11, 14, None),
    (18, "Larvik Data AS", "SMB", "Larvik", date(2023, 8, 14), 18, 30, None),
    (19, "Sandefjord Transport AS", "Mid-market", "Sandefjord", date(2023, 9, 25), 22, 30, None),
    (20, "Nordland Havbruk AS", "Enterprise", "Bodø", date(2023, 11, 6), 3, 45, None),
    # --- 2024: +10 (2 Enterprise, 4 Mid-market, 4 SMB) ---
    (21, "Buskerud Finans AS", "Mid-market", "Kongsberg", date(2024, 1, 8), 13, 30, None),
    (22, "Gjøvik Verksted AS", "SMB", "Gjøvik", date(2024, 2, 12), 26, 30, None),
    (23, "Møre Industri AS", "Enterprise", "Ålesund", date(2024, 3, 18), 7, 45, None),
    (24, "Hedmark Logistikk AS", "Mid-market", "Elverum", date(2024, 4, 22), 16, 30, None),
    (25, "Halden Design AS", "SMB", "Halden", date(2024, 5, 27), 21, 30, None),
    (26, "Kongsberg Teknikk AS", "Enterprise", "Kongsberg", date(2024, 7, 1), 9, 45, None),
    (47, "Skien Data AS", "SMB", "Skien", date(2024, 6, 16), 22, 30, None),
    (28, "Molde Sjømat AS", "SMB", "Molde", date(2024, 9, 9), 19, 30, None),
    (29, "Steinkjer Bygg AS", "Mid-market", "Steinkjer", date(2024, 10, 14), 12, 30, None),
    (30, "Askøy Rådgivning AS", "Mid-market", "Askøy", date(2024, 11, 18), 17, 30, None),
    # --- 2025: +10 (3 Enterprise, 3 Mid-market, 4 SMB) ---
    (31, "Innlandet Data AS", "Enterprise", "Lillehammer", date(2025, 1, 13), 5, 45, None),
    (48, "Levanger Elektro AS", "SMB", "Levanger", date(2025, 1, 27), 8, 30, None),
    (33, "Narvik Elektro AS", "SMB", "Narvik", date(2025, 3, 24), 23, 30, None),
    (35, "Stjørdal Industri AS", "Enterprise", "Stjørdal", date(2025, 6, 2), 8, 45, None),
    (36, "Hønefoss Eiendom AS", "Mid-market", "Hønefoss", date(2025, 7, 7), 13, 30, None),
    (37, "Sarpsborg Logistikk AS", "Mid-market", "Sarpsborg", date(2025, 8, 11), 20, 30, None),
    (38, "Notodden Verksted AS", "SMB", "Notodden", date(2025, 9, 15), 27, 30, None),
    (39, "Bodø Maritime AS", "Enterprise", "Bodø", date(2025, 10, 20), 6, 45, None),
    (40, "Tromsø Rådgivning AS", "Mid-market", "Tromsø", date(2025, 11, 24), 11, 30, None),
    (49, "Mo i Rana Bygg AS", "SMB", "Mo i Rana", date(2025, 12, 8), 15, 30, None),
    # --- 2026 (do lipca): +6 (2 Enterprise, 2 Mid-market, 2 SMB) ---
    (41, "Ålesund Energi AS", "Enterprise", "Ålesund", date(2026, 1, 12), 4, 45, None),
    (42, "Fredrikstad Data AS", "Mid-market", "Fredrikstad", date(2026, 2, 16), 14, 30, None),
    (43, "Kongsvinger Bygg AS", "SMB", "Kongsvinger", date(2026, 3, 23), 24, 30, None),
    (50, "Jessheim Design AS", "SMB", "Jessheim", date(2026, 4, 20), 21, 30, None),
    (44, "Hamar Teknikk AS", "Enterprise", "Hamar", date(2026, 5, 4), 9, 45, None),
    (45, "Bergen Finans AS", "Mid-market", "Bergen", date(2026, 6, 15), 17, 30, None),
]

CUSTOMERS.extend(
    CustomerSeed(
        f"K{n:02d}", name, segment, city, "A",
        invoice_day=invoice_day, payment_terms=payment_terms,
        onboarding_date=onboarding_date, churn_date=churn_date,
    )
    for n, name, segment, city, onboarding_date, invoice_day, payment_terms, churn_date in _NEW_CUSTOMER_SEED_DATA
)


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


# Dodatek — kody branżowe NACE/SN2007 (norweska klasyfikacja "næringskode",
# zgodna z unijnym NACE Rev.2). Czysto opisowy dodatek metadanych — nie
# wpływa na przychód/koszty/marżę, nie wymaga backfillu transakcyjnego.

# Kod główny firmy — łączy S01 (Managed IT Support) + S02 (zarządzanie
# Microsoft/Azure) + S03 (Cyberbezpieczeństwo). Realny odpowiednik: Garnes
# Data AS, benchmark marżowy z Fazy 6, zarejestrowany pod 62.030 (bliższy
# czystemu "drift"); 62.020 wybrany tu jako kod NADRZĘDNY, bo obejmuje
# explicite i konsulting/zarządzanie IT, i drift systemów — pasuje do
# całego portfela usług, nie tylko do S01.
COMPANY_NACE_CODE = "62.020"
COMPANY_NACE_NAME = "Konsulentvirksomhet tilknyttet informasjonsteknologi og forvaltning og drift av it-systemer"

# Kod sekundarny (70.220, konsulting >20% przychodu) NIE dodany — S04
# (Konsulting i digitalizacja) to ~1,9% przychodu 2025-2026 po obniżce ceny
# w Fazie 6 (950 NOK/h), daleko poniżej progu 20% z zadania. Zweryfikowane
# zapytaniem SQL na żywej bazie (order_lines JOIN products.service_code),
# nie założone z poprzedniej (wyższej) ceny S04 sprzed tej fazy.
COMPANY_NACE_SECONDARY_CODE: Optional[str] = None
COMPANY_NACE_SECONDARY_NAME: Optional[str] = None


@dataclass(frozen=True)
class NaceCode:
    code: str
    name: str


# Kod branżowy per klient, dopasowany do rzeczywistej nazwy firmy (nie
# losowo) — jeden z osobnym mapowaniem od CustomerSeed (jak
# CUSTOMER_PRICE_MULTIPLIER wyżej), nie nowe pole na CustomerSeed, żeby
# uniknąć zmiany sygnatury w 50 miejscach konstrukcji CUSTOMERS. Grupowanie
# wg powtarzających się wzorców nazw (nie każdy klient unikalny sektor):
# Energi -> 35.140, Finans -> 64.190, Logistikk/Transport -> 49.410,
# Bygg -> 41.200, Industri/Teknikk -> 25.110, Elektro -> 43.210,
# Verksted -> 45.200, Rådgivning/Konsult -> 70.220, Eiendom -> 68.100,
# Maritime -> 50.200 (transport morski), Data -> 62.090 (inne usługi IT —
# klienci nazwani "Data AS" to mniejsze firmy technologiczne kupujące nasz
# S01/S02, nie sama nasza branża), Design -> 74.100, Havbruk -> 03.210
# (akwakultura), Sjømat -> 10.200 (przetwórstwo rybne), Helse -> 86.909,
# Handel -> 47.190, Partnere (kancelaria) -> 69.100, Gruppen (holding,
# licencja bez wsparcia — wzorzec C) -> 70.100.
CUSTOMER_NACE: dict[str, NaceCode] = {
    "K01": NaceCode("25.110", "Produksjon av metallkonstruksjoner"),  # Bergström Industri
    "K02": NaceCode("69.100", "Juridisk tjenesteyting"),  # Halvorsen & Partnere
    "K03": NaceCode("35.140", "Handel med elektrisitet"),  # Nordkraft Energi
    "K04": NaceCode("41.200", "Oppføring av bygninger"),  # Solberg Bygg
    "K05": NaceCode("49.410", "Godstransport på vei"),  # Fjord Logistikk
    "K06": NaceCode("70.220", "Bedriftsrådgivning og annen administrativ rådgivning"),  # Telemark Konsult
    "K07": NaceCode("64.190", "Bankvirksomhet ellers"),  # Østfold Finans
    "K08": NaceCode("86.909", "Andre helsetjenester"),  # Innlandet Helse
    "K09": NaceCode("47.190", "Annen butikkhandel med bredt vareutvalg"),  # Vestfold Handel
    "K10": NaceCode("70.100", "Hovedkontortjenester"),  # Kristiansen Gruppen (licencja-only, wzorzec C)
    "K11": NaceCode("25.110", "Produksjon av metallkonstruksjoner"),  # Rogaland Teknikk
    "K12": NaceCode("50.200", "Sjøtransport med gods"),  # Agder Maritime
    "K13": NaceCode("25.110", "Produksjon av metallkonstruksjoner"),  # Trøndelag Industri
    "K14": NaceCode("70.220", "Bedriftsrådgivning og annen administrativ rådgivning"),  # Sørlandet Rådgivning
    "K15": NaceCode("43.210", "Elektrisk installasjonsarbeid"),  # Moss Elektro
    "K16": NaceCode("50.200", "Sjøtransport med gods"),  # Vestland Maritime
    "K17": NaceCode("68.100", "Kjøp og salg av egen fast eiendom"),  # Drammen Eiendom
    "K18": NaceCode("62.090", "Andre tjenester tilknyttet informasjonsteknologi"),  # Larvik Data
    "K19": NaceCode("49.410", "Godstransport på vei"),  # Sandefjord Transport
    "K20": NaceCode("03.210", "Havbruk av fisk i sjøvann"),  # Nordland Havbruk
    "K21": NaceCode("64.190", "Bankvirksomhet ellers"),  # Buskerud Finans
    "K22": NaceCode("45.200", "Vedlikehold og reparasjon av motorvogner"),  # Gjøvik Verksted
    "K23": NaceCode("25.110", "Produksjon av metallkonstruksjoner"),  # Møre Industri
    "K24": NaceCode("49.410", "Godstransport på vei"),  # Hedmark Logistikk
    "K25": NaceCode("74.100", "Spesialisert designvirksomhet"),  # Halden Design
    "K26": NaceCode("25.110", "Produksjon av metallkonstruksjoner"),  # Kongsberg Teknikk
    "K27": NaceCode("35.140", "Handel med elektrisitet"),  # Grenland Energi
    "K28": NaceCode("10.200", "Bearbeiding og konservering av fisk, skalldyr og bløtdyr"),  # Molde Sjømat
    "K29": NaceCode("41.200", "Oppføring av bygninger"),  # Steinkjer Bygg
    "K30": NaceCode("70.220", "Bedriftsrådgivning og annen administrativ rådgivning"),  # Askøy Rådgivning
    "K31": NaceCode("62.090", "Andre tjenester tilknyttet informasjonsteknologi"),  # Innlandet Data
    "K32": NaceCode("64.190", "Bankvirksomhet ellers"),  # Harstad Finans
    "K33": NaceCode("43.210", "Elektrisk installasjonsarbeid"),  # Narvik Elektro
    "K34": NaceCode("49.410", "Godstransport på vei"),  # Kristiansund Transport
    "K35": NaceCode("25.110", "Produksjon av metallkonstruksjoner"),  # Stjørdal Industri
    "K36": NaceCode("68.100", "Kjøp og salg av egen fast eiendom"),  # Hønefoss Eiendom
    "K37": NaceCode("49.410", "Godstransport på vei"),  # Sarpsborg Logistikk
    "K38": NaceCode("45.200", "Vedlikehold og reparasjon av motorvogner"),  # Notodden Verksted
    "K39": NaceCode("50.200", "Sjøtransport med gods"),  # Bodø Maritime
    "K40": NaceCode("70.220", "Bedriftsrådgivning og annen administrativ rådgivning"),  # Tromsø Rådgivning
    "K41": NaceCode("35.140", "Handel med elektrisitet"),  # Ålesund Energi
    "K42": NaceCode("62.090", "Andre tjenester tilknyttet informasjonsteknologi"),  # Fredrikstad Data
    "K43": NaceCode("41.200", "Oppføring av bygninger"),  # Kongsvinger Bygg
    "K44": NaceCode("25.110", "Produksjon av metallkonstruksjoner"),  # Hamar Teknikk
    "K45": NaceCode("64.190", "Bankvirksomhet ellers"),  # Bergen Finans
    "K46": NaceCode("45.200", "Vedlikehold og reparasjon av motorvogner"),  # Lillestrøm Verksted
    "K47": NaceCode("62.090", "Andre tjenester tilknyttet informasjonsteknologi"),  # Skien Data
    "K48": NaceCode("43.210", "Elektrisk installasjonsarbeid"),  # Levanger Elektro
    "K49": NaceCode("41.200", "Oppføring av bygninger"),  # Mo i Rana Bygg
    "K50": NaceCode("74.100", "Spesialisert designvirksomhet"),  # Jessheim Design
}


def customer_nace(customer: CustomerSeed) -> NaceCode:
    """Kod NACE/SN2007 klienta — zob. CUSTOMER_NACE."""
    return CUSTOMER_NACE[customer.number]


# Poprawki eksportu — kody pocztowe (postnummer) dla geokodowania w BI.
# `customers.postal_code`/`suppliers.postal_code` już istnieją w schema.sql
# (TEXT, część oryginalnego schematu) — nigdy nie były wypełniane. Realne
# kody centrów miast/głównych urzędów pocztowych (Posten/Bring
# postnummerregister), nie losowe. Tylko klienci — SupplierSeed nie ma pola
# `city` (dostawcy nigdy nie mieli przypisanego miasta w tym modelu, zob.
# DATA_DICTIONARY.md), więc nie ma z czego wyprowadzić kodu pocztowego dla
# dostawców bez wymyślania nowych danych adresowych spoza zakresu tego
# zadania — `suppliers.postal_code` zostaje NULL, świadomie udokumentowane
# ograniczenie (nie przeoczenie).
NORWEGIAN_POSTAL_CODES: dict[str, str] = {
    "Oslo": "0150",
    "Bergen": "5003",
    "Trondheim": "7010",
    "Stavanger": "4005",
    "Tromsø": "9008",
    "Kristiansand": "4611",
    "Fredrikstad": "1607",
    "Skien": "3717",
    "Hamar": "2317",
    "Tønsberg": "3111",
    "Sandefjord": "3210",
    "Bodø": "8005",
    "Ålesund": "6002",
    "Drammen": "3017",
    "Kongsvinger": "2212",
    "Mo i Rana": "8622",
    "Notodden": "3671",
    "Jessheim": "2050",
    "Kristiansund": "6509",
    "Arendal": "4836",
    "Askøy": "5300",
    "Elverum": "2408",
    "Gjøvik": "2815",
    "Halden": "1767",
    "Harstad": "9405",
    "Haugesund": "5527",
    "Hønefoss": "3510",
    "Kongsberg": "3611",
    "Larvik": "3256",
    "Levanger": "7600",
    "Lillehammer": "2609",
    "Lillestrøm": "2000",
    "Molde": "6413",
    "Moss": "1530",
    "Narvik": "8514",
    "Porsgrunn": "3915",
    "Sarpsborg": "1721",
    "Steinkjer": "7713",
    "Stjørdal": "7500",
}


def customer_postal_code(customer: CustomerSeed) -> str:
    """Kod pocztowy klienta na podstawie jego miasta — zob. NORWEGIAN_POSTAL_CODES."""
    return NORWEGIAN_POSTAL_CODES[customer.city]


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


# Faza 4 — jeden projekt per klient (1:1, PRJnnn <-> Knnn ten sam numer),
# nie 8 ręcznie utrzymywanych wpisów jak przed Fazą 4 (wystarczające przy 12
# klientach ze statycznym EMPLOYEE_PROJECT_MAP, ale przy 45 klientach i
# dynamicznym przydziale konsultantów — Zadanie 5 — każdy aktywny klient
# potrzebuje własnego projektu jako celu hour_entries.project_id, w tym
# klienci SMB, którzy wcześniej nie mieli żadnego przypisanego projektu).
# start_date = customer.onboarding_date (poprawia wcześniejsze mylące
# ograniczenie z DATA_DICTIONARY.md: "projects.start_date to data założenia
# rekordu w katalogu (2026), NIE data rozpoczęcia współpracy" — teraz to jest
# ta sama data, bardziej użyteczna semantycznie).
PROJECTS: list[ProjectSeed] = [
    # int(c.number[1:]) zamiast numeric_id(c.number) — numeric_id() jest
    # zdefiniowane niżej w tym pliku (po wszystkich seedach), nie da się go
    # jeszcze użyć tutaj; c.number to zawsze "K" + 2 cyfry, więc [1:] wystarcza.
    ProjectSeed(f"PRJ{int(c.number[1:]):03d}", f"IT-tjenester — {c.name}", int(c.number[1:]), c.onboarding_date)
    for c in CUSTOMERS
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
# Faza 2 (rekalibracja #1): pierwotne base_price_* (S01 Enterprise/Mid/SMB
# 45000/18000/4500, S02 20000/8000, S03 15000) zawaliły marżę operacyjną do
# -70%..-183%/rok (payroll 16-osobowego zespołu przewyższał cały przychód
# nawet 2.4x) — skorygowane w górę do 133000/84500/49000 (S01),
# 59000/37500 (S02), 44000 (S03) — dopasowane pod ÓWCZESNĄ liczbę klientów (12).
#
# Faza 4 (rekalibracja #2, PORZUCONA): te same ceny Fazy 2, zastosowane teraz
# do 50 klientów zamiast 12 (~4x), dały ODWROTNY problem — marża eksplodowała
# do 40-73%/rok. Próbowano naprawić obniżając WSZYSTKIE ceny SERVICES ~2.2x
# — ale to jeden globalny cennik obowiązujący całą historię 2019-2026, więc
# obniżka zepsuła retroaktywnie lata 2019-2023 (kiedy K01-K12 byli JEDYNĄ
# bazą przychodową, a ceny Fazy 2 były już skalibrowane pod TAMTEN payroll) —
# margines spadł do -138%..-15% zamiast poprawy.
#
# Faza 4 (rekalibracja #3, OSTATECZNA): DWIE KOHORTY CENOWE zamiast jednego
# globalnego cennika — LEGACY_SERVICES (ceny Fazy 2, niezmienione) dla
# klientów onboardowanych PRZED CUSTOMER_PRICING_COHORT_CUTOFF (2023-01-01;
# obejmuje K01-K12 I kohortę fuzji z 2022-09), SCALE_SERVICES (ceny obniżone
# ~2.2x) dla klientów onboardowanych OD tej daty. `SERVICES` (dawny globalny
# katalog) = alias do LEGACY_SERVICES — zasila tabelę `services` w Supabase
# (klucz PK = code, jedna cena/usługę — SCALE_SERVICES istnieje TYLKO w
# kodzie Python, nie ma reprezentacji w DB, zob. DATA_DICTIONARY.md). Zob.
# get_service_price_table()/service_by_code_for_customer() niżej i
# SESSION_HANDOFF.md (Faza 4) po pełne uzasadnienie + liczby marży PRZED/PO.
CUSTOMER_PRICING_COHORT_CUTOFF = date(2023, 1, 1)

LEGACY_SERVICES: list[Service] = [
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
        base_price_enterprise=950,
        base_price_mid=950,
        base_price_smb=950,
    ),
]

SCALE_SERVICES: list[Service] = [
    Service(
        code="S01",
        name="Managed IT Support",
        description="Helpdesk, incydenty, monitoring infrastruktury IT",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ALL,
        base_price_enterprise=60_000,
        base_price_mid=24_000,
        base_price_smb=6_000,
    ),
    Service(
        code="S02",
        name="Zarządzanie infrastrukturą Microsoft",
        description="Administracja Azure/M365, zarządzana infrastruktura chmurowa",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ENTERPRISE_MID,
        base_price_enterprise=25_000,
        base_price_mid=10_000,
        base_price_smb=None,
    ),
    Service(
        code="S03",
        name="Cyberbezpieczeństwo",
        description="Monitoring bezpieczeństwa, zgodność NIS2, reagowanie na incydenty",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ENTERPRISE_ONLY,
        base_price_enterprise=18_000,
        base_price_mid=None,
        base_price_smb=None,
    ),
    Service(
        code="S04",
        name="Konsulting i digitalizacja",
        description="Projekty digitalizacyjne, doradztwo IT, wdrożenia",
        billing_model=BillingModel.HOURLY,
        availability=ServiceSegmentAvailability.ALL,
        base_price_enterprise=950,
        base_price_mid=950,
        base_price_smb=950,
    ),
]

SERVICES: list[Service] = LEGACY_SERVICES  # katalog referencyjny / zasila tabelę `services` w Supabase


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


def get_service_price_table(customer: CustomerSeed) -> list[Service]:
    """Wybiera tabelę cenową wg kohorty klienta (Faza 4, rekalibracja #3) —
    LEGACY_SERVICES (K01-K12 + kohorta fuzji 2022-09-01) dla klientów
    onboardowanych przed CUSTOMER_PRICING_COHORT_CUTOFF, SCALE_SERVICES dla
    klientów onboardowanych od tej daty — żeby obniżka cen dla nowych
    klientów (Faza 4) nie psuła retroaktywnie przychodu/marży lat, kiedy
    starsi klienci byli jedyną (lub większościową) bazą przychodową firmy."""
    if customer.onboarding_date < CUSTOMER_PRICING_COHORT_CUTOFF:
        return LEGACY_SERVICES
    return SCALE_SERVICES


def service_by_code_for_customer(customer: CustomerSeed, code: str) -> Service:
    """service_by_code(), ale respektujące kohortę cenową klienta (zob.
    get_service_price_table) — używane przez order_generator.build_order_lines
    zamiast service_by_code() (który zawsze zwraca z globalnego SERVICES/
    LEGACY_SERVICES, ignorując kohortę)."""
    for service in get_service_price_table(customer):
        if service.code == code:
            return service
    raise KeyError(f"Nieznany kod usługi: {code!r}")


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


def is_customer_active(customer: CustomerSeed, on_date: date) -> bool:
    """Klient jest aktywny (onboarding_date <= on_date, i jeśli ma churn_date,
    jeszcze nie odszedł). Wspólna implementacja używana przez
    order_generator._is_active i generators.opex_generator (Faza 3) — wcześniej
    zduplikowana logicznie (order_generator, hours_generator)."""
    if on_date < customer.onboarding_date:
        return False
    if customer.churn_date is not None and on_date > customer.churn_date:
        return False
    return True


def active_customers(on_date: date) -> list[CustomerSeed]:
    """Klienci aktywni w danym dniu (zob. is_customer_active) — analogiczne do
    seed.payroll.active_employees dla pracowników."""
    return [c for c in CUSTOMERS if is_customer_active(c, on_date)]


# Faza 3 — nowe kategorie kosztów (kantyna, reprezentacja, kilometrówka).
# Kwoty celowo skromne (lekcja z Fazy 2: dosłowne przepisanie cen bez
# weryfikacji marży zawaliło wynik do -183%) — te koszty dodają się do już
# zweryfikowanej, zdrowej marży 20-23% i muszą pozostać niewielkie.
CANTEEN_SUBSIDY_PER_EMPLOYEE_MONTHLY = 820  # NOK, ustalone, nie zmieniać (polityka firmy, nie cena rynkowa)

REPRESENTATION_COST_PER_ENTERPRISE_CLIENT_MONTHLY = 1_000  # NOK, bazowe 2019
REPRESENTATION_COST_PER_MID_CLIENT_MONTHLY = 400
# SMB — brak kosztów reprezentacyjnych, relacja czysto transakcyjna.

KM_RATE_2019 = 3.5  # NOK/km, stawka bazowa 2019 — płaska w tej fazie (kwota
# na tyle mała, że inflacja nie ma praktycznego znaczenia; brak zastosowania
# apply_annual_inflation tutaj jest świadome, nie przeoczenie).

CONFERENCE_HOTEL_RATES: dict[str, float] = {
    "Oslo": 2_200, "Bergen": 1_600, "Trondheim": 1_500, "Stavanger": 1_700,
    "default": 1_200,  # mniejsze miasta
}


def calc_canteen_cost(active_employee_count: int) -> float:
    """Dopłata do kantyny — 820 NOK/pracownika/miesiąc, bez inflacji (to jest
    polityka firmy, nie cena rynkowa — zostaje stała)."""
    return active_employee_count * CANTEEN_SUBSIDY_PER_EMPLOYEE_MONTHLY


def calc_representation_cost(customers: list[CustomerSeed]) -> float:
    """Koszty reprezentacyjne — relacje z klientami, zależne od segmentu.
    SMB nie generuje kosztu (relacja czysto transakcyjna). Zwraca kwotę bazową
    (rok 2019) — inflacja +3%/rok stosowana przez wywołującego
    (generators.opex_generator.apply_annual_inflation z order_generator.py;
    roster.py celowo nie zależy od modułów generators, żeby uniknąć cyklu
    importu z order_generator, który już importuje z roster.py)."""
    total = 0.0
    for c in customers:
        if c.segment == "Enterprise":
            total += REPRESENTATION_COST_PER_ENTERPRISE_CLIENT_MONTHLY
        elif c.segment == "Mid-market":
            total += REPRESENTATION_COST_PER_MID_CLIENT_MONTHLY
    return total


def calc_client_visit_transport(customers: list[CustomerSeed], month: int) -> float:
    """Kilometrówka za wizyty u klientów — Enterprise: spotkania kwartalne
    (~150km/wizyta), Mid-market: 2x/rok, SMB: ~1x/rok. Stawka płaska (zob.
    KM_RATE_2019) — kwota zbyt mała, żeby inflacja miała praktyczne znaczenie
    w tej fazie."""
    total_km = 0
    for c in customers:
        if c.segment == "Enterprise" and month in (2, 5, 8, 11):
            total_km += 150
        elif c.segment == "Mid-market" and month in (3, 9):
            total_km += 120
        elif c.segment == "SMB" and month == 6:
            total_km += 80
    return total_km * KM_RATE_2019


# Faza 6 — COGS pass-through dla S02 (zastępuje płaski koszt Azure z Fazy 2,
# 35 000 NOK/mies. stałe — zob. supplier_invoice_generator.MICROSOFT_COST_LINES).
# Koszt firmy wobec Microsoftu za infrastrukturę klientów, skalujący się z
# liczbą i segmentem klientów kupujących S02 (Enterprise + Mid-market — SMB
# nigdy nie kupuje S02 wg bundlingu Faza 2, roster.SEGMENT_SERVICE_BUNDLES).
# Stawki (rok bazowy 2019, przed inflacją) skalibrowane offline (Faza 6) tak,
# żeby przy pełnym portfelu S02 w 2026 (15 Enterprise + 18 Mid-market = 33
# klientów) roczny COGS wyniósł 6,5-8,5M NOK — zob. SESSION_HANDOFF.md dla
# wyprowadzenia i rzeczywistego wyniku po backfillu.
AZURE_COGS_PER_ENTERPRISE_S02_CLIENT_MONTHLY = 22_000
AZURE_COGS_PER_MID_S02_CLIENT_MONTHLY = 11_500


def calc_azure_cogs_monthly(customers: list[CustomerSeed]) -> float:
    """COGS pass-through dla S02 — koszt jaki firma płaci Microsoftowi za
    infrastrukturę klientów kupujących S02 (Enterprise + Mid-market, nie SMB).
    Zwraca kwotę bazową (rok 2019) — inflacja +3%/rok stosowana przez
    wywołującego (opex_generator.generate_monthly_opex, tak jak
    calc_representation_cost — roster.py celowo nie zależy od modułów
    generators, zob. ten komentarz przy calc_representation_cost)."""
    total = 0.0
    for c in customers:
        if c.segment == "Enterprise":
            total += AZURE_COGS_PER_ENTERPRISE_S02_CLIENT_MONTHLY
        elif c.segment == "Mid-market":
            total += AZURE_COGS_PER_MID_S02_CLIENT_MONTHLY
    return total


# Faza 6, druga próba kalibracji — COGS pass-through dla S01 (Managed IT
# Support), NOWY mechanizm dodany po tym, jak offline sanity-check wykazał, że
# COGS S02-only (Azure, wyżej) nie może fizycznie wypełnić luki między
# przychodem (52,4M NOK projekcja 2026, nie zakładane 35M) a celem
# headcount~17/marża 7%: S02 generuje tylko ~13M NOK/rok przychodu, więc
# nawet przy COGS = 87% przychodu S02 brakowało ~15M NOK/rok. Realny
# benchmark Garnes Data AS (IT drift/support, odpowiednik S01) ma
# opex+COGS/przychód = 61,6% — sugeruje, że w tym segmencie to WŁAŚNIE S01
# (narzędzia RMM/PSA, licencje ticketing, EDR/antywirus odsprzedawane
# klientom, sprzęt zapasowy), nie S02, niesie główny ciężar kosztów
# przepływowych. Skaluje się z WSZYSTKIMI klientami S01 (wszyscy segmenty,
# S01 kupują wszyscy — roster.SEGMENT_SERVICE_BUNDLES), wagi 4:2:1
# (Enterprise:Mid-market:SMB) — większe organizacje wymagają więcej
# stanowisk/licencji narzędziowych do obsługi. Stawka SMB (rok bazowy 2019)
# skalibrowana offline tak, żeby (opex_tradycyjny + cogs_s02 + cogs_s01) /
# przychód wylądowało w 58-62% (środek 60%, zakotwiczone w Garnes Data
# 61,6%) — zob. SESSION_HANDOFF.md (Faza 6, druga kalibracja) dla
# wyprowadzenia i rzeczywistego wyniku po backfillu.
S01_COGS_PER_ENTERPRISE_CLIENT_MONTHLY = 53_000  # waga 4x
S01_COGS_PER_MID_CLIENT_MONTHLY = 26_500  # waga 2x
S01_COGS_PER_SMB_CLIENT_MONTHLY = 13_300  # waga 1x (jednostka bazowa)


def calc_s01_cogs_monthly(customers: list[CustomerSeed]) -> float:
    """COGS pass-through dla S01 — koszt narzędzi/licencji/sprzętu
    wspierającego Managed IT Support, płacony przez WSZYSTKICH aktywnych
    klientów (S01 kupują wszystkie segmenty), nie tylko Enterprise+Mid jak
    calc_azure_cogs_monthly (S02). Zwraca kwotę bazową (rok 2019) — inflacja
    +3%/rok stosowana przez wywołującego (opex_generator.generate_monthly_opex),
    tak jak calc_azure_cogs_monthly."""
    total = 0.0
    for c in customers:
        if c.segment == "Enterprise":
            total += S01_COGS_PER_ENTERPRISE_CLIENT_MONTHLY
        elif c.segment == "Mid-market":
            total += S01_COGS_PER_MID_CLIENT_MONTHLY
        else:
            total += S01_COGS_PER_SMB_CLIENT_MONTHLY
    return total


# Faza 4 — reguła wzrostu: sprzedaż vs zdolność zespołu (Zadanie 2).
#
# SEGMENT_HOURS_PER_MONTH/HOURS_PER_YEAR_PER_CONSULTANT/UTILIZATION_TARGET
# zostają — używane WYŁĄCZNIE przez hours_generator.assign_customers_to_consultants
# (limit obciążenia per konsultant przy budowaniu portfolio na timesheety,
# Zadanie 5) — to inne zagadnienie niż "ile osób zatrudnić" (niżej).
HOURS_PER_YEAR_PER_CONSULTANT = 1_700  # typowe roczne godziny netto
UTILIZATION_TARGET = 0.80  # 80% obłożenia billable

SEGMENT_HOURS_PER_MONTH: dict[str, float] = {
    "Enterprise": 20,  # średnia 15-25h/mies.
    "Mid-market": 11,  # średnia 8-15h/mies.
    "SMB": 5,  # średnia 3-8h/mies.
}


# Faza 6 (druga kalibracja) — TARGET_MARGIN obniżony z 0,19 (Faza 3/4) do
# 0,07: realne norweskie firmy IT tego segmentu (Brønnøysundregistrene, zob.
# roster.calc_s01_cogs_monthly) mają marże 3-10%, nie 15-25%. Rachunek
# TOP-DOWN (Faza 4, korekta #4) zostaje niezmieniony w STRUKTURZE — znany
# przychód/opex+COGS -> budżet payrollu -> liczba etatów — ale offline
# sanity-check tej fazy wykazał, że projekcja przychodu jest realnie ~52,4M
# NOK w 2026, nie ~35M jak pierwotnie zakładano: przy TYM przychodzie i
# skromnym, realistycznym COGS (S02-only, Zadanie 2a) formuła dawała
# headcount ~31, nie ~17 (COGS S02 fizycznie nie mógł przekroczyć własnego
# przychodu S02, ~13M/rok). Rozwiązanie: DRUGI kubełek COGS (S01, zob.
# calc_s01_cogs_monthly) zakotwiczony w realnym Garnes Data AS (IT
# drift/support, opex+COGS/przychód = 61,6%) — nie stałe TARGET_COGS_S02/
# TARGET_TRADITIONAL_OPEX (niezależne od przychodu), tylko funkcje
# `calc_*_cogs_monthly(customers)` skalujące się z rzeczywistym portfelem, tak
# jak payroll skaluje się z rzeczywistym EMPLOYEES — dlatego
# calc_target_headcount() świadomie NIE przyjmuje stałych progów kosztowych,
# tylko projected_opex_cogs policzony z prawdziwych generatorów (jak w Fazie
# 4), żeby nigdy nie rozjechać się z tym, co faktycznie trafia do bazy.
TARGET_MARGIN = 0.07  # środek zakresu 5,5-9%, zweryfikowanego w Fazie 6 (2. kalibracja)
AVG_FULLY_LOADED_EMPLOYEE_COST_2026 = 1_150_000  # NOK, z rzeczywistych danych payrollu (uwzględnia AGA, feriepenger)


def calc_target_headcount(projected_revenue: float, projected_opex_cogs: float) -> int:
    """Oblicza docelowy zespół z celu marży, nie z zgadywanych godzin/
    przychodu per konsultant (korekty #2/#3, porzucone) — allowed_total_cost
    to maksymalny koszt (payroll+opex+COGS) przy TARGET_MARGIN, payroll_budget
    to co z tego zostaje na płace po odjęciu opex/COGS (Faza 3: kantyna,
    reprezentacja, transport, sprzęt wdrożeniowy + L01-L08; Faza 6: + COGS
    S02 Azure + COGS S01 narzędzia/licencje, zob. calc_azure_cogs_monthly/
    calc_s01_cogs_monthly)."""
    allowed_total_cost = projected_revenue * (1 - TARGET_MARGIN)
    payroll_budget = allowed_total_cost - projected_opex_cogs
    return round(payroll_budget / AVG_FULLY_LOADED_EMPLOYEE_COST_2026)


# Weryfikacja harmonogramu zatrudnienia (Faza 6, 2. kalibracja) —
# calc_target_headcount() vs rzeczywista liczba EMPLOYEES aktywnych na koniec
# każdego roku, z rzeczywistym przychodem/opex+COGS wygenerowanym przez
# generatory (nie przybliżeniem) — zob. SESSION_HANDOFF.md (Faza 6) dla
# pełnych danych liczbowych z offline sanity-checku wykonanego PRZED
# backfillem. Docelowa trajektoria zatrudnienia: 16 (2022 po fuzji) -> 17
# (2022-10, E17, jedyne dociążenie) -> 17 (bez zmian do 2026) — zespół
# PRZESTAJE rosnąć z portfelem klientów (12 -> 48 aktywnych 2019 -> 2026),
# bo model wsparcia jest ticketowy (hours_generator.generate_daily_support_hours,
# jeden konsultant obsługuje kilku klientów dziennie), nie 1:1 klient-konsultant,
# a większość kosztu obsługi jest kosztem materiałowym (COGS), nie osobowym.
# Zmierzona marża: 11,5% (2022) -> 7,1% (2023) -> 7,3% (2024) -> 7,0-7,5%
# (2025) -> 6,9-7,6% (2026, częściowy/pełny rok) — w celu 5,5-9% dla obu lat
# dojrzałych wymaganych przez próg bezpieczeństwa.


def employee_by_number(number: str) -> EmployeeSeed:
    for e in EMPLOYEES:
        if e.number == number:
            return e
    raise KeyError(f"Nieznany numer pracownika: {number}")


def employee_by_id(employee_id: int) -> EmployeeSeed:
    """Odwrotność numeric_id() dla pracowników — employee_id z bazy (1-17)
    -> EmployeeSeed. Potrzebne w hours_generator (Faza 4) — generate_daily_hours
    dostaje tylko listę int id, nie obiekty EmployeeSeed."""
    return employee_by_number(f"E{employee_id:02d}")


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
    """Odwrotność numeric_id() dla projektów — project_id (1-45) -> ProjectSeed."""
    return project_by_number(f"PRJ{project_id:03d}")


_PROJECT_FOR_CUSTOMER_ID: dict[int, ProjectSeed] = {p.customer_id: p for p in PROJECTS}


def project_for_customer(customer: CustomerSeed) -> ProjectSeed:
    """Projekt przypisany klientowi (Faza 4: 1:1, PRJnnn <-> Knnn) — używane
    przez hours_generator.assign_customers_to_consultants zamiast statycznego
    EMPLOYEE_PROJECT_MAP sprzed Fazy 4."""
    return _PROJECT_FOR_CUSTOMER_ID[int(customer.number[1:])]


def numeric_id(code: str) -> int:
    """Konwertuje kod seed (E07, K03, L05, P02, PRJ001) na numeryczne id
    Warstwy 1/2 (Employee 1-17, Customer 1-50, Supplier 1-8, Product 1-7,
    Project 1-50 — Faza 4 rozszerzyła Customer/Project, Faza 6 skróciła
    Employee z powrotem do 17 — przypisywane
    sekwencyjnie wg kolejności w dokumentacji). Obsługuje zarówno
    jednoliterowe (E/K/L/P), jak i wieloliterowe (PRJ) prefiksy."""
    return int(re.sub(r"^[A-Za-z]+", "", code))
