"""Wspólne typy pomocnicze odwzorowujące konwencje Tripletex API v2."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class TripletexRef(BaseModel):
    """Referencja do innej encji w stylu Tripletex: {id, url}."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    url: Optional[str] = None


class Address(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    addressLine1: Optional[str] = None
    postalCode: Optional[str] = None
    city: Optional[str] = None
    country: Optional[TripletexRef] = None


NORWAY_COUNTRY_REF = TripletexRef(id=161)
NOK_CURRENCY_REF = TripletexRef(id=1)


class CompanyBase(BaseModel):
    """Pola wspólne dla Customer i Supplier (~75% wg dokumentacji Warstwy 1)."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    name: str
    organizationNumber: Optional[str] = None
    email: Optional[str] = None
    phoneNumber: Optional[str] = None
    isPrivateIndividual: bool = False
    address: Optional[Address] = None
    currency: Optional[TripletexRef] = NOK_CURRENCY_REF
    isInactive: bool = False
