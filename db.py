"""SQLite / Turso data layer for the budget tracker.

Uses a local SQLite file by default (unchanged local-dev behavior). If Turso credentials are
present -- TURSO_DATABASE_URL / TURSO_AUTH_TOKEN as environment variables or Streamlit secrets
-- it transparently talks to a remote Turso (libSQL) database instead. Same schema, same SQL;
only the connection underneath differs, via a thin shim so the rest of this module (and every
caller) is unchanged either way.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "budget.db"

GROUP_NAMES = ["Needs", "Wants", "Savings"]
GROUP_COLORS = {
    "Needs": "#2563eb",      # blue
    "Wants": "#f59e0b",      # amber
    "Savings": "#16a34a",    # green
}

# Distinct, colorblind-friendlyish qualitative palette for an arbitrary number of savings goals
# on the same chart (cycles if there are ever more goals than colors).
GOAL_PALETTE = [
    "#2563eb", "#f59e0b", "#16a34a", "#dc2626", "#9333ea",
    "#0891b2", "#ca8a04", "#db2777", "#4d7c0f", "#7c3aed",
]


def goal_colors(goal_names: list[str]) -> dict[str, str]:
    """Stable color assignment for a list of goal names, in the order given."""
    return {name: GOAL_PALETTE[i % len(GOAL_PALETTE)] for i, name in enumerate(goal_names)}


# Seed data used only the first time the database is created (or to backfill any
# category found in old transaction data that isn't in the categories table yet).
_SEED_EXPENSE_GROUPS = {
    "Cell Phone": "Needs", "Internet": "Needs", "Loans": "Needs", "Insurance": "Needs",
    "Gas": "Needs", "Presto": "Needs", "Groceries": "Needs", "Miscellaneous": "Needs",
    "Donations": "Needs",
    "Uber": "Wants", "Eating Out": "Wants", "Tims/Coffee": "Wants", "Subscriptions": "Wants",
    "Dates": "Wants", "Activities": "Wants", "Gym/Fitness": "Wants",
    "Clothing/Personal Care": "Wants", "Travel": "Wants", "Gifts": "Wants",
    "Savings/Investments": "Savings",
}
_SEED_INCOME_CATEGORIES = ["Salary", "Side Income", "Government", "Other Income"]

DEFAULT_SETTINGS = {
    "weekly_goal_needs": "200",
    "weekly_goal_wants": "200",
    "weekly_goal_total": "400",
}


# ----------------------------------------------------------------- Turso backend
def _turso_credentials() -> tuple[str | None, str | None]:
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url:
        try:
            import streamlit as st
            url = url or st.secrets.get("TURSO_DATABASE_URL")
            token = token or st.secrets.get("TURSO_AUTH_TOKEN")
        except Exception:
            pass
    return url, token


class _TursoRow:
    """Matches sqlite3.Row's dual access: row[0] (positional) and row["col"] (named), plus
    dict(row) support (via .keys() + __getitem__, which the dict() constructor uses)."""

    def __init__(self, columns, values):
        self._columns = columns
        self._values = values
        self._map = dict(zip(columns, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._map[key]

    def get(self, key, default=None):
        return self._map.get(key, default)

    def keys(self):
        return self._columns

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return f"_TursoRow({self._map!r})"


class _TursoCursorShim:
    """Makes a libsql_client ResultSet look like a sqlite3 cursor: .fetchall()/.fetchone()."""

    def __init__(self, result_set):
        columns = result_set.columns
        self._rows = [_TursoRow(columns, row.astuple()) for row in result_set.rows]
        self.lastrowid = result_set.last_insert_rowid

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _TursoConnShim:
    """Makes a libsql_client ClientSync look like a sqlite3 connection for this module's
    execute()-only usage pattern."""

    def __init__(self, client):
        self._client = client

    def execute(self, sql, params=()):
        result = self._client.execute(sql, list(params) if params else None)
        return _TursoCursorShim(result)


_turso_client = None


def _get_turso_client():
    global _turso_client
    if _turso_client is None:
        import libsql_client
        url, token = _turso_credentials()
        _turso_client = libsql_client.create_client_sync(url=url, auth_token=token)
    return _turso_client


@contextmanager
def get_conn():
    url, _ = _turso_credentials()
    if url:
        conn = _TursoConnShim(_get_turso_client())
        yield conn
        return
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
            CREATE TABLE IF NOT EXISTS savings_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
                period_type TEXT NOT NULL CHECK (period_type IN ('weekly', 'monthly')),
                period_date TEXT NOT NULL,
                amount REAL NOT NULL,
                UNIQUE(goal_id, period_type, period_date)
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
            CREATE TABLE IF NOT EXISTS recurring_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                category TEXT NOT NULL,
                description TEXT,
                amount REAL NOT NULL CHECK (amount > 0),
                frequency_interval INTEGER NOT NULL CHECK (frequency_interval > 0),
                frequency_unit TEXT NOT NULL CHECK (frequency_unit IN ('day', 'week', 'month')),
                start_date TEXT NOT NULL,
                next_due_date TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                goal_id INTEGER REFERENCES savings_goals(id) ON DELETE SET NULL
            )
            """
        )
        # Migrate a pre-existing table still using the old fixed-enum `frequency` column
        # (weekly/biweekly/monthly/yearly) to frequency_interval + frequency_unit, which
        # supports any "every N days/weeks/months" schedule instead of only those four presets.
        # Rebuilding the table (rather than ALTER ... DROP COLUMN) is what actually removes the
        # old CHECK constraint, which would otherwise reject any custom interval.
        rec_cols = [r["name"] for r in conn.execute("SELECT name FROM pragma_table_info('recurring_transactions')")]
        if "frequency" in rec_cols and "frequency_interval" not in rec_cols:
            legacy_map = {
                "weekly": (1, "week"), "biweekly": (2, "week"),
                "monthly": (1, "month"), "yearly": (12, "month"),
            }
            old_rows = conn.execute("SELECT * FROM recurring_transactions").fetchall()
            # Build the replacement under a temp name and drop the original directly (never
            # RENAME the original table away) -- SQLite auto-rewrites *other* tables' FK clauses
            # to follow a renamed table, so renaming "recurring_transactions" itself, even as a
            # throwaway intermediate step, silently repoints transactions.recurring_id's FK at
            # whatever it was renamed to. Once that intermediate table is dropped, the FK is left
            # referencing a name that no longer exists, breaking every future INSERT INTO
            # transactions. Creating the new table under its own temp name sidesteps this
            # entirely, since nothing references that temp name to begin with.
            conn.execute(
                """
                CREATE TABLE recurring_transactions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                    category TEXT NOT NULL,
                    description TEXT,
                    amount REAL NOT NULL CHECK (amount > 0),
                    frequency_interval INTEGER NOT NULL CHECK (frequency_interval > 0),
                    frequency_unit TEXT NOT NULL CHECK (frequency_unit IN ('day', 'week', 'month')),
                    start_date TEXT NOT NULL,
                    next_due_date TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    goal_id INTEGER REFERENCES savings_goals(id) ON DELETE SET NULL
                )
                """
            )
            for r in old_rows:
                interval, unit = legacy_map.get(r["frequency"], (1, "month"))
                conn.execute(
                    "INSERT INTO recurring_transactions_new (id, type, category, description, amount, "
                    "frequency_interval, frequency_unit, start_date, next_due_date, active, goal_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (r["id"], r["type"], r["category"], r["description"], r["amount"], interval, unit,
                     r["start_date"], r["next_due_date"], r["active"], r["goal_id"]),
                )
            conn.execute("DROP TABLE recurring_transactions")
            conn.execute("ALTER TABLE recurring_transactions_new RENAME TO recurring_transactions")
        # Link generated transactions back to the rule that created them (nullable — manual
        # transactions and anything created before this feature existed just have NULL here).
        # Uses the pragma_table_info() table-valued function (portable SQL) rather than a bare
        # PRAGMA statement, since the latter isn't guaranteed over every remote SQL protocol.
        txn_cols = [r["name"] for r in conn.execute("SELECT name FROM pragma_table_info('transactions')")]
        if "recurring_id" not in txn_cols:
            conn.execute(
                "ALTER TABLE transactions ADD COLUMN recurring_id "
                "INTEGER REFERENCES recurring_transactions(id) ON DELETE SET NULL"
            )

        # Self-healing repair: an earlier version of the recurring_transactions migration above
        # renamed that table away as an intermediate step, which (per the comment above) silently
        # rewrote this column's FK to follow the rename -- leaving it referencing a name that no
        # longer exists once that intermediate table was dropped, and breaking every INSERT INTO
        # transactions. Detect that dangling reference directly from the stored DDL and rebuild
        # the table with a correct FK, preserving every row exactly.
        txn_ddl_row = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'transactions'").fetchone()
        if txn_ddl_row and "recurring_transactions_old" in txn_ddl_row["sql"]:
            old_txn_rows = conn.execute("SELECT * FROM transactions").fetchall()
            conn.execute(
                """
                CREATE TABLE transactions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                    category TEXT NOT NULL,
                    description TEXT,
                    amount REAL NOT NULL CHECK (amount > 0),
                    goal_id INTEGER REFERENCES savings_goals(id) ON DELETE SET NULL,
                    recurring_id INTEGER REFERENCES recurring_transactions(id) ON DELETE SET NULL
                )
                """
            )
            for r in old_txn_rows:
                conn.execute(
                    "INSERT INTO transactions_new (id, date, type, category, description, amount, "
                    "goal_id, recurring_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (r["id"], r["date"], r["type"], r["category"], r["description"], r["amount"],
                     r["goal_id"], r["recurring_id"]),
                )
            conn.execute("DROP TABLE transactions")
            conn.execute("ALTER TABLE transactions_new RENAME TO transactions")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                name TEXT PRIMARY KEY,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                group_name TEXT CHECK (group_name IN ('Needs', 'Wants', 'Savings', 'Donations'))
            )
            """
        )
        # Donations was folded into Needs; migrate any leftover rows from the old 4-group
        # scheme (harmless no-op if none exist). Left in the CHECK constraint above for
        # compatibility with tables created before this change.
        conn.execute("UPDATE categories SET group_name = 'Needs' WHERE group_name = 'Donations'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        # One-time seed of the categories table.
        has_categories = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] > 0
        if not has_categories:
            # Carry over any grouping from the old (pre-Settings-page) category_groups
            # table if it exists, so upgrading doesn't silently reset groupings.
            old_groups: dict[str, str] = {}
            try:
                rows = conn.execute("SELECT category, group_name FROM category_groups").fetchall()
                for r in rows:
                    old = r["group_name"]
                    # Old scheme had a single combined "Savings & Donations" group.
                    if old == "Savings & Donations":
                        old_groups[r["category"]] = (
                            "Donations" if r["category"] == "Donations" else "Savings"
                        )
                    else:
                        old_groups[r["category"]] = old
            except Exception:
                pass  # no old table (or backend doesn't have it), fine

            for category, default_group in _SEED_EXPENSE_GROUPS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO categories (name, type, group_name) VALUES (?, 'expense', ?)",
                    (category, old_groups.get(category, default_group)),
                )
            for category in _SEED_INCOME_CATEGORIES:
                conn.execute(
                    "INSERT OR IGNORE INTO categories (name, type, group_name) VALUES (?, 'income', NULL)",
                    (category,),
                )

        # Backfill: any category already used in transactions but missing from the
        # categories table (e.g. from data imported before Settings existed).
        known = {r["name"] for r in conn.execute("SELECT name FROM categories")}
        used = conn.execute(
            "SELECT category, type, COUNT(*) as n FROM transactions GROUP BY category, type"
        ).fetchall()
        seen_categories = set()
        for row in used:
            if row["category"] in seen_categories:
                continue
            seen_categories.add(row["category"])
            if row["category"] not in known:
                group = "Wants" if row["type"] == "expense" else None
                conn.execute(
                    "INSERT OR IGNORE INTO categories (name, type, group_name) VALUES (?, ?, ?)",
                    (row["category"], row["type"], group),
                )

        existing_settings = {r["key"] for r in conn.execute("SELECT key FROM settings")}
        for key, value in DEFAULT_SETTINGS.items():
            if key not in existing_settings:
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))


# ------------------------------------------------------------------ transactions
def add_transaction(
    date: str, type_: str, category: str, description: str, amount: float,
    goal_id: int | None = None, recurring_id: int | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO transactions (date, type, category, description, amount, goal_id, recurring_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (date, type_, category, description, amount, goal_id, recurring_id),
        )
        return cur.lastrowid


def update_transaction(
    transaction_id: int, date: str, type_: str, category: str, description: str,
    amount: float, goal_id: int | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE transactions SET date = ?, type = ?, category = ?, description = ?, "
            "amount = ?, goal_id = ? WHERE id = ?",
            (date, type_, category, description, amount, goal_id, transaction_id),
        )


def delete_transaction(transaction_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


def get_transactions() -> list:
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


def get_budgets() -> list:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM budgets ORDER BY category").fetchall()


def delete_budget(category: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM budgets WHERE category = ?", (category,))


# ------------------------------------------------------------------- categories
def get_categories(type_: str | None = None) -> list:
    with get_conn() as conn:
        if type_:
            return conn.execute(
                "SELECT * FROM categories WHERE type = ? ORDER BY name", (type_,)
            ).fetchall()
        return conn.execute("SELECT * FROM categories ORDER BY type, name").fetchall()


def category_names(type_: str) -> list[str]:
    return [r["name"] for r in get_categories(type_)]


def get_category_groups() -> dict[str, str]:
    """category name -> group name, expense categories only."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, group_name FROM categories WHERE type = 'expense'"
        ).fetchall()
    return {r["name"]: (r["group_name"] or "Wants") for r in rows}


