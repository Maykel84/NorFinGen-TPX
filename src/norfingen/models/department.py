"""Department — encja bazowa, prerekvizyt dla Employee. POST /v2/department."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class Department(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    name: str
    number: Optional[str] = None
    isInactive: bool = False
    url: Optional[str] = None
