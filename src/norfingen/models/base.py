"""Common helper types mirroring Tripletex API v2 conventions."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class TripletexRef(BaseModel):
    """Reference to another entity, Tripletex-style: {id, url}."""

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
    """Fields shared by Customer and Supplier (~75% per the Layer 1 docs)."""

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
