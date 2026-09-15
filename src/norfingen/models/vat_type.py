"""VatType — MVA (VAT) codes. Read-only: GET /v2/ledger/vatType.

Note: vatCode "0" means no VAT at all (a posting without a vatAmount field),
not a zero rate — that's different from vatCode "6" (vatAmount = 0, exempt/export).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class VatType(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    name: str
    number: Optional[str] = None
    percentage: float
    vatCode: str
    url: Optional[str] = None
