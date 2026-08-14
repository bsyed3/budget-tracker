"""Personal budget tracker built with Streamlit."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import analytics
import db

st.set_page_config(page_title="Budget Tracker", page_icon="💰", layout="wide")
db.init_db()

CURRENT_MONTH = dt.date.today().strftime("%Y-%m")

st.title("💰 Budget Tracker")
page = st.sidebar.radio(
    "Go to", ["Dashboard", "Add Transaction", "Transactions", "Master Table", "Budget", "Savings"]
)

df = analytics.load_df()
groups = db.get_category_groups()

# ===================================================================== Dashboard
if page == "Dashboard":
    months = analytics.all_months(df)
    options = ["All time"] + months
    default_index = options.index(CURRENT_MONTH) if CURRENT_MONTH in options else len(options) - 1
    selected = st.selectbox("Month", options, index=default_index)
    month_df = df if selected == "All time" else df[df["month"] == selected]

    income = month_df.loc[month_df["type"] == "income", "amount"].sum()
    expenses = month_df.loc[month_df["type"] == "expense", "amount"].sum()
    savings_contrib = month_df.loc[
        (month_df["type"] == "expense") & (month_df["category"] == "Savings/Investments"), "amount"
    ].sum()
    net = income - expenses

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Income", f"${income:,.2f}")
    c2.metric("Expenses", f"${expenses:,.2f}")
    c3.metric("Net", f"${net:,.2f}")
    c4.metric("To Savings", f"${savings_contrib:,.2f}")

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Spending by category")
        expense_df = month_df[month_df["type"] == "expense"]
        if expense_df.empty:
            st.info("No expenses recorded for this period yet.")
        else:
            by_cat = expense_df.groupby("category")["amount"].sum().sort_values(ascending=False)
            st.bar_chart(by_cat)

    with right:
        st.subheader("Needs / Wants / Savings & Donations")
        expense_df = month_df[month_df["type"] == "expense"].copy()
        if expense_df.empty:
            st.info("No expenses recorded for this period yet.")
        else:
            expense_df["group"] = expense_df["category"].map(groups).fillna("Wants")
            by_group = expense_df.groupby("group")["amount"].sum().reindex(db.GROUP_NAMES, fill_value=0.0)
            st.bar_chart(by_group)

    st.divider()
    st.subheader("Income vs. expenses over time")
    if df.empty:
        st.info("No transactions yet.")
    else:
        summary = analytics.monthly_summary(df, groups)
        trend = pd.DataFrame(
            {
                "Income": summary["Total Income"],
                "Expenses": summary["Total Needs"] + summary["Total Wants"] + summary["Total Savings & Donations"],
            }
        )
        st.line_chart(trend)

    st.divider()
    st.subheader("Weekly spending vs. goal")
    st.caption("Week starting date shown. Excludes Savings/Investments and Donations.")
    weekly_goal = float(db.get_setting("weekly_spending_goal", "400"))
    weekly = analytics.weekly_totals(df, weeks=12).set_index("week_start")
    weekly["Goal"] = weekly_goal
    st.bar_chart(weekly[["amount", "Goal"]].rename(columns={"amount": "Spent"}), stack=False)

# ================================================================ Add Transaction
elif page == "Add Transaction":
    st.subheader("Add a transaction")
    type_ = st.radio("Type", ["expense", "income"], horizontal=True)
    category_options = (db.EXPENSE_CATEGORIES if type_ == "expense" else db.INCOME_CATEGORIES) + ["Custom..."]

    with st.form("add_transaction", clear_on_submit=True):
        c1, c2 = st.columns(2)
        date = c1.date_input("Date", value=dt.date.today())
        category = c2.selectbox("Category", category_options)
        custom_category = ""
        if category == "Custom...":
            custom_category = st.text_input("Custom category name")

        goal_id = None
        if type_ == "expense" and category == "Savings/Investments":
            goals = db.get_savings_goals()
            if goals:
                goal_choice = st.selectbox(
                    "Contributing to which savings goal? (optional)",
                    ["None"] + [g["name"] for g in goals],
                )
                if goal_choice != "None":
                    goal_id = next(g["id"] for g in goals if g["name"] == goal_choice)
            else:
                st.caption("No savings goals set up yet — add one on the Savings page to link contributions.")

        description = st.text_input("Description (optional)")
        amount = st.number_input("Amount", min_value=0.0, step=1.0, format="%.2f")
        submitted = st.form_submit_button("Add")

        if submitted:
            final_category = custom_category.strip() if category == "Custom..." else category
            if not final_category:
                st.error("Please provide a category.")
            elif amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                db.add_transaction(date.isoformat(), type_, final_category, description, amount, goal_id)
                st.success(f"Added {type_}: ${amount:,.2f} ({final_category})")
                st.rerun()

# =================================================================== Transactions
elif page == "Transactions":
    st.subheader("All transactions")
    if df.empty:
        st.info("No transactions yet. Add one from the 'Add Transaction' page.")
    else:
        f1, f2, f3 = st.columns(3)
        type_filter = f1.multiselect("Type", ["income", "expense"], default=["income", "expense"])
        all_cats = sorted(df["category"].unique())
        cat_filter = f2.multiselect("Category", all_cats, default=all_cats)
        months = analytics.all_months(df, pad_current=False)
        month_filter = f3.multiselect("Month", months, default=months)

        shown = df[
            df["type"].isin(type_filter) & df["category"].isin(cat_filter) & df["month"].isin(month_filter)
        ]
        display = shown.copy()
        display["date"] = display["date"].dt.strftime("%Y-%m-%d")
        st.caption(f"{len(display)} transaction(s) — total ${shown['amount'].sum():,.2f}")
        st.dataframe(
            display[["id", "date", "type", "category", "description", "amount"]],
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.subheader("Delete a transaction")
        if not shown.empty:
            to_delete = st.selectbox(
                "Select by ID",
                shown["id"],
                format_func=lambda i: f"#{i} — {shown.loc[shown['id'] == i, 'category'].values[0]} "
                f"(${shown.loc[shown['id'] == i, 'amount'].values[0]:,.2f})",
            )
            if st.button("Delete selected transaction", type="primary"):
                db.delete_transaction(int(to_delete))
                st.success("Deleted.")
                st.rerun()

# =================================================================== Master Table
elif page == "Master Table":
    st.subheader("Month-by-month breakdown")
    if df.empty:
        st.info("No transactions yet — this table fills in as you log income and expenses.")
    else:
        st.markdown("#### Summary")
        summary = analytics.monthly_summary(df, groups).T
        st.dataframe(summary.style.format("${:,.2f}"), use_container_width=True)

        st.markdown("#### Expenses by category")
        expense_pivot = analytics.category_month_pivot(df, "expense")
        if expense_pivot.empty:
            st.info("No expenses recorded yet.")
        else:
            st.dataframe(expense_pivot.style.format("${:,.2f}"), use_container_width=True)

        st.markdown("#### Income by category")
        income_pivot = analytics.category_month_pivot(df, "income")
        if income_pivot.empty:
            st.info("No income recorded yet.")
        else:
            st.dataframe(income_pivot.style.format("${:,.2f}"), use_container_width=True)

    st.caption(
        "This table covers every month you have data for — past or future — as soon as you log a transaction "
        "in it."
    )

# =========================================================================== Budget
elif page == "Budget":
    st.subheader("Set a monthly budget")
    with st.form("set_budget", clear_on_submit=True):
        c1, c2 = st.columns(2)
        category = c1.selectbox("Category", db.EXPENSE_CATEGORIES)
        limit = c2.number_input("Monthly limit", min_value=0.0, step=10.0, format="%.2f")
        if st.form_submit_button("Save budget"):
            db.set_budget(category, limit)
            st.success(f"Budget set: {category} → ${limit:,.2f}/month")
            st.rerun()

    st.divider()
    st.subheader("Budget vs. actual")
    months = analytics.all_months(df)
    default_index = months.index(CURRENT_MONTH) if CURRENT_MONTH in months else len(months) - 1
    selected_month = st.selectbox("Month", months, index=default_index)
    budgets = db.get_budgets()

    if not budgets:
        st.info("No budgets set yet — add one above.")
    else:
        month_df = df[df["month"] == selected_month] if not df.empty else df
        spent_by_cat = (
            month_df[month_df["type"] == "expense"].groupby("category")["amount"].sum()
            if not month_df.empty
            else pd.Series(dtype=float)
        )
        rows = []
        for b in budgets:
            category, limit = b["category"], b["monthly_limit"]
            spent = float(spent_by_cat.get(category, 0.0))
            remaining = limit - spent
            pct = (spent / limit) if limit > 0 else 0.0
            avg3 = analytics.three_month_avg(df, category, selected_month)
            rows.append(
                {
                    "Category": category,
                    "Budget": limit,
                    "Spent": spent,
                    "Remaining": remaining,
                    "% Used": pct,
                    "3-Month Avg": avg3,
                }
            )
        table = pd.DataFrame(rows).set_index("Category")
        st.dataframe(
            table.style.format(
                {"Budget": "${:,.2f}", "Spent": "${:,.2f}", "Remaining": "${:,.2f}",
                 "% Used": "{:.0%}", "3-Month Avg": "${:,.2f}"}
            ),
            use_container_width=True,
        )
        for _, row in table.reset_index().iterrows():
            st.write(f"**{row['Category']}** — ${row['Spent']:,.2f} / ${row['Budget']:,.2f}")
            st.progress(min(row["% Used"], 1.0))

        remove_cat = st.selectbox("Remove a budget", [b["category"] for b in budgets])
        if st.button("Remove budget"):
            db.delete_budget(remove_cat)
            st.success("Removed.")
            st.rerun()

    st.divider()
    st.subheader("Weekly spending goal")
    st.caption("Used on the Dashboard's weekly chart. Excludes Savings/Investments and Donations.")
    current_goal = float(db.get_setting("weekly_spending_goal", "400"))
    new_goal = st.number_input("Weekly goal", min_value=0.0, step=10.0, value=current_goal, format="%.2f")
    if st.button("Save weekly goal"):
        db.set_setting("weekly_spending_goal", str(new_goal))
        st.success("Saved.")
        st.rerun()

    st.divider()
    st.subheader("Category groups (Needs / Wants / Savings & Donations)")
    st.caption("Used for the Needs/Wants/Savings breakdown on the Dashboard and Master Table.")
    for category in db.EXPENSE_CATEGORIES:
        current_group = groups.get(category, "Wants")
        new_group = st.selectbox(
            category, db.GROUP_NAMES, index=db.GROUP_NAMES.index(current_group), key=f"group_{category}"
        )
        if new_group != current_group:
            db.set_category_group(category, new_group)
            st.rerun()

# ========================================================================== Savings
elif page == "Savings":
    st.subheader("Savings goals")
    goals = db.get_savings_goals()

    if not goals:
        st.info("No savings goals yet — add one below.")
    else:
        for g in goals:
            current = analytics.savings_current_amount(g, df)
            pct = min(current / g["goal_amount"], 1.0) if g["goal_amount"] > 0 else 0.0
            st.markdown(f"**{g['name']}** — ${current:,.2f} / ${g['goal_amount']:,.2f}  ({pct:.0%})")
            st.progress(pct)
            st.caption(f"Monthly target: ${g['monthly_target']:,.2f}")
        st.divider()

    st.subheader("Add a contribution")
    if goals:
        with st.form("contribute", clear_on_submit=True):
            c1, c2 = st.columns(2)
            goal_name = c1.selectbox("Goal", [g["name"] for g in goals])
            amount = c2.number_input("Amount", min_value=0.0, step=10.0, format="%.2f")
            date = st.date_input("Date", value=dt.date.today())
            description = st.text_input("Description (optional)")
            if st.form_submit_button("Add contribution"):
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    goal_id = next(g["id"] for g in goals if g["name"] == goal_name)
                    db.add_transaction(
                        date.isoformat(), "expense", "Savings/Investments", description or goal_name,
                        amount, goal_id,
                    )
                    st.success(f"Added ${amount:,.2f} to {goal_name}")
                    st.rerun()
    else:
        st.caption("Add a goal first to log contributions toward it.")

    st.divider()
    st.subheader("Add / edit a goal")
    with st.form("add_goal", clear_on_submit=True):
        name = st.text_input("Goal name (e.g. Emergency Fund, Travel, Car)")
        c1, c2, c3 = st.columns(3)
        goal_amount = c1.number_input("Target amount", min_value=0.0, step=100.0, format="%.2f")
        monthly_target = c2.number_input("Monthly contribution target", min_value=0.0, step=10.0, format="%.2f")
        starting_amount = c3.number_input("Starting balance (already saved)", min_value=0.0, step=10.0, format="%.2f")
        if st.form_submit_button("Save goal"):
            if not name.strip():
                st.error("Please name the goal.")
            else:
                existing = {g["name"]: g["id"] for g in goals}
                if name in existing:
                    db.update_savings_goal(existing[name], goal_amount, monthly_target, starting_amount)
                else:
                    db.add_savings_goal(name.strip(), goal_amount, monthly_target, starting_amount, dt.date.today().isoformat())
                st.success(f"Saved goal: {name}")
                st.rerun()

    if goals:
        st.divider()
        remove_goal = st.selectbox("Remove a goal", [g["name"] for g in goals])
        if st.button("Remove goal", type="primary"):
            goal_id = next(g["id"] for g in goals if g["name"] == remove_goal)
            db.delete_savings_goal(goal_id)
            st.success("Removed.")
            st.rerun()
