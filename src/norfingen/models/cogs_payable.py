"""CogsPayable - a liability for a COGS pass-through cost (accounts 4291 / 4292), phase 4.

Why this exists. The monthly COGS cost (Microsoft/Azure resale, RMM/EDR tools) is booked as an accrual voucher
Dr 4291|4292 / Cr 2400 Leverandørgjeld, but - unlike a purchase invoice - there is no SupplierInvoice behind it. Left
like that the liability could never be paid: 88 mln NOK sat on 2400 for good (gl_checks T8). A CogsPayable is the missing
document: one row per accrual with a due date, an amount and a status, paid like a purchase invoice (Dr 2400 / Cr 1910 on
the due date moved to the next working day) and flipped to PAID by the payment itself.

It is an internal model, not a Tripletex entity (no such endpoint), hence snake_case like BankTransaction. Giving COGS real
SupplierInvoices instead (variant A) is on the README backlog.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CogsPayableStatus(str, Enum):
    UNPAID = "UNPAID"
    PAID = "PAID"


class CogsPayable(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    accrual_date: date  # the accrual voucher's date
    payment_due_date: date  # accrual_date + COGS_PAYMENT_TERMS_DAYS
    account_number: int  # 4291 | 4292 - the cost account that was debited
    supplier_id: int  # L01 for 4291, L09 for 4292 (roster.COGS_SUPPLIER_BY_ACCOUNT)
    description: str  # the accrual voucher's description
    amount_currency: float  # NOK, gross - COGS is booked without VAT, so net == gross
    status: CogsPayableStatus = CogsPayableStatus.UNPAID
