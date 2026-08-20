"""Faza 7, Zadanie 2 — zdarzenia losowe na poziomie klienta (life events).

ŚWIADOMA ZMIANA ARCHITEKTURY względem Zadania 2d: prompt zakładał "stan w
pamięci podczas backfillu, jeden sekwencyjny przebieg wystarczy — sprawdź
czy backfill faktycznie działa sekwencyjnie po miesiącach". Sprawdzone —
NIE do końca: backfill w tym repo to w praktyce DWA OSOBNE przebiegi
procesu uruchamiane ręcznie jeden po drugim (`run_backfill.py --mode
monthly`, potem `--mode daily`, zob. SESSION_HANDOFF.md p. 5), a
`--mode daily` i żywy cron (`run_daily.py`, `.github/workflows/daily.yml`)
w ogóle dzielą tę samą funkcję `run_daily()` wołaną raz per proces/dzień
— żaden mutowalny obiekt stanu przekazywany "z zewnątrz" nie przetrwałby
między tymi przebiegami.

Rozwiązanie: `customer_event_state_asof()` to CZYSTA, memoizowana funkcja
(customer, year, month) -> stan skumulowany — rekurencyjnie dokłada
miesiąc po miesiącu od onboardingu, cache'owana przez functools.lru_cache
(każda para (klient, rok, miesiąc) liczona raz w całym czasie życia
procesu, niezależnie od tego, kto i kiedy o nią zapyta). Dzięki temu
działa poprawnie i identycznie w każdym z trzech miejsc wywołania (pętla
monthly, pętla daily, żywy cron) bez żadnego jawnego przekazywania stanu
między nimi i bez nowej kolumny/tabeli w Supabase (Zadanie 2d) —
mocniejsza wersja tego samego wymogu determinizmu, nie jego złamanie."""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from norfingen.seed.roster import CustomerSeed, customer_by_number, get_customer_services

CLIENT_LIFE_EVENTS: dict[str, dict] = {
    "OFFER_EXPANSION": {
        "monthly_probability": 0.004,
        "eligible_segments": ("Mid-market", "SMB"),
        "effect": "add_service",
        "duration_months": None,
    },
    "OFFER_REDUCTION": {
        "monthly_probability": 0.003,
        "eligible_segments": ("Enterprise", "Mid-market"),
        "effect": "remove_service",
        "duration_months": None,
    },
    "TEMPORARY_HARDSHIP": {
        "monthly_probability": 0.004,
        "eligible_segments": ("Enterprise", "Mid-market", "SMB"),
        "effect": "reduced_volume_and_late_payment",
        "duration_months": (2, 4),
    },
    "BANKRUPTCY": {
        "monthly_probability": 0.0008,
        "eligible_segments": ("SMB",),
        "effect": "immediate_churn_and_writeoff",
        "duration_months": None,
    },
    "ONE_OFF_LARGE_PROJECT": {
        "monthly_probability": 0.005,
        "eligible_segments": ("Enterprise", "Mid-market"),
        "effect": "large_s04_order",
        "duration_months": None,
    },
}

# OFFER_EXPANSION — usługa "o poziom wyżej" niż standardowy bundel segmentu
# (roster.SEGMENT_SERVICE_BUNDLES). Enterprise ma już pełny pakiet S01+S02+S03
# — celowo nieobecny tu, spójne z eligible_segments powyżej.
#
# ŚWIADOMA KOREKTA względem naiwnego "kolejny poziom w górę" (SMB->S02,
# Mid-market->S03): S02 ma roster.Service.availability=ENTERPRISE_MID (brak
# base_price_smb — crash przy próbie wyceny dla SMB), S03 ma
# availability=ENTERPRISE_ONLY (brak base_price_mid) — obie łamią już
# istniejące ograniczenia katalogu usług. S04 (Konsulting i digitalizacja)
# ma availability=ALL i wycenę dla każdego segmentu — jedyna usługa, którą
# oba segmenty mogą faktycznie legalnie "dokupić" jako trwałą, dodatkową
# linię subskrypcyjną, niezależnie od okazjonalnych zamówień
# should_generate_extra_consulting/ONE_OFF_LARGE_PROJECT.
EXPANSION_SERVICE_BY_SEGMENT: dict[str, str] = {
    "SMB": "S04",
    "Mid-market": "S04",
}

# OFFER_REDUCTION — usługi możliwe do usunięcia, nigdy S01 (Zadanie 2c).
# Mid-market ma tylko jedną sensowną opcję (S02); Enterprise wybiera
# deterministycznie między S02/S03 osobnym rng (zob. _advance_one_month).
REDUCIBLE_SERVICES_BY_SEGMENT: dict[str, tuple[str, ...]] = {
    "Mid-market": ("S02",),
    "Enterprise": ("S02", "S03"),
}

