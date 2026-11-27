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
    "orders": (1853, "06c17bcf956dd3d3"),
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
    "opex_net_amounts": (897, "c61acc2030452f32"),  # was (469, 07558a544853af26)
    "opex_amounts": (897, "835eabfee6f4c24f"),  # was (469, cd0b0cd25ef42c79) before the split
    "opex_vouchers": (897, "f21f3eeeb33f2036"),  # was (469, 9295494bec49bbe1) before the split
    # Round 2, point 3 (COGS split between several suppliers). Computed on the code BEFORE the split and never changed since:
    # the TOTAL net COGS per month and account (91 months x 2 accounts) and every operating-cost voucher that is not a COGS accrual.
    "cogs_month_net_totals": (182, "9dfd3138eb89540b"),
    "opex_non_cogs": (351, "3da016d63f4abef4"),
    # Round 4, step 3 (2026-11-25, decision D1) re-pinned on purpose, in one go: the COGS volume discount, the extra operating costs
    # (opex_extras: 6410 / 6700 / 7320 / 6600 cash purchases, 64 more vouchers), the usage variability of S01-S03 (orders, sales vouchers,
    # the S02 share of the Azure COGS), five hires and individual raises (salary, OTP, hours). What did NOT move: supplier_invoices and
    # depreciation_vouchers (the capitalised L05 invoices are unchanged) - the proof that the rest of the model is the same.
    # Round 4, step 2 (2026-11-25): the new structure, additive - no existing hash above moved. 93 payroll months of OTP (2 % of the
    # gross pay) and 92 monthly depreciation vouchers from the capitalised L05 invoices (60 months straight line, last working day).
    "otp_vouchers": (93, "e42f1cbaef8ec0fe"),
    "depreciation_vouchers": (92, "57968d02a477743f"),
    "cogs_payable_amounts": (546, "56405ec36d3544a3"),  # no dates; was (182, 5488bc97aba376c9) before the split
    # Phase 3: the sales voucher of every invoice (Dr 1500 / Cr 3000 / Cr 2700). Same count as the orders, and the
    # revenue it books equals the 209 030 662 of the regression rule (to the cent: the exact figure is 661.93).
    # (Pinned after pg_round2 was corrected to the psycopg2 literal path: the first value, 47c32992810ab004, had 137
    # gross amounts one cent off the stored ones. Revenue - the net side - was already right and did not move.)
    # Phase 4: one payable per COGS accrual (4291 / 4292): 182 over 91 months, due 30 days after the accrual. The opex /
    # salary / sales hashes above did not move: the payables are new, no existing amount changed.
    "cogs_payables": (546, "134ea2f9676c1dc9"),  # was (182, a9624a0e7f05d59e) before the split;  # gross since phase 2; dates: accrual at month end, due = last working day of the NEXT month (round 2, point 1; was 827a4e89c6a70989 with due +30 days). Amounts hash above is unchanged.
    "sales_vouchers": (1853, "857749653687aeb2"),
    "revenue_in_gl": 209_036_182.96,
    # With the phase-1 accounts mapped back to the old ones this is the hash frozen BEFORE phase 1 (see
    # golden_fingerprint.PHASE1_TO_LEGACY_ACCOUNTS): phase 1 renumbered accounts and changed nothing else.
    "salary_vouchers": (279, "3e8a7228948c20e2"),
    # The real phase-1 accounts: 2930 net pay / 2600 tax / 2770 AGA / 2940 feriepenger.
    "salary_vouchers_phase1_accounts": (279, "dc614f7511d4773a"),
    "hour_entries": (54513, "fb183225d5f67f3c"),
    "revenue_net": 209_036_183,
    "payroll_gross": 85_780_527,
}


@pytest.fixture(scope="module")
def fingerprint():
    return build(CUTOFF)


@pytest.mark.parametrize("component", list(GOLDEN))
def test_golden_component_unchanged(fingerprint, component):
    assert fingerprint[component] == GOLDEN[component]


def test_regression_revenue_and_payroll_up_to_2026_09_30(fingerprint):
    # Round 4, step 3 (2026-11-25, D1): re-pinned on purpose. Revenue +5 521 NOK (+0.003 %): the monthly usage variability is zero-sum
    # over a year, so the yearly revenue is what the price list says (it was 209 030 662). Payroll +4.36 mln (+5.3 %): the five hires of
    # 2024-26 and the individual raises (1-5 %, mean 3 %) instead of a flat 3 % (it was 81 422 455).
    assert fingerprint["revenue_net"] == 209_036_183
    assert fingerprint["payroll_gross"] == 85_780_527
    assert abs(fingerprint["revenue_in_gl"] - 209_036_183) < 0.5  # the ledger's revenue is the regression revenue
