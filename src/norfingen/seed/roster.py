"""Single source of truth for NorFinGen's static company data.

Data transcribed 1:1 from docs/norfingen_warstwa1_schemas.html (Department,
Employee, Customer, Supplier) and docs/norfingen_warstwa2_schemas.html
(Product catalog, A/B/C/D order patterns, supplier invoicing rhythm and GL
accounts). All other modules (generators, payroll functions) read from
here — no company data is duplicated anywhere else.
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
    number: str  # "E01" - "E16"
    first_name: str
    last_name: str
    department_number: int  # FK -> DepartmentSeed.number
    start_date: date
    phase: str  # founding / growth1 / growth2 / merger
    role: str
    annual_salary: float  # NOK / year


@dataclass(frozen=True)
class CustomerSeed:
    number: str  # "K01" - "K12"
    name: str
    segment: str  # Enterprise / Mid-market / SMB
    city: str
    order_pattern: str  # A (IT Support) / B (IT Support + License) / C (License only) / D (Consulting)
    support_product: Optional[str] = None  # Product number for the IT Support line
    license_product: Optional[str] = None  # Product number for the License line
    invoice_day: Optional[int] = None  # day of month the invoice is issued; None = irregular (K06 consulting)
    payment_terms: int = 30  # days until due date (net 14/30/45)
    onboarding_date: date = field(kw_only=True)  # start-of-relationship date — no orders before this date
    churn_date: Optional[date] = field(default=None, kw_only=True)  # departure date — no orders after this date (None = no churn)


@dataclass(frozen=True)
class SupplierSeed:
    number: str  # "L01" - "L08"
    name: str
    cost_category: str
    gl_account: int  # cost account DR (6xxx/7xxx)
    rhythm: str  # description of invoicing cadence
    amount_min: float  # NOK, net amount (excl. VAT)
    amount_max: float
    capitalization_threshold: Optional[float] = None  # L05: >= 30,000 -> capitalized
    capitalization_account: Optional[int] = None  # L05: 1200 Maskiner og anlegg
    # Supplier audit against Brønnøysundregistrene (data.brreg.no) — purely
    # informational, does not affect any financial logic. Populated only for
    # suppliers with an EXACT match to a real company (see
    # scripts/audit_supplier_names.py, docs/DATA_SAFETY.md). None = supplier
    # is deliberately fictional (L05, L08 before the correction) or
    # unconfirmed by the API itself (L07 — Brreg search engine limitation on
    # the ambiguous word "avis").
    real_org_number: Optional[str] = None


@dataclass(frozen=True)
class ProjectSeed:
    number: str  # "PRJ001" - "PRJ008"
    name: str
    customer_id: int  # numeric customer id (FK -> CustomerSeed, see numeric_id)
    start_date: date


@dataclass(frozen=True)
class ProductSeed:
    number: str  # "P01" - "P06"
    name: str
    category: str
    gl_account: int  # 3000 (services) / 3100 (licenses)
    service_code: str  # FK -> Service.code (Phase 1) — S01-S04
    default_price: Optional[float] = None  # None = variable (P06 consulting)


DEPARTMENTS: list[DepartmentSeed] = [
    DepartmentSeed(number=1, name="Salg"),
    DepartmentSeed(number=2, name="Leveranse"),
    DepartmentSeed(number=3, name="Teknologi"),
    DepartmentSeed(number=4, name="Økonomi"),
]


EMPLOYEES: list[EmployeeSeed] = [
    # --- Company founding: founding cohort spread over 4 months
    # (2019-01 -> 2019-04), not a single day — a realistic team build-up from
    # scratch, not a company "born fully formed".
    EmployeeSeed("E01", "Erik", "Strand", 1, date(2019, 1, 1), "founding", "Sales Manager", 880_000),
    EmployeeSeed("E02", "Marte", "Haugen", 2, date(2019, 2, 1), "founding", "IT Consultant", 720_000),
    EmployeeSeed("E03", "Bjørn", "Dahl", 2, date(2019, 2, 1), "founding", "Senior IT Specialist", 800_000),
    EmployeeSeed("E04", "Kari", "Lund", 2, date(2019, 3, 1), "founding", "IT Support", 620_000),
    EmployeeSeed("E05", "Thomas", "Berg", 3, date(2019, 3, 1), "founding", "System Architect", 860_000),
    EmployeeSeed("E06", "Ingrid", "Moen", 4, date(2019, 4, 1), "founding", "Finance Manager", 820_000),
    # --- Growth 1: 2020-03-01 (+2 people) ---
    EmployeeSeed("E07", "Lars", "Eriksen", 2, date(2020, 3, 2), "growth1", "IT Consultant", 700_000),
    EmployeeSeed("E08", "Silje", "Voss", 3, date(2020, 3, 2), "growth1", "Developer", 760_000),
    # --- Growth 2: 2021-06-01 (+2 people) ---
    EmployeeSeed("E09", "Ole", "Pedersen", 2, date(2021, 6, 1), "growth2", "IT Specialist", 680_000),
    EmployeeSeed("E10", "Nina", "Holm", 2, date(2021, 6, 1), "growth2", "Project Coordinator", 700_000),
    # --- Merger: 2022-09-01 (+6 people) ---
    EmployeeSeed("E11", "Petter", "Nygaard", 1, date(2022, 9, 1), "merger", "Account Manager", 720_000),
    EmployeeSeed("E12", "Hanna", "Kjær", 2, date(2022, 9, 1), "merger", "IT Consultant", 700_000),
    EmployeeSeed("E13", "Rune", "Sæther", 2, date(2022, 9, 1), "merger", "IT Support", 620_000),
    EmployeeSeed("E14", "Camilla", "Bø", 2, date(2022, 9, 1), "merger", "IT Specialist", 680_000),
    EmployeeSeed("E15", "Anders", "Johansen", 3, date(2022, 9, 1), "merger", "Developer", 760_000),
    EmployeeSeed("E16", "Marit", "Sundby", 4, date(2022, 9, 1), "merger", "Admin Coordinator", 640_000),
    # --- Phase 6 (second calibration, REPLACES Phase 4): the team STOPS
    # growing after one addition right after the merger (E17) — it no longer
    # scales linearly with the customer portfolio (Phase 4: 22 further hires
    # up to 38 people for 50 customers). Reason: calibration against real
    # market data (Brønnøysundregistrene, see roster.calc_s01_cogs_monthly)
    # showed that comparable Norwegian IT drift/support firms (Garnes Data
    # AS: 17 employees, 48M NOK revenue, 5.4% margin) serve a large customer
    # portfolio with a small team precisely BECAUSE most of the servicing
    # cost (RMM/PSA tools, licenses, hardware) is a materials cost (COGS
    # pass-through), not a headcount cost (payroll) — and because support
    # runs on a ticketing model (one consultant serves many customers per
    # day, see hours_generator.generate_daily_support_hours), not a 1:1
    # customer-consultant model. The previous attempt (Phase 4, 38 FTEs) was
    # calibrated against the old, much thinner cost model (only Phase 3:
    # canteen/representation/transport/equipment) and produced an
    # unrealistically high revenue/employee ratio relative to real firms in
    # this segment. E17 (Vegard Lien) remains the only post-merger addition —
    # verified by simulation BEFORE the backfill (not an estimate, see
    # calc_target_headcount below): margin 11.5% (2022) -> 7.1% (2023) ->
    # 7.3% (2024) -> 7.0-7.5% (2025) -> 6.9-7.6% (2026, partial/full year) —
    # a smooth decline to the 5.5-9% target, never below the safety
    # threshold in mature years.
    EmployeeSeed("E17", "Vegard", "Lien", 2, date(2022, 10, 3), "scaling", "Senior IT Consultant", 950_000),
]


# Gradual onboarding — 6 customers by end of 2019 (year 1, once the team
# reaches 5+ people), +2 in 2020 (stabilization year at 8 staff), +2 in 2021
# (growth to 10 staff), +2 in 2022 before/after the merger to 16 staff.
# Enterprise/Mid-market first, so revenue grows faster than with a random order.
CUSTOMERS: list[CustomerSeed] = [
    CustomerSeed("K01", "Bergström Industri AS", "Enterprise", "Bergen", "B", "P01", "P04",
                 invoice_day=3, payment_terms=30, onboarding_date=date(2019, 3, 1)),  # first customer
    CustomerSeed("K02", "Halvorsen & Partnere AS", "Mid-market", "Oslo", "A", "P02", None,
                 invoice_day=7, payment_terms=14, onboarding_date=date(2019, 6, 1)),  # fast payer
    CustomerSeed("K03", "Nordkraft Energi AS", "Enterprise", "Tromsø", "B", "P01", "P04",
                 invoice_day=1, payment_terms=45, onboarding_date=date(2019, 4, 15),  # large customer, longer terms
                 # Phase 7c, Task 1 — MAJOR_INCIDENT_2023 (ENTERPRISE_CONTRACT_LOSS):
                 # lost the contract to a competitor at renewal, not
                 # BANKRUPTCY (that's reserved for SMB) — the customer's
                 # company still exists, it simply stops being a customer.
                 # Chosen among the 4 largest Enterprise accounts (Bergström
                 # Industri, Nordkraft Energi, Rogaland Teknikk, Innlandet
                 # Helse) as the only one (along with K08) with no prior
                 # events from Phase 7/7b — second largest (24.0M NOK), so a
                 # real impact from the loss. Same mechanism as K09/K15
                 # (static churn_date) — no forced WRITTEN_OFF (unlike
                 # BANKRUPTCY): this is a loss of future revenue, not a
                 # receivables-collection problem.
                 churn_date=date(2023, 4, 1)),
    CustomerSeed("K04", "Solberg Bygg AS", "SMB", "Stavanger", "A", "P03", None,
                 invoice_day=10, payment_terms=30, onboarding_date=date(2020, 8, 1)),  # once the team had stabilized
    CustomerSeed("K05", "Fjord Logistikk AS", "Mid-market", "Bergen", "A", "P02", None,
                 invoice_day=5, payment_terms=30, onboarding_date=date(2019, 9, 1)),
    CustomerSeed("K06", "Telemark Konsult AS", "SMB", "Skien", "D", None, None,
                 invoice_day=None, payment_terms=14, onboarding_date=date(2022, 3, 1)),  # consulting — last one, irregular
    CustomerSeed("K07", "Østfold Finans AS", "Mid-market", "Fredrikstad", "B", "P02", "P05",
                 invoice_day=15, payment_terms=30, onboarding_date=date(2020, 1, 1)),
    CustomerSeed("K08", "Innlandet Helse AS", "Enterprise", "Hamar", "A", "P01", None,
                 invoice_day=1, payment_terms=45, onboarding_date=date(2019, 7, 15)),
    CustomerSeed("K09", "Vestfold Handel AS", "SMB", "Tønsberg", "A", "P03", None,
                 invoice_day=20, payment_terms=30, onboarding_date=date(2021, 2, 1),  # once the team reached 10 staff
                 churn_date=date(2024, 11, 30)),  # leaves after 3.5 years — realistic SMB churn
    CustomerSeed("K10", "Kristiansen Gruppen AS", "Mid-market", "Oslo", "C", None, "P05",
                 # Phase 7b, Task 1c — MACRO_SHOCK (COVID_2020): the original
                 # onboarding date 2020-04-01 fell inside the lockdown window
                 # (March-June) — new_client_onboarding_freeze, shifted
                 # deterministically to the first month after the window (not
                 # randomly, a deliberate historical correction, confirmed by
                 # the user even though it touches an already-backfilled
                 # history).
                 invoice_day=8, payment_terms=30, onboarding_date=date(2020, 7, 1)),
    CustomerSeed("K11", "Rogaland Teknikk AS", "Enterprise", "Stavanger", "B", "P01", "P04",
                 invoice_day=2, payment_terms=30, onboarding_date=date(2019, 10, 15)),  # rounds out all 4 Enterprise by end of 2019
    CustomerSeed("K12", "Agder Maritime AS", "SMB", "Kristiansand", "A", "P03", None,
                 invoice_day=12, payment_terms=30, onboarding_date=date(2021, 9, 1)),
]


# Phase 4 — scaling from 12 to 50 customers (K13-K50), onboarding spread from
# 2022-09 (merger) to 2026-07 (2022 merger: +4, 2023: +8, 2024: +10, 2025:
# +10, 2026 through July: +6 = 38 new). Target segment mix: 15 Enterprise
# (4+11), 18 Mid-market (4+14), 17 SMB (4+13).
#
# Merger cohort (2022-09-01, the SAME date as the E11-E16 employee merger,
# recalibration #3) — 4 customers = exactly 1/3 of the 12 held at that point,
# acquired together with the employees of the acquired company (one coherent
# business event, not two separate ones). They onboard BEFORE
# CUSTOMER_PRICING_COHORT_CUTOFF (2023-01-01) -> LEGACY_SERVICES, not
# SCALE_SERVICES (see get_service_price_table above).
#
# order_pattern/support_product/license_product no longer matter for
# generating order lines as of Phase 2 (see order_generator.build_order_lines)
# — all new customers get "A" / None / None, because the only thing this
# pattern still does is distinguish "regular subscription" (A/B/C) from
# "consulting only, irregular" (D, K06 only). The table below (not fully
# literal CustomerSeed entries like K01-K12 — more readable for 38 new
# records) feeds the list via a comprehension.
#
# (number_suffix, name, segment, city, onboarding_date, invoice_day, payment_terms, churn_date)
_NEW_CUSTOMER_SEED_DATA: list[tuple[int, str, str, str, date, int, int, Optional[date]]] = [
    # --- Merger 2022-09-01: +4 (1 Enterprise, 2 Mid-market, 1 SMB) — LEGACY_SERVICES ---
    (27, "Grenland Energi AS", "Enterprise", "Porsgrunn", date(2022, 9, 1), 4, 45, None),
    (32, "Harstad Finans AS", "Mid-market", "Harstad", date(2022, 9, 1), 10, 30, None),
    (34, "Kristiansund Transport AS", "Mid-market", "Kristiansund", date(2022, 9, 1), 15, 14, None),
    (46, "Lillestrøm Verksted AS", "SMB", "Lillestrøm", date(2022, 9, 1), 16, 30, None),
    # --- 2023: +8 (3 Enterprise, 3 Mid-market, 2 SMB) ---
    (13, "Trøndelag Industri AS", "Enterprise", "Trondheim", date(2023, 1, 16), 4, 45, None),
    (14, "Sørlandet Rådgivning AS", "Mid-market", "Arendal", date(2023, 2, 27), 9, 30, None),
    (15, "Moss Elektro AS", "SMB", "Moss", date(2023, 4, 10), 14, 30, date(2025, 10, 31)),  # churn after ~2.5 years — Task 4
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
    # --- 2026 (through July): +6 (2 Enterprise, 2 Mid-market, 2 SMB) ---
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
    """Individual price multiplier per customer — simulates the outcome of
    contract-signing negotiations (±8%), fixed once and for good.
    Deterministic: a local random.Random seeded with a string, NOT the
    built-in hash() — hash() on a str is randomly salted per process in
    Python 3 (security), which would break backfill reproducibility across
    successive runs."""
    rng = random.Random(f"price-multiplier-{customer_number}")
    return round(rng.uniform(0.92, 1.08), 4)


# The multiplier is part of the outcome of the customer negotiation, not a
# separate CustomerSeed field — computed once at module import from the
# customer number.
CUSTOMER_PRICE_MULTIPLIER: dict[str, float] = {
    c.number: _customer_price_multiplier(c.number) for c in CUSTOMERS
}


# Addendum — NACE/SN2007 industry codes (the Norwegian "næringskode"
# classification, aligned with the EU's NACE Rev.2). A purely descriptive
# metadata addendum — does not affect revenue/costs/margin, requires no
# transactional backfill.

# The company's primary code — combines S01 (Managed IT Support) + S02
# (Microsoft/Azure management) + S03 (Cybersecurity). Real-world equivalent:
# Garnes Data AS, the margin benchmark from Phase 6, registered under 62.030
# (closer to pure "drift"/operations); 62.020 is chosen here as the PARENT
# code, because it explicitly covers both IT consulting/management and
# systems operations — it fits the whole service portfolio, not just S01.
COMPANY_NACE_CODE = "62.020"
COMPANY_NACE_NAME = "Konsulentvirksomhet tilknyttet informasjonsteknologi og forvaltning og drift av it-systemer"

# A secondary code (70.220, consulting >20% of revenue) was NOT added — S04
# (Consulting and digitalization) is ~1.9% of revenue in 2025-2026 after the
# price cut in Phase 6 (950 NOK/h), far below the 20% threshold from the
# task. Verified with a SQL query on the live database (order_lines JOIN
# products.service_code), not assumed from the previous (higher) S04 price
# that predates this phase.
COMPANY_NACE_SECONDARY_CODE: Optional[str] = None
COMPANY_NACE_SECONDARY_NAME: Optional[str] = None


@dataclass(frozen=True)
class NaceCode:
    code: str
    name: str


# Industry code per customer, matched to the actual company name (not
# random) — a separate mapping keyed off CustomerSeed (like
# CUSTOMER_PRICE_MULTIPLIER above), not a new field on CustomerSeed, to avoid
# changing the constructor signature in 50 places where CUSTOMERS is built.
# Grouped by recurring name patterns (not every customer is a unique sector):
# Energi -> 35.140, Finans -> 64.190, Logistikk/Transport -> 49.410,
# Bygg -> 41.200, Industri/Teknikk -> 25.110, Elektro -> 43.210,
# Verksted -> 45.200, Rådgivning/Konsult -> 70.220, Eiendom -> 68.100,
# Maritime -> 50.200 (maritime transport), Data -> 62.090 (other IT
# services — customers named "Data AS" are smaller tech companies buying our
# S01/S02, not our own industry), Design -> 74.100, Havbruk -> 03.210
# (aquaculture), Sjømat -> 10.200 (fish processing), Helse -> 86.909,
# Handel -> 47.190, Partnere (law firm) -> 69.100, Gruppen (holding,
# license without support — pattern C) -> 70.100.
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
    "K10": NaceCode("70.100", "Hovedkontortjenester"),  # Kristiansen Gruppen (license-only, pattern C)
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
    """The customer's NACE/SN2007 code — see CUSTOMER_NACE."""
    return CUSTOMER_NACE[customer.number]


