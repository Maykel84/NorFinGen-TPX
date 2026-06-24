"""Customer — kontrahent po stronie przychodów. POST /v2/customer."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from norfingen.models.base import CompanyBase, TripletexRef

NET_30_PAYMENT_TERMS_REF = TripletexRef(id=2)


class InvoicesDueInType(str, Enum):
    DAYS = "DAYS"


class Customer(CompanyBase):
    customerNumber: Optional[str] = None
    paymentTerms: Optional[TripletexRef] = NET_30_PAYMENT_TERMS_REF
    invoicesDueIn: int = 30
    invoicesDueInType: InvoicesDueInType = InvoicesDueInType.DAYS
    url: Optional[str] = None
