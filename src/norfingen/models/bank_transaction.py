"""BankTransaction — ruchy gotówkowe na koncie bankowym (wpływy od klientów,
wypływy do dostawców/payroll). To NIE jest encja Tripletex API v2 (brak takiego
endpointu) — model wewnętrzny do śledzenia faktycznych przepływów pieniężnych
i uzgadniania ich z Order/SupplierInvoice/SalaryTransaction, stąd snake_case
(zgodny z kolumnami db/schema.sql), nie camelCase jak w modelach Tripletex.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BankTransactionType(str, Enum):
    INCOMING = "INCOMING"  # klient płaci fakturę
    OUTGOING = "OUTGOING"  # firma płaci dostawcę lub payroll


class BankTransaction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    date: date  # data płatności
    amount: float  # kwota dodatnia
    transaction_type: BankTransactionType
    description: str
    customer_id: Optional[int] = None  # jeśli płatność od klienta
    supplier_id: Optional[int] = None  # jeśli płatność do dostawcy
    order_id: Optional[int] = None  # powiązana faktura sprzedaży
    supplier_invoice_id: Optional[int] = None  # powiązana faktura zakupu
    account_from: int  # konto źródłowe
    account_to: int  # konto docelowe