# Export fix — postal codes (postnummer) for geocoding in BI.
# `customers.postal_code`/`suppliers.postal_code` already existed in
# schema.sql (TEXT, part of the original schema) — never populated. Real
# codes for city centers/main post offices (Posten/Bring postnummerregister),
# not random. Customers only — SupplierSeed has no `city` field (suppliers
# never had a city assigned in this model, see DATA_DICTIONARY.md), so
# there's nothing to derive a postal code from for suppliers without
# inventing new address data outside the scope of this task —
# `suppliers.postal_code` stays NULL, a deliberately documented limitation
# (not an oversight).
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
    """The customer's postal code based on their city — see NORWEGIAN_POSTAL_CODES."""
    return NORWEGIAN_POSTAL_CODES[customer.city]


SUPPLIERS: list[SupplierSeed] = [
    SupplierSeed("L01", "Microsoft Norge AS", "Software licenses", 6410, "monthly_day_1", 85_000, 85_000,
                 real_org_number="957485030"),
    SupplierSeed("L02", "Telenor Norge AS", "Telecommunications", 6900, "monthly_day_5", 17_100, 18_900,
                 real_org_number="976967631"),
    SupplierSeed("L03", "Reitan Convenience AS", "Office / catering", 6800, "monthly_day_15", 8_000, 14_000,
                 real_org_number="983415652"),
    SupplierSeed("L04", "Statsbygg", "Office rent", 6300, "monthly_day_1", 45_000, 45_000,
                 real_org_number="971278374"),
    SupplierSeed(
        "L05",
        "Sandvik IT Solutions AS",
        "IT equipment",
        6540,
        "3_5x_yearly",
        15_000,
        80_000,
        capitalization_threshold=30_000,
        capitalization_account=1200,
        # Deliberately fictional — the Brreg audit (2026-09) found only a
        # small, unrelated company "SANDVIK IT" (Fister, org.nr 933277437),
        # not the global Sandvik AB conglomerate. A match would not have
        # increased realism.
    ),
    # Typo fix (Brreg audit, 2026-09) — was missing "et":
    # the real, well-known law firm is "Advokatfirmaet Thommessen AS".
    SupplierSeed("L06", "Advokatfirmaet Thommessen AS", "Legal services", 6700, "quarterly_mar_jun_sep_dec", 25_000, 60_000,
                 real_org_number="957423248"),
    # Deliberately left unconfirmed (Brreg audit, 2026-09) — the Brreg search
    # engine returns thousands of hits for the ambiguous word "avis"
    # (Norwegian for "newspaper"), so this method cannot conclusively confirm
    # or rule out the exact legal name of Avis in Norway. "Avis" as a brand
    # is recognizable regardless of the exact legal form anyway.
    SupplierSeed("L07", "Avis Norge AS", "Car rental", 7000, "monthly_day_20", 12_000, 28_000),
    # Replaced with a real insurance brand (Brreg audit, 2026-09) —
    # the original "Nordic Insurance Partners AS" was entirely fictional.
    SupplierSeed("L08", "Gjensidige Forsikring ASA", "Insurance", 7500, "quarterly_jan_apr_jul_oct", 38_000, 38_000,
                 real_org_number="995568217"),
]