HARDSHIP_TICKET_REDUCTION_MIN = 0.40  # "redukcja wolumenu o 40-60%" — mnożnik zostających godzin: 1-0.6=0.40 .. 1-0.4=0.60
HARDSHIP_TICKET_REDUCTION_MAX = 0.60

# Elevated bad-debt/OVERDUE próg podczas aktywnego kryzysu klienta —
# zadanie nie podało konkretnej wartości ("podnieś próg"), skalibrowano
# na wyraźnie podwyższony, ale nie absurdalny poziom: x5 normalnego
# order_generator.BAD_DEBT_PROBABILITY (0.02 -> 0.10).
HARDSHIP_BAD_DEBT_MULTIPLIER = 5.0

LARGE_PROJECT_HOURS_MIN = 80.0
LARGE_PROJECT_HOURS_MAX = 200.0


@dataclass(frozen=True)
class CustomerEventState:
    """Stan skumulowany klienta na koniec danego (roku, miesiąca) — zob.
    customer_event_state_asof(). Frozen — _advance_one_month zwraca zawsze
    NOWĄ instancję zamiast mutować, żeby wynik cache'owany przez lru_cache
    nigdy nie mógł zostać przypadkiem zmodyfikowany przez wywołującego."""

    added_service: Optional[str] = None
    removed_service: Optional[str] = None
    hardship_active_until: Optional[tuple[int, int]] = None  # (year, month) — ostatni miesiąc kryzysu włącznie
    hardship_ticket_multiplier: Optional[float] = None  # 0.40-0.60, wylosowany raz na start okna, stały przez cały czas trwania
    churned: bool = False
    churn_year_month: Optional[tuple[int, int]] = None
    triggered_this_month: Optional[str] = None  # kod zdarzenia, jeśli coś wystrzeliło DOKŁADNIE w (year, month) tego stanu


_EMPTY_STATE = CustomerEventState()


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + n
    return total // 12, total % 12 + 1


def roll_client_events(customer: CustomerSeed, year: int, month: int, prev_state: CustomerEventState) -> Optional[str]:
    """Deterministyczne losowanie — jeden rng seedowany
    customer_number+rok+miesiąc, iterowany w kolejności katalogu (jak w
    Zadaniu 2b). Świadome odstępstwo od danego pseudokodu: zamiast
    sprawdzać `active_event == event_code` (pojedyncze pole String, które
    nie oddaje "trwałych" zmian OFFER_EXPANSION/REDUCTION współistniejących
    z późniejszym kryzysem), efekty trwałe (bez duration_months) są
    odhaczane raz na zawsze przez sam stan (added_service/removed_service
    już ustawiony -> nieeligible na kolejne miesiące), a jedyny naprawdę
    "aktywny, blokujący nowe losowania" stan to TEMPORARY_HARDSHIP (jedyny
    z określonym duration_months) — sprawdzane PRZED wywołaniem tej
    funkcji, zob. _advance_one_month. Pierwsze trafienie w kolejności
    katalogu wygrywa (klient przechodzi jedno zdarzenie na miesiąc)."""
    rng = random.Random(f"{customer.number}-{year}-{month}-events")
    for event_code, event_def in CLIENT_LIFE_EVENTS.items():
        if customer.segment not in event_def["eligible_segments"]:
            continue
        if event_code == "OFFER_EXPANSION" and prev_state.added_service is not None:
            continue
        if event_code == "OFFER_REDUCTION" and prev_state.removed_service is not None:
            continue
        if rng.random() < event_def["monthly_probability"]:
            return event_code
    return None


def _advance_one_month(customer: CustomerSeed, year: int, month: int, prev_state: CustomerEventState) -> CustomerEventState:
    if prev_state.churned:
        return CustomerEventState(
            added_service=prev_state.added_service, removed_service=prev_state.removed_service,
            churned=True, churn_year_month=prev_state.churn_year_month, triggered_this_month=None,
        )

    hardship_until = prev_state.hardship_active_until
    if hardship_until is not None and (year, month) > hardship_until:
        hardship_until = None  # kryzys wygasł przed tym miesiącem

    if hardship_until is not None:
        # klient w trakcie aktywnego kryzysu — nie losujemy nowych zdarzeń
        # (2d: jeden "aktywny" stan na raz)
        return CustomerEventState(
            added_service=prev_state.added_service, removed_service=prev_state.removed_service,
            hardship_active_until=hardship_until, hardship_ticket_multiplier=prev_state.hardship_ticket_multiplier,
            triggered_this_month=None,
        )

    code = roll_client_events(customer, year, month, prev_state)
    if code is None:
        return CustomerEventState(added_service=prev_state.added_service, removed_service=prev_state.removed_service)

    effect_rng = random.Random(f"{customer.number}-{year}-{month}-{code}-effect")

    if code == "OFFER_EXPANSION":
        new_service = EXPANSION_SERVICE_BY_SEGMENT[customer.segment]
        return CustomerEventState(added_service=new_service, removed_service=prev_state.removed_service, triggered_this_month=code)

    if code == "OFFER_REDUCTION":
        options = REDUCIBLE_SERVICES_BY_SEGMENT[customer.segment]
        removed = effect_rng.choice(options)
        return CustomerEventState(added_service=prev_state.added_service, removed_service=removed, triggered_this_month=code)

    if code == "TEMPORARY_HARDSHIP":
        duration_min, duration_max = CLIENT_LIFE_EVENTS[code]["duration_months"]
        duration = effect_rng.randint(duration_min, duration_max)
        end_year, end_month = _add_months(year, month, duration - 1)
        reduction_multiplier = effect_rng.uniform(HARDSHIP_TICKET_REDUCTION_MIN, HARDSHIP_TICKET_REDUCTION_MAX)
        return CustomerEventState(
            added_service=prev_state.added_service, removed_service=prev_state.removed_service,
            hardship_active_until=(end_year, end_month), hardship_ticket_multiplier=reduction_multiplier,
            triggered_this_month=code,
        )

    if code == "BANKRUPTCY":
        return CustomerEventState(
            added_service=prev_state.added_service, removed_service=prev_state.removed_service,
            churned=True, churn_year_month=(year, month), triggered_this_month=code,
        )

    if code == "ONE_OFF_LARGE_PROJECT":
        return CustomerEventState(added_service=prev_state.added_service, removed_service=prev_state.removed_service, triggered_this_month=code)

    raise AssertionError(f"Nieobsłużony kod zdarzenia: {code!r}")  # pragma: no cover


