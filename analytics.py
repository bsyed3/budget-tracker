"""Pandas helpers that turn raw transaction rows into the views the app needs."""
from __future__ import annotations

import datetime as dt

import pandas as pd

import db


def load_df() -> pd.DataFrame:
    rows = db.get_transactions()
    cols = ["id", "date", "type", "category", "description", "amount", "goal_id"]
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


def category_month_pivot(df: pd.DataFrame, type_: str) -> pd.DataFrame:
    """Rows = category, columns = YYYY-MM, values = summed amount."""
    subset = df[df["type"] == type_]
    if subset.empty:
        return pd.DataFrame()
    pivot = subset.pivot_table(index="category", columns="month", values="amount", aggfunc="sum", fill_value=0)
    return pivot.sort_index(axis=1)


def monthly_summary(df: pd.DataFrame, groups: dict[str, str]) -> pd.DataFrame:
    """One row per month: Total Income, Total Needs, Total Wants, Total Savings & Donations, Net."""
    if df.empty:
        return pd.DataFrame(
            columns=["Total Income", "Total Needs", "Total Wants", "Total Savings & Donations", "Net Income"]
        )
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
    out["Total Needs"] = expense_by_group["Needs"].reindex(out.index, fill_value=0.0)
    out["Total Wants"] = expense_by_group["Wants"].reindex(out.index, fill_value=0.0)
    out["Total Savings & Donations"] = expense_by_group["Savings & Donations"].reindex(out.index, fill_value=0.0)
    out["Net Income"] = out["Total Income"] - out["Total Needs"] - out["Total Wants"] - out["Total Savings & Donations"]
    return out.sort_index()


def three_month_avg(df: pd.DataFrame, category: str, month: str) -> float:
    """Average expense for `category` over the 3 calendar months preceding `month`."""
    target = pd.Period(month, freq="M")
    prior_months = [(target - i).strftime("%Y-%m") for i in (1, 2, 3)]
    subset = df[
        (df["type"] == "expense") & (df["category"] == category) & (df["month"].isin(prior_months))
    ]
    if subset.empty:
        return 0.0
    return subset.groupby("month")["amount"].sum().reindex(prior_months, fill_value=0.0).mean()


def weekly_totals(df: pd.DataFrame, weeks: int = 12) -> pd.DataFrame:
    """Last `weeks` calendar weeks (Mon-Sun) of discretionary spend (excludes Savings/Investments & Donations)."""
    today = dt.date.today()
    this_monday = today - dt.timedelta(days=today.weekday())
    week_starts = [this_monday - dt.timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    rows = []
    excluded = {"Savings/Investments", "Donations"}
    spend = df[(df["type"] == "expense") & (~df["category"].isin(excluded))] if not df.empty else df
    for start in week_starts:
        end = start + dt.timedelta(days=6)
        if spend.empty:
            total = 0.0
        else:
            mask = (spend["date"].dt.date >= start) & (spend["date"].dt.date <= end)
            total = spend.loc[mask, "amount"].sum()
        rows.append({"week_start": pd.Timestamp(start), "amount": total})
    return pd.DataFrame(rows)


def savings_current_amount(goal_row, df: pd.DataFrame) -> float:
    contributed = 0.0
    if not df.empty:
        contributed = df.loc[df["goal_id"] == goal_row["id"], "amount"].sum()
    return goal_row["starting_amount"] + contributed
