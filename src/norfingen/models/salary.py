"""SalaryTransaction + Payslip + SalarySpecification — miesięczna lista płac.

POST /v2/salaryV2/transaction · POST /v2/salaryV2/payslip

Jeden SalaryTransaction na miesiąc, jeden Payslip na pracownika. Generator tworzy
Vouchery jawnie — dwa osobne: lista płac (5000/2710/2740) + AGA (5400/2700).
Czerwiec ma odmienny pattern (zob. norfingen.seed.payroll): kod 920 nieobecny,
kod 260 (Feriepenger) liczony od brutto roku poprzedniego.
"""

import datetime
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from norfingen.models.base import TripletexRef

WAGE_TYPE_FAST_LONN = TripletexRef(id=100)  # Fast lønn — miesiące 1-12
WAGE_TYPE_SKATTETREKK = TripletexRef(id=920)  # Skattetrekk — miesiące 1-5, 7-12
WAGE_TYPE_FERIEPENGER = TripletexRef(id=260)  # Feriepenger — tylko czerwiec


class SalaryTransactionStatus(str, Enum):
    OPEN = "OPEN"
    PROCESSED = "PROCESSED"


class SalarySpecification(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    wageType: TripletexRef
    description: str
    amount: float  # ujemne dla potrąceń (np. skattetrekk)


class Payslip(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    transaction: Optional[TripletexRef] = None  # None gdy zagnieżdżony w SalaryTransaction.payslips
    employee: TripletexRef
    # Optional[datetime.date] (nie "date") — pole nazwane "date" przesłania bare import
    # "date" w lokalnym namespace klasy przy ewaluacji default=None (gotcha pydantic/Python).
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
