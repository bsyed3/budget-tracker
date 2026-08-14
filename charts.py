"""Altair-based chart helpers: colorful, non-interactive (no scroll-zoom/pan), consistent styling.

Streamlit's built-in st.bar_chart/st.line_chart allow the user to scroll-zoom and drag-pan,
which distorts the scale. Building explicit Altair specs and never calling .interactive()
keeps these static and predictable while giving full control over color and axis formatting.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from components import theme_text_color

MONEY_AXIS = alt.Axis(format="$,.0f")
# Force every category label to show, even if that means some crowding — dropping labels on a
# categorical axis (unlike a dense time axis) makes bars unidentifiable.
CATEGORY_AXIS = alt.Axis(labelAngle=-40, labelOverlap=False)


def category_bar_by_group(series: pd.Series, group_map: dict[str, str], group_colors: dict[str, str],
                           height: int = 280) -> None:
    """One bar per category, colored by each category's group (e.g. Needs=blue, Wants=orange)."""
    if series.empty or series.sum() <= 0:
        st.caption("No data yet.")
        return
    data = series.reset_index()
    data.columns = ["Category", "Amount"]
    data["Group"] = data["Category"].map(group_map).fillna("Wants")
    # Only legend groups actually present in this chart's data (e.g. don't show a "Savings"
    # swatch on a chart that has no Savings bars).
    present = [g for g in group_colors if g in set(data["Group"])]
    domain = present
    range_ = [group_colors[g] for g in present]
    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("Category:N", sort="-y", title=None, axis=CATEGORY_AXIS),
            y=alt.Y("Amount:Q", title=None, axis=MONEY_AXIS),
            color=alt.Color("Group:N", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("Category:N"), alt.Tooltip("Group:N"), alt.Tooltip("Amount:Q", format="$,.2f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def category_bar_flat(series: pd.Series, color: str, height: int = 280) -> None:
    """One bar per category, all the same flat color (e.g. Income by category)."""
    if series.empty or series.sum() <= 0:
        st.caption("No data yet.")
        return
    data = series.reset_index()
    data.columns = ["Category", "Amount"]
    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, color=color)
        .encode(
            x=alt.X("Category:N", sort="-y", title=None, axis=CATEGORY_AXIS),
            y=alt.Y("Amount:Q", title=None, axis=MONEY_AXIS),
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
    """Spent vs. Goal over time, temporal x-axis (sorts naturally, no ordering issues).

    Tick labels are pinned to the exact week_start dates in the data (no interpolated ticks
    that land between real points) and overlapping labels are dropped rather than crammed —
    every label shown lines up exactly with its point.
    """
    if weekly_df.empty:
        st.caption("No data yet.")
        return
    tick_values = sorted(pd.to_datetime(weekly_df["week_start"]).unique().tolist())
    long_df = weekly_df.melt(id_vars=["week_start"], value_vars=["Spent", "Goal"], var_name="Series", value_name="Amount")
    colors = {"Spent": "#2563eb", "Goal": "#64748b"}
    chart = (
        alt.Chart(long_df)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X(
                "week_start:T", title=None,
                axis=alt.Axis(format="%b %d", values=tick_values, labelOverlap=True, labelAngle=-40),
            ),
            y=alt.Y("Amount:Q", title=None, axis=MONEY_AXIS),
            color=alt.Color("Series:N", scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())), legend=alt.Legend(title=None, orient="top")),
            strokeDash=alt.condition(alt.datum.Series == "Goal", alt.value([5, 4]), alt.value([1, 0])),
            tooltip=[alt.Tooltip("week_start:T", format="%b %d, %Y"), alt.Tooltip("Series:N"), alt.Tooltip("Amount:Q", format="$,.2f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def group_by_month_bar(long_df: pd.DataFrame, x_order: list[str], colors: dict[str, str],
                        height: int = 300, normalize: bool = False) -> None:
    """Stacked bars of Needs/Wants/Savings amounts per month (long_df has month_label/group/amount,
    plus a pre-computed 'pct' column — each group's share of that month's total).

    `normalize=True` shows each month as a 100%-stacked bar (share of that month) instead of
    absolute dollars, and the tooltip/labels show the percentage instead of the dollar amount.
    Values are also printed directly on each bar segment, not just in the hover tooltip — on
    mobile there's no hover, so tap-only tooltips would otherwise be unreadable.
    """
    if long_df.empty:
        st.caption("No data yet.")
        return
    domain = list(colors.keys())
    range_ = list(colors.values())
    y_axis = alt.Axis(format="%") if normalize else MONEY_AXIS
    text_field = "pct" if normalize else "amount"
    text_format = ".0%" if normalize else "$,.0f"
    value_tooltip = (
        alt.Tooltip("pct:Q", title="Share", format=".0%")
        if normalize
        else alt.Tooltip("amount:Q", title="Amount", format="$,.2f")
    )

    base = alt.Chart(long_df).encode(
        x=alt.X("month_label:N", title=None, sort=x_order),
        y=alt.Y("amount:Q", title=None, axis=y_axis, stack="normalize" if normalize else "zero"),
    )
    bars = base.mark_bar().encode(
        color=alt.Color("group:N", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("month_label:N", title="Month"), alt.Tooltip("group:N", title="Group"), value_tooltip],
    )
    labels = (
        base.transform_filter("datum.amount > 0")
        .mark_text(color=theme_text_color(), fontWeight="bold", fontSize=11)
        .encode(text=alt.Text(f"{text_field}:Q", format=text_format))
    )

    st.altair_chart((bars + labels).properties(height=height), use_container_width=True)


def single_series_bar(df: pd.DataFrame, x_col: str, y_col: str, x_order: list[str],
                       color: str, height: int = 280) -> None:
    """One bar per x value (e.g. per month), single flat color."""
    if df.empty:
        st.caption("No data yet.")
        return
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, color=color)
        .encode(
            x=alt.X(f"{x_col}:N", title=None, sort=x_order),
            y=alt.Y(f"{y_col}:Q", title=None, axis=MONEY_AXIS),
            tooltip=[alt.Tooltip(f"{x_col}:N", title="Month"), alt.Tooltip(f"{y_col}:Q", title="Amount", format="$,.2f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)
