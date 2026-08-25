"""Recurring transaction rules: schedule math and auto-generation.

A rule fires whenever its `next_due_date` has arrived — checked once at the top of every
app load (see app.py). If the app wasn't opened for a while, every missed occurrence between
the old next_due_date and today is backfilled (e.g. two missed monthly insurance payments
both get logged), not just one.

Schedules are fully custom: "every N days/weeks/months" (frequency_interval + frequency_unit),
not limited to a fixed set of presets.
"""
from __future__ import annotations

import calendar
import datetime as dt

import db

FREQUENCY_UNITS = ["day", "week", "month"]
FREQUENCY_UNIT_LABELS = {"day": "Days", "week": "Weeks", "month": "Months"}

_MAX_BACKFILL = 500  # sanity guard against a corrupted/ancient start_date looping forever


def frequency_label(interval: int, unit: str) -> str:
    """(1, 'week') -> 'Every week'; (2, 'week') -> 'Every 2 weeks'; (31, 'day') -> 'Every 31 days'."""
    if interval == 1:
        return f"Every {unit}"
    return f"Every {interval} {unit}s"


def next_occurrence(d: dt.date, interval: int, unit: str) -> dt.date:
    if unit == "day":
        return d + dt.timedelta(days=interval)
    if unit == "week":
        return d + dt.timedelta(weeks=interval)
    if unit == "month":
        total_months = d.year * 12 + (d.month - 1) + interval
        year, month0 = divmod(total_months, 12)
        month = month0 + 1
        last_day = calendar.monthrange(year, month)[1]
        return dt.date(year, month, min(d.day, last_day))
    raise ValueError(f"Unknown frequency unit: {unit}")


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
            next_due = next_occurrence(next_due, rule["frequency_interval"], rule["frequency_unit"])
            guard += 1
        db.set_recurring_next_due(rule["id"], next_due.isoformat())
    return created


def upcoming_occurrences(
    n: int = 3, today: dt.date | None = None, exclude_categories: set[str] | None = None,
) -> list[dict]:
    """The next n occurrences across every active rule, soonest first.

    Each active rule's next_due_date is already its own soonest future occurrence (assuming
    generate_due_transactions has run this session, which backfills everything through today).
    Projecting n occurrences forward per rule is always enough to fill a global top-n list,
    since no single rule could ever need to contribute more than n of the n results. Rules whose
    category is in `exclude_categories` are skipped entirely -- filtering *before* projecting
    (rather than after) is what keeps that guarantee of "up to n results" intact.
    """
    today = today or dt.date.today()
    exclude_categories = exclude_categories or set()
    occurrences = []
    for rule in db.get_recurring_rules():
        if not rule["active"] or rule["category"] in exclude_categories:
            continue
        d = dt.date.fromisoformat(rule["next_due_date"])
        for _ in range(n):
            occurrences.append({
                "date": d, "type": rule["type"], "category": rule["category"],
                "description": rule["description"] or "", "amount": rule["amount"],
            })
            d = next_occurrence(d, rule["frequency_interval"], rule["frequency_unit"])
    occurrences.sort(key=lambda o: o["date"])
    return occurrences[:n]
