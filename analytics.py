"""Pandas helpers that turn raw transaction rows into the views the app needs."""
from __future__ import annotations

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
    return df


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
    expense_by_group = (
        work[work["type"] == "expense"].groupby(["month", "group"])["amount"].sum().unstack(fill_value=0)
    )
    for g in db.GROUP_NAMES:
        if g not in expense_by_group.columns:
            expense_by_group[g] = 0.0

    out = pd.DataFrame(index=sorted(set(income.index) | set(expense_by_group.index)))
    out["Total Income"] = income.reindex(out.index, fill_value=0.0)
    for g in db.GROUP_NAMES:
        out[g] = expense_by_group[g].reindex(out.index, fill_value=0.0)
    out["Expenses"] = out["Needs"] + out["Wants"]
    out["Net Income"] = out["Total Income"] - out["Needs"] - out["Wants"] - out["Savings"]
    out = out.sort_index()
    out.index.name = "month"
    return out


def group_breakdown(df: pd.DataFrame, groups: dict[str, str]) -> pd.Series:
    """Total expense amount per Needs/Wants/Savings group for whatever rows are passed in."""
    expense_df = df[df["type"] == "expense"].copy()
    if expense_df.empty:
        return pd.Series(0.0, index=db.GROUP_NAMES)
    expense_df["group"] = expense_df["category"].map(groups).fillna("Wants")
    return expense_df.groupby("group")["amount"].sum().reindex(db.GROUP_NAMES, fill_value=0.0)


def group_breakdown_by_month(df: pd.DataFrame, groups: dict[str, str]) -> pd.DataFrame:
    """Long-format month/group/amount, for a Needs/Wants/Savings-over-time chart."""
    work = df[df["type"] == "expense"].copy()
    if work.empty:
        return pd.DataFrame(columns=["month", "group", "amount"])
    work["group"] = work["category"].map(groups).fillna("Wants")
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
    latest = db.latest_savings_amount(goal_row["id"])
    if latest is not None:
        return latest
    contributed = 0.0
    if not df.empty:
        contributed = df.loc[df["goal_id"] == goal_row["id"], "amount"].sum()
    return goal_row["starting_amount"] + contributed


def tfsa_room_remaining(df: pd.DataFrame, anchor_value: float, anchor_date: str, linked_goal_ids: list[int]) -> float:
    """Anchor value minus contributions (expense transactions linked to one of the given goals)
    dated strictly after the anchor date -- setting a new anchor resets the clock, so anything
    logged before/on that date no longer counts against it."""
    if df.empty or not linked_goal_ids:
        return anchor_value
    anchor = pd.Timestamp(anchor_date)
    mask = df["goal_id"].isin(linked_goal_ids) & (df["type"] == "expense") & (df["date"] > anchor)
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
