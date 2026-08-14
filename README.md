# Budget Tracker

A personal budgeting app built with [Streamlit](https://streamlit.io) and SQLite, modeled on a
prior Excel-based budget (transactions, income, monthly pivots, savings goals, and budgets).

## Pages

- **📸 Snapshot** — quick overview of the current month: income/expenses/net, budget warnings
  (🔴 over / 🟡 near limit), this week's spending vs. goal, and a savings mini-summary
- **📊 Overview** — everything you've logged, unfiltered: income vs. expenses trend, an all-time
  Needs/Wants/Savings breakdown, monthly summary, category pivots, and an all-time weekly breakdown
- **📅 Breakdown** — pick a month or a year; shows spending/income by category, a color-coded
  Needs/Wants/Savings bar, a "this month vs. your 3-month average" comparison, and the matching
  transactions
- **🎯 Budget** — set a monthly budget per expense category; see spent/remaining/% used, sorted
  worst-first with color-coded warning bars scaled to 100% (the 3-month average lives in the
  detail table below, not the bars)
- **🏦 Savings** — named savings goals with progress bars; log contributions as linked transactions
- **🧾 Transactions** — browse/search/filter everything, split income/expense totals, pagination
- **➕ Add Transaction** — log income or an expense, categories pulled live from Settings
- **⚙️ Settings** — manage categories (add/remove, assign Needs/Wants/Savings group), set the
  weekly spending goal

Every table (Savings goals, Budgets, Transactions, Categories) supports add/edit/delete directly:
a "➕ Add" button below the table opens a popup form, and each row has a "⋮" menu with Edit/Delete.

Categories are fully user-editable on the Settings page — there's no hardcoded category list.
"Expenses" in trend charts = Needs + Wants; Savings contributions are tracked separately since
that money isn't spent. Donations counts as a Need.

## Getting started

```bash
python -m venv venv
venv\Scripts\activate      # on Windows
pip install -r requirements.txt
streamlit run app.py
```

Data is stored locally in `data/budget.db` (SQLite), which is git-ignored.

## Importing historical data

To import transactions, income, savings goals, and budgets from an old Excel budget workbook
(expects sheets named `Transactions`, `Income`, `Savings`, and `Budget Tracking` with the same
column layout as the original):

```bash
python import_xlsx.py "C:\path\to\your\budget.xlsx"
```

This only adds rows — it doesn't wipe existing data. Run it once against a fresh `data/budget.db`
to avoid duplicate transactions.

## Roadmap

- Possible future move to a React frontend + Python (FastAPI) backend if the app outgrows Streamlit.
