"""HourEntry — dzienne wpisy godzin pracowników (timesheet). To NIE jest encja
Tripletex API v2 — model wewnętrzny do śledzenia wykorzystania czasu (fakturowalne
vs wewnętrzne vs chorobowe), stąd snake_case (zgodny z db/schema.sql), nie
camelCase jak w modelach Tripletex. Zob. też models/bank_transaction.py.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ActivityType(str, Enum):
    BILLABLE = "BILLABLE"  # fakturowalne — przypisane do projektu klienta
    INTERNAL = "INTERNAL"  # wewnętrzne — spotkania, admin
    SICK = "SICK"  # chorobowe


class HourEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    date: date
    employee_id: int
    project_id: Optional[int] = None  # None dla INTERNAL/SICK
    activity_type: ActivityType
    hours: float  # 0.5 – 7.5
    description: Optional[str] = None
