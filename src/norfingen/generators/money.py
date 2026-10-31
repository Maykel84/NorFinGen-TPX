"""Rounding that matches what Postgres does when it stores a float.

The generators compute amounts as Python floats and psycopg2 sends them as
float8; Postgres then converts float8 -> numeric(14,2). That conversion is NOT
Python's `round(x, 2)`:

* Postgres formats the double with 15 significant digits (`%.15g`) and then
  rounds that decimal text half away from zero;
* Python's `round()` works on the exact binary value and rounds half to even.

They disagree exactly at `.xx5` boundaries (e.g. 114249.135 -> PG 114249.14,
Python 114249.13). Summing Python-rounded lines therefore produced a gross
amount up to 0.02 NOK different from SUM(order_lines.amount_currency) in the
database (445 orders in the 2026-10-30 snapshot).

Rules (docs/SPEC_poprawki_ksiegowe.md, phase 0.5a):

* An amount that already lives in the database is READ from the database, never
  recomputed in Python (payment amount and Dr 1500 use SUM(amount_currency)).
* `pg_round2` is used only where Python writes an amount for the first time and
  needs the value the database will end up holding.

Migrating the whole pipeline to Decimal is on the README backlog as a separate,
deliberate change of history (it would need a new golden hash).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def pg_round2(value: float) -> float:
    """float8 -> numeric(_, 2) exactly as Postgres does it."""
    return float(Decimal(format(value, ".15g")).quantize(_CENT, rounding=ROUND_HALF_UP))
