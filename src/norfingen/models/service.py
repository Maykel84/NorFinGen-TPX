"""Service — the company's service catalog (Phase 1). This is NOT a Tripletex
API v2 entity (no such endpoint) — an internal model describing the product
offering independently of per-customer pricing (that's set by
roster.CustomerSeed / CUSTOMER_PRICE_MULTIPLIER), hence snake_case, not
camelCase like the Tripletex-mirroring models. See also
models/bank_transaction.py, models/hours.py.
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
    base_price_enterprise: Optional[float] = None  # NOK/month or NOK/hour
    base_price_mid: Optional[float] = None
    base_price_smb: Optional[float] = None