# Phase 4 — one project per customer (1:1, PRJnnn <-> Knnn same number), not
# 8 manually maintained entries like before Phase 4 (sufficient with 12
# customers using a static EMPLOYEE_PROJECT_MAP, but with 45 customers and
# dynamic consultant assignment — Task 5 — every active customer needs its
# own project as a target for hour_entries.project_id, including SMB
# customers who previously had no assigned project at all). start_date =
# customer.onboarding_date (fixes a previously misleading limitation from
# DATA_DICTIONARY.md: "projects.start_date is the date the catalog record
# was created (2026), NOT the relationship start date" — now it's the same
# date, more semantically useful).
PROJECTS: list[ProjectSeed] = [
    # int(c.number[1:]) instead of numeric_id(c.number) — numeric_id() is
    # defined further down in this file (after all the seeds), so it can't
    # be used here yet; c.number is always "K" + 2 digits, so [1:] is enough.
    ProjectSeed(f"PRJ{int(c.number[1:]):03d}", f"IT-tjenester — {c.name}", int(c.number[1:]), c.onboarding_date)
    for c in CUSTOMERS
]


PRODUCTS: list[ProductSeed] = [
    # Prices reduced ~17% (2026-07) to close the operating margin gap down to
    # the target 15-25% band (previously ~33% — operating costs too low
    # relative to revenue at unchanged rates; payroll dominates the cost
    # structure and was not touched here, see the note in docs/).
    # service_code (Phase 1): P01-P03 (support) -> S01, P04-P05
    # (licenses/Microsoft) -> S02, P06 (consulting) -> S04, P07 (Phase 2) ->
    # S03 (Cybersecurity).
    #
    # Phase 2: the price actually used on the invoice is now computed from
    # Service.base_price_{segment} (build_order_lines/product_for_service in
    # order_generator.py), not from default_price below — these products
    # remain as the Tripletex reference (product_id) and invoice label, one
    # canonical product per service regardless of customer segment.
    # P02/P03/P05 are no longer used to generate lines (replaced by
    # segment-based bundling), they stay in the catalog for
    # backward-compatibility/FK purposes.
    ProductSeed("P01", "Managed IT Support", "Monthly subscription", 3000, "S01", 183_000),
    ProductSeed("P02", "IT Support — Mid-market", "Monthly subscription", 3000, "S01", 133_000),
    ProductSeed("P03", "IT Support — SMB", "Monthly subscription", 3000, "S01", 62_000),
    ProductSeed("P04", "Microsoft Infrastructure Management", "Monthly subscription", 3100, "S02", 79_000),
    ProductSeed("P05", "Software License — Mid-market", "Monthly license", 3100, "S02", 58_000),
    ProductSeed("P06", "Consulting and Digitalization", "Project / engagement", 3000, "S04", None),
    ProductSeed("P07", "Cybersecurity", "Monthly subscription", 3000, "S03", None),
]


