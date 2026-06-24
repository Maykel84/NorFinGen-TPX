"""Account (GL) — plan kont NS 4102. Tylko do odczytu: GET /v2/ledger/account."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict

from norfingen.models.base import TripletexRef


class AccountType(str, Enum):
    ASSETS = "ASSETS"
    EQUITY_AND_LIABILITY = "EQUITY_AND_LIABILITY"
    OPERATING_INCOME = "OPERATING_INCOME"
    OPERATING_EXPENSE = "OPERATING_EXPENSE"


class Account(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    number: int
    name: str
    type: Optional[AccountType] = None
    vatType: Optional[TripletexRef] = None
    url: Optional[str] = None
