from datetime import date

from norfingen.seed.payroll import (
    active_employees,
    calc_aga,
    calc_brutto,
    calc_brutto_with_raises,
    calc_feriepenger,
    calc_netto,
    calc_skattetrekk,
    is_june,
    last_working_day,
)
from norfingen.models.service import BillingModel, ServiceSegmentAvailability
from norfingen.seed.roster import (
    CUSTOMERS,
    DEPARTMENTS,
    EMPLOYEES,
    LEGACY_SERVICES,
    PRODUCTS,
    PROJECTS,
    SCALE_SERVICES,
    SERVICES,
    SUPPLIERS,
    customer_by_number,
    employee_by_number,
    get_service_price_table,
    numeric_id,
    project_by_number,
    service_by_code,
    service_by_code_for_customer,
)


def test_roster_counts_match_docs():
    assert len(DEPARTMENTS) == 4
    assert len(EMPLOYEES) == 38  # Faza 4: 16 + E17-E38
    assert len(CUSTOMERS) == 50  # Faza 4: 12 + K13-K50
    assert len(SUPPLIERS) == 8
    assert len(PRODUCTS) == 7  # Faza 2: +P07 Cyberbezpieczeństwo (S03)
    assert len(SERVICES) == 4


def test_services_seed_data():
    # SERVICES == LEGACY_SERVICES (Faza 2 ceny) — katalog referencyjny /
    # zasila tabelę `services` w Supabase (jedna cena/usługę, zob. roster.py).
    s01 = service_by_code("S01")
    assert s01.name == "Managed IT Support"
    assert s01.billing_model == BillingModel.SUBSCRIPTION
    assert s01.availability == ServiceSegmentAvailability.ALL
    assert s01.base_price_enterprise == 133_000
    assert s01.base_price_smb == 49_000

    s03 = service_by_code("S03")
    assert s03.availability == ServiceSegmentAvailability.ENTERPRISE_ONLY
    assert s03.base_price_mid is None
    assert s03.base_price_smb is None

    s04 = service_by_code("S04")
    assert s04.billing_model == BillingModel.HOURLY
    assert s04.base_price_enterprise == s04.base_price_mid == s04.base_price_smb == 1_450


def test_faza4_dual_pricing_cohorts():
    # K01 (onboarding 2019, legacy) vs K13 (onboarding 2023, scale) —
    # rekalibracja #3: dwie kohorty cenowe zamiast jednego globalnego cennika.
    k01 = customer_by_number("K01")
    k13 = customer_by_number("K13")
    assert get_service_price_table(k01) is LEGACY_SERVICES
    assert get_service_price_table(k13) is SCALE_SERVICES

    s01_legacy = service_by_code_for_customer(k01, "S01")
    s01_scale = service_by_code_for_customer(k13, "S01")
    assert s01_legacy.base_price_enterprise == 133_000
    assert s01_scale.base_price_enterprise == 60_000


def test_faza4_merger_cohort_uses_legacy_pricing():
    # Kohorta fuzji (2022-09-01, K27/K32/K34/K46) onboarduje się PRZED
    # cutoff (2023-01-01) -> LEGACY_SERVICES mimo że są w numeracji K13-K50.
    for number in ("K27", "K32", "K34", "K46"):
        customer = customer_by_number(number)
        assert customer.onboarding_date == date(2022, 9, 1)
        assert get_service_price_table(customer) is LEGACY_SERVICES


def test_every_product_maps_to_a_valid_service():
    valid_codes = {s.code for s in SERVICES}
    for product in PRODUCTS:
        assert product.service_code in valid_codes, f"{product.number} ma nieprawidłowy service_code: {product.service_code!r}"


def test_product_service_mapping_matches_category():
    expected = {
        "P01": "S01", "P02": "S01", "P03": "S01",  # IT Support -> Managed IT Support
        "P04": "S02", "P05": "S02",  # Licencje/Microsoft -> Zarządzanie infrastrukturą Microsoft
        "P06": "S04",  # Consulting -> Konsulting i digitalizacja
        "P07": "S03",  # Faza 2 -> Cyberbezpieczeństwo
    }
    for product in PRODUCTS:
        assert product.service_code == expected[product.number]


def test_active_employees_respects_historical_phases():
    assert len(active_employees(date(2019, 6, 1))) == 6
    assert len(active_employees(date(2020, 6, 1))) == 8
    assert len(active_employees(date(2021, 12, 1))) == 10
    # 2022-10-01: po fuzji (2022-09-01, +6), przed pierwszą rekrutacją Faza 4
    # (E17, 2022-10-03 od Fazy 5 — pierwszy dzień roboczy października) -> 16.
    assert len(active_employees(date(2022, 10, 1))) == 16


def test_founding_cohort_staggered_over_four_months():
    # Kohorta założycielska rozłożona 2019-01 -> 2019-04, nie jednego dnia.
    # Faza 5: E03/E05 przyciągnięte do 1. dnia roboczego swojego miesiąca
    # (Zadanie 1b) -> teraz start dokładnie tego samego dnia co E02/E04
    # (oboje w lutym/marcu), staggering wyraża się przez MIESIĄC, nie już
    # przez dzień w miesiącu.
    assert len(active_employees(date(2019, 1, 1))) == 1  # tylko E01 (CEO)
    assert len(active_employees(date(2019, 1, 31))) == 1
    assert len(active_employees(date(2019, 2, 1))) == 3  # +E02, +E03 (oboje 2019-02-01)
    assert len(active_employees(date(2019, 3, 1))) == 5  # +E04, +E05 (oboje 2019-03-01)
    assert len(active_employees(date(2019, 4, 1))) == 6  # +E06 -> zespół kompletny


