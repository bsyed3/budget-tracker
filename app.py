"""Personal budget tracker built with Streamlit."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import analytics
import components
import db

st.set_page_config(page_title="Budget Tracker", page_icon="💰", layout="wide")
db.init_db()

CURRENT_MONTH = dt.date.today().strftime("%Y-%m")

st.title("💰 Budget Tracker")
page = st.sidebar.radio(
    "Go to",
    [
        "📸 Snapshot", "📊 Overview", "🔍 Explore", "🎯 Budget", "🏦 Savings",
        "🧾 Transactions", "➕ Add Transaction", "⚙️ Settings",
    ],
)

df = analytics.load_df()
groups = db.get_category_groups()

# ======================================================================= Snapshot
if page == "📸 Snapshot":
    st.caption(f"Quick overview for {CURRENT_MONTH}")
    month_df = df[df["month"] == CURRENT_MONTH] if not df.empty else df
    income = month_df.loc[month_df["type"] == "income", "amount"].sum()
    breakdown = analytics.group_breakdown(month_df, groups)
    expenses = breakdown["Needs"] + breakdown["Wants"] + breakdown["Donations"]
    net = income - breakdown.sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Income", f"${income:,.2f}")
    c2.metric("Expenses", f"${expenses:,.2f}")
    c3.metric("Net", f"${net:,.2f}")
    c4.metric("To Savings", f"${breakdown['Savings']:,.2f}")

    st.divider()
    st.subheader("⚠️ Budget warnings")
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
        st.caption("No budgets set yet — set some on the Budget page.")
    elif not warnings:
        st.success("No budgets are near or over their limit this month.")
    else:
        for category, spent, limit, pct in warnings:
            st.write(f"{components.status_badge(pct)} **{category}** — ${spent:,.2f} / ${limit:,.2f} ({pct:.0%})")
            components.colored_progress(pct)

    st.divider()
    st.subheader("This week")
    weekly_goal = float(db.get_setting("weekly_spending_goal", "400"))
    this_week = analytics.weekly_totals(df, weeks=1)
    spent_this_week = float(this_week["amount"].iloc[0]) if not this_week.empty else 0.0
    week_pct = spent_this_week / weekly_goal if weekly_goal > 0 else 0.0
    st.write(
        f"{components.status_badge(week_pct)} Spent ${spent_this_week:,.2f} of ${weekly_goal:,.2f} this week"
    )
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
            st.write(f"**{g['name']}** — ${current:,.2f} / ${g['goal_amount']:,.2f} ({pct:.0%})")
            st.progress(pct)

# ======================================================================= Overview
elif page == "📊 Overview":
    st.caption("Everything you've logged, broken down by month and by week — no filters.")
    if df.empty:
        st.info("No transactions yet — this page fills in as you log income and expenses.")
    else:
        summary = analytics.monthly_summary(df, groups)
        st.subheader("Income vs. expenses over time")
        st.caption("Expenses here = Needs + Wants + Donations. Savings contributions are excluded (that money isn't spent).")
        st.line_chart(summary[["Total Income", "Expenses"]].rename(columns={"Total Income": "Income"}))

        st.subheader("Monthly summary")
        display_cols = ["Total Income", "Needs", "Wants", "Savings", "Donations", "Expenses", "Net Income"]
        st.dataframe(summary[display_cols].T.style.format("${:,.2f}"), use_container_width=True)

        st.subheader("Expenses by category")
        expense_pivot = analytics.category_month_pivot(df, "expense")
        if not expense_pivot.empty:
            st.dataframe(expense_pivot.style.format("${:,.2f}"), use_container_width=True)

        st.subheader("Income by category")
        income_pivot = analytics.category_month_pivot(df, "income")
        if not income_pivot.empty:
            st.dataframe(income_pivot.style.format("${:,.2f}"), use_container_width=True)

        st.divider()
        st.subheader("Weekly breakdown (all time)")
        st.caption("Discretionary spend only — excludes Savings and Donations.")
        weekly_goal = float(db.get_setting("weekly_spending_goal", "400"))
        weekly = analytics.weekly_totals(df, all_time=True)
        weekly["Goal"] = weekly_goal
        st.line_chart(weekly.set_index("week_start")[["amount", "Goal"]].rename(columns={"amount": "Spent"}))

        weekly_table = weekly.copy()
        weekly_table["Week"] = (
            weekly_table["week_start"].dt.strftime("%Y-%m-%d") + " to " + weekly_table["week_end"].dt.strftime("%Y-%m-%d")
        )
        weekly_table["Over/Under"] = weekly_table["amount"] - weekly_table["Goal"]
        st.dataframe(
            weekly_table[["Week", "amount", "Goal", "Over/Under"]]
            .rename(columns={"amount": "Spent"})
            .sort_values("Week", ascending=False)
            .style.format({"Spent": "${:,.2f}", "Goal": "${:,.2f}", "Over/Under": "${:,.2f}"}),
            use_container_width=True,
            hide_index=True,
        )

# ========================================================================= Explore
elif page == "🔍 Explore":
    months = analytics.all_months(df)
    default_index = months.index(CURRENT_MONTH) if CURRENT_MONTH in months else len(months) - 1
    selected_month = st.selectbox("Month", months, index=default_index)
    month_df = df[df["month"] == selected_month] if not df.empty else df

    f1, f2 = st.columns(2)
    all_cats = sorted(month_df.loc[month_df["type"] == "expense", "category"].unique()) if not month_df.empty else []
    cat_filter = f1.multiselect("Category (leave empty for all)", all_cats)
    group_filter = f2.multiselect("Group (leave empty for all)", db.GROUP_NAMES)

    income_total = month_df.loc[month_df["type"] == "income", "amount"].sum()
    expense_filtered = month_df[month_df["type"] == "expense"]
    if group_filter:
        expense_filtered = expense_filtered[expense_filtered["category"].map(groups).isin(group_filter)]
    if cat_filter:
        expense_filtered = expense_filtered[expense_filtered["category"].isin(cat_filter)]

    breakdown = analytics.group_breakdown(expense_filtered, groups)
    expenses = breakdown["Needs"] + breakdown["Wants"] + breakdown["Donations"]
    has_filter = bool(group_filter) or bool(cat_filter)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Income", f"${income_total:,.2f}")
    c2.metric("Expenses" + (" (filtered)" if has_filter else ""), f"${expenses:,.2f}")
    c3.metric("Net" + (" (filtered)" if has_filter else ""), f"${income_total - breakdown.sum():,.2f}")
    c4.metric("To Savings", f"${breakdown['Savings']:,.2f}")

    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("Spending by category")
        if expense_filtered.empty:
            st.info("No expenses match this filter.")
        else:
            by_cat = expense_filtered.groupby("category")["amount"].sum().sort_values(ascending=False)
            st.bar_chart(by_cat)
    with right:
        st.subheader("Needs / Wants / Savings / Donations")
        components.percentage_bar(breakdown.to_dict())

    st.divider()
    st.subheader("Transactions in this view")
    table_df = expense_filtered if has_filter else month_df
    if table_df.empty:
        st.info("No transactions match this filter.")
    else:
        display = table_df.copy()
        display["date"] = display["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            display[["date", "type", "category", "description", "amount"]].sort_values("date", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

# =========================================================================== Budget
elif page == "🎯 Budget":
    st.subheader("Set a monthly budget")
    expense_cats = db.category_names("expense")
    if not expense_cats:
        st.warning("No expense categories yet — add one on the Settings page first.")
    else:
        with st.form("set_budget", clear_on_submit=True):
            c1, c2 = st.columns(2)
            category = c1.selectbox("Category", expense_cats)
            limit = c2.number_input("Monthly limit", min_value=0.0, step=10.0, format="%.2f")
            if st.form_submit_button("Save budget"):
                db.set_budget(category, limit)
                st.success(f"Budget set: {category} → ${limit:,.2f}/month")
                st.rerun()

    st.divider()
    st.subheader("Budget vs. actual")
    months = analytics.all_months(df)
    default_index = months.index(CURRENT_MONTH) if CURRENT_MONTH in months else len(months) - 1
    selected_month = st.selectbox("Month", months, index=default_index, key="budget_month")
    budgets = db.get_budgets()

    if not budgets:
        st.info("No budgets set yet — add one above.")
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
            st.write(
                f"{components.status_badge(row['% Used'])} **{row['Category']}** — "
                f"${row['Spent']:,.2f} / ${row['Budget']:,.2f} ({row['% Used']:.0%})  ·  "
                f"3-mo avg ${row['3-Month Avg']:,.2f}"
            )
            components.colored_progress(row["% Used"])

        st.divider()
        table = pd.DataFrame(rows).set_index("Category")
        st.dataframe(
            table.style.format(
                {"Budget": "${:,.2f}", "Spent": "${:,.2f}", "Remaining": "${:,.2f}",
                 "% Used": "{:.0%}", "3-Month Avg": "${:,.2f}"}
            ),
            use_container_width=True,
        )

        remove_cat = st.selectbox("Remove a budget", [b["category"] for b in budgets])
        if st.button("Remove budget"):
            db.delete_budget(remove_cat)
            st.success("Removed.")
            st.rerun()

# ========================================================================== Savings
elif page == "🏦 Savings":
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
                    st.success(f"Added ${amount:,.2f} to {goal_name}")
                    st.rerun()
    elif not savings_categories:
        st.caption("No 'Savings' group category exists yet — add or assign one on the Settings page.")
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

# ===================================================================== Transactions
elif page == "🧾 Transactions":
    st.subheader("All transactions")
    if df.empty:
        st.info("No transactions yet. Add one from the 'Add Transaction' page.")
    else:
        f1, f2, f3 = st.columns([1, 1.4, 1.6])
        type_choice = f1.radio("Type", ["All", "Income", "Expense"], horizontal=True)
        min_date, max_date = df["date"].min().date(), df["date"].max().date()
        date_range = f2.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        search = f3.text_input("Search category or description")

        f4, f5 = st.columns(2)
        cat_filter = f4.multiselect("Category (leave empty = all)", sorted(df["category"].unique()))
        group_filter = f5.multiselect("Group (leave empty = all, expenses only)", db.GROUP_NAMES)

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
            filtered = filtered[(filtered["type"] == "expense") & (filtered["category"].map(groups).isin(group_filter))]

        filtered = filtered.sort_values(["date", "id"], ascending=[False, False])
        st.caption(f"{len(filtered)} transaction(s) — total ${filtered['amount'].sum():,.2f}")

        # Pending-delete confirmation, shown above the table so it's never missed.
        pending_id = st.session_state.get("pending_delete_id")
        if pending_id is not None:
            match = df[df["id"] == pending_id]
            if not match.empty:
                r = match.iloc[0]
                st.warning(
                    f"Delete transaction #{pending_id}: {r['category']} — ${r['amount']:,.2f} "
                    f"on {r['date'].strftime('%Y-%m-%d')}? This can't be undone."
                )
                cc1, cc2 = st.columns([1, 4])
                if cc1.button("Yes, delete", type="primary"):
                    db.delete_transaction(int(pending_id))
                    st.session_state.pending_delete_id = None
                    st.success("Deleted.")
                    st.rerun()
                if cc2.button("Cancel"):
                    st.session_state.pending_delete_id = None
                    st.rerun()
            else:
                st.session_state.pending_delete_id = None

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

        header = st.columns([0.6, 1, 0.8, 1.3, 2, 1, 0.6])
        for col, label in zip(header, ["ID", "Date", "Type", "Category", "Description", "Amount", ""]):
            col.markdown(f"**{label}**")

        for _, row in page_df.iterrows():
            c = st.columns([0.6, 1, 0.8, 1.3, 2, 1, 0.6])
            c[0].write(str(row["id"]))
            c[1].write(row["date"].strftime("%Y-%m-%d"))
            c[2].write(row["type"])
            c[3].write(row["category"])
            c[4].write(row["description"] or "")
            c[5].write(f"${row['amount']:,.2f}")
            if c[6].button("🗑️", key=f"del_{row['id']}"):
                st.session_state.pending_delete_id = int(row["id"])
                st.rerun()

# ================================================================ Add Transaction
elif page == "➕ Add Transaction":
    st.subheader("Add a transaction")
    type_ = st.radio("Type", ["expense", "income"], horizontal=True)
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
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    db.add_transaction(date.isoformat(), type_, category, description, amount, goal_id)
                    st.success(f"Added {type_}: ${amount:,.2f} ({category})")
                    st.rerun()

# ========================================================================= Settings
elif page == "⚙️ Settings":
    st.subheader("Categories")
    st.caption(
        "These populate the Add Transaction dropdowns. Removing a category doesn't change past "
        "transactions — they keep their original category text."
    )
    cats = db.get_categories()
    if cats:
        table = pd.DataFrame([dict(c) for c in cats])
        table["group_name"] = table["group_name"].fillna("—")
        st.dataframe(
            table.rename(columns={"name": "Category", "type": "Type", "group_name": "Group"}),
            use_container_width=True, hide_index=True,
        )

    st.markdown("#### Add a category")
    with st.form("add_category", clear_on_submit=True):
        name = st.text_input("Category name")
        c1, c2 = st.columns(2)
        new_type = c1.selectbox("Type", ["expense", "income"])
        new_group = c2.selectbox("Group (expense only)", db.GROUP_NAMES)
        if st.form_submit_button("Add category"):
            existing_names = {c["name"] for c in cats}
            if not name.strip():
                st.error("Please name the category.")
            elif name.strip() in existing_names:
                st.error("That category already exists.")
            else:
                db.add_category(name.strip(), new_type, new_group if new_type == "expense" else None)
                st.success(f"Added category: {name.strip()}")
                st.rerun()

    expense_cats = [c for c in cats if c["type"] == "expense"]
    if expense_cats:
        st.markdown("#### Edit a category's group")
        c1, c2 = st.columns(2)
        edit_cat = c1.selectbox("Category", [c["name"] for c in expense_cats], key="edit_cat_select")
        current_group = next(c["group_name"] for c in expense_cats if c["name"] == edit_cat) or "Wants"
        new_group_val = c2.selectbox(
            "Group", db.GROUP_NAMES,
            index=db.GROUP_NAMES.index(current_group) if current_group in db.GROUP_NAMES else 0,
            key="edit_cat_group",
        )
        if st.button("Update group"):
            db.update_category_group(edit_cat, new_group_val)
            st.success("Updated.")
            st.rerun()

    if cats:
        st.markdown("#### Remove a category")
        remove_name = st.selectbox("Category to remove", [c["name"] for c in cats], key="remove_cat_select")
        if st.button("Remove category", type="primary"):
            db.delete_category(remove_name)
            st.success("Removed.")
            st.rerun()

    st.divider()
    st.subheader("Weekly spending goal")
    st.caption("Used on the Snapshot, Overview, and Explore pages. Excludes Savings and Donations categories.")
    current_goal = float(db.get_setting("weekly_spending_goal", "400"))
    new_goal = st.number_input("Weekly goal", min_value=0.0, step=10.0, value=current_goal, format="%.2f")
    if st.button("Save weekly goal"):
        db.set_setting("weekly_spending_goal", str(new_goal))
        st.success("Saved.")
        st.rerun()