@lru_cache(maxsize=None)
def customer_event_state_asof(customer_number: str, year: int, month: int) -> CustomerEventState:
    """Skumulowany stan zdarzeń klienckich klienta na koniec (year, month) —
    czysta funkcja, cache'owana (zob. docstring modułu). Przyjmuje
    customer_number (str), nie CustomerSeed — dataclass jest frozen, ale
    lru_cache i tak wymaga hashowalnych argumentów, a numer jest naturalnym
    kluczem.

    Faza 7, Zadanie 2 — świadomie wykluczony wzorzec D (K06, jedyny klient
    consultingowy bez stałego bundla usług, zob. roster.py/order_generator.py
    "osobna logika"): OFFER_EXPANSION/REDUCTION nie mają się do czego
    zastosować (K06 nie przechodzi przez build_order_lines wcale), a
    BANKRUPTCY byłby martwy (branch pattern=="D" w generate_monthly_orders
    nie sprawdza event_aware_is_customer_active) — podłączenie tego
    wymagałoby przeprojektowania osobnej logiki K06, poza zakresem tego
    zadania. K06 nigdy nie rolluje żadnego zdarzenia."""
    customer = customer_by_number(customer_number)
    if customer.order_pattern not in ("A", "B", "C"):
        return _EMPTY_STATE
    onboarding = customer.onboarding_date
    if (year, month) < (onboarding.year, onboarding.month):
        return _EMPTY_STATE

    if (year, month) == (onboarding.year, onboarding.month):
        prev_state = _EMPTY_STATE
    else:
        prev_year, prev_month = _prev_month(year, month)
        prev_state = customer_event_state_asof(customer_number, prev_year, prev_month)

    return _advance_one_month(customer, year, month, prev_state)


def effective_customer_services(customer: CustomerSeed, state: CustomerEventState) -> list[str]:
    """get_customer_services(), ale z trwałymi efektami OFFER_EXPANSION/
    OFFER_REDUCTION zastosowanymi (Zadanie 2c)."""
    services = list(get_customer_services(customer))
    if state.added_service and state.added_service not in services:
        services.append(state.added_service)
    if state.removed_service and state.removed_service in services:
        services.remove(state.removed_service)
    return services


def event_aware_is_customer_active(customer: CustomerSeed, on_date) -> bool:
    """roster.is_customer_active(), rozszerzone o BANKRUPTCY — klient
    przestaje być aktywny od miesiąca PO tym, w którym zdarzenie
    wystrzeliło (miesiąc triggera generuje jeszcze swoją ostatnią,
    odpisaną fakturę, zob. order_generator)."""
    from norfingen.seed.roster import is_customer_active  # import lokalny — unika cyklu na poziomie modułu

    if not is_customer_active(customer, on_date):
        return False
    state = customer_event_state_asof(customer.number, on_date.year, on_date.month)
    if state.churned and state.churn_year_month != (on_date.year, on_date.month):
        return False
    return True


def hardship_ticket_multiplier_for(customer_number: str, on_date) -> float:
    """Faza 7, Zadanie 2c — mnożnik wolumenu ticketów wsparcia (hours_generator)
    dla klienta w aktywnym oknie TEMPORARY_HARDSHIP na daną datę; 1.0 (brak
    redukcji) poza oknem kryzysu."""
    state = customer_event_state_asof(customer_number, on_date.year, on_date.month)
    if state.hardship_active_until is None:
        return 1.0
    return state.hardship_ticket_multiplier
