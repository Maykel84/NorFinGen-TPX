"""Working-day calendar shared by the generators.

A working day is Monday-Friday. Norwegian public holidays (17 May, Easter,
Christmas, ...) are deliberately NOT modelled - a known simplification kept on
the README backlog ("holidays as days without bank payments"). Keeping this in
one place matters now that payments are shifted to the next working day.
"""

from __future__ import annotations

from datetime import date, timedelta


def is_working_day(d: date) -> bool:
    """Mon-Fri, without Norwegian holidays (simplified)."""
    return d.weekday() < 5


def next_working_day(d: date) -> date:
    """`d` itself if it is a working day, otherwise the following Monday.

    Used for events that the bank books on business days only: customer
    payments and supplier payments. Invoices are NOT shifted - they keep
    their own date, weekends included.
    """
    while not is_working_day(d):
        d += timedelta(days=1)
    return d
