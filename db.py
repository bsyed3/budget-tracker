"""SQLite data layer for the budget tracker."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "budget.db"

EXPENSE_CATEGORIES = [
    "Cell Phone", "Internet", "Loans", "Insurance", "Gas", "Presto", "Uber",
    "Groceries", "Eating Out", "Tims/Coffee", "Subscriptions", "Dates",
    "Activities", "Gym/Fitness", "Clothing/Personal Care", "Travel", "Gifts",
    "Donations", "Miscellaneous", "Savings/Investments",
]

INCOME_CATEGORIES = ["Salary", "Side Income", "Government", "Other Income"]

# Default Needs / Wants / Savings & Donations grouping, editable by the user.
DEFAULT_GROUPS = {
    "Cell Phone": "Needs", "Internet": "Needs", "Loans": "Needs", "Insurance": "Needs",
    "Gas": "Needs", "Presto": "Needs", "Groceries": "Needs", "Miscellaneous": "Needs",
    "Uber": "Wants", "Eating Out": "Wants", "Tims/Coffee": "Wants", "Subscriptions": "Wants",
    "Dates": "Wants", "Activities": "Wants", "Gym/Fitness": "Wants",
    "Clothing/Personal Care": "Wants", "Travel": "Wants", "Gifts": "Wants",
    "Donations": "Savings & Donations", "Savings/Investments": "Savings & Donations",
}
GROUP_NAMES = ["Needs", "Wants", "Savings & Donations"]

DEFAULT_SETTINGS = {
    "weekly_spending_goal": "400",
}


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                goal_amount REAL NOT NULL DEFAULT 0,
                monthly_target REAL NOT NULL DEFAULT 0,
                starting_amount REAL NOT NULL DEFAULT 0,
                starting_date TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                category TEXT NOT NULL,
                description TEXT,
                amount REAL NOT NULL CHECK (amount > 0),
                goal_id INTEGER REFERENCES savings_goals(id) ON DELETE SET NULL
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS category_groups (
                category TEXT PRIMARY KEY,
                group_name TEXT NOT NULL CHECK (group_name IN ('Needs', 'Wants', 'Savings & Donations'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        # Seed default category groupings and settings if not already present.
        existing_groups = {r["category"] for r in conn.execute("SELECT category FROM category_groups")}
        for category, group_name in DEFAULT_GROUPS.items():
            if category not in existing_groups:
                conn.execute(
                    "INSERT INTO category_groups (category, group_name) VALUES (?, ?)",
                    (category, group_name),
                )
        existing_settings = {r["key"] for r in conn.execute("SELECT key FROM settings")}
        for key, value in DEFAULT_SETTINGS.items():
            if key not in existing_settings:
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))


# ------------------------------------------------------------------ transactions
def add_transaction(
    date: str, type_: str, category: str, description: str, amount: float, goal_id: int | None = None
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO transactions (date, type, category, description, amount, goal_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date, type_, category, description, amount, goal_id),
        )
        return cur.lastrowid


def delete_transaction(transaction_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


def get_transactions() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()


# ---------------------------------------------------------------------- budgets
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


# --------------------------------------------------------------- category groups
def get_category_groups() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT category, group_name FROM category_groups").fetchall()
    return {r["category"]: r["group_name"] for r in rows}


def set_category_group(category: str, group_name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO category_groups (category, group_name) VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET group_name = excluded.group_name
            """,
            (category, group_name),
        )


# ----------------------------------------------------------------- savings goals
def add_savings_goal(
    name: str, goal_amount: float, monthly_target: float, starting_amount: float, starting_date: str
) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO savings_goals (name, goal_amount, monthly_target, starting_amount, starting_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, goal_amount, monthly_target, starting_amount, starting_date),
        )


def update_savings_goal(goal_id: int, goal_amount: float, monthly_target: float, starting_amount: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE savings_goals SET goal_amount = ?, monthly_target = ?, starting_amount = ? WHERE id = ?",
            (goal_amount, monthly_target, starting_amount, goal_id),
        )


def delete_savings_goal(goal_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))


def get_savings_goals() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM savings_goals ORDER BY name").fetchall()


# --------------------------------------------------------------------- settings
def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