# Service catalog (Phase 1) — independent of per-customer pricing (that's set
# by CustomerSeed/CUSTOMER_PRICE_MULTIPLIER). Base prices from 2019 (base
# year for apply_annual_inflation), per segment.
#
# Phase 2 (recalibration #1): the original base_price_* values (S01
# Enterprise/Mid/SMB 45000/18000/4500, S02 20000/8000, S03 15000) collapsed
# the operating margin to -70%..-183%/year (a 16-person team's payroll
# exceeded total revenue by up to 2.4x) — corrected upward to
# 133000/84500/49000 (S01), 59000/37500 (S02), 44000 (S03) — fitted to the
# THEN-current customer count (12).
#
# Phase 4 (recalibration #2, ABANDONED): the same Phase 2 prices, now applied
# to 50 customers instead of 12 (~4x), produced the OPPOSITE problem —
# margin exploded to 40-73%/year. An attempt was made to fix it by lowering
# ALL SERVICES prices ~2.2x — but that's one global price list applying to
# the entire 2019-2026 history, so the cut retroactively broke the
# 2019-2023 years (when K01-K12 were the ONLY revenue base, and the Phase 2
# prices were already calibrated for THAT payroll) — margin dropped to
# -138%..-15% instead of improving.
#
# Phase 4 (recalibration #3, FINAL): TWO PRICING COHORTS instead of one
# global price list — LEGACY_SERVICES (Phase 2 prices, unchanged) for
# customers onboarded BEFORE CUSTOMER_PRICING_COHORT_CUTOFF (2023-01-01;
# covers K01-K12 AND the 2022-09 merger cohort), SCALE_SERVICES (prices cut
# ~2.2x) for customers onboarded from that date on. `SERVICES` (the former
# global catalog) = alias for LEGACY_SERVICES — feeds the `services` table in
# Supabase (PK = code, one price per service — SCALE_SERVICES exists ONLY in
# Python code, has no representation in the DB, see DATA_DICTIONARY.md). See
# get_service_price_table()/service_by_code_for_customer() below and
# SESSION_HANDOFF.md (Phase 4) for the full rationale + margin numbers BEFORE/AFTER.
CUSTOMER_PRICING_COHORT_CUTOFF = date(2023, 1, 1)

