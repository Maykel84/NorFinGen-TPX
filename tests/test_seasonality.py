"""Faza 7, Zadanie 1 — sezonowe wzorce norweskiego B2B (poziom firmy)."""

from norfingen.generators.seasonality import (
    fellesferie_activity_multiplier,
    january_new_initiative_boost,
    q4_budget_flush_multiplier,
)


def test_fellesferie_halves_july_only():
    assert fellesferie_activity_multiplier(7) == 0.5
    for month in range(1, 13):
        if month == 7:
            continue
        assert fellesferie_activity_multiplier(month) == 1.0


def test_q4_budget_flush_only_nov_dec_enterprise_midmarket():
    for month in (11, 12):
        assert q4_budget_flush_multiplier(month, "Enterprise") == 1.4
        assert q4_budget_flush_multiplier(month, "Mid-market") == 1.4
        assert q4_budget_flush_multiplier(month, "SMB") == 1.0
    for month in range(1, 11):
        assert q4_budget_flush_multiplier(month, "Enterprise") == 1.0


def test_january_boost_only_january():
    assert january_new_initiative_boost(1) == 1.2
    for month in range(2, 13):
        assert january_new_initiative_boost(month) == 1.0
