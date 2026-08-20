"""Sezonowe wzorce norweskiego B2B (Faza 7, Zadanie 1) — poziom całej firmy.

Czyste mnożniki bez losowości (deterministyczne funkcje miesiąca/segmentu),
używane przez inne generatory żeby modulować już istniejącą losowość
(hours_generator.generate_daily_support_hours, order_generator.
should_generate_extra_consulting) zamiast dodawać równoległe mechanizmy.

Nie są tu żadnego stanu ani RNG — te funkcje same w sobie nic nie losują,
tylko skalują istniejące progi/zakresy w miejscu wywołania. Dzięki temu
determinizm (random.Random(string) w wywołującym kodzie) jest zachowany bez
zmian."""

from __future__ import annotations


def fellesferie_activity_multiplier(month: int) -> float:
    """Lipiec: ~50% normalnego wolumenu nowych ticketów wsparcia i tempa
    decyzji zakupowych. Nie wpływa na już podpisane subskrypcje
    S01/S02/S03 (fakturują się normalnie — patrz order_generator,
    subskrypcje A/B/C nie są w ogóle skalowane tym mnożnikiem)."""
    if month == 7:
        return 0.5
    return 1.0


def q4_budget_flush_multiplier(month: int, customer_segment: str) -> float:
    """Listopad-grudzień: podwyższone prawdopodobieństwo dodatkowych
    zamówień S04 dla Enterprise/Mid-market, ponad standardową sezonowość
    już istniejącą w extra-consulting z Fazy 2 (Q2/Q4 w
    order_generator.EXTRA_CONSULTING_MONTHS)."""
    if month in (11, 12) and customer_segment in ("Enterprise", "Mid-market"):
        return 1.4
    return 1.0


def january_new_initiative_boost(month: int) -> float:
    """Styczeń: nieznacznie podwyższone prawdopodobieństwo nowych projektów
    S02 (nowe inicjatywy IT na nowy rok budżetowy).

    UWAGA — świadomie NIEPODŁĄCZONE na razie (Faza 7, Zadanie 1c): w
    kodzie nie istnieje obecnie żaden dyskretny mechanizm "nowy projekt
    S02" analogiczny do should_generate_extra_consulting (S02 jest
    sprzedawany wyłącznie jako część stałego bundla segmentowego —
    roster.get_customer_services — nie jako osobne zamówienie). Podłączenie
    tego mnożnika wymagałoby najpierw zaprojektowania takiego mechanizmu,
    co wykracza poza zakres Zadania 1 — zob. SESSION_HANDOFF.md."""
    return 1.2 if month == 1 else 1.0
