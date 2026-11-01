"""Rounding that matches what Postgres STORES when the pipeline writes a float.

The generators compute amounts as Python floats and psycopg2 writes them into numeric(14,2) columns. How a float
becomes a stored cent is not Python's `round(x, 2)`, and it is not Postgres' `float8::numeric` cast either:

* psycopg2 adapts a float to an SQL *numeric literal* made of `repr(x)` - the shortest string that round-trips, up to
  17 significant digits (`52733.024999999994`);
* Postgres reads that literal as the exact decimal it spells and rounds it to 2 places half away from zero
  (`52733.02`, because 0.024999999994 < 0.025);
* Python's `round()` works on the exact binary value and rounds half to even (`round(114249.135, 2)` -> 114249.13, the
  literal 114249.135 -> 114249.14);
* the `float8 -> numeric` CAST (not the write path!) goes through 15 significant digits and would say 52733.03.

`pg_round2` is the literal path: `Decimal(repr(x))` rounded half-up. tests/test_money_pg_round.py checks it against a real
Postgres through the very same psycopg2 insert, on >= 10 000 values including every .xx5 boundary and the doubles on
either side of it. (In phase 0.5a this module emulated the cast path instead and was validated against the cast - 18 050
values agreed - so it passed while 137 order lines, 1.37 NOK in all, were stored differently from what it predicted.
It showed up in phase 3 as the receivable 1500 missing the unpaid invoices by exactly that amount.)

Rules (docs/SPEC_poprawki_ksiegowe.md):

* An amount that already lives in the database is READ from the database, never recomputed in Python (the payment amount
  and Dr 1500 for a stored Order use SUM(order_lines.amount_currency)).
* `pg_round2` is used only where Python writes an amount for the first time and needs the value the database will end up
  holding - e.g. the sales voucher, which is built from the fresh Order before its lines are stored.

Migrating the whole pipeline to Decimal is on the README backlog as a separate, deliberate change of history (it would
need a new golden hash).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def pg_round2(value: float) -> float:
    """The cent Postgres stores when psycopg2 writes `value` into a numeric(_, 2) column."""
    return float(Decimal(repr(float(value))).quantize(_CENT, rounding=ROUND_HALF_UP))
