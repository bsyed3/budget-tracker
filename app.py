"""Personal budget tracker built with Streamlit."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import analytics
import charts
import components
import db
import recurring

st.set_page_config(page_title="Budget Tracker", page_icon="💰", layout="wide")
db.init_db()

# Auto-generate any recurring transactions that have come due (checked on every load; cheap
# and idempotent — backfills every missed occurrence, not just one, if it's been a while).
_recurring_created = recurring.generate_due_transactions()
if _recurring_created and st.session_state.get("_last_recurring_toast") != dt.date.today().isoformat():
    st.toast(f"Added {_recurring_created} recurring transaction(s) that came due.")
    st.session_state["_last_recurring_toast"] = dt.date.today().isoformat()

CURRENT_MONTH = dt.date.today().strftime("%Y-%m")
money = components.money
fmt_month = analytics.format_month

TREND_COLORS = {"Income": "#0ea5e9", "Expenses": "#ef4444", "Savings": "#16a34a"}
COMPARE_COLORS = {"This month": "#2563eb", "3-month avg": "#94a3b8"}

page = st.sidebar.radio(
    "Go to",
    [
        "Snapshot", "Overview", "Breakdown", "Monthly Budget", "Savings",
        "Transactions", "Recurring", "Add Transaction", "Settings",
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
    st.subheader("Budget warnings")
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
            wc1, wc2 = st.columns([1, 6])
            with wc1:
                st.markdown(components.status_pill(pct), unsafe_allow_html=True)
            with wc2:
                st.write(f"**{category}** — {money(spent)} / {money(limit)} ({pct:.0%})")
            components.colored_progress(pct)

    st.divider()
    st.subheader("This week")
    weekly_goal = float(db.get_setting("weekly_spending_goal", "400"))
    this_week = analytics.weekly_totals(df, weeks=1)
    spent_this_week = float(this_week["amount"].iloc[0]) if not this_week.empty else 0.0
    week_pct = spent_this_week / weekly_goal if weekly_goal > 0 else 0.0
    wk1, wk2 = st.columns([1, 6])
    with wk1:
        st.markdown(components.status_pill(week_pct), unsafe_allow_html=True)
    with wk2:
        st.write(f"Spent {money(spent_this_week)} of {money(weekly_goal)} this week")
    components.colored_progress(week_pct)

    st.divider()
    st.subheader("Savings snapshot")
    goals = db.get_savings_goals()
    if not goals:
        st.caption("No savings goals yet — add one on the Savings page.")
    else:
        for g in goals:
            current = analytics.savings_current_amount(g, df)
            pct = min(current / g["goal_amount"], 1.0) if g["goal_amount"] > 0 else 0.0
            st.write(f"**{g['name']}** — {money(current)} / {money(g['goal_amount'])} ({pct:.0%})")
            st.progress(pct)

# ======================================================================= Overview
elif page == "Overview":
    st.caption("Everything you've logged, broken down by month and by week — no filters.")
    if df.empty:
        st.info("No transactions yet — this page fills in as you log income and expenses.")
    else:
        summary = analytics.monthly_summary(df, groups)
        month_order = list(summary.index)
        x_order = [fmt_month(m) for m in month_order]

        st.subheader("Income vs. expenses vs. savings over time")
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

        st.subheader("Expense breakdown (all time)")
        st.caption("Needs / Wants / Savings share of everything you've logged.")
        all_time_breakdown = analytics.group_breakdown(df, groups)
        components.percentage_bar(all_time_breakdown.to_dict())

        st.subheader("Needs / Wants / Savings by month")
        gbm = analytics.group_breakdown_by_month(df, groups)
        if not gbm.empty:
            gbm_months = sorted(gbm["month"].unique())
            gbm_order = [fmt_month(m) for m in gbm_months]
            gbm = gbm.copy()
            gbm["month_label"] = gbm["month"].map(fmt_month)
            charts.group_by_month_bar(gbm, x_order=gbm_order, colors=db.GROUP_COLORS)

        st.subheader("Monthly summary")
        display_cols = ["Total Income", "Needs", "Wants", "Savings", "Expenses", "Net Income"]
        display_summary = summary[display_cols].T
        display_summary.columns = [fmt_month(c) for c in display_summary.columns]
        st.dataframe(display_summary.style.format("${:,.2f}"), use_container_width=True)

        st.subheader("Expenses by category")
        expense_pivot = analytics.category_month_pivot(df, "expense")
        if not expense_pivot.empty:
            expense_pivot = expense_pivot.copy()
            expense_pivot.columns = [fmt_month(c) for c in expense_pivot.columns]
            st.dataframe(expense_pivot.style.format("${:,.2f}"), use_container_width=True)

        st.subheader("Income by category")
        income_pivot = analytics.category_month_pivot(df, "income")
        if not income_pivot.empty:
            income_pivot = income_pivot.copy()
            income_pivot.columns = [fmt_month(c) for c in income_pivot.columns]
            st.dataframe(income_pivot.style.format("${:,.2f}"), use_container_width=True)

        st.divider()
        st.subheader("Weekly breakdown (all time)")
        st.caption("Discretionary spend only — excludes Savings.")
        weekly_goal = float(db.get_setting("weekly_spending_goal", "400"))
        weekly = analytics.weekly_totals(df, all_time=True)
        weekly_chart_df = weekly.rename(columns={"amount": "Spent"})
        weekly_chart_df["Goal"] = weekly_goal
        charts.weekly_line(weekly_chart_df[["week_start", "Spent", "Goal"]])

        weekly_table = weekly.copy()
        weekly_table["Week"] = (
            weekly_table["week_start"].dt.strftime("%b %d, %Y") + " to " + weekly_table["week_end"].dt.strftime("%b %d, %Y")
        )
        weekly_table["Goal"] = weekly_goal
        weekly_table["Over/Under"] = weekly_table["amount"] - weekly_table["Goal"]
        st.dataframe(
            weekly_table[["Week", "amount", "Goal", "Over/Under"]]
            .rename(columns={"amount": "Spent"})
            .sort_values("Week", ascending=False)
            .style.format({"Spent": "${:,.2f}", "Goal": "${:,.2f}", "Over/Under": "${:,.2f}"}),
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
    left, right = st.columns(2)
    with left:
        st.subheader("Spending by category")
        st.caption("Excludes Savings contributions.")
        expense_df = scope_df[(scope_df["type"] == "expense") & (scope_df["category"].map(groups) != "Savings")]
        if expense_df.empty:
            st.info("No expenses this period.")
        else:
            by_cat = expense_df.groupby("category")["amount"].sum().sort_values(ascending=False)
            charts.category_bar(by_cat)
    with right:
        st.subheader("Income by category")
        income_df = scope_df[scope_df["type"] == "income"]
        if income_df.empty:
            st.info("No income this period.")
        else:
            by_cat_income = income_df.groupby("category")["amount"].sum().sort_values(ascending=False)
            charts.category_bar(by_cat_income)

    st.divider()
    st.subheader("Needs / Wants / Savings")
    components.percentage_bar(breakdown.to_dict())

    if view_mode == "Month":
        st.divider()
        st.subheader("This month vs. your 3-month average")
        st.caption("Where you're spending more or less than your recent trailing average, by category.")
        expense_df = scope_df[scope_df["type"] == "expense"]
        if expense_df.empty:
            st.info("No expenses this period.")
        else:
            compare_rows = []
            for cat in sorted(expense_df["category"].unique()):
                spent = float(expense_df.loc[expense_df["category"] == cat, "amount"].sum())
                avg3 = analytics.three_month_avg(df, cat, selected_month)
                compare_rows.append({"Category": cat, "This month": spent, "3-month avg": avg3})
            compare_df = pd.DataFrame(compare_rows).set_index("Category")
            compare_df = compare_df.sort_values("This month", ascending=False)
            charts.compare_bar(compare_df, COMPARE_COLORS)

    st.divider()
    st.subheader(f"Transactions — {period_label}")
    if scope_df.empty:
        st.info("No transactions in this period.")
    else:
        display = scope_df.copy()
        display["date"] = display["date"].dt.strftime("%Y-%m-%d")
        display["type"] = display["type"].str.capitalize()
        st.dataframe(
            display[["date", "type", "category", "description", "amount"]].sort_values("date", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

# ================================================================= Monthly Budget
elif page == "Monthly Budget":
    expense_cats = db.category_names("expense")
    budgets = db.get_budgets()
    existing_budget_cats = {b["category"] for b in budgets}

    @st.dialog("Add a budget")
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

    @st.dialog("Edit budget")
    def edit_budget_dialog(category: str, current_limit: float):
        st.write(f"**{category}**")
        limit = st.number_input("Monthly limit", min_value=0.0, step=10.0, value=float(current_limit), format="%.2f")
        if st.button("Save changes", type="primary"):
            db.set_budget(category, limit)
            st.rerun()

    @st.dialog("Remove budget")
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
                    "% Used": pct, "3-Month Avg": analytics.three_month_avg(df, category, selected_month),
                }
            )
        rows.sort(key=lambda r: -r["% Used"])

        for row in rows:
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

    @st.dialog("Add a savings goal")
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

    @st.dialog("Edit savings goal")
    def edit_goal_dialog(goal):
        st.write(f"**{goal['name']}**")
        c1, c2, c3 = st.columns(3)
        goal_amount = c1.number_input("Target amount", min_value=0.0, step=100.0, value=float(goal["goal_amount"]), format="%.2f")
        monthly_target = c2.number_input("Monthly target", min_value=0.0, step=10.0, value=float(goal["monthly_target"]), format="%.2f")
        starting_amount = c3.number_input("Starting balance", min_value=0.0, step=10.0, value=float(goal["starting_amount"]), format="%.2f")
        if st.button("Save changes", type="primary"):
            db.update_savings_goal(goal["id"], goal_amount, monthly_target, starting_amount)
            st.rerun()

    @st.dialog("Delete savings goal")
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

    st.subheader("Savings goals")
    if not goals:
        st.info("No savings goals yet — add one below.")
    else:
        total_current = sum(analytics.savings_current_amount(g, df) for g in goals)
        total_goal = sum(g["goal_amount"] for g in goals)
        pct_all = min(total_current / total_goal, 1.0) if total_goal > 0 else 0.0
        st.markdown(f"**Total across all goals** — {money(total_current)} / {money(total_goal)} ({pct_all:.0%})")
        components.colored_progress(pct_all)
        st.divider()

        for g in goals:
            current = analytics.savings_current_amount(g, df)
            pct = min(current / g["goal_amount"], 1.0) if g["goal_amount"] > 0 else 0.0
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
    st.subheader("Add a contribution")
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
    st.subheader("All transactions")

    @st.dialog("Add a transaction")
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

    @st.dialog("Edit transaction")
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
                goal_id = txn["goal_id"] if category == txn["category"] else None
                db.update_transaction(tid, date.isoformat(), type_, category, description, amount, goal_id)
                st.rerun()

    @st.dialog("Delete transaction")
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

    if df.empty:
        st.info("No transactions yet.")
    else:
        f1, f2, f3 = st.columns([1, 1.4, 1.6])
        type_choice = f1.radio("Type", ["All", "Income", "Expense"], horizontal=True)
        min_date, max_date = df["date"].min().date(), df["date"].max().date()
        date_range = f2.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
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

        header = st.columns([0.6, 1, 0.8, 1.3, 2, 1, 0.5])
        for col, label in zip(header, ["ID", "Date", "Type", "Category", "Description", "Amount", ""]):
            col.markdown(f"**{label}**")

        for _, row in page_df.iterrows():
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

    st.divider()
    if st.button("+ Add transaction"):
        add_transaction_dialog()

# ========================================================================= Recurring
elif page == "Recurring":
    st.subheader("Recurring transactions")
    st.caption(
        "Automatically logged when they come due — every time you open the app. "
        "Editing a rule only affects future occurrences; past transactions it already created "
        "stay as-is (edit those individually on the Transactions page)."
    )
    rules = db.get_recurring_rules()

    @st.dialog("Add a recurring transaction")
    def add_recurring_dialog():
        type_ = st.radio("Type", ["expense", "income"], horizontal=True, format_func=str.capitalize, key="rec_add_type")
        cats = db.category_names(type_)
        if not cats:
            st.warning(f"No {type_} categories yet — add one on the Settings page first.")
            return
        c1, c2 = st.columns(2)
        category = c1.selectbox("Category", cats, key="rec_add_cat")
        frequency = c2.selectbox(
            "Repeats", recurring.FREQUENCIES, format_func=lambda f: recurring.FREQUENCY_LABELS[f], key="rec_add_freq"
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
                db.add_recurring(type_, category, description, amount, frequency, start_date.isoformat(), goal_id)
                st.rerun()

    @st.dialog("Edit recurring transaction")
    def edit_recurring_dialog(rule):
        rid = int(rule["id"])
        st.write(f"**{rule['category']}** ({rule['type'].capitalize()})")
        c1, c2 = st.columns(2)
        amount = c1.number_input("Amount", min_value=0.0, step=1.0, value=float(rule["amount"]), format="%.2f", key=f"rec_edit_amt_{rid}")
        frequency = c2.selectbox(
            "Repeats", recurring.FREQUENCIES, index=recurring.FREQUENCIES.index(rule["frequency"]),
            format_func=lambda f: recurring.FREQUENCY_LABELS[f], key=f"rec_edit_freq_{rid}",
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
                db.update_recurring(rid, rule["category"], description, amount, frequency, next_due.isoformat(), active)
                st.rerun()

    @st.dialog("Delete recurring transaction")
    def delete_recurring_dialog(rule):
        rid = int(rule["id"])
        st.warning(
            f"Delete the recurring rule for **{rule['category']}** ({money(rule['amount'])}, "
            f"{recurring.FREQUENCY_LABELS[rule['frequency']]})? Transactions it already created stay — "
            "this only stops future ones."
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
        header = st.columns([1.4, 1.6, 1.2, 1.4, 0.9, 0.6])
        for col, label in zip(header, ["Category", "Description", "Amount", "Repeats", "Next due", ""]):
            col.markdown(f"**{label}**")
        for rule in rules:
            c = st.columns([1.4, 1.6, 1.2, 1.4, 0.9, 0.6])
            c[0].write(f"{rule['category']} ({rule['type'].capitalize()})")
            c[1].write(rule["description"] or "")
            c[2].write(money(rule["amount"]))
            c[3].write(recurring.FREQUENCY_LABELS[rule["frequency"]])
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

# ================================================================ Add Transaction
elif page == "Add Transaction":
    st.subheader("Add a transaction")
    type_ = st.radio("Type", ["expense", "income"], horizontal=True, format_func=str.capitalize)
    category_options = db.category_names(type_)

    if not category_options:
        st.warning(f"No {type_} categories yet. Add one on the Settings page first.")
    else:
        with st.form("add_transaction", clear_on_submit=True):
            c1, c2 = st.columns(2)
            date = c1.date_input("Date", value=dt.date.today())
            category = c2.selectbox("Category", category_options)

            goal_id = None
            if type_ == "expense" and groups.get(category) == "Savings":
                sgoals = db.get_savings_goals()
                if sgoals:
                    goal_choice = st.selectbox(
                        "Contributing to which savings goal? (optional)",
                        ["None"] + [g["name"] for g in sgoals],
                    )
                    if goal_choice != "None":
                        goal_id = next(g["id"] for g in sgoals if g["name"] == goal_choice)
                else:
                    st.caption("No savings goals set up yet — add one on the Savings page to link contributions.")

            description = st.text_input("Description (optional)")
            amount = st.number_input("Amount", min_value=0.0, step=1.0, format="%.2f")
            submitted = st.form_submit_button("Add")

            if submitted:
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    db.add_transaction(date.isoformat(), type_, category, description, amount, goal_id)
                    st.success(f"Added {type_.capitalize()}: {money(amount)} ({category})")
                    st.rerun()

# ========================================================================= Settings
elif page == "Settings":
    cats = db.get_categories()

    @st.dialog("Add a category")
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

    @st.dialog("Edit category")
    def edit_category_dialog(cat):
        st.write(f"**{cat['name']}** ({cat['type'].capitalize()})")
        if cat["type"] == "expense":
            current = cat["group_name"] or "Wants"
            new_group = st.selectbox(
                "Group", db.GROUP_NAMES, index=db.GROUP_NAMES.index(current) if current in db.GROUP_NAMES else 0
            )
            if st.button("Save changes", type="primary"):
                db.update_category_group(cat["name"], new_group)
                st.rerun()
        else:
            st.caption("Income categories don't have a group.")

    @st.dialog("Remove category")
    def delete_category_dialog(cat):
        st.warning(
            f"Remove **{cat['name']}**? Past transactions keep their category text — this only "
            "removes it from the Add Transaction dropdown."
        )
        c1, c2 = st.columns(2)
        if c1.button("Yes, remove", type="primary"):
            db.delete_category(cat["name"])
            st.rerun()
        if c2.button("Cancel"):
            st.rerun()

    st.subheader("Categories")
    st.caption(
        "These populate the Add Transaction dropdowns. Removing a category doesn't change past "
        "transactions — they keep their original category text."
    )
    if not cats:
        st.info("No categories yet — add one below.")
    else:
        header = st.columns([2.5, 1, 1.5, 0.6])
        for col, label in zip(header, ["Category", "Type", "Group", ""]):
            col.markdown(f"**{label}**")
        for cat in cats:
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
    st.subheader("Weekly spending goal")
    st.caption("Used on the Snapshot and Overview pages. Excludes Savings.")
    current_goal = float(db.get_setting("weekly_spending_goal", "400"))
    new_goal = st.number_input("Weekly goal", min_value=0.0, step=10.0, value=current_goal, format="%.2f")
    if st.button("Save weekly goal"):
        db.set_setting("weekly_spending_goal", str(new_goal))
        st.success("Saved.")
        st.rerun()
