"""Product — prerekvizyt dla OrderLine. POST /v2/product."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from norfingen.models.base import NOK_CURRENCY_REF, TripletexRef

SALES_VAT_TYPE_REF = TripletexRef(id=3)  # vatCode "3" — 25%, sprzedaż


class Product(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    name: str
    number: Optional[str] = None
    description: Optional[str] = None
    salesPrice: Optional[float] = None
    vatType: Optional[TripletexRef] = SALES_VAT_TYPE_REF
    currency: Optional[TripletexRef] = NOK_CURRENCY_REF
    isInactive: bool = False
    url: Optional[str] = None