LEGACY_SERVICES: list[Service] = [
    Service(
        code="S01",
        name="Managed IT Support",
        description="Helpdesk, incidents, IT infrastructure monitoring",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ALL,
        base_price_enterprise=133_000,
        base_price_mid=84_500,
        base_price_smb=49_000,
    ),
    Service(
        code="S02",
        name="Microsoft Infrastructure Management",
        description="Azure/M365 administration, managed cloud infrastructure",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ENTERPRISE_MID,
        base_price_enterprise=59_000,
        base_price_mid=37_500,
        base_price_smb=None,
    ),
    Service(
        code="S03",
        name="Cybersecurity",
        description="Security monitoring, NIS2 compliance, incident response",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ENTERPRISE_ONLY,
        base_price_enterprise=44_000,
        base_price_mid=None,
        base_price_smb=None,
    ),
    Service(
        code="S04",
        name="Consulting and Digitalization",
        description="Digitalization projects, IT advisory, implementations",
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
        description="Helpdesk, incidents, IT infrastructure monitoring",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ALL,
        base_price_enterprise=60_000,
        base_price_mid=24_000,
        base_price_smb=6_000,
    ),
    Service(
        code="S02",
        name="Microsoft Infrastructure Management",
        description="Azure/M365 administration, managed cloud infrastructure",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ENTERPRISE_MID,
        base_price_enterprise=25_000,
        base_price_mid=10_000,
        base_price_smb=None,
    ),
    Service(
        code="S03",
        name="Cybersecurity",
        description="Security monitoring, NIS2 compliance, incident response",
        billing_model=BillingModel.SUBSCRIPTION,
        availability=ServiceSegmentAvailability.ENTERPRISE_ONLY,
        base_price_enterprise=18_000,
        base_price_mid=None,
        base_price_smb=None,
    ),
    Service(
        code="S04",
        name="Consulting and Digitalization",
        description="Digitalization projects, IT advisory, implementations",
        billing_model=BillingModel.HOURLY,
        availability=ServiceSegmentAvailability.ALL,
        base_price_enterprise=950,
        base_price_mid=950,
        base_price_smb=950,
    ),
]

SERVICES: list[Service] = LEGACY_SERVICES  # reference catalog / feeds the `services` table in Supabase


# Phase 2 — which customer buys which services, by segment. Independent of
# order_pattern/support_product/license_product (Phase 1 and earlier) — those
# CustomerSeed fields remain (they still drive invoicing day/rhythm and K06's
# consulting pattern D), but the number and choice of subscription lines
# A/B/C is now computed from per-segment bundling, not from assigned products.
SEGMENT_SERVICE_BUNDLES: dict[str, tuple[str, ...]] = {
    "Enterprise": ("S01", "S02", "S03"),
    "Mid-market": ("S01", "S02"),
    "SMB": ("S01",),
}


def get_customer_services(customer: CustomerSeed) -> list[str]:
    """Returns the service codes a customer buys in their standard
    subscription, by segment: Enterprise gets the full S01+S02+S03 bundle,
    Mid-market S01+S02, SMB only S01."""
    return list(SEGMENT_SERVICE_BUNDLES[customer.segment])


