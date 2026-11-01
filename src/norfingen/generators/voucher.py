"""Voucher + Posting — the ledger's backbone (Layer 3).

POST /v2/ledger/voucher · POST /v2/ledger/posting

Sign of Posting.amount: + = debit, - = credit. The sum of amount across all
postings in a Voucher must equal 0 - strictly, to the cent (BALANCE_TOLERANCE).

VAT is a separate posting (phase 2, docs/SPEC_poprawki_ksiegowe.md), as in real
Tripletex, where VAT lines are generated from the VAT code of a posting: input
VAT on a purchase invoice is its own Dr 2710 line, output VAT on a sales
invoice its own Cr 2700 line (phase 3). Posting.vatType / vatAmount stay on the
cost or revenue line as information about the VAT it contains; they are NOT
part of the balance - the VAT line is. Before phase 2 the VAT was only that
vatAmount field, the voucher did not balance by exactly its VAT, and
validate_balance() excused the gap - which left the whole ledger out of balance
by the sum of the input VAT (3.7 mln NOK).

See docs/norfingen_warstwa3_schemas.html — 7 DR/CR patterns (W1-W7) and
validation rules.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from norfingen.models.base import TripletexRef

PURCHASE_AND_SALES_VAT_RATE = 0.25  # the only rate used in NorFinGen (vatCode "1" and "3")

# A voucher balances when its postings sum to zero at the cent. Amounts are rounded to 2 decimals before
# they are posted, so the only slack left is float noise (~1e-11): half a cent is far above it and
# far below any real imbalance.
BALANCE_TOLERANCE = 0.005


class VoucherType(str, Enum):
    OUTGOING_INVOICE = "OUTGOING_INVOICE"  # a sales invoice (Order) — booked by the generator from phase 3: Dr 1500 / Cr 3000 / Cr 2700
    INCOMING_INVOICE = "INCOMING_INVOICE"  # a SupplierInvoice — created explicitly by the generator
    SALARY = "SALARY"  # SalaryTransaction + feriepenger — created explicitly by the generator
    BANK = "BANK"  # bank payments — Tier 4
    MANUAL = "MANUAL"  # founding capital, corrections — backfill
    OPERATING_COST = "OPERATING_COST"  # Phase 3 — canteen/representation/transport/implementation equipment: a cash cost with no separate source document (not a SupplierInvoice)


class AccountRef(BaseModel):
    """Reference to a GL account on a Posting — Tripletex addresses accounts by number."""

    model_config = ConfigDict(populate_by_name=True)

    number: int
    id: Optional[int] = None


def acct(number: int) -> AccountRef:
    return AccountRef(number=number)


def expected_vat_amount(amount_excluding_vat: float, vat_rate: float = PURCHASE_AND_SALES_VAT_RATE) -> float:
    """The generator computes VAT from the net amount — round(net x rate, 2), never the reverse from gross."""
    return round(amount_excluding_vat * vat_rate, 2)


class Posting(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    voucher: Optional[TripletexRef] = None
    date: date
    description: Optional[str] = None
    account: AccountRef
    amount: float  # + debit / - credit
    currency: str = "NOK"
    vatType: Optional[TripletexRef] = None
    vatAmount: Optional[float] = None  # the VAT contained in this line (information); the VAT itself is its own posting
    customer: Optional[TripletexRef] = None  # required for account 1500 (AR aging)
    supplier: Optional[TripletexRef] = None  # required for account 2400 (AP aging)
    employee: Optional[TripletexRef] = None  # employee card for payroll liabilities 2930/2600 (not populated today)
    department: Optional[TripletexRef] = None  # for accounts 5000/5400/3000/3100 (departmental reports)
    url: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def amountCurrency(self) -> float:
        return self.amount

    @computed_field  # type: ignore[misc]
    @property
    def vatAmountCurrency(self) -> Optional[float]:
        return self.vatAmount


class Voucher(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    date: date
    description: Optional[str] = None
    voucherType: VoucherType
    postings: list[Posting] = []
    url: Optional[str] = None

    def validate_balance(self, tolerance: float = BALANCE_TOLERANCE) -> bool:
        """The postings sum to zero, to the cent. VAT is a posting like any
        other (Dr 2710 on a purchase, Cr 2700 on a sale), so there is no
        'difference must equal the VAT' exception any more: vatAmount is
        information, not a balancing term."""
        return abs(sum(p.amount for p in self.postings)) <= tolerance


def assert_voucher_valid(voucher: Voucher) -> None:
    """Validation rules called before every Voucher save: at least two
    postings, every posting has a GL account, and the voucher balances to the
    cent (the VAT line included - see the module docstring)."""
    assert len(voucher.postings) >= 2, "A Voucher requires at least 2 postings"
    assert all(p.account is not None for p in voucher.postings), "Missing GL account on a posting"
    assert voucher.validate_balance(), f"Unbalanced Voucher: {sum(p.amount for p in voucher.postings):.4f}"
