"""BankTransaction — cash movements on the bank account (inflows from
customers, outflows to suppliers/payroll). This is NOT a Tripletex API v2
entity (no such endpoint) — an internal model for tracking actual cash flows
and reconciling them against Order/SupplierInvoice/SalaryTransaction, hence
snake_case (matching db/schema.sql columns), not camelCase like the
Tripletex-mirroring models.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BankTransactionType(str, Enum):
    INCOMING = "INCOMING"  # customer pays an invoice
    OUTGOING = "OUTGOING"  # company pays a supplier or payroll


class BankTransaction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    date: date  # payment date
    amount: float  # positive amount
    transaction_type: BankTransactionType
    description: str
    customer_id: Optional[int] = None  # set if payment from a customer
    supplier_id: Optional[int] = None  # set if payment to a supplier
    order_id: Optional[int] = None  # linked sales invoice
    supplier_invoice_id: Optional[int] = None  # linked purchase invoice
    salary_transaction_id: Optional[int] = None  # linked payroll run (Step 2, payroll OUTGOING fix)
    account_from: int  # source account
    account_to: int  # destination account
