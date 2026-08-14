# Budget Tracker

A simple personal budgeting app built with [Streamlit](https://streamlit.io) and SQLite.

## Features

- Log income and expense transactions by date, category, and amount
- Dashboard with monthly income/expenses/net, spending-by-category chart, and daily balance trend
- Set monthly budgets per category and track spending against them
- Browse, filter, and delete past transactions

## Getting started

```bash
python -m venv venv
venv\Scripts\activate      # on Windows
pip install -r requirements.txt
streamlit run app.py
```

The app stores data locally in `data/budget.db` (SQLite), which is git-ignored.

## Roadmap

- Possible future move to a React frontend + Python (FastAPI) backend if the app outgrows Streamlit.