def test_customer_count_grows_with_headcount():
    """Liczba aktywnych klientów rośnie wraz z zatrudnieniem, nie wyprzedza go —
    na koniec 2019 (6 pracowników) liczba onboardowanych klientów nie przekracza
    liczby pracowników w tym momencie."""
    headcount_end_2019 = len(active_employees(date(2019, 12, 31)))
    active_customers_end_2019 = [c for c in CUSTOMERS if c.onboarding_date <= date(2019, 12, 31)]
    assert headcount_end_2019 == 6
    assert len(active_customers_end_2019) <= headcount_end_2019


def test_founding_hires_not_paid_before_their_start_month():
    # E04 startuje 2019-03-01 -> nieaktywny w lutym, aktywny od marca.
    e04 = employee_by_number("E04")
    assert e04.start_date == date(2019, 3, 1)
    active_february = active_employees(date(2019, 2, 1))
    active_march = active_employees(date(2019, 3, 1))
    assert e04 not in active_february
    assert e04 in active_march


def test_new_hire_starting_day_two_or_three_paid_in_own_start_month():
    """Faza 5 — naprawiony błąd: pracownik, którego pierwszy dzień roboczy
    miesiąca wypada 2./3. (bo 1. to weekend), MUSI dostać wypłatę za SWÓJ
    miesiąc startu, nie dopiero za kolejny (dawne active_employees(date(year,
    month, 1)) błędnie porównywało do kalendarzowego dnia 1, wykluczając
    takiego pracownika z jego własnego miesiąca — zob. salary_generator.py,
    generate_monthly_salary/brutto_earned_in_year, first_working_day_of_month())."""
    e17 = employee_by_number("E17")
    assert e17.start_date == date(2022, 10, 3)  # 1./2. października 2022 to weekend
    from norfingen.generators.salary_generator import generate_monthly_salary
    transaction, _ = generate_monthly_salary(2022, 10)
    assert any(p.employee.id == numeric_id("E17") for p in transaction.payslips)


def test_active_employees_brutto_aggregate_matches_docs():
    # Łączne brutto/mies. tuż po fuzji (2022-09), przed pierwszą rekrutacją
    # Faza 4: 16 os. ≈ 955 000 NOK (docs W2, wartość zaokrąglona w
    # dokumentacji — dopuszczamy tolerancję wynikającą z sumy rzeczywistych
    # stawek rocznych w roster.py).
    active = active_employees(date(2022, 10, 1))
    total_brutto = sum(calc_brutto(e) for e in active)
    assert abs(total_brutto - 955_000) < 20_000


def test_payroll_calculations():
    brutto = 73_333
    skattetrekk = calc_skattetrekk(brutto)
    assert skattetrekk == round(brutto * 0.33)
    netto = calc_netto(brutto, skattetrekk)
    assert netto == brutto - skattetrekk
    aga = calc_aga(brutto)
    assert aga == round(brutto * 0.141)


def test_calc_feriepenger():
    assert calc_feriepenger(955_000) == round(955_000 * 0.12)


def test_calc_brutto_with_raises_no_raise_in_founding_year():
    e01 = employee_by_number("E01")  # start 2019-01-01
    assert calc_brutto_with_raises(e01, 2019, 1) == round(calc_brutto(e01), 2)
    assert calc_brutto_with_raises(e01, 2019, 12) == round(calc_brutto(e01), 2)


def test_calc_brutto_with_raises_first_raise_next_july():
    e01 = employee_by_number("E01")  # start 2019-01-01 -> pierwsza podwyżka lipiec 2020
    assert calc_brutto_with_raises(e01, 2020, 6) == round(calc_brutto(e01), 2)
    assert calc_brutto_with_raises(e01, 2020, 7) == round(calc_brutto(e01) * 1.03, 2)


def test_calc_brutto_with_raises_compounds_annually():
    e01 = employee_by_number("E01")
    # 880 000 NOK/rok w 2019 -> ~1 081 000 NOK/rok (brutto x12) w 2026 po H2 (7 podwyżek).
    monthly_2026_h2 = calc_brutto_with_raises(e01, 2026, 7)
    assert abs(monthly_2026_h2 * 12 - 1_081_000) < 5_000


def test_projects_seed_data():
    # Faza 4: jeden projekt per klient (1:1, PRJnnn <-> Knnn), nie 8 ręcznie
    # utrzymywanych wpisów jak przed Fazą 4.
    assert len(PROJECTS) == 50
    prj005 = project_by_number("PRJ005")
    assert prj005.customer_id == 5
    assert prj005.start_date == date(2019, 9, 1)  # = K05 (Fjord Logistikk AS) onboarding_date


def test_numeric_id_handles_single_and_multi_letter_prefixes():
    assert numeric_id("E07") == 7
    assert numeric_id("K03") == 3
    assert numeric_id("L05") == 5
    assert numeric_id("P02") == 2
    assert numeric_id("PRJ001") == 1
    assert numeric_id("PRJ008") == 8


def test_last_working_day_rolls_back_from_weekend():
    # Czerwiec 2024 -> 30.06.2024 to niedziela -> powinno przesunąć na piątek 28.06
    assert last_working_day(2024, 6) == date(2024, 6, 28)
    # Styczeń 2024 -> 31.01.2024 to środa -> bez zmian
    assert last_working_day(2024, 1) == date(2024, 1, 31)


def test_is_june():
    assert is_june(6) is True
    assert is_june(5) is False