def add_category(name: str, type_: str, group_name: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO categories (name, type, group_name) VALUES (?, ?, ?)",
            (name, type_, group_name if type_ == "expense" else None),
        )


def update_category_group(name: str, group_name: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE categories SET group_name = ? WHERE name = ?", (group_name, name))


def update_category(old_name: str, new_name: str, type_: str, group_name: str | None) -> None:
    """Rename and/or change a category's type/group, cascading to every place its name or type
    is referenced (transactions, budgets, recurring rules) so historical data stays consistent."""
    with get_conn() as conn:
        old_row = conn.execute("SELECT type FROM categories WHERE name = ?", (old_name,)).fetchone()
        old_type = old_row["type"] if old_row else type_

        current_name = old_name
        if new_name != old_name:
            conn.execute("UPDATE categories SET name = ? WHERE name = ?", (new_name, old_name))
            conn.execute("UPDATE transactions SET category = ? WHERE category = ?", (new_name, old_name))
            conn.execute("UPDATE budgets SET category = ? WHERE category = ?", (new_name, old_name))
            conn.execute("UPDATE recurring_transactions SET category = ? WHERE category = ?", (new_name, old_name))
            current_name = new_name

        conn.execute(
            "UPDATE categories SET type = ?, group_name = ? WHERE name = ?",
            (type_, group_name, current_name),
        )
        if type_ != old_type:
            conn.execute("UPDATE transactions SET type = ? WHERE category = ?", (type_, current_name))
            conn.execute("UPDATE recurring_transactions SET type = ? WHERE category = ?", (type_, current_name))
            if type_ == "income":
                # Budgets only make sense for expense categories.
                conn.execute("DELETE FROM budgets WHERE category = ?", (current_name,))


def delete_category(name: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM categories WHERE name = ?", (name,))


# ------------------------------------------------------------ recurring transactions
def add_recurring(
    type_: str, category: str, description: str, amount: float,
    frequency_interval: int, frequency_unit: str, start_date: str, goal_id: int | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO recurring_transactions "
            "(type, category, description, amount, frequency_interval, frequency_unit, "
            "start_date, next_due_date, active, goal_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (type_, category, description, amount, frequency_interval, frequency_unit,
             start_date, start_date, goal_id),
        )
        return cur.lastrowid


def update_recurring(
    rule_id: int, category: str, description: str, amount: float,
    frequency_interval: int, frequency_unit: str, next_due_date: str, active: bool,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE recurring_transactions SET category = ?, description = ?, amount = ?, "
            "frequency_interval = ?, frequency_unit = ?, next_due_date = ?, active = ? WHERE id = ?",
            (category, description, amount, frequency_interval, frequency_unit,
             next_due_date, int(active), rule_id),
        )


def set_recurring_active(rule_id: int, active: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE recurring_transactions SET active = ? WHERE id = ?", (int(active), rule_id))


def set_recurring_next_due(rule_id: int, next_due_date: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE recurring_transactions SET next_due_date = ? WHERE id = ?", (next_due_date, rule_id))


def delete_recurring(rule_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM recurring_transactions WHERE id = ?", (rule_id,))


def get_recurring_rules() -> list:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM recurring_transactions ORDER BY next_due_date").fetchall()


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
        # Deleted explicitly rather than relying on the ON DELETE CASCADE in the schema --
        # Turso's connection doesn't necessarily have "PRAGMA foreign_keys = ON" active the way
        # the local sqlite3 branch does, so cascade delete isn't guaranteed to actually fire there.
        conn.execute("DELETE FROM savings_snapshots WHERE goal_id = ?", (goal_id,))
        conn.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))


def get_savings_goals() -> list:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM savings_goals ORDER BY name").fetchall()


# -------------------------------------------------------------- savings snapshots
def add_savings_snapshot(goal_id: int, period_type: str, period_date: str, amount: float) -> None:
    """Record (or override, if one already exists for this goal/period_type/date) a point-in-time
    total balance for a goal -- the source of truth for its "current amount" once any exist."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO savings_snapshots (goal_id, period_type, period_date, amount) VALUES (?, ?, ?, ?)
            ON CONFLICT(goal_id, period_type, period_date) DO UPDATE SET amount = excluded.amount
            """,
            (goal_id, period_type, period_date, amount),
        )


def get_savings_snapshots(period_type: str | None = None) -> list:
    with get_conn() as conn:
        if period_type:
            return conn.execute(
                "SELECT * FROM savings_snapshots WHERE period_type = ? ORDER BY period_date", (period_type,)
            ).fetchall()
        return conn.execute("SELECT * FROM savings_snapshots ORDER BY period_date").fetchall()


def get_goal_snapshots(goal_id: int, period_type: str) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM savings_snapshots WHERE goal_id = ? AND period_type = ? ORDER BY period_date",
            (goal_id, period_type),
        ).fetchall()


