"""SupplierInvoice — cost documents. POST /v2/supplierInvoice.

Unlike Order — the Voucher must be created explicitly by the generator.

Rule L05 (Sandvik IT Solutions): if amountExcludingVatCurrency >= 30,000 NOK
→ account 1200 (capitalized, fixed asset), otherwise → account 6540 (period expense).
See norfingen.seed.roster.SupplierSeed.capitalization_threshold/capitalization_account.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from norfingen.models.base import NOK_CURRENCY_REF, TripletexRef

PURCHASE_VAT_TYPE_REF = TripletexRef(id=1)  # vatCode "1" — input VAT 25%
PURCHASE_VAT_RATE = 0.25


class SupplierInvoiceStatus(str, Enum):
    UNPAID = "UNPAID"
    PAID = "PAID"


class SupplierInvoice(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    invoiceNumber: str
    supplier: TripletexRef
    invoiceDate: date
    receivedDate: Optional[date] = None
    paymentDueDate: Optional[date] = None
    amountCurrency: float  # amount incl. VAT
    currency: Optional[TripletexRef] = NOK_CURRENCY_REF
    account: Optional[TripletexRef] = None
    vatType: Optional[TripletexRef] = PURCHASE_VAT_TYPE_REF
    comment: Optional[str] = None
    voucher: Optional[TripletexRef] = None
    status: SupplierInvoiceStatus = SupplierInvoiceStatus.UNPAID
    url: Optional[str] = None

    @model_validator(mode="after")
    def _apply_defaults(self) -> "SupplierInvoice":
        if self.receivedDate is None:
            object.__setattr__(self, "receivedDate", self.invoiceDate)
        if self.paymentDueDate is None:
            object.__setattr__(self, "paymentDueDate", self.invoiceDate + timedelta(days=30))
        return self

    @computed_field  # type: ignore[misc]
    @property
    def vatAmountCurrency(self) -> float:
        return self.amountCurrency * (PURCHASE_VAT_RATE / (1 + PURCHASE_VAT_RATE))

    @computed_field  # type: ignore[misc]
    @property
    def amountExcludingVatCurrency(self) -> float:
        return self.amountCurrency - self.vatAmountCurrency
