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
    # Phase 5 moved operating costs off "the 1st of the month" onto realistic days. The hash is therefore split:
    #   opex_amounts          - descriptions + postings WITHOUT dates. 40e3213e20e9d7e9 was computed on the pre-phase-5 code
    #                           and MUST NOT change: not one amount moved, only the day.
    #   opex_vouchers         - the same with dates; re-pinned (was 892715817cd39468 with every entry on the 1st).
    # Audit 2026-11-16, phase 2 (VAT on COGS and on 4290): the vouchers gained a 2710 line and the 2400 / 1910 credit became
    # gross, so opex_amounts / opex_vouchers / cogs_payables are re-pinned. What MUST NOT move is the NET cost, and it did
    # not: opex_net_amounts (every debit except 2710) was computed on the pre-phase-2 code and is unchanged, as is
    # cogs_payable_amounts (now hashed on the net column).
    # Re-pinned in round 2, point 3 (COGS split over 3 suppliers per account: 91 months x 2 accounts x 3 = 546 accrual vouchers):
    # these five moved BY DESIGN; what must NOT move is pinned above them: cogs_month_net_totals and opex_non_cogs.
    "opex_net_amounts": (833, "0c3c238a905702a6"),  # was (469, 07558a544853af26)
    "opex_amounts": (833, "b2867fdeda21ab81"),  # was (469, cd0b0cd25ef42c79) before the split
    "opex_vouchers": (833, "3ea01fe15f6eb541"),  # was (469, 9295494bec49bbe1) before the split
    # Round 2, point 3 (COGS split between several suppliers). Computed on the code BEFORE the split and never changed since:
    # the TOTAL net COGS per month and account (91 months x 2 accounts) and every operating-cost voucher that is not a COGS accrual.
    "cogs_month_net_totals": (182, "61a6792a23427970"),
    "opex_non_cogs": (287, "6497c363a8d01072"),
    "cogs_payable_amounts": (546, "8bd8a746be0f615c"),  # no dates; was (182, 5488bc97aba376c9) before the split
    # Phase 3: the sales voucher of every invoice (Dr 1500 / Cr 3000 / Cr 2700). Same count as the orders, and the
    # revenue it books equals the 209 030 662 of the regression rule (to the cent: the exact figure is 661.93).
    # (Pinned after pg_round2 was corrected to the psycopg2 literal path: the first value, 47c32992810ab004, had 137
    # gross amounts one cent off the stored ones. Revenue - the net side - was already right and did not move.)
    # Phase 4: one payable per COGS accrual (4291 / 4292): 182 over 91 months, due 30 days after the accrual. The opex /
    # salary / sales hashes above did not move: the payables are new, no existing amount changed.
    "cogs_payables": (546, "c2b96a332a701375"),  # was (182, a9624a0e7f05d59e) before the split;  # gross since phase 2; dates: accrual at month end, due = last working day of the NEXT month (round 2, point 1; was 827a4e89c6a70989 with due +30 days). Amounts hash above is unchanged.
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
