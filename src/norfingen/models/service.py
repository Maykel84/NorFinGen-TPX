"""Service — katalog usług firmy (Faza 1). To NIE jest encja Tripletex API v2
(brak takiego endpointu) — model wewnętrzny opisujący ofertę produktową
niezależnie od konkretnych cen per klient (te ustala roster.CustomerSeed /
CUSTOMER_PRICE_MULTIPLIER), stąd snake_case, nie camelCase jak w modelach
Tripletex. Zob. też models/bank_transaction.py, models/hours.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ServiceSegmentAvailability(str, Enum):
    ALL = "ALL"
    ENTERPRISE_MID = "ENTERPRISE_MID"
    ENTERPRISE_ONLY = "ENTERPRISE_ONLY"


class BillingModel(str, Enum):
    SUBSCRIPTION = "SUBSCRIPTION"
    HOURLY = "HOURLY"


class Service(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str  # "S01"-"S04"
    name: str
    description: str
    billing_model: BillingModel
    availability: ServiceSegmentAvailability
    base_price_enterprise: Optional[float] = None  # NOK/mies. lub NOK/h
    base_price_mid: Optional[float] = None
    base_price_smb: Optional[float] = None
