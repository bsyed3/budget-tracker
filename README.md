# Budget Tracker

A personal budgeting app built with [Streamlit](https://streamlit.io) and SQLite, modeled on a
prior Excel-based budget (transactions, income, monthly pivots, savings goals, and budgets).

## Pages

- **Snapshot** — the only page with the app title. Quick overview of the current month:
  income/expenses/net, budget warnings, this week's spending vs. goal, and a savings mini-summary
- **Overview** — everything you've logged, unfiltered: income/expenses/savings trend, an all-time
  Needs/Wants/Savings breakdown, Needs/Wants/Savings by month (toggle between dollar amounts and
  percentage-of-month), monthly summary, category pivots, and an all-time weekly breakdown you can
  scope to Wants / Needs / Total
- **Breakdown** — pick a month or a year; shows spending by category (colored by group — Needs
  blue, Wants orange, Savings excluded) and income by category (flat color) on separate rows, a
  Needs/Wants/Savings bar, a side-by-side "this month vs. your trailing average" comparison
  (Savings excluded; auto-adjusts to 1 or 2 months right after your first month of data, then a
  full 3-month average from then on), and the matching transactions
- **Monthly Budget** — set a monthly budget per expense category; see spent/remaining/% used,
  sorted worst-first with color-coded warning bars scaled to 100% and a status pill (OVER/NEAR/OK)
  (the 3-month average lives in the detail table below, not the bars)
- **Savings** — a total-across-all-goals summary, a savings-by-month chart, and named savings
  goals with progress bars; log contributions as linked transactions
- **Transactions** — browse/search/filter everything, income/expense totals shown separately,
  pagination; add, edit, or delete any transaction via the prominent "+ Add transaction" button
  or each row's "⋮" menu
- **Recurring Transactions** — rules for transactions that repeat (weekly / every 2 weeks /
  monthly / yearly), e.g. a paycheck every 2 weeks or insurance on the same day each month.
  Auto-generated as transactions every time the app is opened — including backfilling any
  occurrences missed while it was closed. Pause, edit, or delete a rule anytime; past transactions
  it already created are untouched either way
- **Settings** — manage categories (add/remove, rename, change type, assign Needs/Wants/Savings
  group — renaming or re-typing a category cascades to its existing transactions/budgets/recurring
  rules so history stays consistent), set the weekly spending goal

There's no separate "Add Transaction" page — adding happens via the dialog on the Transactions
page (and Recurring Transactions, Budget, Savings, Settings pages for their own kinds of rows).
Every table supports add/edit/delete directly: a "+ Add" button opens a popup form, and each row
has a "⋮" menu with Edit/Delete.

Categories are fully user-editable on the Settings page — there's no hardcoded category list.
"Expenses" in trend charts = Needs + Wants; Savings contributions are tracked separately since
that money isn't spent. Donations counts as a Need. All charts are built with Altair (`charts.py`)
so they're colorful but static — no accidental scroll-zoom/pan distorting the scale, and axis
labels line up exactly with real data points instead of interpolating.

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