def service_base_price(service: Service, segment: str) -> Optional[float]:
    """Base price of a service (year 2019, pre-inflation) for a given segment."""
    if segment == "Enterprise":
        return service.base_price_enterprise
    if segment == "Mid-market":
        return service.base_price_mid
    return service.base_price_smb


def get_service_price_table(customer: CustomerSeed) -> list[Service]:
    """Selects the price table by customer cohort (Phase 4, recalibration #3)
    — LEGACY_SERVICES (K01-K12 + the 2022-09-01 merger cohort) for customers
    onboarded before CUSTOMER_PRICING_COHORT_CUTOFF, SCALE_SERVICES for
    customers onboarded from that date on — so that the price cut for new
    customers (Phase 4) doesn't retroactively break revenue/margin in the
    years when older customers were the sole (or majority) revenue base."""
    if customer.onboarding_date < CUSTOMER_PRICING_COHORT_CUTOFF:
        return LEGACY_SERVICES
    return SCALE_SERVICES


def service_by_code_for_customer(customer: CustomerSeed, code: str) -> Service:
    """Like service_by_code(), but respecting the customer's pricing cohort
    (see get_service_price_table) — used by
    order_generator.build_order_lines instead of service_by_code() (which
    always returns from the global SERVICES/LEGACY_SERVICES, ignoring the
    cohort)."""
    for service in get_service_price_table(customer):
        if service.code == code:
            return service
    raise KeyError(f"Unknown service code: {code!r}")


_PRODUCT_FOR_SERVICE: dict[str, ProductSeed] = {}
for _product in PRODUCTS:
    _PRODUCT_FOR_SERVICE.setdefault(_product.service_code, _product)
del _product


def product_for_service(service_code: str) -> ProductSeed:
    """The canonical product (Tripletex reference/FK) for a given service —
    one per service_code regardless of customer segment, because Phase 2
    computes the price directly from Service.base_price_* (see
    service_base_price), not from Product.default_price. Returns the first
    product in PRODUCTS mapped to this code (P01 for S01, P04 for S02, P07
    for S03, P06 for S04)."""
    try:
        return _PRODUCT_FOR_SERVICE[service_code]
    except KeyError:
        raise KeyError(f"No product mapped to service: {service_code!r}")


def is_customer_active(customer: CustomerSeed, on_date: date) -> bool:
    """A customer is active (onboarding_date <= on_date, and if they have a
    churn_date, they haven't left yet). Shared implementation used by
    order_generator._is_active and generators.opex_generator (Phase 3) —
    previously logically duplicated (order_generator, hours_generator)."""
    if on_date < customer.onboarding_date:
        return False
    if customer.churn_date is not None and on_date > customer.churn_date:
        return False
    return True


def active_customers(on_date: date) -> list[CustomerSeed]:
    """Customers active on a given date (see is_customer_active) — analogous
    to seed.payroll.active_employees for employees."""
    return [c for c in CUSTOMERS if is_customer_active(c, on_date)]


# Phase 3 — new cost categories (canteen, representation, mileage). Amounts
# deliberately kept modest (lesson from Phase 2: transcribing prices verbatim
# without verifying margin crashed the result to -183%) — these costs add on
# top of an already-verified, healthy 20-23% margin and must stay small.
CANTEEN_SUBSIDY_PER_EMPLOYEE_MONTHLY = 820  # NOK, fixed, do not change (company policy, not a market price)

REPRESENTATION_COST_PER_ENTERPRISE_CLIENT_MONTHLY = 1_000  # NOK, 2019 base
REPRESENTATION_COST_PER_MID_CLIENT_MONTHLY = 400
# SMB — no representation costs, a purely transactional relationship.

KM_RATE_2019 = 3.5  # NOK/km, 2019 base rate — flat throughout this phase
# (the amount is small enough that inflation has no practical effect; not
# applying apply_annual_inflation here is deliberate, not an oversight).

CONFERENCE_HOTEL_RATES: dict[str, float] = {
    "Oslo": 2_200, "Bergen": 1_600, "Trondheim": 1_500, "Stavanger": 1_700,
    "default": 1_200,  # smaller cities
}


def calc_canteen_cost(active_employee_count: int) -> float:
    """Canteen subsidy — 820 NOK/employee/month, not inflated (this is
    company policy, not a market price — stays fixed)."""
    return active_employee_count * CANTEEN_SUBSIDY_PER_EMPLOYEE_MONTHLY


def calc_representation_cost(customers: list[CustomerSeed]) -> float:
    """Representation costs — customer relationship spend, dependent on
    segment. SMB generates no cost (a purely transactional relationship).
    Returns the base amount (year 2019) — 3%/year inflation is applied by the
    caller (generators.opex_generator.apply_annual_inflation from
    order_generator.py; roster.py deliberately does not depend on the
    generators modules, to avoid an import cycle with order_generator, which
    already imports from roster.py)."""
    total = 0.0
    for c in customers:
        if c.segment == "Enterprise":
            total += REPRESENTATION_COST_PER_ENTERPRISE_CLIENT_MONTHLY
        elif c.segment == "Mid-market":
            total += REPRESENTATION_COST_PER_MID_CLIENT_MONTHLY
    return total


def calc_client_visit_transport(customers: list[CustomerSeed], month: int) -> float:
    """Mileage for customer visits — Enterprise: quarterly meetings
    (~150km/visit), Mid-market: 2x/year, SMB: ~1x/year. Flat rate (see
    KM_RATE_2019) — the amount is too small for inflation to matter in this
    phase."""
    total_km = 0
    for c in customers:
        if c.segment == "Enterprise" and month in (2, 5, 8, 11):
            total_km += 150
        elif c.segment == "Mid-market" and month in (3, 9):
            total_km += 120
        elif c.segment == "SMB" and month == 6:
            total_km += 80
    return total_km * KM_RATE_2019


