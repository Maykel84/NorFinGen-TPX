"""SalaryTransaction + Payslip + SalarySpecification — monthly payroll run.

POST /v2/salaryV2/transaction · POST /v2/salaryV2/payslip

One SalaryTransaction per month, one Payslip per employee. The generator
creates Vouchers explicitly — two separate ones: payroll (5000/2710/2740) +
employer's social security contribution/AGA (5400/2700). June has a different
pattern (see norfingen.seed.payroll): wage type 920 is absent, wage type 260
(feriepenger/holiday pay) is calculated from the previous year's gross pay.
"""

import datetime
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from norfingen.models.base import TripletexRef

WAGE_TYPE_FAST_LONN = TripletexRef(id=100)  # Fast lønn (base salary) — months 1-12
WAGE_TYPE_SKATTETREKK = TripletexRef(id=920)  # Skattetrekk (tax withholding) — months 1-5, 7-12
WAGE_TYPE_FERIEPENGER = TripletexRef(id=260)  # Feriepenger (holiday pay) — June only


class SalaryTransactionStatus(str, Enum):
    OPEN = "OPEN"
    PROCESSED = "PROCESSED"


class SalarySpecification(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    wageType: TripletexRef
    description: str
    amount: float  # negative for deductions (e.g. skattetrekk)


class Payslip(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    transaction: Optional[TripletexRef] = None  # None when nested in SalaryTransaction.payslips
    employee: TripletexRef
    # Optional[datetime.date] (not "date") — a field named "date" shadows the bare
    # "date" import in the class's local namespace when evaluating default=None (a pydantic/Python gotcha).
    date: Optional[datetime.date] = None
    specifications: list[SalarySpecification] = []
    url: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def amount(self) -> float:
        return sum(spec.amount for spec in self.specifications)


class SalaryTransaction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    date: date
    year: int
    month: int
    status: SalaryTransactionStatus = SalaryTransactionStatus.OPEN
    payslips: list[Payslip] = []
    url: Optional[str] = None
