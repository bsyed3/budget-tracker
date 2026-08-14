"""Personal budget tracker built with Streamlit."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="Budget Tracker", page_icon="💰", layout="wide")
db.init_db()


def load_df() -> pd.DataFrame:
    rows = db.get_transactions()
    if not rows:
        return pd.DataFrame(columns=["id", "date", "type", "category", "description", "amount"])
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


def month_options(df: pd.DataFrame) -> list[str]:
    current = dt.date.today().strftime("%Y-%m")
    if df.empty:
        return [current]
    months = sorted(df["date"].dt.strftime("%Y-%m").unique(), reverse=True)
    if current not in months:
        months = [current] + months
    return months


st.title("💰 Budget Tracker")

page = st.sidebar.radio("Go to", ["Dashboard", "Add Transaction", "Transactions", "Budgets"])

df = load_df()

# ---------------------------------------------------------------- Dashboard
if page == "Dashboard":
    months = month_options(df)
    selected_month = st.selectbox("Month", months, index=0)
    month_df = df[df["date"].dt.strftime("%Y-%m") == selected_month] if not df.empty else df

    income = month_df.loc[month_df["type"] == "income", "amount"].sum()
    expenses = month_df.loc[month_df["type"] == "expense", "amount"].sum()
    net = income - expenses

    col1, col2, col3 = st.columns(3)
    col1.metric("Income", f"${income:,.2f}")
    col2.metric("Expenses", f"${expenses:,.2f}")
    col3.metric("Net", f"${net:,.2f}", delta=f"{net:,.2f}")

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Spending by category")
        expense_df = month_df[month_df["type"] == "expense"]
        if expense_df.empty:
            st.info("No expenses recorded for this month yet.")
        else:
            by_cat = expense_df.groupby("category")["amount"].sum().sort_values(ascending=False)
            st.bar_chart(by_cat)

    with right:
        st.subheader("Budget vs. actual")
        budgets = {b["category"]: b["monthly_limit"] for b in db.get_budgets()}
        if not budgets:
            st.info("No budgets set yet. Add some on the Budgets page.")
        else:
            spent_by_cat = month_df[month_df["type"] == "expense"].groupby("category")["amount"].sum()
            for category, limit in sorted(budgets.items()):
                spent = float(spent_by_cat.get(category, 0.0))
                pct = min(spent / limit, 1.0) if limit > 0 else 0.0
                st.write(f"**{category}** — ${spent:,.2f} / ${limit:,.2f}")
                st.progress(pct)

    st.divider()
    st.subheader("Daily balance trend")
    if month_df.empty:
        st.info("No transactions yet this month.")
    else:
        signed = month_df.copy()
        signed["signed_amount"] = signed.apply(
            lambda r: r["amount"] if r["type"] == "income" else -r["amount"], axis=1
        )
        daily = signed.groupby(signed["date"].dt.date)["signed_amount"].sum().sort_index().cumsum()
        st.line_chart(daily)

# ------------------------------------------------------------ Add Transaction
elif page == "Add Transaction":
    st.subheader("Add a transaction")
    with st.form("add_transaction", clear_on_submit=True):
        c1, c2 = st.columns(2)
        date = c1.date_input("Date", value=dt.date.today())
        type_ = c2.selectbox("Type", ["expense", "income"])
        category = st.selectbox("Category", db.DEFAULT_CATEGORIES + ["Income", "Custom..."])
        custom_category = ""
        if category == "Custom...":
            custom_category = st.text_input("Custom category name")
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
                db.add_transaction(date.isoformat(), type_, final_category, description, amount)
                st.success(f"Added {type_}: ${amount:,.2f} ({final_category})")
                st.rerun()

# --------------------------------------------------------------- Transactions
elif page == "Transactions":
    st.subheader("All transactions")
    if df.empty:
        st.info("No transactions yet. Add one from the 'Add Transaction' page.")
    else:
        filter_col1, filter_col2 = st.columns(2)
        type_filter = filter_col1.multiselect("Type", ["income", "expense"], default=["income", "expense"])
        cat_filter = filter_col2.multiselect(
            "Category", sorted(df["category"].unique()), default=sorted(df["category"].unique())
        )
        shown = df[df["type"].isin(type_filter) & df["category"].isin(cat_filter)]
        display = shown.copy()
        display["date"] = display["date"].dt.strftime("%Y-%m-%d")
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

# ------------------------------------------------------------------- Budgets
elif page == "Budgets":
    st.subheader("Monthly budgets")
    with st.form("set_budget", clear_on_submit=True):
        c1, c2 = st.columns(2)
        category = c1.selectbox("Category", db.DEFAULT_CATEGORIES)
        limit = c2.number_input("Monthly limit", min_value=0.0, step=10.0, format="%.2f")
        if st.form_submit_button("Save budget"):
            db.set_budget(category, limit)
            st.success(f"Budget set: {category} → ${limit:,.2f}/month")
            st.rerun()

    st.divider()
    budgets = db.get_budgets()
    if not budgets:
        st.info("No budgets set yet.")
    else:
        budget_df = pd.DataFrame([dict(b) for b in budgets])
        st.dataframe(budget_df, use_container_width=True, hide_index=True)
        remove_cat = st.selectbox("Remove a budget", [b["category"] for b in budgets])
        if st.button("Remove budget"):
            db.delete_budget(remove_cat)
            st.success("Removed.")
            st.rerun()
