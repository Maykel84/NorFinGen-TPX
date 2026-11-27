"""Operating costs with spikes (round 4, step 3, 2026-11-25).

The ordinary operating costs of the generator are almost flat month after month (150-240 k NOK), which real books are not: annual
licences and insurance fall due in January, the auditor comes in spring, marketing and events cluster, equipment breaks, and every
hire costs a recruitment fee. Together with the growth costs of the early years this also lifts the operating-cost share of
revenue to what a firm of this size carries (8-9 %, the generator had 5-6 % in the later years).

The yearly budget is a decision of the margin calibration (D1, `docs/PROJECT_HISTORY.md`): EXTRA_OPEX_NET_BY_YEAR, NET of VAT. It is
split into items, each booked as a cash purchase with 25 % VAT on a reproducible working day:

    recruitment fee   one per hire (roster.EMPLOYEES with phase "scaling2"), 20 % of the first annual salary, in the month before the start
    annual licences   January, 40 % of the rest                 account 6410 Lisenser og programvare
    audit and books   April or May, 20 % of the rest            account 6700 Fremmed tjeneste
    marketing, events 4 months of the year (never July), 20 %   account 7320 Reklamekostnad
    repairs           3 months of the year, 20 %                account 6600 Reparasjon og vedlikehold

Amounts inside a component vary (weights 0.6-1.4) but always add up to the component's share, and the last item takes the cent
remainder, so a year's extras equal its budget to the cent. A pure function of the year (a local `random.Random`).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from norfingen.seed.roster import EMPLOYEES

# NET of VAT, NOK per calendar year. 2019 has none (start-up). 2026 is the full year; the months not reached yet are simply not generated.
EXTRA_OPEX_NET_BY_YEAR: dict[int, float] = {
    2019: 0.0, 2020: 780_000.0, 2021: 560_000.0, 2022: 50_000.0, 2023: 480_000.0,
    2024: 1_000_000.0, 2025: 1_170_000.0, 2026: 1_500_000.0,
}
RECRUITMENT_FEE_SHARE_OF_SALARY = 0.20
COMPONENT_SHARES = {"licenses": 0.40, "audit": 0.20, "marketing": 0.20, "repairs": 0.20}

ACCOUNT_LICENSES = 6410
ACCOUNT_SERVICES = 6700
ACCOUNT_MARKETING = 7320
ACCOUNT_REPAIRS = 6600


@dataclass(frozen=True)
class ExtraCost:
    month: int
    kind: str  # licenses / audit / marketing / repairs / recruitment
    account: int
    description: str
    net: float


def _recruitment_costs(year: int) -> list[ExtraCost]:
    out = []
    for employee in EMPLOYEES:
        if employee.phase != "scaling2":
            continue
        month, y = (employee.start_date.month - 1, employee.start_date.year) if employee.start_date.month > 1 else (12, employee.start_date.year - 1)
        if y == year:
            fee = round(employee.annual_salary * RECRUITMENT_FEE_SHARE_OF_SALARY, -2)
            out.append(ExtraCost(month, "recruitment", ACCOUNT_SERVICES, f"Rekrutteringsbistand — {employee.role}", fee))
    return out


def _spread(rng: random.Random, total: float, count: int) -> list[float]:
    weights = [rng.uniform(0.6, 1.4) for _ in range(count)]
    parts = [round(total * w / sum(weights), 2) for w in weights[:-1]]
    parts.append(round(total - sum(parts), 2))
    return parts


@lru_cache(maxsize=None)
def extra_costs_for_year(year: int) -> tuple[ExtraCost, ...]:
    budget = EXTRA_OPEX_NET_BY_YEAR.get(year, 0.0)
    if budget <= 0:
        return ()
    recruitment = _recruitment_costs(year)
    remaining = max(0.0, budget - sum(c.net for c in recruitment))
    rng = random.Random(f"extra-opex-{year}")
    items: list[ExtraCost] = list(recruitment)
    items.append(ExtraCost(1, "licenses", ACCOUNT_LICENSES, f"Årslisenser og abonnement {year}",
                           round(remaining * COMPONENT_SHARES["licenses"], 2)))
    audit_month = rng.choice([4, 5])
    items.append(ExtraCost(audit_month, "audit", ACCOUNT_SERVICES, f"Revisjon og regnskapsføring {year - 1}",
                           round(remaining * COMPONENT_SHARES["audit"], 2)))
    marketing_months = sorted(rng.sample([m for m in range(1, 13) if m != 7], 4))
    for month, net in zip(marketing_months, _spread(rng, remaining * COMPONENT_SHARES["marketing"], 4)):
        items.append(ExtraCost(month, "marketing", ACCOUNT_MARKETING, "Markedsføring og arrangement", net))
    repair_months = sorted(rng.sample(range(1, 13), 3))
    for month, net in zip(repair_months, _spread(rng, remaining * COMPONENT_SHARES["repairs"], 3)):
        items.append(ExtraCost(month, "repairs", ACCOUNT_REPAIRS, "Reparasjon og vedlikehold av utstyr", net))
    return tuple(sorted(items, key=lambda c: (c.month, c.kind)))


def extra_costs(year: int, month: int) -> list[ExtraCost]:
    """The extra costs of one month."""
    return [c for c in extra_costs_for_year(year) if c.month == month]
