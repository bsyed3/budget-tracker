"""Personal budget tracker built with Streamlit."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import analytics
import charts
import components
import db
import pwa
import recurring

st.set_page_config(page_title="Budget Tracker", page_icon="💰", layout="wide")
db.init_db()
pwa.inject()  # iOS "Add to Home Screen" -> full-screen app icon/name instead of a Safari tab
pwa.inject_number_input_ux()  # tapping a number field selects its value instead of appending

# Auto-generate any recurring transactions that have come due (checked on every load; cheap
# and idempotent — backfills every missed occurrence, not just one, if it's been a while).
_recurring_created = recurring.generate_due_transactions()
if _recurring_created and st.session_state.get("_last_recurring_toast") != dt.date.today().isoformat():
    st.toast(f"Added {_recurring_created} recurring transaction(s) that came due.")
    st.session_state["_last_recurring_toast"] = dt.date.today().isoformat()

CURRENT_MONTH = dt.date.today().strftime("%Y-%m")
money = components.money
fmt_month = analytics.format_month

# Row "⋮" edit/delete menus only reveal themselves when hovering the row they belong to.
# Every hoverable row is wrapped in st.container(key=f"hoverrow_..."), which Streamlit renders
# with a stable "st-key-hoverrow_..." class on the wrapping div — this CSS targets that.
# Table header rows use the same treatment (minus the popover) via "st-key-tablehead_...".
st.markdown(
    """
    <style>
    div[class*="st-key-hoverrow_"] div[data-testid="stPopover"] { visibility: hidden; }
    div[class*="st-key-hoverrow_"]:hover div[data-testid="stPopover"] { visibility: visible; }
    /* Touch devices have no hover state, so the menu would otherwise never appear. */
    @media (hover: none) {
        div[class*="st-key-hoverrow_"] div[data-testid="stPopover"] { visibility: visible; }
    }
    /* Keep each row's cells side-by-side instead of Streamlit's default of stacking them on
       narrow screens. Scrolling itself happens once, on the outer "tablewrap_" container that
       wraps the whole table (header + every row) -- so everything scrolls together and stays
       column-aligned, instead of each row scrolling independently out of sync. */
    div[class*="st-key-hoverrow_"] div[data-testid="stHorizontalBlock"],
    div[class*="st-key-tablehead_"] div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        width: max-content !important;
        min-width: 100% !important;
    }
    div[class*="st-key-hoverrow_"] div[data-testid="stColumn"],
    div[class*="st-key-tablehead_"] div[data-testid="stColumn"] {
        min-width: fit-content !important;
    }
    div[class*="st-key-tablewrap_"] {
        overflow-x: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

TREND_COLORS = {"Income": "#0ea5e9", "Expenses": "#ef4444", "Savings": "#16a34a"}
COMPARE_COLORS = {"This month": "#2563eb", "3-month avg": "#94a3b8"}

page = st.sidebar.radio(
    "Go to",
    [
        "Snapshot", "Overview", "Breakdown", "Monthly Budget", "Savings",
        "Transactions", "Recurring Transactions", "Settings",
    ],
)

df = analytics.load_df()
groups = db.get_category_groups()

# ======================================================================= Snapshot
if page == "Snapshot":
    st.title("💰 Budget Tracker")
    st.caption(f"Quick overview for {fmt_month(CURRENT_MONTH)}")
    month_df = df[df["month"] == CURRENT_MONTH] if not df.empty else df
    income = month_df.loc[month_df["type"] == "income", "amount"].sum()
    breakdown = analytics.group_breakdown(month_df, groups)
    expenses = breakdown["Needs"] + breakdown["Wants"]
    net = income - breakdown.sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Income", f"${income:,.2f}")
    c2.metric("Expenses", f"${expenses:,.2f}")
    c3.metric("Net", f"${net:,.2f}")
    c4.metric("To Savings", f"${breakdown['Savings']:,.2f}")

    st.divider()
    st.subheader("Budget Warnings")
    budgets = db.get_budgets()
    spent_by_cat = (
        month_df[month_df["type"] == "expense"].groupby("category")["amount"].sum()
        if not month_df.empty else pd.Series(dtype=float)
    )
    warnings = []
    for b in budgets:
        limit = b["monthly_limit"]
        spent = float(spent_by_cat.get(b["category"], 0.0))
        pct = spent / limit if limit > 0 else 0.0
        if pct >= 0.8:
            warnings.append((b["category"], spent, limit, pct))
    warnings.sort(key=lambda x: -x[3])
    if not budgets:
        st.caption("No budgets set yet — set some on the Monthly Budget page.")
    elif not warnings:
        st.success("No budgets are near or over their limit this month.")
    else:
        for category, spent, limit, pct in warnings:
            wc1, wc2, wc3 = st.columns([0.9, 2.5, 3])
            with wc1:
                st.markdown(components.status_pill(pct), unsafe_allow_html=True)
            with wc2:
                st.markdown(f"**{category}**")
            with wc3:
                st.markdown(f"{money(spent)} / {money(limit)}  ({pct:.0%})")
            components.colored_progress(pct)
            st.write("")

    st.divider()
    st.subheader("This Week")
    weekly_goal = float(db.get_setting("weekly_goal_total", "400"))
    two_weeks = analytics.weekly_totals(df, weeks=2)
    spent_last_week = float(two_weeks["amount"].iloc[0]) if len(two_weeks) > 0 else 0.0
    spent_this_week = float(two_weeks["amount"].iloc[1]) if len(two_weeks) > 1 else 0.0
    for label, spent in [("This week", spent_this_week), ("Last week", spent_last_week)]:
        week_pct = spent / weekly_goal if weekly_goal > 0 else 0.0
        wk1, wk2, wk3 = st.columns([0.9, 2.5, 3])
        with wk1:
            st.markdown(components.status_pill(week_pct), unsafe_allow_html=True)
        with wk2:
            st.markdown(f"**{label}**")
        with wk3:
            st.markdown(f"{money(spent)} / {money(weekly_goal)}  ({week_pct:.0%})")
        components.colored_progress(week_pct)
        st.write("")

    st.divider()
    st.subheader("Savings Snapshot")
    goals = db.get_savings_goals()
    if not goals:
        st.caption("No savings goals yet — add one on the Savings page.")
    else:
        for g in goals:
            current = analytics.savings_current_amount(g, df)
            pct = min(current / g["goal_amount"], 1.0) if g["goal_amount"] > 0 else 0.0
            sc1, sc2 = st.columns([2.5, 3])
            with sc1:
                st.markdown(f"**{g['name']}**")
            with sc2:
                st.markdown(f"{money(current)} / {money(g['goal_amount'])}  ({pct:.0%})")
            st.progress(pct)
            st.write("")

    st.divider()
    st.subheader("Upcoming")
    upcoming = recurring.upcoming_occurrences(3)
    if not upcoming:
        st.caption("No upcoming recurring transactions — set some up on the Recurring Transactions page.")
    else:
        for occ in upcoming:
            uc1, uc2, uc3 = st.columns([0.9, 2.5, 3])
            with uc1:
                badge_color = "#0ea5e9" if occ["type"] == "income" else "#64748b"
                st.markdown(components.tag(occ["type"].capitalize(), badge_color), unsafe_allow_html=True)
            with uc2:
                label = occ["category"] + (f" — {occ['description']}" if occ["description"] else "")
                st.markdown(f"**{label}**")
            with uc3:
                st.markdown(f"{money(occ['amount'])} · {occ['date'].strftime('%b %d, %Y')}")

# ======================================================================= Overview
elif page == "Overview":
    st.caption("Everything you've logged, broken down by month and by week.")
    if df.empty:
        st.info("No transactions yet — this page fills in as you log income and expenses.")
    else:
        summary = analytics.monthly_summary(df, groups)
        month_order = list(summary.index)
        x_order = [fmt_month(m) for m in month_order]

        st.subheader("Income vs. Expenses vs. Savings Over Time")
        st.caption("Expenses = Needs + Wants. Savings is tracked separately since that money isn't spent.")
        trend_long = summary.reset_index()
        trend_long["month_label"] = trend_long["month"].map(fmt_month)
        trend_long = trend_long.rename(columns={"Total Income": "Income"})
        trend_long = trend_long.melt(
            id_vars=["month_label"], value_vars=["Income", "Expenses", "Savings"],
            var_name="Series", value_name="Amount",
        )
        charts.multi_line(trend_long, x_col="month_label", series_col="Series", y_col="Amount",
                           colors=TREND_COLORS, x_order=x_order)

        st.subheader("Expense Breakdown (All Time)")
        st.caption("Needs / Wants / Savings share of everything you've logged.")
        all_time_breakdown = analytics.group_breakdown(df, groups)
        components.percentage_bar(all_time_breakdown.to_dict())

        nws_header, nws_toggle = st.columns([4, 1])
        nws_header.subheader("Needs / Wants / Savings by Month")
        show_pct = nws_toggle.toggle("Show %", key="nws_by_month_pct")
        gbm = analytics.group_breakdown_by_month(df, groups)
        if not gbm.empty:
            gbm_months = sorted(gbm["month"].unique())
            gbm_order = [fmt_month(m) for m in gbm_months]
            gbm = gbm.copy()
            gbm["month_label"] = gbm["month"].map(fmt_month)
            gbm["pct"] = gbm.groupby("month")["amount"].transform(lambda x: x / x.sum())
            charts.group_by_month_bar(gbm, x_order=gbm_order, colors=db.GROUP_COLORS, normalize=show_pct)

        st.subheader("Monthly Summary")
        display_cols = ["Total Income", "Needs", "Wants", "Savings", "Expenses", "Net Income"]
        display_summary = summary[display_cols].T
        display_summary.columns = [fmt_month(c) for c in display_summary.columns]
        st.dataframe(display_summary.style.format("${:,.2f}"), use_container_width=True)

        st.subheader("Expenses by Category")
        expense_pivot = analytics.category_month_pivot(df, "expense")
        if not expense_pivot.empty:
            expense_pivot = expense_pivot.copy()
            expense_pivot.columns = [fmt_month(c) for c in expense_pivot.columns]
            expense_pivot.index.name = "Category"
            st.dataframe(expense_pivot.style.format("${:,.2f}"), use_container_width=True)

        st.subheader("Income by Category")
        income_pivot = analytics.category_month_pivot(df, "income")
        if not income_pivot.empty:
            income_pivot = income_pivot.copy()
            income_pivot.columns = [fmt_month(c) for c in income_pivot.columns]
            income_pivot.index.name = "Category"
            st.dataframe(income_pivot.style.format("${:,.2f}"), use_container_width=True)

        st.divider()
        weekly_scope_label = st.radio("Weekly Breakdown Scope", ["Wants", "Needs", "Total"], horizontal=True)
        weekly_scope = weekly_scope_label.lower()
        st.subheader(f"Weekly Breakdown - {weekly_scope_label}")
        if weekly_scope_label == "Total":
            st.caption("Needs + Wants, all time — excludes Savings contributions.")
        else:
            st.caption(f"{weekly_scope_label}-only spending, all time.")

        weekly_goal_key = {"Wants": "weekly_goal_wants", "Needs": "weekly_goal_needs", "Total": "weekly_goal_total"}[weekly_scope_label]
        weekly_goal_default = "400" if weekly_scope_label == "Total" else "200"
        weekly_goal = float(db.get_setting(weekly_goal_key, weekly_goal_default))
        weekly = analytics.weekly_totals(df, all_time=True, scope=weekly_scope)
        weekly_chart_df = weekly.rename(columns={"amount": "Spent"})
        weekly_chart_df["Goal"] = weekly_goal
        charts.weekly_line(weekly_chart_df[["week_start", "Spent", "Goal"]])

        weekly_table = weekly.sort_values("week_start", ascending=False).copy()
        weekly_table["Week"] = (
            weekly_table["week_start"].dt.strftime("%b %d, %Y") + " to " + weekly_table["week_end"].dt.strftime("%b %d, %Y")
        )
        st.dataframe(
            weekly_table[["Week", "amount"]]
            .rename(columns={"amount": "Spent"})
            .style.format({"Spent": "${:,.2f}"}),
            use_container_width=True,
            hide_index=True,
        )

# ======================================================================= Breakdown
elif page == "Breakdown":
    view_mode = st.radio("View by", ["Month", "Year"], horizontal=True)

    if view_mode == "Month":
        months = analytics.all_months(df)
        default_index = months.index(CURRENT_MONTH) if CURRENT_MONTH in months else len(months) - 1
        selected_month = st.selectbox("Month", months, index=default_index, format_func=fmt_month)
        scope_df = df[df["month"] == selected_month] if not df.empty else df
        period_label = fmt_month(selected_month)
    else:
        years = sorted({d.year for d in df["date"]}) if not df.empty else [dt.date.today().year]
        this_year = dt.date.today().year
        default_year_index = years.index(this_year) if this_year in years else len(years) - 1
        selected_year = st.selectbox("Year", years, index=default_year_index)
        scope_df = df[df["date"].dt.year == selected_year] if not df.empty else df
        period_label = str(selected_year)

    income_total = scope_df.loc[scope_df["type"] == "income", "amount"].sum()
    breakdown = analytics.group_breakdown(scope_df, groups)
    expenses = breakdown["Needs"] + breakdown["Wants"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Income", f"${income_total:,.2f}")
    c2.metric("Expenses", f"${expenses:,.2f}")
    c3.metric("To Savings", f"${breakdown['Savings']:,.2f}")

    st.divider()
    st.subheader("Spending by Category")
    st.caption("Excludes Savings contributions. Colored by group — Needs (blue) / Wants (orange).")
    expense_df = scope_df[(scope_df["type"] == "expense") & (scope_df["category"].map(groups) != "Savings")]
    if expense_df.empty:
        st.info("No expenses this period.")
    else:
        by_cat = expense_df.groupby("category")["amount"].sum().sort_values(ascending=False)
        charts.category_bar_by_group(by_cat, groups, db.GROUP_COLORS)

    st.divider()
    st.subheader("Income by Category")
    income_df = scope_df[scope_df["type"] == "income"]
    if income_df.empty:
        st.info("No income this period.")
    else:
        by_cat_income = income_df.groupby("category")["amount"].sum().sort_values(ascending=False)
        charts.category_bar_flat(by_cat_income, TREND_COLORS["Income"])

    st.divider()
    st.subheader("Needs / Wants / Savings")
    components.percentage_bar(breakdown.to_dict())

    if view_mode == "Month":
        st.divider()
        first_month = analytics.first_transaction_month(df)
        prior_available = analytics.prior_months_available(selected_month, first_month) if first_month else []
        n_prior = len(prior_available)
        avg_label = {0: None, 1: "Previous month", 2: "Previous 2 months"}.get(n_prior, "3-month avg")
        title = {
            0: "This Month vs. Your Average",
            1: "This Month vs. Last Month",
            2: "This Month vs. Your 2-Month Average",
        }.get(n_prior, "This Month vs. Your 3-Month Average")
        st.subheader(title)

        if n_prior == 0:
            st.info("No previous data yet — this is your first month with transactions.")
        else:
            st.caption("Where you're spending more or less than your recent trailing average, by category. Excludes Savings.")
            expense_df = scope_df[(scope_df["type"] == "expense") & (scope_df["category"].map(groups) != "Savings")]
            if expense_df.empty:
                st.info("No expenses this period.")
            else:
                compare_rows = []
                for cat in sorted(expense_df["category"].unique()):
                    spent = float(expense_df.loc[expense_df["category"] == cat, "amount"].sum())
                    avg = analytics.three_month_avg(df, cat, selected_month, first_month)
                    compare_rows.append({"Category": cat, "This month": spent, avg_label: avg})
                compare_df = pd.DataFrame(compare_rows).set_index("Category")
                compare_df = compare_df.sort_values("This month", ascending=False)
                compare_colors = {"This month": COMPARE_COLORS["This month"], avg_label: COMPARE_COLORS["3-month avg"]}
                charts.compare_bar(compare_df, compare_colors)

    st.divider()
    st.subheader(f"Transactions — {period_label}")
    if scope_df.empty:
        st.info("No transactions in this period.")
    else:
        display = scope_df.copy()
        display["date"] = display["date"].dt.strftime("%Y-%m-%d")
        display["type"] = display["type"].str.capitalize()
        display = display[["date", "type", "category", "description", "amount"]].sort_values("date", ascending=False)
        display.columns = ["Date", "Type", "Category", "Description", "Amount"]
        st.dataframe(
            display.style.format({"Amount": "${:,.2f}"}),
            use_container_width=True,
            hide_index=True,
        )

# ================================================================= Monthly Budget
elif page == "Monthly Budget":
    expense_cats = db.category_names("expense")
    budgets = db.get_budgets()
    existing_budget_cats = {b["category"] for b in budgets}

    @st.dialog("Add a Budget")
    def add_budget_dialog():
        available = [c for c in expense_cats if c not in existing_budget_cats]
        if not available:
            st.info("Every expense category already has a budget.")
            return
        category = st.selectbox("Category", available)
        limit = st.number_input("Monthly limit", min_value=0.0, step=10.0, format="%.2f")
        if st.button("Save", type="primary"):
            db.set_budget(category, limit)
            st.rerun()

    @st.dialog("Edit Budget")
    def edit_budget_dialog(category: str, current_limit: float):
        st.write(f"**{category}**")
        limit = st.number_input("Monthly limit", min_value=0.0, step=10.0, value=float(current_limit), format="%.2f")
        if st.button("Save changes", type="primary"):
            db.set_budget(category, limit)
            st.rerun()

    @st.dialog("Remove Budget")
    def delete_budget_dialog(category: str):
        st.warning(f"Remove the budget for **{category}**?")
        c1, c2 = st.columns(2)
        if c1.button("Yes, remove", type="primary"):
            db.delete_budget(category)
            st.rerun()
        if c2.button("Cancel"):
            st.rerun()

    st.subheader("Monthly Budget")
    if not expense_cats:
        st.warning("No expense categories yet — add one on the Settings page first.")
    months = analytics.all_months(df)
    default_index = months.index(CURRENT_MONTH) if CURRENT_MONTH in months else len(months) - 1
    selected_month = st.selectbox("Month", months, index=default_index, key="budget_month", format_func=fmt_month)

    if not budgets:
        st.info("No budgets set yet — add one below.")
    else:
        first_month = analytics.first_transaction_month(df)
        month_df = df[df["month"] == selected_month] if not df.empty else df
        spent_by_cat = (
            month_df[month_df["type"] == "expense"].groupby("category")["amount"].sum()
            if not month_df.empty else pd.Series(dtype=float)
        )
        rows = []
        for b in budgets:
            category, limit = b["category"], b["monthly_limit"]
            spent = float(spent_by_cat.get(category, 0.0))
            pct = (spent / limit) if limit > 0 else 0.0
            rows.append(
                {
                    "Category": category, "Budget": limit, "Spent": spent, "Remaining": limit - spent,
                    "% Used": pct, "3-Month Avg": analytics.three_month_avg(df, category, selected_month, first_month),
                }
            )
        rows.sort(key=lambda r: -r["% Used"])

        for i, row in enumerate(rows):
            with st.container(key=f"hoverrow_budget_{i}"):
                rc1, rc2, rc3, rc4 = st.columns([0.9, 2.5, 3, 0.6])
                with rc1:
                    st.markdown(components.status_pill(row["% Used"]), unsafe_allow_html=True)
                with rc2:
                    st.markdown(f"**{row['Category']}**")
                with rc3:
                    st.markdown(f"{money(row['Spent'])} / {money(row['Budget'])}  ({row['% Used']:.0%})")
                with rc4:
                    with st.popover("⋮", key=f"budget_pop_{row['Category']}"):
                        if st.button("Edit", key=f"budget_edit_{row['Category']}", use_container_width=True):
                            edit_budget_dialog(row["Category"], row["Budget"])
                        if st.button("Delete", key=f"budget_del_{row['Category']}", use_container_width=True):
                            delete_budget_dialog(row["Category"])
                components.colored_progress(row["% Used"])
            st.write("")

        st.divider()
        st.caption("Full detail, including the 3-month trailing average:")
        table = pd.DataFrame(rows).set_index("Category")
        st.dataframe(
            table.style.format(
                {"Budget": "${:,.2f}", "Spent": "${:,.2f}", "Remaining": "${:,.2f}",
                 "% Used": "{:.0%}", "3-Month Avg": "${:,.2f}"}
            ),
            use_container_width=True,
        )

    st.divider()
    if st.button("+ Add budget"):
        add_budget_dialog()

# ========================================================================== Savings
elif page == "Savings":
    goals = db.get_savings_goals()

    @st.dialog("Add a Savings Goal")
    def add_goal_dialog():
        name = st.text_input("Goal name (e.g. Emergency Fund, Travel, Car)")
        c1, c2, c3 = st.columns(3)
        goal_amount = c1.number_input("Target amount", min_value=0.0, step=100.0, format="%.2f")
        monthly_target = c2.number_input("Monthly target", min_value=0.0, step=10.0, format="%.2f")
        starting_amount = c3.number_input("Starting balance (already saved)", min_value=0.0, step=10.0, format="%.2f")
        if st.button("Save", type="primary"):
            if not name.strip():
                st.error("Please name the goal.")
            else:
                db.add_savings_goal(name.strip(), goal_amount, monthly_target, starting_amount, dt.date.today().isoformat())
                st.rerun()

    @st.dialog("Edit Savings Goal")
    def edit_goal_dialog(goal):
        st.write(f"**{goal['name']}**")
        c1, c2, c3 = st.columns(3)
        goal_amount = c1.number_input("Target amount", min_value=0.0, step=100.0, value=float(goal["goal_amount"]), format="%.2f")
        monthly_target = c2.number_input("Monthly target", min_value=0.0, step=10.0, value=float(goal["monthly_target"]), format="%.2f")
        starting_amount = c3.number_input("Starting balance", min_value=0.0, step=10.0, value=float(goal["starting_amount"]), format="%.2f")
        if st.button("Save changes", type="primary"):
            db.update_savings_goal(goal["id"], goal_amount, monthly_target, starting_amount)
            st.rerun()

    @st.dialog("Delete Savings Goal")
    def delete_goal_dialog(goal):
        st.warning(
            f"Delete **{goal['name']}**? This can't be undone. Past contributions logged to it "
            "keep their category but lose the goal link."
        )
        c1, c2 = st.columns(2)
        if c1.button("Yes, delete", type="primary"):
            db.delete_savings_goal(goal["id"])
            st.rerun()
        if c2.button("Cancel"):
            st.rerun()

    st.subheader("Savings Goals")
    if not goals:
        st.info("No savings goals yet — add one below.")
    else:
        total_current = sum(analytics.savings_current_amount(g, df) for g in goals)
        total_goal = sum(g["goal_amount"] for g in goals)
        pct_all = min(total_current / total_goal, 1.0) if total_goal > 0 else 0.0
        st.markdown(f"**Total across all goals** — {money(total_current)} / {money(total_goal)} ({pct_all:.0%})")
        components.colored_progress(pct_all)
        st.divider()

        for i, g in enumerate(goals):
            current = analytics.savings_current_amount(g, df)
            pct = min(current / g["goal_amount"], 1.0) if g["goal_amount"] > 0 else 0.0
            with st.container(key=f"hoverrow_goal_{i}"):
                rc1, rc2 = st.columns([12, 1])
                with rc1:
                    st.markdown(f"**{g['name']}** — {money(current)} / {money(g['goal_amount'])}  ({pct:.0%})")
                    st.progress(pct)
                    st.caption(f"Monthly target: {money(g['monthly_target'])}")
                with rc2:
                    with st.popover("⋮", key=f"goal_pop_{g['id']}"):
                        if st.button("Edit", key=f"goal_edit_{g['id']}", use_container_width=True):
                            edit_goal_dialog(g)
                        if st.button("Delete", key=f"goal_del_{g['id']}", use_container_width=True):
                            delete_goal_dialog(g)
        st.divider()

    if st.button("+ Add goal"):
        add_goal_dialog()

    st.divider()
    st.subheader("Savings by Month")
    gbm_savings = analytics.group_breakdown_by_month(df, groups)
    savings_by_month = gbm_savings[gbm_savings["group"] == "Savings"] if not gbm_savings.empty else gbm_savings
    if savings_by_month.empty:
        st.caption("No savings contributions logged yet.")
    else:
        sm_months = sorted(savings_by_month["month"].unique())
        sm_order = [fmt_month(m) for m in sm_months]
        savings_by_month = savings_by_month.copy()
        savings_by_month["month_label"] = savings_by_month["month"].map(fmt_month)
        charts.single_series_bar(
            savings_by_month, x_col="month_label", y_col="amount", x_order=sm_order, color=db.GROUP_COLORS["Savings"]
        )

    st.divider()
    st.subheader("Add a Contribution")
    savings_categories = [c for c, g in groups.items() if g == "Savings"]
    if goals and savings_categories:
        with st.form("contribute", clear_on_submit=True):
            c1, c2 = st.columns(2)
            goal_name = c1.selectbox("Goal", [g["name"] for g in goals])
            amount = c2.number_input("Amount", min_value=0.0, step=10.0, format="%.2f")
            c3, c4 = st.columns(2)
            category = c3.selectbox("Category", savings_categories)
            date = c4.date_input("Date", value=dt.date.today())
            description = st.text_input("Description (optional)")
            if st.form_submit_button("Add contribution"):
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    goal_id = next(g["id"] for g in goals if g["name"] == goal_name)
                    db.add_transaction(
                        date.isoformat(), "expense", category, description or goal_name, amount, goal_id,
                    )
                    st.success(f"Added {money(amount)} to {goal_name}")
                    st.rerun()
    elif not savings_categories:
        st.caption("No 'Savings' group category exists yet — add or assign one on the Settings page.")
    else:
        st.caption("Add a goal first to log contributions toward it.")

# ===================================================================== Transactions
elif page == "Transactions":
    st.subheader("All Transactions")

    @st.dialog("Add a Transaction")
    def add_transaction_dialog():
        type_ = st.radio("Type", ["expense", "income"], horizontal=True, format_func=str.capitalize, key="dlg_add_type")
        cats = db.category_names(type_)
        if not cats:
            st.warning(f"No {type_} categories yet — add one on the Settings page first.")
            return
        c1, c2 = st.columns(2)
        date = c1.date_input("Date", value=dt.date.today(), key="dlg_add_date")
        category = c2.selectbox("Category", cats, key="dlg_add_cat")
        goal_id = None
        if type_ == "expense" and groups.get(category) == "Savings":
            dlg_goals = db.get_savings_goals()
            if dlg_goals:
                choice = st.selectbox("Savings goal (optional)", ["None"] + [g["name"] for g in dlg_goals], key="dlg_add_goal")
                if choice != "None":
                    goal_id = next(g["id"] for g in dlg_goals if g["name"] == choice)
        description = st.text_input("Description (optional)", key="dlg_add_desc")
        amount = st.number_input("Amount", min_value=0.0, step=1.0, format="%.2f", key="dlg_add_amt")
        if st.button("Add", type="primary", key="dlg_add_submit"):
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                db.add_transaction(date.isoformat(), type_, category, description, amount, goal_id)
                st.rerun()

    @st.dialog("Edit Transaction")
    def edit_transaction_dialog(txn):
        tid = int(txn["id"])
        type_ = st.radio(
            "Type", ["expense", "income"], horizontal=True, format_func=str.capitalize,
            index=0 if txn["type"] == "expense" else 1, key=f"dlg_edit_type_{tid}",
        )
        cats = db.category_names(type_)
        default_idx = cats.index(txn["category"]) if txn["category"] in cats else 0
        c1, c2 = st.columns(2)
        date = c1.date_input("Date", value=txn["date"].date(), key=f"dlg_edit_date_{tid}")
        category = c2.selectbox("Category", cats, index=default_idx if cats else 0, key=f"dlg_edit_cat_{tid}")
        description = st.text_input("Description", value=txn["description"] or "", key=f"dlg_edit_desc_{tid}")
        amount = st.number_input(
            "Amount", min_value=0.0, step=1.0, value=float(txn["amount"]), format="%.2f", key=f"dlg_edit_amt_{tid}"
        )
        if st.button("Save changes", type="primary", key=f"dlg_edit_submit_{tid}"):
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                raw_goal_id = txn["goal_id"] if category == txn["category"] else None
                # txn comes from a pandas DataFrame -- a column with any real goal_id mixed with
                # NULLs gets upcast to float64, so a missing goal_id arrives here as NaN rather
                # than None. Turso's wire protocol rejects non-finite floats outright (unlike
                # local sqlite3, which silently tolerates it), so this must be normalized back to
                # a real None before hitting the database.
                goal_id = None if pd.isna(raw_goal_id) else int(raw_goal_id)
                db.update_transaction(tid, date.isoformat(), type_, category, description, amount, goal_id)
                st.rerun()

    @st.dialog("Delete Transaction")
    def delete_transaction_dialog(txn):
        tid = int(txn["id"])
        st.warning(
            f"Delete transaction #{tid}: {txn['category']} — {money(txn['amount'])} "
            f"on {txn['date'].strftime('%Y-%m-%d')}? This can't be undone."
        )
        c1, c2 = st.columns(2)
        if c1.button("Yes, delete", type="primary", key=f"dlg_del_confirm_{tid}"):
            db.delete_transaction(tid)
            st.rerun()
        if c2.button("Cancel", key=f"dlg_del_cancel_{tid}"):
            st.rerun()

    if st.button("+ Add transaction", type="primary"):
        add_transaction_dialog()
    st.divider()

    if df.empty:
        st.info("No transactions yet.")
    else:
        f1, f2, f3 = st.columns([1, 1.4, 1.6])
        type_choice = f1.radio("Type", ["All", "Income", "Expense"], horizontal=True)
        min_date, max_date = df["date"].min().date(), df["date"].max().date()
        date_range = f2.date_input("Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        search = f3.text_input("Search category or description")

        f4, f5 = st.columns(2)
        cat_filter = f4.multiselect("Category (leave empty = all)", sorted(df["category"].unique()))
        group_filter = f5.multiselect("Group (leave empty = all)", db.GROUP_NAMES + ["Income"])

        filtered = df.copy()
        if type_choice != "All":
            filtered = filtered[filtered["type"] == type_choice.lower()]
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start, end = date_range
            filtered = filtered[(filtered["date"].dt.date >= start) & (filtered["date"].dt.date <= end)]
        if search:
            s = search.lower()
            filtered = filtered[
                filtered["description"].fillna("").str.lower().str.contains(s)
                | filtered["category"].str.lower().str.contains(s)
            ]
        if cat_filter:
            filtered = filtered[filtered["category"].isin(cat_filter)]
        if group_filter:
            expense_groups_selected = [g for g in group_filter if g in db.GROUP_NAMES]
            include_income = "Income" in group_filter
            mask = pd.Series(False, index=filtered.index)
            if expense_groups_selected:
                mask |= (filtered["type"] == "expense") & (filtered["category"].map(groups).isin(expense_groups_selected))
            if include_income:
                mask |= filtered["type"] == "income"
            filtered = filtered[mask]

        filtered = filtered.sort_values(["date", "id"], ascending=[False, False])
        income_total = filtered.loc[filtered["type"] == "income", "amount"].sum()
        expense_total = filtered.loc[filtered["type"] == "expense", "amount"].sum()
        st.caption(
            f"{len(filtered)} transaction(s) — Income: {money(income_total)} · Expenses: {money(expense_total)}"
        )

        PAGE_SIZE = 20
        total_pages = max(1, -(-len(filtered) // PAGE_SIZE))
        st.session_state.setdefault("txn_page", 1)
        st.session_state.txn_page = min(st.session_state.txn_page, total_pages)

        pcol1, pcol2, pcol3 = st.columns([1, 2, 1])
        if pcol1.button("◀ Prev", disabled=st.session_state.txn_page <= 1):
            st.session_state.txn_page -= 1
            st.rerun()
        pcol2.markdown(
            f"<div style='text-align:center;padding-top:6px;'>Page {st.session_state.txn_page} of {total_pages}</div>",
            unsafe_allow_html=True,
        )
        if pcol3.button("Next ▶", disabled=st.session_state.txn_page >= total_pages):
            st.session_state.txn_page += 1
            st.rerun()

        start_i = (st.session_state.txn_page - 1) * PAGE_SIZE
        page_df = filtered.iloc[start_i : start_i + PAGE_SIZE]

        with st.container(key="tablewrap_txn"):
            with st.container(key="tablehead_txn"):
                header = st.columns([0.6, 1, 0.8, 1.3, 2, 1, 0.5])
                for col, label in zip(header, ["ID", "Date", "Type", "Category", "Description", "Amount", ""]):
                    col.markdown(f"**{label}**")

            for i, (_, row) in enumerate(page_df.iterrows()):
                with st.container(key=f"hoverrow_txn_{i}"):
                    c = st.columns([0.6, 1, 0.8, 1.3, 2, 1, 0.5])
                    c[0].write(str(row["id"]))
                    c[1].write(row["date"].strftime("%Y-%m-%d"))
                    c[2].write(row["type"].capitalize())
                    c[3].write(row["category"])
                    desc = row["description"] or ""
                    if pd.notna(row.get("recurring_id")):
                        c[4].markdown(f"{desc}  {components.tag('AUTO', '#64748b')}", unsafe_allow_html=True)
                    else:
                        c[4].write(desc)
                    c[5].write(money(row["amount"]))
                    with c[6]:
                        with st.popover("⋮", key=f"txn_pop_{row['id']}"):
                            if st.button("Edit", key=f"txn_edit_{row['id']}", use_container_width=True):
                                edit_transaction_dialog(row)
                            if st.button("Delete", key=f"txn_del_{row['id']}", use_container_width=True):
                                delete_transaction_dialog(row)

# ========================================================================= Recurring
elif page == "Recurring Transactions":
    st.subheader("Recurring Transactions")
    st.caption(
        "Automatically logged when they come due — every time you open the app. "
        "Editing a rule only affects future occurrences; past transactions it already created "
        "stay as-is (edit those individually on the Transactions page)."
    )
    rules = db.get_recurring_rules()

    @st.dialog("Add a Recurring Transaction")
    def add_recurring_dialog():
        type_ = st.radio("Type", ["expense", "income"], horizontal=True, format_func=str.capitalize, key="rec_add_type")
        cats = db.category_names(type_)
        if not cats:
            st.warning(f"No {type_} categories yet — add one on the Settings page first.")
            return
        c1, c2 = st.columns(2)
        category = c1.selectbox("Category", cats, key="rec_add_cat")
        st.write("Repeats")
        fc1, fc2 = st.columns(2)
        freq_interval = fc1.number_input("Every", min_value=1, step=1, value=1, key="rec_add_freq_n")
        freq_unit = fc2.selectbox(
            "Unit", recurring.FREQUENCY_UNITS, index=2, format_func=lambda u: recurring.FREQUENCY_UNIT_LABELS[u],
            key="rec_add_freq_unit",
        )
        goal_id = None
        if type_ == "expense" and groups.get(category) == "Savings":
            rgoals = db.get_savings_goals()
            if rgoals:
                choice = st.selectbox("Savings goal (optional)", ["None"] + [g["name"] for g in rgoals], key="rec_add_goal")
                if choice != "None":
                    goal_id = next(g["id"] for g in rgoals if g["name"] == choice)
        description = st.text_input("Description (optional)", key="rec_add_desc")
        c3, c4 = st.columns(2)
        amount = c3.number_input("Amount", min_value=0.0, step=1.0, format="%.2f", key="rec_add_amt")
        start_date = c4.date_input("First occurrence", value=dt.date.today(), key="rec_add_start")
        st.caption("Past dates are backfilled immediately; future dates start on that day.")
        if st.button("Save", type="primary", key="rec_add_submit"):
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                db.add_recurring(
                    type_, category, description, amount, int(freq_interval), freq_unit,
                    start_date.isoformat(), goal_id,
                )
                st.rerun()

    @st.dialog("Edit Recurring Transaction")
    def edit_recurring_dialog(rule):
        rid = int(rule["id"])
        st.write(f"**{rule['category']}** ({rule['type'].capitalize()})")
        amount = st.number_input("Amount", min_value=0.0, step=1.0, value=float(rule["amount"]), format="%.2f", key=f"rec_edit_amt_{rid}")
        st.write("Repeats")
        fc1, fc2 = st.columns(2)
        freq_interval = fc1.number_input(
            "Every", min_value=1, step=1, value=int(rule["frequency_interval"]), key=f"rec_edit_freq_n_{rid}"
        )
        freq_unit = fc2.selectbox(
            "Unit", recurring.FREQUENCY_UNITS, index=recurring.FREQUENCY_UNITS.index(rule["frequency_unit"]),
            format_func=lambda u: recurring.FREQUENCY_UNIT_LABELS[u], key=f"rec_edit_freq_unit_{rid}",
        )
        description = st.text_input("Description", value=rule["description"] or "", key=f"rec_edit_desc_{rid}")
        next_due = st.date_input(
            "Next due date", value=dt.date.fromisoformat(rule["next_due_date"]), key=f"rec_edit_next_{rid}"
        )
        active = st.checkbox("Active", value=bool(rule["active"]), key=f"rec_edit_active_{rid}")
        if st.button("Save changes", type="primary", key=f"rec_edit_submit_{rid}"):
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                db.update_recurring(
                    rid, rule["category"], description, amount, int(freq_interval), freq_unit,
                    next_due.isoformat(), active,
                )
                st.rerun()

    @st.dialog("Delete Recurring Transaction")
    def delete_recurring_dialog(rule):
        rid = int(rule["id"])
        st.warning(
            f"Delete the recurring rule for **{rule['category']}** ({money(rule['amount'])}, "
            f"{recurring.frequency_label(rule['frequency_interval'], rule['frequency_unit'])})? "
            "Transactions it already created stay — this only stops future ones."
        )
        c1, c2 = st.columns(2)
        if c1.button("Yes, delete", type="primary", key=f"rec_del_confirm_{rid}"):
            db.delete_recurring(rid)
            st.rerun()
        if c2.button("Cancel", key=f"rec_del_cancel_{rid}"):
            st.rerun()

    if not rules:
        st.info("No recurring transactions yet — add one below.")
    else:
        with st.container(key="tablewrap_rec"):
            with st.container(key="tablehead_rec"):
                header = st.columns([1.4, 1.6, 1.2, 1.4, 0.9, 0.6])
                for col, label in zip(header, ["Category", "Description", "Amount", "Repeats", "Next Due", ""]):
                    col.markdown(f"**{label}**")
            for i, rule in enumerate(rules):
                with st.container(key=f"hoverrow_rec_{i}"):
                    c = st.columns([1.4, 1.6, 1.2, 1.4, 0.9, 0.6])
                    c[0].write(f"{rule['category']} ({rule['type'].capitalize()})")
                    c[1].write(rule["description"] or "")
                    c[2].write(money(rule["amount"]))
                    c[3].write(recurring.frequency_label(rule["frequency_interval"], rule["frequency_unit"]))
                    with c[4]:
                        if rule["active"]:
                            c[4].write(dt.date.fromisoformat(rule["next_due_date"]).strftime("%b %d, %Y"))
                        else:
                            st.markdown(components.tag("PAUSED", "#64748b"), unsafe_allow_html=True)
                    with c[5]:
                        with st.popover("⋮", key=f"rec_pop_{rule['id']}"):
                            if st.button("Edit", key=f"rec_edit_{rule['id']}", use_container_width=True):
                                edit_recurring_dialog(rule)
                            pause_label = "Resume" if not rule["active"] else "Pause"
                            if st.button(pause_label, key=f"rec_toggle_{rule['id']}", use_container_width=True):
                                db.set_recurring_active(rule["id"], not rule["active"])
                                st.rerun()
                            if st.button("Delete", key=f"rec_del_{rule['id']}", use_container_width=True):
                                delete_recurring_dialog(rule)

    st.divider()
    if st.button("+ Add recurring transaction"):
        add_recurring_dialog()

# ========================================================================= Settings
elif page == "Settings":
    cats = db.get_categories()

    @st.dialog("Add a Category")
    def add_category_dialog():
        name = st.text_input("Category name")
        c1, c2 = st.columns(2)
        new_type = c1.selectbox("Type", ["expense", "income"], format_func=str.capitalize)
        new_group = c2.selectbox("Group (expense only)", db.GROUP_NAMES)
        if st.button("Add", type="primary"):
            existing_names = {c["name"] for c in db.get_categories()}
            if not name.strip():
                st.error("Please name the category.")
            elif name.strip() in existing_names:
                st.error("That category already exists.")
            else:
                db.add_category(name.strip(), new_type, new_group if new_type == "expense" else None)
                st.rerun()

    @st.dialog("Edit Category")
    def edit_category_dialog(cat):
        old_name = cat["name"]
        new_name = st.text_input("Category name", value=old_name)
        new_type = st.selectbox(
            "Type", ["expense", "income"], index=0 if cat["type"] == "expense" else 1, format_func=str.capitalize
        )
        new_group = None
        if new_type == "expense":
            current = cat["group_name"] or "Wants"
            new_group = st.selectbox(
                "Group", db.GROUP_NAMES, index=db.GROUP_NAMES.index(current) if current in db.GROUP_NAMES else 0
            )
        else:
            st.caption("Income categories don't have a group.")

        if new_type != cat["type"]:
            st.warning(
                f"Changing the type also updates existing transactions and recurring rules using "
                f"'{old_name}' from {cat['type'].capitalize()} to {new_type.capitalize()}, so your "
                "totals stay consistent. Switching to Income also removes any budget set for it."
            )

        if st.button("Save changes", type="primary"):
            clean_name = new_name.strip()
            if not clean_name:
                st.error("Please name the category.")
            else:
                existing_names = {c["name"] for c in db.get_categories()} - {old_name}
                if clean_name in existing_names:
                    st.error("That category name already exists.")
                else:
                    db.update_category(old_name, clean_name, new_type, new_group)
                    st.rerun()

    @st.dialog("Remove Category")
    def delete_category_dialog(cat):
        st.warning(
            f"Remove **{cat['name']}**? Past transactions keep their category text — this only "
            "removes it from the Add transaction dropdown."
        )
        c1, c2 = st.columns(2)
        if c1.button("Yes, remove", type="primary"):
            db.delete_category(cat["name"])
            st.rerun()
        if c2.button("Cancel"):
            st.rerun()

    st.subheader("Categories")
    st.caption(
        "These populate the Add transaction dropdowns. Removing a category doesn't change past "
        "transactions — they keep their original category text."
    )
    if not cats:
        st.info("No categories yet — add one below.")
    else:
        with st.container(key="tablewrap_cat"):
            with st.container(key="tablehead_cat"):
                header = st.columns([2.5, 1, 1.5, 0.6])
                for col, label in zip(header, ["Category", "Type", "Group", ""]):
                    col.markdown(f"**{label}**")
            for i, cat in enumerate(cats):
                with st.container(key=f"hoverrow_cat_{i}"):
                    c = st.columns([2.5, 1, 1.5, 0.6])
                    c[0].write(cat["name"])
                    c[1].write(cat["type"].capitalize())
                    c[2].write(cat["group_name"] or "—")
                    with c[3]:
                        with st.popover("⋮", key=f"cat_pop_{cat['name']}"):
                            if st.button("Edit", key=f"cat_edit_{cat['name']}", use_container_width=True):
                                edit_category_dialog(cat)
                            if st.button("Delete", key=f"cat_del_{cat['name']}", use_container_width=True):
                                delete_category_dialog(cat)

    st.divider()
    if st.button("+ Add category"):
        add_category_dialog()

    st.divider()
    st.subheader("Weekly Spending Goals")
    st.caption(
        "Total is used on Snapshot's weekly check (Needs + Wants, excludes Savings) and on "
        "Overview's Weekly Breakdown when scoped to Total. Needs/Wants apply on Overview when "
        "scoped to that group."
    )
    wg1, wg2, wg3 = st.columns(3)
    needs_goal = wg1.number_input(
        "Needs weekly goal", min_value=0.0, step=10.0,
        value=float(db.get_setting("weekly_goal_needs", "200")), format="%.2f",
    )
    wants_goal = wg2.number_input(
        "Wants weekly goal", min_value=0.0, step=10.0,
        value=float(db.get_setting("weekly_goal_wants", "200")), format="%.2f",
    )
    total_goal = wg3.number_input(
        "Total weekly goal", min_value=0.0, step=10.0,
        value=float(db.get_setting("weekly_goal_total", "400")), format="%.2f",
    )
    if st.button("Save weekly goals"):
        db.set_setting("weekly_goal_needs", str(needs_goal))
        db.set_setting("weekly_goal_wants", str(wants_goal))
        db.set_setting("weekly_goal_total", str(total_goal))
        st.success("Saved.")
        st.rerun()
