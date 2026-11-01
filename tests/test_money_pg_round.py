"""pg_round2 must equal the cent Postgres STORES when the pipeline writes a float through psycopg2.

Two layers:
* pure tests of the rule on known boundary values (always run);
* a comparison against a REAL Postgres on >= 10 000 values, including every .xx5 boundary and the doubles on either
  side of it. It goes through the same psycopg2 INSERT the pipeline uses - NOT through a `float8::numeric` cast, which
  rounds differently (15 significant digits instead of the literal psycopg2 sends) and is exactly the mistake the
  first version of this test made (phase 0.5a validated the cast path; phase 3 found 137 stored lines it predicted
  wrongly). It runs only when NORFINGEN_TEST_PG_URL points at a scratch database; the only thing it creates is a TEMP
  table, gone with the connection, and the variable is separate from DATABASE_URL on purpose so it can never be pointed
  at production by accident.

    NORFINGEN_TEST_PG_URL=postgresql://user@127.0.0.1:54329/scratch pytest tests/test_money_pg_round.py
"""

import math
import os
import random
from decimal import Decimal

import pytest

from norfingen.generators.backfill import months_range
from norfingen.generators.money import pg_round2
from norfingen.generators.order_generator import generate_monthly_orders
from datetime import date

# --- the rule, on values whose PG result was observed ------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (114249.135, 114249.14),      # the real order (K01, 2020-07-26) that Python's round() got wrong
    (0.005, 0.01),
    (2.675, 2.68),                # the literal 2.675 is exactly half: Postgres rounds it up; Python's round() says 2.67
    (1.005, 1.01),
    (-2.675, -2.68),              # half away from zero
    (52733.024999999994, 52733.02),   # a real order line (K08, 2020-11-25): just BELOW the boundary, stored as .02 -
    (114119.42499999999, 114119.42),  # the float8::numeric cast would say .03 / .43; the literal psycopg2 sends does not
    (0.0, 0.0),
    (298215.505, 298215.51),
    (100.0, 100.0),
])
def test_pg_round2_known_boundaries(value, expected):
    assert pg_round2(value) == expected


def test_python_round_really_differs_somewhere():
    # Guards the premise of this module: if Python's round ever agreed everywhere we could drop pg_round2.
    assert round(114249.135, 2) != pg_round2(114249.135)


# --- against a real Postgres --------------------------------------------------------------------

def _candidate_values() -> list[float]:
    rng = random.Random("pg-round2-fixture")
    values: list[float] = []

    # 1. .xx5 boundaries across magnitudes, plus the doubles on either side of each
    for _ in range(2500):
        cents = rng.randint(1, 99_999_999)
        boundary = cents / 100 + 0.005
        values += [boundary, math.nextafter(boundary, math.inf), math.nextafter(boundary, -math.inf)]

    # 2. random values with 1-6 decimals over many magnitudes, both signs
    for _ in range(3000):
        magnitude = 10 ** rng.uniform(-2, 7)
        values.append(round(rng.choice((-1, 1)) * magnitude, rng.randint(1, 6)))

    # 3. real order-line gross amounts from the generators (what actually gets stored)
    for year, month in months_range(date(2019, 1, 1), date(2026, 9, 30)):
        for order in generate_monthly_orders(year, month):
            for line in order.orderLines:
                values.append(line.amountCurrency)
                values.append(line.amountExcludingVatCurrency)
    return values


@pytest.mark.skipif(not os.environ.get("NORFINGEN_TEST_PG_URL"), reason="NORFINGEN_TEST_PG_URL not set (no scratch Postgres)")
def test_pg_round2_matches_what_postgres_stores_on_10k_values():
    import psycopg2

    values = _candidate_values()
    assert len(values) >= 10_000

    conn = psycopg2.connect(os.environ["NORFINGEN_TEST_PG_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE pg_round2_probe (id integer PRIMARY KEY, v numeric(14,2))")
            for i, x in enumerate(values):            # one INSERT per value: exactly how repository.py writes amounts
                cur.execute("INSERT INTO pg_round2_probe (id, v) VALUES (%s, %s)", (i, x))
            cur.execute("SELECT id, v FROM pg_round2_probe ORDER BY id")
            stored = cur.fetchall()
    finally:
        conn.close()

    assert len(stored) == len(values)
    mismatches = [
        (values[i], v, pg_round2(values[i])) for i, v in stored if Decimal(str(pg_round2(values[i]))) != v
    ]
    assert not mismatches, f"{len(mismatches)} of {len(stored)} differ, first: {mismatches[:5]}"
