"""Order + OrderLine — dokumenty sprzedaży.

POST /v2/order · POST /v2/order/orderline

Wypełniony invoiceDate wyzwala automatyczne utworzenie Vouchera przez Tripletex —
generator NIE tworzy Vouchera sprzedaży ręcznie (w przeciwieństwie do SupplierInvoice).
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from norfingen.models.base import NOK_CURRENCY_REF, TripletexRef
from norfingen.models.product import SALES_VAT_TYPE_REF

SALES_VAT_RATE = 0.25  # vatCode "3" — jedyna stawka używana w OrderLine


class InvoicesDueInType(str, Enum):
    DAYS = "DAYS"


class OrderLine(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    order: Optional[TripletexRef] = None  # None gdy linia zagnieżdżona w Order.orderLines (id rodzica jeszcze nieznane)
    product: Optional[TripletexRef] = None
    count: float = 1.0
    unitPriceExcludingVatCurrency: float = 0.0
    vatType: Optional[TripletexRef] = SALES_VAT_TYPE_REF
    discount: float = 0.0  # fraction 0.0-1.0
    url: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def amountExcludingVatCurrency(self) -> float:
        return self.count * self.unitPriceExcludingVatCurrency * (1 - self.discount)

    @computed_field  # type: ignore[misc]
    @property
    def amountCurrency(self) -> float:
        return self.amountExcludingVatCurrency * (1 + SALES_VAT_RATE)


class Order(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    customer: TripletexRef
    orderDate: date
    deliveryDate: Optional[date] = None
    invoiceDate: Optional[date] = None
    invoicesDueIn: int = 30
    invoicesDueInType: InvoicesDueInType = InvoicesDueInType.DAYS
    orderLines: list[OrderLine] = []
    department: Optional[TripletexRef] = None
    currency: Optional[TripletexRef] = NOK_CURRENCY_REF
    isPrioritizeVat: bool = False
    comment: Optional[str] = None
    ourContact: Optional[TripletexRef] = None
    url: Optional[str] = None
