# Budget Tracker

A personal budgeting app built with [Streamlit](https://streamlit.io) and SQLite, modeled on a
prior Excel-based budget (transactions, income, monthly pivots, savings goals, and budgets).

## Features

- **Transactions** — log expenses with date, category, and description; browse/filter/delete
- **Income** — log income by category (Salary, Side Income, Government, Other Income)
- **Master Table** — month-by-month breakdown (income, Needs/Wants/Savings & Donations totals,
  net income, and per-category pivots) for every month you have data in — past or future, no
  fixed date range
- **Dashboard** — spending by category, Needs/Wants/Savings breakdown, income vs. expense trend,
  and weekly spending vs. a configurable weekly goal
- **Budget** — set a monthly budget per expense category; track spent, remaining, % used, and a
  3-month trailing average; edit which Needs/Wants/Savings & Donations group each category falls in
- **Savings** — named savings goals (e.g. Emergency Fund, Travel, Car) with a target amount,
  monthly contribution target, and progress bar; log contributions as linked transactions

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
