"""Golden hash of the generated history up to 2026-09-30 (docs/SPEC_poprawki_ksiegowe.md, phase 0.5).

Frozen BEFORE any change to the pipeline and re-run after every step. Pins two
things at once:

* determinism - the same value under any PYTHONHASHSEED / call order;
* the regression rule agreed for the accounting fixes: up to 2026-09-30 nothing
  changes - revenue 209 030 662 NOK, payroll gross 81 422 455 NOK, same invoices to the grosz.

If this test fails after a refactor, a drawn value moved. Do NOT just paste the
new hashes: find the reordered/split generator call. Only a deliberate change of
history (e.g. the Decimal-end-to-end migration in the README backlog) justifies a new version
of these constants, and then in its own commit.

Amounts are the generators' in-memory values (Python rounding), not the values
read back from Postgres - the two differ by <= 0.02 NOK per order, see the
pg_round2 notes in docs/SPEC_poprawki_ksiegowe.md.
"""

import pytest

from tests.golden_fingerprint import CUTOFF, build

GOLDEN = {
    "orders": (1853, "62f1f25e5f6fdb88"),
    "supplier_invoices": (745, "4a571fa9fea764a7"),
    "opex_vouchers": (469, "892715817cd39468"),
    # Phase 3: the sales voucher of every invoice (Dr 1500 / Cr 3000 / Cr 2700). Same count as the orders, and the
    # revenue it books equals the 209 030 662 of the regression rule (to the cent: the exact figure is 661.93).
    # (Pinned after pg_round2 was corrected to the psycopg2 literal path: the first value, 47c32992810ab004, had 137
    # gross amounts one cent off the stored ones. Revenue - the net side - was already right and did not move.)
    "sales_vouchers": (1853, "d87b271c20eb9788"),
    "revenue_in_gl": 209_030_661.93,
    # With the phase-1 accounts mapped back to the old ones this is the hash frozen BEFORE phase 1 (see
    # golden_fingerprint.PHASE1_TO_LEGACY_ACCOUNTS): phase 1 renumbered accounts and changed nothing else.
    "salary_vouchers": (279, "ea2df287fc8f69c1"),
    # The real phase-1 accounts: 2930 net pay / 2600 tax / 2770 AGA / 2940 feriepenger.
    "salary_vouchers_phase1_accounts": (279, "5041bde7f3f0b4cd"),
    "hour_entries": (51444, "be85fd57c76cdb56"),
    "revenue_net": 209_030_662,
    "payroll_gross": 81_422_455,
}


@pytest.fixture(scope="module")
def fingerprint():
    return build(CUTOFF)


@pytest.mark.parametrize("component", list(GOLDEN))
def test_golden_component_unchanged(fingerprint, component):
    assert fingerprint[component] == GOLDEN[component]


def test_regression_revenue_and_payroll_up_to_2026_09_30(fingerprint):
    assert fingerprint["revenue_net"] == 209_030_662
    assert fingerprint["payroll_gross"] == 81_422_455
    assert abs(fingerprint["revenue_in_gl"] - 209_030_662) < 0.5  # the ledger's revenue is the regression revenue
