"""SQLite data layer for the budget tracker."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "budget.db"

DEFAULT_CATEGORIES = [
    "Housing", "Utilities", "Groceries", "Transportation", "Dining Out",
    "Entertainment", "Health", "Insurance", "Savings", "Debt Payment",
    "Shopping", "Subscriptions", "Other",
]


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                category TEXT NOT NULL,
                description TEXT,
                amount REAL NOT NULL CHECK (amount > 0)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                monthly_limit REAL NOT NULL CHECK (monthly_limit >= 0)
            )
            """
        )


def add_transaction(date: str, type_: str, category: str, description: str, amount: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO transactions (date, type, category, description, amount) VALUES (?, ?, ?, ?, ?)",
            (date, type_, category, description, amount),
        )


def delete_transaction(transaction_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


def get_transactions() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()


def set_budget(category: str, monthly_limit: float) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO budgets (category, monthly_limit) VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit
            """,
            (category, monthly_limit),
        )


def get_budgets() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM budgets ORDER BY category").fetchall()


def delete_budget(category: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM budgets WHERE category = ?", (category,))