# Phase 6 — COGS pass-through for S02 (replaces the flat Azure cost from
# Phase 2, 35,000 NOK/month fixed — see
# supplier_invoice_generator.MICROSOFT_COST_LINES). The company's cost to
# Microsoft for customer infrastructure, scaling with the number and segment
# of customers buying S02 (Enterprise + Mid-market — SMB never buys S02
# under the Phase 2 bundling, roster.SEGMENT_SERVICE_BUNDLES). Rates (2019
# base year, pre-inflation) calibrated offline (Phase 6) so that with the
# full S02 portfolio in 2026 (15 Enterprise + 18 Mid-market = 33 customers)
# annual COGS lands at 6.5-8.5M NOK — see SESSION_HANDOFF.md for the
# derivation and the actual result after the backfill.
AZURE_COGS_PER_ENTERPRISE_S02_CLIENT_MONTHLY = 22_000
AZURE_COGS_PER_MID_S02_CLIENT_MONTHLY = 11_500


def calc_azure_cogs_monthly(customers: list[CustomerSeed]) -> float:
    """COGS pass-through for S02 — the cost the company pays Microsoft for
    the infrastructure of customers buying S02 (Enterprise + Mid-market, not
    SMB). Returns the base amount (year 2019) — 3%/year inflation is applied
    by the caller (opex_generator.generate_monthly_opex, same as
    calc_representation_cost — roster.py deliberately does not depend on the
    generators modules, see that comment on calc_representation_cost)."""
    total = 0.0
    for c in customers:
        if c.segment == "Enterprise":
            total += AZURE_COGS_PER_ENTERPRISE_S02_CLIENT_MONTHLY
        elif c.segment == "Mid-market":
            total += AZURE_COGS_PER_MID_S02_CLIENT_MONTHLY
    return total


# Phase 6, second calibration attempt — COGS pass-through for S01 (Managed
# IT Support), a NEW mechanism added after an offline sanity-check showed
# that S02-only COGS (Azure, above) cannot physically close the gap between
# revenue (52.4M NOK projected for 2026, not the assumed 35M) and the
# headcount~17/margin 7% target: S02 generates only ~13M NOK/year of
# revenue, so even at COGS = 87% of S02 revenue there was still a ~15M
# NOK/year shortfall. The real-world benchmark Garnes Data AS (IT
# drift/support, the S01 equivalent) has opex+COGS/revenue = 61.6% —
# suggesting that in this segment it is actually S01 (RMM/PSA tools,
# ticketing licenses, EDR/antivirus resold to customers, spare hardware),
# not S02, that carries the main burden of pass-through costs. Scales with
# ALL S01 customers (every segment buys S01 — roster.SEGMENT_SERVICE_BUNDLES),
# weighted 4:2:1 (Enterprise:Mid-market:SMB) — larger organizations require
# more tooling seats/licenses to service. The SMB rate (2019 base year) was
# calibrated offline so that (traditional_opex + cogs_s02 + cogs_s01) /
# revenue lands at 58-62% (midpoint 60%, anchored on Garnes Data's 61.6%) —
# see SESSION_HANDOFF.md (Phase 6, second calibration) for the derivation
# and the actual result after the backfill.
S01_COGS_PER_ENTERPRISE_CLIENT_MONTHLY = 53_000  # weight 4x
S01_COGS_PER_MID_CLIENT_MONTHLY = 26_500  # weight 2x
S01_COGS_PER_SMB_CLIENT_MONTHLY = 13_300  # weight 1x (base unit)


def calc_s01_cogs_monthly(customers: list[CustomerSeed]) -> float:
    """COGS pass-through for S01 — the cost of tools/licenses/hardware
    supporting Managed IT Support, paid for by ALL active customers (every
    segment buys S01), not just Enterprise+Mid like calc_azure_cogs_monthly
    (S02). Returns the base amount (year 2019) — 3%/year inflation is
    applied by the caller (opex_generator.generate_monthly_opex), same as
    calc_azure_cogs_monthly."""
    total = 0.0
    for c in customers:
        if c.segment == "Enterprise":
            total += S01_COGS_PER_ENTERPRISE_CLIENT_MONTHLY
        elif c.segment == "Mid-market":
            total += S01_COGS_PER_MID_CLIENT_MONTHLY
        else:
            total += S01_COGS_PER_SMB_CLIENT_MONTHLY
    return total


# Phase 4 — growth rule: sales vs. team capacity (Task 2).
#
# SEGMENT_HOURS_PER_MONTH/HOURS_PER_YEAR_PER_CONSULTANT/UTILIZATION_TARGET
# remain — used EXCLUSIVELY by
# hours_generator.assign_customers_to_consultants (per-consultant workload
# cap when building the timesheet portfolio, Task 5) — a different concern
# than "how many people to hire" (below).
HOURS_PER_YEAR_PER_CONSULTANT = 1_700  # typical net annual hours
UTILIZATION_TARGET = 0.80  # 80% billable utilization

SEGMENT_HOURS_PER_MONTH: dict[str, float] = {
    "Enterprise": 20,  # average 15-25h/month
    "Mid-market": 11,  # average 8-15h/month
    "SMB": 5,  # average 3-8h/month
}


# Phase 6 (second calibration) — TARGET_MARGIN lowered from 0.19 (Phase 3/4)
# to 0.07: real Norwegian IT firms in this segment (Brønnøysundregistrene,
# see roster.calc_s01_cogs_monthly) have margins of 3-10%, not 15-25%. The
# TOP-DOWN calculation (Phase 4, correction #4) remains STRUCTURALLY
# unchanged — known revenue/opex+COGS -> payroll budget -> headcount — but
# this phase's offline sanity-check showed that the actual revenue
# projection is ~52.4M NOK in 2026, not the originally assumed ~35M: at THAT
# revenue with modest, realistic COGS (S02-only, Task 2a) the formula
# produced a headcount of ~31, not ~17 (S02 COGS could not physically exceed
# S02's own revenue, ~13M/year). Solution: a SECOND COGS bucket (S01, see
# calc_s01_cogs_monthly) anchored to the real Garnes Data AS (IT
# drift/support, opex+COGS/revenue = 61.6%) — not fixed
# TARGET_COGS_S02/TARGET_TRADITIONAL_OPEX constants (independent of
# revenue), but `calc_*_cogs_monthly(customers)` functions that scale with
# the actual portfolio, the same way payroll scales with the actual
# EMPLOYEES — which is why calc_target_headcount() deliberately does NOT
# take fixed cost thresholds, only projected_opex_cogs computed from the
# real generators (as in Phase 4), so it can never drift from what actually
# lands in the database.
TARGET_MARGIN = 0.07  # midpoint of the 5.5-9% band verified in Phase 6 (2nd calibration)
AVG_FULLY_LOADED_EMPLOYEE_COST_2026 = 1_150_000  # NOK, from actual payroll data (includes AGA, feriepenger)


