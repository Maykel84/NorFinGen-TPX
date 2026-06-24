"""Employee + Employment — zależy od Department.

Dwa wywołania API na pracownika:
  POST /v2/employee
  POST /v2/employee/{id}/employment
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict

from norfingen.models.base import TripletexRef


class EmploymentType(str, Enum):
    ORDINARY = "ORDINARY"


class RemunerationType(str, Enum):
    FIXED_SALARY = "FIXED_SALARY"


class PayrollTaxZone(str, Enum):
    ZONE_1 = "ZONE_1"  # Oslo, 14,1%


class Employee(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    firstName: str
    lastName: str
    employeeNumber: Optional[str] = None
    email: Optional[str] = None
    department: Optional[TripletexRef] = None
    bankAccountNumber: Optional[str] = None
    nationalIdentityNumber: Optional[str] = None
    dateOfBirth: Optional[date] = None
    allowInformationRegistration: bool = True
    url: Optional[str] = None


class Employment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    startDate: date
    endDate: Optional[date] = None
    employmentType: EmploymentType = EmploymentType.ORDINARY
    remunerationType: RemunerationType = RemunerationType.FIXED_SALARY
    weeklyWorkingHours: float = 37.5
    percentage: float = 100.0
    payrollTaxZone: PayrollTaxZone = PayrollTaxZone.ZONE_1
