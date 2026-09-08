"""Altair-based chart helpers: colorful, non-interactive (no scroll-zoom/pan), consistent styling.

Streamlit's built-in st.bar_chart/st.line_chart allow the user to scroll-zoom and drag-pan,
which distorts the scale. Building explicit Altair specs and never calling .interactive()
keeps these static and predictable while giving full control over color and axis formatting.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

MONEY_AXIS = alt.Axis(format="$,.0f")
# Force every category label to show, even if that means some crowding — dropping labels on a
# categorical axis (unlike a dense time axis) makes bars unidentifiable.
CATEGORY_AXIS = alt.Axis(labelAngle=-40, labelOverlap=False)


_OTHER_COLOR = "#94a3b8"  # neutral gray for the catch-all "Other" slice, distinct from the palette
_OTHER_THRESHOLD = 0.05  # a category under 5% of the total gets folded into "Other"


def category_pie(series: pd.Series, palette: list[str], group_small: bool = True, height: int = 320) -> None:
    """One slice per category, colored from a flat qualitative palette (no Needs/Wants coloring).

    If there are more than 3 categories, the largest ones are kept individually for as long as
    what's left over is still at least 5% of the total; once the remaining tail drops under 5%,
    that whole tail is folded into a single "Other" slice -- so "Other" itself never exceeds 5%
    (rather than every category individually under 5% landing in it, which could make "Other"
    itself the largest slice). Pass group_small=False to disable this and always show every
    category (e.g. for income, which usually has too few categories for "Other" to make sense).
    """
    if series.empty or series.sum() <= 0:
        st.caption("No data yet.")
        return
    data = series.sort_values(ascending=False)
    if group_small and len(data) > 3:
        total = data.sum()
        cumulative = 0.0
        cutoff = len(data)
        for i, amount in enumerate(data):
            cumulative += amount
            if total - cumulative < _OTHER_THRESHOLD * total:
                cutoff = i + 1
                break
        if cutoff < len(data):
            data = pd.concat([data.iloc[:cutoff], pd.Series({"Other": data.iloc[cutoff:].sum()})])

    df = data.reset_index()
    df.columns = ["Category", "Amount"]
    df["Pct"] = df["Amount"] / df["Amount"].sum()
    domain = df["Category"].tolist()
    range_ = [_OTHER_COLOR if cat == "Other" else palette[i % len(palette)] for i, cat in enumerate(domain)]

    chart = (
        alt.Chart(df)
        .mark_arc()
        .encode(
            theta=alt.Theta("Amount:Q", stack=True),
            color=alt.Color("Category:N", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title=None, orient="right")),
            tooltip=[alt.Tooltip("Category:N"), alt.Tooltip("Amount:Q", format="$,.2f"), alt.Tooltip("Pct:Q", title="Share", format=".1%")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def spending_category_pie(
    series: pd.Series, groups: dict[str, list[str]], shades: dict[str, list[str]],
    other_colors: dict[str, str], height: int = 420,
) -> None:
    """Spending by category, colored in per-meta-group families (e.g. every Transportation
    category gets its own shade of amber) so a category's color never depends on amount or rank
    -- Gas is always the same color whether or not it happens to be the biggest slice this month.

    Within each meta-group that has more than 3 categories present, the same 5%-of-total
    cumulative-tail logic as category_pie() folds that group's smallest categories into a single
    "<Group> - Other" slice (hovering it lists exactly what's inside, with each one's own amount
    and share) instead of splintering the chart with one slice per tiny category. If only one
    category would end up in "Other", there's nothing to lump it in with -- it's shown under its
    own name and color instead of a pointless one-item "Other".
    """
    if series.empty or series.sum() <= 0:
        st.caption("No data yet.")
        return
    total = series.sum()
    rows = []

    def own_color(group: str, cat: str) -> str:
        group_shades = shades.get(group) or [_OTHER_COLOR]
        cats_in_group = groups.get(group, [])
        idx = cats_in_group.index(cat) if cat in cats_in_group else 0
        return group_shades[idx % len(group_shades)]

    for group, cats_in_group in groups.items():
        present = series[series.index.isin(cats_in_group)]
        present = present[present > 0].sort_values(ascending=False)
        if present.empty:
            continue

        cutoff = len(present)
        if len(present) > 3:
            group_total = present.sum()
            cumulative = 0.0
            for i, amount in enumerate(present):
                cumulative += amount
                if group_total - cumulative < _OTHER_THRESHOLD * total:
                    cutoff = i + 1
                    break

        # A single leftover category isn't grouped with anything -- show it plainly instead of
        # a one-item "<Group> - Other".
        if len(present) - cutoff == 1:
            cutoff = len(present)

        for cat, amount in present.iloc[:cutoff].items():
            pct = amount / total
            rows.append({
                "Category": cat, "Amount": amount, "Color": own_color(group, cat),
                "Detail": f"{cat}\n${amount:,.2f} ({pct:.1%})",
            })

        leftover = present.iloc[cutoff:]
        if not leftover.empty:
            other_amount = leftover.sum()
            other_pct = other_amount / total
            detail_lines = [f"{group} - Other", f"${other_amount:,.2f} ({other_pct:.1%})", ""]
            detail_lines += [f"{cat} - ${amt:,.2f} ({amt / total:.0%})" for cat, amt in leftover.items()]
            rows.append({
                "Category": f"{group} - Other", "Amount": other_amount,
                "Color": other_colors.get(group, _OTHER_COLOR),
                "Detail": "\n".join(detail_lines),
            })

    df = pd.DataFrame(rows)
    domain = df["Category"].tolist()
    range_ = df["Color"].tolist()

    chart = (
        alt.Chart(df)
        .mark_arc()
        .encode(
            theta=alt.Theta("Amount:Q", stack=True),
            color=alt.Color("Category:N", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title=None, orient="right", columns=1)),
            tooltip=[alt.Tooltip("Detail:N", title=None)],
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
            x=alt.X("Category:N", title=None, sort=list(compare_df.index), axis=CATEGORY_AXIS),
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


def savings_balance_line(long_df: pd.DataFrame, colors: dict[str, str], height: int = 320) -> None:
    """Multiple goals' total-balance-over-time, one line per goal. long_df has period_date/goal/amount.

    Temporal x-axis (like weekly_line) rather than a categorical month label -- tick marks land
    exactly on the real snapshot dates instead of interpolating, and weekly vs. monthly data both
    space out correctly by real elapsed time.
    """
    if long_df.empty:
        st.caption("No snapshots recorded yet.")
        return
    tick_values = sorted(long_df["period_date"].unique().tolist())
    domain = list(colors.keys())
    range_ = list(colors.values())
    chart = (
        alt.Chart(long_df)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X(
                "period_date:T", title=None,
                axis=alt.Axis(format="%b %d, %Y", values=tick_values, labelOverlap=True, labelAngle=-40),
            ),
            # zero=False -- a trend line (unlike a bar) doesn't need to start at $0. A goal like
            # Loans moves a few hundred dollars around a ~$26,000 balance; forcing the axis down
            # to zero flattens that into an invisible near-straight line. Letting the axis fit
            # the data's actual range is what makes week-to-week movement visible.
            y=alt.Y("amount:Q", title=None, axis=MONEY_AXIS, scale=alt.Scale(zero=False)),
            color=alt.Color("goal:N", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("period_date:T", title="Date", format="%b %d, %Y"), alt.Tooltip("goal:N", title="Goal"), alt.Tooltip("amount:Q", title="Amount", format="$,.2f")],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def group_by_month_bar(long_df: pd.DataFrame, x_order: list[str], colors: dict[str, str],
                        height: int = 300, normalize: bool = False) -> None:
    """Stacked bars of Needs/Wants/Savings amounts per month (long_df has month_label/group/amount,
    plus a pre-computed 'pct' column — each group's share of that month's total).

    `normalize=True` shows each month as a 100%-stacked bar (share of that month) instead of
    absolute dollars, and the tooltip shows the percentage instead of the dollar amount. Values
    only show on hover (no permanent on-bar labels) -- kept simple to avoid a label ever landing
    on the wrong segment; the color plus the legend already identify each one.
    """
    if long_df.empty:
        st.caption("No data yet.")
        return
    domain = list(colors.keys())
    range_ = list(colors.values())
    y_axis = alt.Axis(format="%") if normalize else MONEY_AXIS
    value_tooltip = (
        alt.Tooltip("pct:Q", title="Share", format=".0%")
        if normalize
        else alt.Tooltip("amount:Q", title="Amount", format="$,.2f")
    )

    chart = (
        alt.Chart(long_df)
        .mark_bar()
        .encode(
            x=alt.X("month_label:N", title=None, sort=x_order),
            y=alt.Y("amount:Q", title=None, axis=y_axis, stack="normalize" if normalize else "zero"),
            color=alt.Color("group:N", scale=alt.Scale(domain=domain, range=range_), legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("month_label:N", title="Month"), alt.Tooltip("group:N", title="Group"), value_tooltip],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


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
