"""Recurring transaction rules: schedule math and auto-generation.

A rule fires whenever its `next_due_date` has arrived — checked once at the top of every
app load (see app.py). If the app wasn't opened for a while, every missed occurrence between
the old next_due_date and today is backfilled (e.g. two missed monthly insurance payments
both get logged), not just one.
"""
from __future__ import annotations

import calendar
import datetime as dt

import db

FREQUENCIES = ["weekly", "biweekly", "monthly", "yearly"]
FREQUENCY_LABELS = {
    "weekly": "Weekly", "biweekly": "Every 2 weeks", "monthly": "Monthly", "yearly": "Yearly",
}

_MAX_BACKFILL = 500  # sanity guard against a corrupted/ancient start_date looping forever


def next_occurrence(d: dt.date, frequency: str) -> dt.date:
    if frequency == "weekly":
        return d + dt.timedelta(days=7)
    if frequency == "biweekly":
        return d + dt.timedelta(days=14)
    if frequency == "monthly":
        year = d.year + (d.month // 12)
        month = d.month % 12 + 1
        last_day = calendar.monthrange(year, month)[1]
        return dt.date(year, month, min(d.day, last_day))
    if frequency == "yearly":
        try:
            return d.replace(year=d.year + 1)
        except ValueError:  # Feb 29 on a non-leap year
            return d.replace(year=d.year + 1, day=28)
    raise ValueError(f"Unknown frequency: {frequency}")


def generate_due_transactions(today: dt.date | None = None) -> int:
    """Create a transaction for every rule occurrence up through today. Returns count created."""
    today = today or dt.date.today()
    created = 0
    for rule in db.get_recurring_rules():
        if not rule["active"]:
            continue
        next_due = dt.date.fromisoformat(rule["next_due_date"])
        guard = 0
        while next_due <= today and guard < _MAX_BACKFILL:
            db.add_transaction(
                next_due.isoformat(), rule["type"], rule["category"], rule["description"] or "",
                rule["amount"], rule["goal_id"], recurring_id=rule["id"],
            )
            created += 1
            next_due = next_occurrence(next_due, rule["frequency"])
            guard += 1
        db.set_recurring_next_due(rule["id"], next_due.isoformat())
    return created