def latest_savings_amount(goal_id: int) -> float | None:
    """The most recent snapshot for this goal across both weekly and monthly, or None if it has
    never had one recorded (callers should fall back to the pre-snapshot calculation)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT amount FROM savings_snapshots WHERE goal_id = ? ORDER BY period_date DESC LIMIT 1",
            (goal_id,),
        ).fetchone()
    return row["amount"] if row else None


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


# ------------------------------------------------------------------- TFSA room
# Stored as plain settings rows (no new table/column) -- an anchor value + the date it was set,
# plus which savings goals' contributions count against it (e.g. accounts inside the same TFSA).
def get_tfsa_room() -> tuple[float, str, list[int]]:
    """(anchor_value, anchor_date, linked_goal_ids). Room remaining = anchor_value minus
    contributions to the linked goals dated after anchor_date -- see analytics.tfsa_room_remaining."""
    value = float(get_setting("tfsa_room_value", "0"))
    anchor_date = get_setting("tfsa_room_anchor_date", "1970-01-01")
    ids_raw = get_setting("tfsa_linked_goal_ids", "")
    linked_ids = [int(x) for x in ids_raw.split(",") if x.strip()]
    return value, anchor_date, linked_ids


def set_tfsa_room(value: float, anchor_date: str, linked_goal_ids: list[int]) -> None:
    """Setting a new value resets the anchor date to `anchor_date` (normally today), so
    contributions already made don't retroactively count against the new value -- only ones
    made after this point do."""
    set_setting("tfsa_room_value", str(value))
    set_setting("tfsa_room_anchor_date", anchor_date)
    set_setting("tfsa_linked_goal_ids", ",".join(str(i) for i in linked_goal_ids))
