"""Altair-based chart helpers: colorful, non-interactive (no scroll-zoom/pan), consistent styling.

Streamlit's built-in st.bar_chart/st.line_chart allow the user to scroll-zoom and drag-pan,
which distorts the scale. Building explicit Altair specs and never calling .interactive()
keeps these static and predictable while giving full control over color and axis formatting.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

CATEGORY_SCHEME = "tableau20"
MONEY_AXIS = alt.Axis(format="$,.0f")


def category_bar(series: pd.Series, height: int = 280) -> None:
    """One bar per category, each a different color, sorted largest first."""
    if series.empty or series.sum() <= 0:
        st.caption("No data yet.")
        return
    data = series.reset_index()
    data.columns = ["Category", "Amount"]
    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("Category:N", sort="-y", title=None, axis=alt.Axis(labelAngle=-40)),
            y=alt.Y("Amount:Q", title=None, axis=MONEY_AXIS),
            color=alt.Color("Category:N", scale=alt.Scale(scheme=CATEGORY_SCHEME), legend=None),
            tooltip=[alt.Tooltip("Category:N"), alt.Tooltip("Amount:Q", format="$,.2f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def compare_bar(compare_df: pd.DataFrame, colors: dict[str, str], height: int = 300) -> None:
    """Side-by-side (not stacked) grouped bars. compare_df: index=Category, columns=series names."""
    if compare_df.empty:
        st.caption("No data yet.")
        return
    long_df = compare_df.reset_index().melt(id_vars=compare_df.index.name or "index", var_name="Series", value_name="Amount")
    long_df.columns = ["Category", "Series", "Amount"]
    domain = list(colors.keys())
    range_ = list(colors.values())
    chart = (
        alt.Chart(long_df)
        .mark_bar()
        .encode(
            x=alt.X("Category:N", title=None, sort=list(compare_df.index), axis=alt.Axis(labelAngle=-40)),
            xOffset=alt.XOffset("Series:N", sort=domain),
            y=alt.Y("Amount:Q", title=None, axis=MONEY_AXIS),
            color=alt.Color("Series:N", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("Category:N"), alt.Tooltip("Series:N"), alt.Tooltip("Amount:Q", format="$,.2f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def multi_line(long_df: pd.DataFrame, x_col: str, series_col: str, y_col: str,
               colors: dict[str, str], x_order: list[str] | None = None, height: int = 300) -> None:
    """Multiple colored lines sharing a nominal (label-based) x-axis, e.g. Income/Expenses/Savings by month."""
    if long_df.empty:
        st.caption("No data yet.")
        return
    domain = list(colors.keys())
    range_ = list(colors.values())
    x_enc = alt.X(f"{x_col}:N", title=None, sort=x_order)
    chart = (
        alt.Chart(long_df)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=x_enc,
            y=alt.Y(f"{y_col}:Q", title=None, axis=MONEY_AXIS),
            color=alt.Color(f"{series_col}:N", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip(f"{x_col}:N"), alt.Tooltip(f"{series_col}:N"), alt.Tooltip(f"{y_col}:Q", format="$,.2f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def weekly_line(weekly_df: pd.DataFrame, height: int = 300) -> None:
    """Spent vs. Goal over time, temporal x-axis (sorts naturally, no ordering issues)."""
    if weekly_df.empty:
        st.caption("No data yet.")
        return
    long_df = weekly_df.melt(id_vars=["week_start"], value_vars=["Spent", "Goal"], var_name="Series", value_name="Amount")
    colors = {"Spent": "#2563eb", "Goal": "#64748b"}
    chart = (
        alt.Chart(long_df)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X("week_start:T", title=None, axis=alt.Axis(format="%b %d")),
            y=alt.Y("Amount:Q", title=None, axis=MONEY_AXIS),
            color=alt.Color("Series:N", scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())), legend=alt.Legend(title=None, orient="top")),
            strokeDash=alt.condition(alt.datum.Series == "Goal", alt.value([5, 4]), alt.value([1, 0])),
            tooltip=[alt.Tooltip("week_start:T", format="%b %d, %Y"), alt.Tooltip("Series:N"), alt.Tooltip("Amount:Q", format="$,.2f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def group_by_month_bar(long_df: pd.DataFrame, x_order: list[str], colors: dict[str, str], height: int = 300) -> None:
    """Stacked bars of Needs/Wants/Savings amounts per month (long_df has month_label/group/amount)."""
    if long_df.empty:
        st.caption("No data yet.")
        return
    domain = list(colors.keys())
    range_ = list(colors.values())
    chart = (
        alt.Chart(long_df)
        .mark_bar()
        .encode(
            x=alt.X("month_label:N", title=None, sort=x_order),
            y=alt.Y("amount:Q", title=None, axis=MONEY_AXIS, stack="zero"),
            color=alt.Color("group:N", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("month_label:N", title="Month"), alt.Tooltip("group:N", title="Group"), alt.Tooltip("amount:Q", format="$,.2f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)
