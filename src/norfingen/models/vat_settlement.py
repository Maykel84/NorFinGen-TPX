"""VatSettlement - one bi-monthly VAT return (mva-oppgjør) and what became of it, phase 5.

Norwegian VAT is settled in six two-month terms (jan-feb, mar-apr, ..., nov-dec). On the LAST DAY of a term the balances
of 2700 (output VAT) and 2710 (input VAT) are moved to the settlement account 2740; the difference is paid to (or
refunded by) the tax authority on the due date of that term. This row is the document behind that voucher: the term, the
two VAT totals, the balance, the planned payment date and a status - paid like any other liability, by a bank
transaction that links back here (bank_transactions.vat_settlement_id).

Internal model, not a Tripletex entity (no such endpoint), snake_case like BankTransaction and CogsPayable.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class VatSettlementStatus(str, Enum):
    UNPAID = "UNPAID"  # settled on the last day of the term, not yet paid / refunded
    PAID = "PAID"  # paid (or refunded) by a booked bank transaction; also a term whose balance is exactly 0


class VatSettlement(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    period_year: int
    term: int  # 1..6
    period_start: date
    period_end: date  # the day the balances are moved to 2740
    payment_date: date  # the due date, moved to the next working day
    output_vat: float  # credit turnover of 2700 in the term, positive
    input_vat: float  # debit turnover of 2710 in the term, positive
    balance: float  # output - input: > 0 to pay, < 0 refund
    status: VatSettlementStatus = VatSettlementStatus.UNPAID
