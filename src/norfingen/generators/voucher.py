"""Voucher + Posting — the ledger's backbone (Layer 3).

POST /v2/ledger/voucher · POST /v2/ledger/posting

Sign of Posting.amount: + = debit, - = credit. The sum of amount across all
postings in a Voucher must equal 0. VAT is not a separate posting — it's the
vatAmount field on the debit posting (account 2770 is fed by Tripletex
automatically).

See docs/norfingen_warstwa3_schemas.html — 7 DR/CR patterns (W1-W7) and
validation rules.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from norfingen.models.base import TripletexRef

PURCHASE_AND_SALES_VAT_RATE = 0.25  # the only rate used in NorFinGen (vatCode "1" and "3")


class VoucherType(str, Enum):
    INVOICE = "INVOICE"  # an Order with invoiceDate — created automatically by Tripletex
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
    vatAmount: Optional[float] = None  # only on the DR posting — embedded, not a separate posting
    customer: Optional[TripletexRef] = None  # required for account 1500 (AR aging)
    supplier: Optional[TripletexRef] = None  # required for account 2400 (AP aging)
    employee: Optional[TripletexRef] = None  # required for accounts 2710/2740 (employee card)
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

    def validate_balance(self, tolerance: float = 0.02) -> bool:
        """A Voucher without VAT: the sum of amount must be ~0. A Voucher
        with VAT (e.g. INCOMING_INVOICE: DR excl. VAT vs CR incl. VAT):
        Tripletex automatically adds a third leg to account 2770 computed
        from the vatAmount field (the generator does NOT create this
        posting manually — see docs/norfingen_warstwa3_schemas.html,
        "VAT rule" section). So the difference |sum of amount| must equal
        |sum of vatAmount|, not a literal zero. The default tolerance of
        0.02 NOK covers rounding on net/gross/VAT conversions (the W3
        documentation itself allows ±1 NOK for vatAmount agreement)."""
        total = sum(p.amount for p in self.postings)
        vat_total = sum(p.vatAmount or 0.0 for p in self.postings)
        return abs(abs(total) - abs(vat_total)) <= tolerance


def assert_voucher_valid(voucher: Voucher) -> None:
    """Validation rules 1-3 from docs/norfingen_warstwa3_schemas.html, called
    before every Voucher save. Rule #4 (vatAmount agreement) is enforced by
    the generators at the point of computation (expected_vat_amount),
    because that's where the actual excl.-VAT amount is known — it can't be
    reliably reconstructed from the sign of Posting.amount alone (sales =
    incl. VAT, purchases = excl. VAT)."""
    assert len(voucher.postings) >= 2, "A Voucher requires at least 2 postings"
    assert all(p.account is not None for p in voucher.postings), "Missing GL account on a posting"
    assert voucher.validate_balance(), "Unbalanced Voucher"
