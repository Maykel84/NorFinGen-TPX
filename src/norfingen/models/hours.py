"""HourEntry — daily employee timesheet entries. This is NOT a Tripletex
API v2 entity — an internal model for tracking time usage (billable vs
internal vs sick leave), hence snake_case (matching db/schema.sql), not
camelCase like the Tripletex-mirroring models. See also models/bank_transaction.py.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ActivityType(str, Enum):
    BILLABLE = "BILLABLE"  # billable — assigned to a customer project
    INTERNAL = "INTERNAL"  # internal — meetings, admin
    SICK = "SICK"  # sick leave — both short self-certified days (hours_generator's
    # daily coin flip) and longer certified blocks (see generators/leave_events.py)
    VACATION = "VACATION"  # ferie — the statutory 25 days/year (see generators/vacation.py). NOT paid via
    # ordinary salary — covered by feriepenger (already modeled independently as the June salary swap,
    # see seed/payroll.py::calc_june_salary — unrelated to which calendar days are marked VACATION here)
    PARENTAL_LEAVE = "PARENTAL_LEAVE"  # foreldrepermisjon, up to 52 weeks total per event — a primary block
    # (20-39 weeks) at one employee plus a ~3-month "fedrekvote" block at a different employee, see leave_events.py
    WELFARE_LEAVE = "WELFARE_LEAVE"  # velferdspermisjon — short, occasional (1-3 days)
    FLEX_LEAVE = "FLEX_LEAVE"  # dager til avspasering — 12/year, taken in blocks of up to 3 days with a
    # mandatory 16-day gap between blocks (see generators/flex_leave.py)
    CHILD_CARE_LEAVE = "CHILD_CARE_LEAVE"  # omsorgsdager (sykt barn) — 10/year, paid child-sick-care days


class HourEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    date: date
    employee_id: int
    project_id: Optional[int] = None  # None for anything but BILLABLE
    activity_type: ActivityType
    hours: float  # 0.5 - 7.5
    description: Optional[str] = None
