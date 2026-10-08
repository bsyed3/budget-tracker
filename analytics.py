"""Pandas helpers that turn raw transaction rows into the views the app needs."""
from __future__ import annotations

import calendar
import datetime as dt

import pandas as pd

import db


def load_df() -> pd.DataFrame:
    rows = db.get_transactions()
    cols = ["id", "date", "type", "category", "description", "amount", "goal_id", "recurring_id"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.strftime("%Y-%m")
    # Savings withdrawals are stored as income rows (see db.SAVINGS_WITHDRAWAL_CATEGORY) but are
    # money moving back out of savings, not earnings -- relabel so every `type == "income"`
    # filter in the app excludes them automatically, and handle "transfer" explicitly below.
    df.loc[(df["type"] == "income") & (df["category"] == db.SAVINGS_WITHDRAWAL_CATEGORY), "type"] = "transfer"
    return df


def _add_months(d: dt.date, n: int) -> dt.date:
    total = d.year * 12 + (d.month - 1) + n
    year, month0 = divmod(total, 12)
    return dt.date(year, month0 + 1, min(d.day, calendar.monthrange(year, month0 + 1)[1]))


def months_elapsed(start: dt.date, end: dt.date) -> float:
    """Whole months from start to end plus the leftover days as a fraction of the month they fall
    in -- June 1 to Oct 8 is 4 months + 7 days = 4 + 7/31."""
    if end <= start:
        return 0.0
    m = (end.year - start.year) * 12 + (end.month - start.month)
    if _add_months(start, m) > end:
        m -= 1
    anchor = _add_months(start, m)
    next_anchor = _add_months(start, m + 1)
    return m + (end - anchor).days / (next_anchor - anchor).days


def all_months(df: pd.DataFrame, pad_current: bool = True) -> list[str]:
    """All months that have data, chronologically, optionally padded to include the current month."""
    months = set(df["month"].unique()) if not df.empty else set()
    if pad_current:
        months.add(dt.date.today().strftime("%Y-%m"))
    return sorted(months)


def format_month(ym: str) -> str:
    """'2026-08' -> 'Aug 2026'."""
    return pd.Period(ym, freq="M").strftime("%b %Y")


def category_month_pivot(df: pd.DataFrame, type_: str) -> pd.DataFrame:
    """Rows = category, columns = YYYY-MM, values = summed amount."""
    subset = df[df["type"] == type_]
    if subset.empty:
        return pd.DataFrame()
    pivot = subset.pivot_table(index="category", columns="month", values="amount", aggfunc="sum", fill_value=0)
    return pivot.sort_index(axis=1)


def monthly_summary(df: pd.DataFrame, groups: dict[str, str]) -> pd.DataFrame:
    """One row per month: Total Income, Needs, Wants, Savings, Expenses, Net Income.

    "Expenses" is Needs + Wants only — money moved into Savings isn't spent, so it's
    excluded from the income-vs-expenses comparison (Net Income still accounts for it).
    """
    cols = ["Total Income", "Needs", "Wants", "Savings", "Expenses", "Net Income"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    work = df.copy()
    work["group"] = work["category"].map(groups).fillna("Wants")
    income = work[work["type"] == "income"].groupby("month")["amount"].sum()
    withdrawn = work[work["type"] == "transfer"].groupby("month")["amount"].sum()
    expense_by_group = (
        work[work["type"] == "expense"].groupby(["month", "group"])["amount"].sum().unstack(fill_value=0)
    )
    for g in db.GROUP_NAMES:
        if g not in expense_by_group.columns:
            expense_by_group[g] = 0.0

    out = pd.DataFrame(index=sorted(set(income.index) | set(expense_by_group.index) | set(withdrawn.index)))
    out["Total Income"] = income.reindex(out.index, fill_value=0.0)
    for g in db.GROUP_NAMES:
        out[g] = expense_by_group[g].reindex(out.index, fill_value=0.0)
    # Money taken back out of savings counts against that month's savings (net contributions),
    # which is also what makes Net Income add it back as cash that was available to spend.
    out["Savings"] = out["Savings"] - withdrawn.reindex(out.index, fill_value=0.0)
    out["Expenses"] = out["Needs"] + out["Wants"]
    out["Net Income"] = out["Total Income"] - out["Needs"] - out["Wants"] - out["Savings"]
    out = out.sort_index()
    out.index.name = "month"
    return out


def group_breakdown(df: pd.DataFrame, groups: dict[str, str]) -> pd.Series:
    """Total expense amount per Needs/Wants/Savings group for whatever rows are passed in.
    Savings is net of any withdrawals from savings in those rows (so it can be negative)."""
    expense_df = df[df["type"] == "expense"].copy()
    withdrawn = df.loc[df["type"] == "transfer", "amount"].sum() if not df.empty else 0.0
    if expense_df.empty:
        out = pd.Series(0.0, index=db.GROUP_NAMES)
    else:
        expense_df["group"] = expense_df["category"].map(groups).fillna("Wants")
        out = expense_df.groupby("group")["amount"].sum().reindex(db.GROUP_NAMES, fill_value=0.0)
    out["Savings"] = out["Savings"] - withdrawn
    return out


def group_breakdown_by_month(df: pd.DataFrame, groups: dict[str, str]) -> pd.DataFrame:
    """Long-format month/group/amount, for a Needs/Wants/Savings-over-time chart."""
    work = df[df["type"].isin(["expense", "transfer"])].copy()
    if work.empty:
        return pd.DataFrame(columns=["month", "group", "amount"])
    work["group"] = work["category"].map(groups).fillna("Wants")
    is_withdrawal = work["type"] == "transfer"
    work.loc[is_withdrawal, "group"] = "Savings"
    work.loc[is_withdrawal, "amount"] = -work.loc[is_withdrawal, "amount"]
    out = work.groupby(["month", "group"])["amount"].sum().reset_index()
    out.columns = ["month", "group", "amount"]
    return out


def first_transaction_month(df: pd.DataFrame) -> str | None:
    """The earliest month with any data at all, or None if there's no data yet."""
    if df.empty:
        return None
    return df["date"].min().strftime("%Y-%m")


def prior_months_available(month: str, first_month: str) -> list[str]:
    """Up to the 3 calendar months immediately before `month`, chronological, excluding any
    that fall before `first_month` (since there's no real data to average there)."""
    target = pd.Period(month, freq="M")
    first_period = pd.Period(first_month, freq="M")
    candidates = [target - i for i in (3, 2, 1)]
    return [c.strftime("%Y-%m") for c in candidates if c >= first_period]


def three_month_avg(df: pd.DataFrame, category: str, month: str, first_month: str | None = None) -> float:
    """Average expense for `category` over however many of the 3 preceding months actually have
    data (1 month right after your first month, 2 the month after that, 3 from then on)."""
    first_month = first_month or first_transaction_month(df)
    if first_month is None:
        return 0.0
    prior_months = prior_months_available(month, first_month)
    if not prior_months:
        return 0.0
    subset = df[
        (df["type"] == "expense") & (df["category"] == category) & (df["month"].isin(prior_months))
    ]
    if subset.empty:
        return 0.0
    return subset.groupby("month")["amount"].sum().reindex(prior_months, fill_value=0.0).mean()


def weekly_totals(
    df: pd.DataFrame, weeks: int | None = 12, all_time: bool = False, scope: str = "total"
) -> pd.DataFrame:
    """Weekly (Mon-Sun) spend, excluding Savings contributions.

    `scope`: "wants" (Wants-group only), "needs" (Needs-group only), or "total" (Needs + Wants).
    Pass `weeks` for a rolling recent window, or `all_time=True` to cover every week from the
    first transaction through the current week.
    """
    today = dt.date.today()
    this_monday = today - dt.timedelta(days=today.weekday())
    groups = db.get_category_groups()

    if all_time and not df.empty:
        first_date = df["date"].min().date()
        first_monday = first_date - dt.timedelta(days=first_date.weekday())
        n_weeks = (this_monday - first_monday).days // 7 + 1
        week_starts = [first_monday + dt.timedelta(weeks=i) for i in range(n_weeks)]
    else:
        n = weeks or 12
        week_starts = [this_monday - dt.timedelta(weeks=i) for i in range(n - 1, -1, -1)]

    spend = df.copy()
    if not spend.empty:
        spend["group"] = spend["category"].map(groups).fillna("Wants")
        spend = spend[spend["type"] == "expense"]
        if scope == "wants":
            spend = spend[spend["group"] == "Wants"]
        elif scope == "needs":
            spend = spend[spend["group"] == "Needs"]
        else:
            spend = spend[spend["group"] != "Savings"]

    rows = []
    for start in week_starts:
        end = start + dt.timedelta(days=6)
        if spend.empty:
            total = 0.0
        else:
            mask = (spend["date"].dt.date >= start) & (spend["date"].dt.date <= end)
            total = spend.loc[mask, "amount"].sum()
        rows.append({"week_start": pd.Timestamp(start), "week_end": pd.Timestamp(end), "amount": total})
    return pd.DataFrame(rows)


def savings_current_amount(goal_row, df: pd.DataFrame) -> float:
    """A goal's current total balance: its most recent weekly/monthly snapshot if it has ever
    had one recorded, otherwise the pre-snapshot calculation (starting balance + linked
    contribution transactions) so numbers don't suddenly change before snapshots are in use."""
    mine = df[df["goal_id"] == goal_row["id"]] if not df.empty else df
    latest = db.latest_savings_snapshot(goal_row["id"])
    if latest is not None:
        snap_date, snap_amount = latest
        # Withdrawals dated after the latest snapshot aren't in it yet. One dated on the
        # snapshot's own date is assumed to already be reflected (a same-day snapshot is
        # recorded from the post-withdrawal balance).
        withdrawn = 0.0
        if not mine.empty:
            after = mine[(mine["type"] == "transfer") & (mine["date"] > pd.Timestamp(snap_date))]
            withdrawn = after["amount"].sum()
        return snap_amount - withdrawn
    contributed = 0.0
    if not mine.empty:
        contributed = (
            mine.loc[mine["type"] != "transfer", "amount"].sum() - mine.loc[mine["type"] == "transfer", "amount"].sum()
        )
    return goal_row["starting_amount"] + contributed


def savings_change_since_month_start(goal_row, df: pd.DataFrame) -> tuple[float, float | None] | None:
    """(dollar_change, pct_change) vs. this goal's recorded monthly snapshot for the 1st of the
    current month, or None if that snapshot hasn't been recorded yet. pct_change is None if the
    baseline itself was $0 (a percentage change from zero is undefined)."""
    month_start = dt.date.today().replace(day=1).isoformat()
    baseline_row = next(
        (s for s in db.get_goal_snapshots(goal_row["id"], "monthly") if s["period_date"] == month_start), None
    )
    if baseline_row is None:
        return None
    baseline = baseline_row["amount"]
    current = savings_current_amount(goal_row, df)
    dollar_change = current - baseline
    pct_change = (dollar_change / baseline * 100) if baseline != 0 else None
    return dollar_change, pct_change


def tfsa_room_remaining(
    df: pd.DataFrame, anchor_value: float, anchor_date: str, linked_goal_ids: list[int],
    anchor_txn_id: int | None = None,
) -> float:
    """Anchor value minus contributions (expense transactions linked to one of the given goals)
    dated on or after the anchor date -- setting a new anchor resets the clock to today, so
    anything logged before today no longer counts against it, while today's (and any later)
    contributions do. Transactions only carry a date, not a timestamp, so "on the anchor date"
    counts as "since the reset" rather than being excluded -- otherwise a contribution added
    later the same day the anchor was reset would never count until the next calendar day.

    When anchor_txn_id is known (the newest transaction id at reset time) it's used instead of
    the date: only transactions created after the reset count, so contributions already logged
    earlier the same day (e.g. recurring transfers) don't immediately push the room negative."""
    if df.empty or not linked_goal_ids:
        return anchor_value
    if anchor_txn_id is not None:
        since = df["id"] > anchor_txn_id
    else:
        since = df["date"] >= pd.Timestamp(anchor_date)
    mask = df["goal_id"].isin(linked_goal_ids) & (df["type"] == "expense") & since
    contributed_since = df.loc[mask, "amount"].sum()
    return anchor_value - contributed_since


def savings_snapshot_series(snapshots: list, goals: list) -> pd.DataFrame:
    """Long-format period_date/goal/amount, for the multi-goal balance-over-time chart."""
    if not snapshots:
        return pd.DataFrame(columns=["period_date", "goal", "amount"])
    goal_names = {g["id"]: g["name"] for g in goals}
    rows = [
        {
            "period_date": pd.Timestamp(s["period_date"]),
            "goal": goal_names.get(s["goal_id"], "Unknown"),
            "amount": s["amount"],
        }
        for s in snapshots
    ]
    return pd.DataFrame(rows).sort_values("period_date")
