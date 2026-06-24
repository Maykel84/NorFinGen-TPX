"""Supplier — kontrahent po stronie kosztów. POST /v2/supplier."""

from __future__ import annotations

from typing import Optional

from norfingen.models.base import CompanyBase


class Supplier(CompanyBase):
    supplierNumber: Optional[str] = None
    bankAccountNumber: Optional[str] = None
    isWholesaler: bool = False
    showProducts: bool = False
    url: Optional[str] = None