def calc_target_headcount(projected_revenue: float, projected_opex_cogs: float) -> int:
    """Computes the target team size from the margin goal, not from guessed
    hours/revenue per consultant (corrections #2/#3, abandoned) —
    allowed_total_cost is the maximum cost (payroll+opex+COGS) at
    TARGET_MARGIN, payroll_budget is what's left for salaries after
    subtracting opex/COGS (Phase 3: canteen, representation, transport,
    onboarding equipment + L01-L08; Phase 6: + S02 Azure COGS + S01
    tools/licenses COGS, see calc_azure_cogs_monthly/calc_s01_cogs_monthly)."""
    allowed_total_cost = projected_revenue * (1 - TARGET_MARGIN)
    payroll_budget = allowed_total_cost - projected_opex_cogs
    return round(payroll_budget / AVG_FULLY_LOADED_EMPLOYEE_COST_2026)


# Hiring-schedule verification (Phase 6, 2nd calibration) —
# calc_target_headcount() vs. the actual number of EMPLOYEES active at the
# end of each year, using actual revenue/opex+COGS generated by the
# generators (not an approximation) — see SESSION_HANDOFF.md (Phase 6) for
# the full figures from the offline sanity-check performed BEFORE the
# backfill. Target hiring trajectory: 16 (2022 post-merger) -> 17 (2022-10,
# E17, the only addition) -> 17 (unchanged through 2026) — the team STOPS
# growing with the customer portfolio (12 -> 48 active, 2019 -> 2026),
# because the support model runs on tickets
# (hours_generator.generate_daily_support_hours, one consultant serves
# several customers per day), not 1:1 customer-consultant, and most of the
# servicing cost is a materials cost (COGS), not a headcount cost. Measured
# margin: 11.5% (2022) -> 7.1% (2023) -> 7.3% (2024) -> 7.0-7.5% (2025) ->
# 6.9-7.6% (2026, partial/full year) — within the 5.5-9% target for both
# mature years, as required by the safety threshold.


def employee_by_number(number: str) -> EmployeeSeed:
    for e in EMPLOYEES:
        if e.number == number:
            return e
    raise KeyError(f"Unknown employee number: {number}")


def employee_by_id(employee_id: int) -> EmployeeSeed:
    """The inverse of numeric_id() for employees — employee_id from the
    database (1-17) -> EmployeeSeed. Needed in hours_generator (Phase 4) —
    generate_daily_hours only gets a list of int ids, not EmployeeSeed objects."""
    return employee_by_number(f"E{employee_id:02d}")


def customer_by_number(number: str) -> CustomerSeed:
    for c in CUSTOMERS:
        if c.number == number:
            return c
    raise KeyError(f"Unknown customer number: {number}")


def customer_by_id(customer_id: int) -> CustomerSeed:
    """The inverse of numeric_id() for customers — customer_id from
    TripletexRef/the database (1-12) -> CustomerSeed. Needed where we only
    have a numeric id (e.g. Order.customer.id), not the seed code ("K01")."""
    return customer_by_number(f"K{customer_id:02d}")


def supplier_by_number(number: str) -> SupplierSeed:
    for s in SUPPLIERS:
        if s.number == number:
            return s
    raise KeyError(f"Unknown supplier number: {number}")


def supplier_by_id(supplier_id: int) -> SupplierSeed:
    """The inverse of numeric_id() for suppliers — supplier_id from
    TripletexRef/the database (1-8) -> SupplierSeed."""
    return supplier_by_number(f"L{supplier_id:02d}")


def product_by_number(number: str) -> ProductSeed:
    for p in PRODUCTS:
        if p.number == number:
            return p
    raise KeyError(f"Unknown product number: {number}")


def service_by_code(code: str) -> Service:
    for s in SERVICES:
        if s.code == code:
            return s
    raise KeyError(f"Unknown service code: {code}")


def project_by_number(number: str) -> ProjectSeed:
    for p in PROJECTS:
        if p.number == number:
            return p
    raise KeyError(f"Unknown project number: {number}")


def project_by_id(project_id: int) -> ProjectSeed:
    """The inverse of numeric_id() for projects — project_id (1-45) -> ProjectSeed."""
    return project_by_number(f"PRJ{project_id:03d}")


_PROJECT_FOR_CUSTOMER_ID: dict[int, ProjectSeed] = {p.customer_id: p for p in PROJECTS}


def project_for_customer(customer: CustomerSeed) -> ProjectSeed:
    """The project assigned to a customer (Phase 4: 1:1, PRJnnn <-> Knnn) —
    used by hours_generator.assign_customers_to_consultants instead of the
    static EMPLOYEE_PROJECT_MAP from before Phase 4."""
    return _PROJECT_FOR_CUSTOMER_ID[int(customer.number[1:])]


def numeric_id(code: str) -> int:
    """Converts a seed code (E07, K03, L05, P02, PRJ001) to a Layer 1/2
    numeric id (Employee 1-17, Customer 1-50, Supplier 1-8, Product 1-7,
    Project 1-50 — Phase 4 expanded Customer/Project, Phase 6 shrank
    Employee back down to 17 — assigned sequentially in documentation
    order). Handles both single-letter (E/K/L/P) and multi-letter (PRJ)
    prefixes."""
    return int(re.sub(r"^[A-Za-z]+", "", code))
