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
    MATERNITY_LEAVE = "MATERNITY_LEAVE"  # foreldrepermisjon, primary-caregiver leave (~30-49 weeks)
    PATERNITY_LEAVE = "PATERNITY_LEAVE"  # foreldrepermisjon, secondary-caregiver/"fedrekvote" leave (~10-15 weeks)


class HourEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    date: date
    employee_id: int
    project_id: Optional[int] = None  # None for INTERNAL/SICK
    activity_type: ActivityType
    hours: float  # 0.5 - 7.5
    description: Optional[str] = None
