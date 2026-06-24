"""VatType — kody MVA. Tylko do odczytu: GET /v2/ledger/vatType.

Uwaga: vatCode "0" oznacza brak VAT w ogóle (posting bez pola vatAmount),
nie zerową stawkę — to różni się od vatCode "6" (vatAmount = 0, zwolnione/eksport).
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
