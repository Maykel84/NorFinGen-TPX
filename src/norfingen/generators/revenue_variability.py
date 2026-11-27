"""Natural month-to-month variability of the revenue (round 4, step 3, 2026-11-25).

Until now the monthly revenue grew almost linearly: every subscription line invoiced exactly its price. A real IT-services company's
revenue breathes: Azure consumption follows the customers' activity, security projects come in lumps, July (fellesferie) and December
are quiet. The three SUBSCRIPTION services that carry a usage / project component now get a monthly factor:

    S01 Managed IT Support       seasonal (July -6 %, August -2 %, December -3 %) and a small noise (4 % standard deviation)
    S02 Microsoft Infrastructure usage-based: July -15 %, August -5 %, December -7 %, January +3 %, noise 10 %
    S03 Cybersecurity            project-driven: July -20 %, December -10 %, June +5 %, noise 12 %
    S04 consulting               unchanged (it already has its own events: extra consulting, large projects, the COVID shock)

The factors of one service and one year are normalised to a mean of exactly 1, so the YEARLY revenue stays what the price list says
(to a few tenths of a percent: the months are not equally big) - the variability moves revenue between months, it does not create or
destroy any. The same S02 factor scales the Azure pass-through COGS (usage is billed to the customer AND to Microsoft), so the
margin on S02 does not wobble with it. Pure function of (service, year, month) from a local `random.Random`, so history and the daily
cron produce the same numbers and no other random stream moves.
"""

from __future__ import annotations

import random
from functools import lru_cache

SEASONALITY: dict[str, dict[int, float]] = {
    "S01": {7: 0.94, 8: 0.98, 12: 0.97},
    "S02": {1: 1.03, 7: 0.85, 8: 0.95, 12: 0.93},
    "S03": {6: 1.05, 7: 0.80, 12: 0.90},
}
NOISE_STD: dict[str, float] = {"S01": 0.04, "S02": 0.10, "S03": 0.12}


@lru_cache(maxsize=None)
def _year_factors(code: str, year: int) -> tuple[float, ...]:
    rng = random.Random(f"usage-{code}-{year}")
    std = NOISE_STD[code]
    raw = []
    for month in range(1, 13):
        noise = max(-2.5 * std, min(2.5 * std, rng.gauss(0.0, std)))  # no month is an outlier beyond 2.5 sigma
        raw.append(SEASONALITY[code].get(month, 1.0) * (1.0 + noise))
    mean = sum(raw) / 12
    return tuple(value / mean for value in raw)


def usage_factor(code: str, year: int, month: int) -> float:
    """The factor of one service in one month (mean 1 over the year); 1.0 for a service without variability."""
    if code not in SEASONALITY:
        return 1.0
    return _year_factors(code, year)[month - 1]
