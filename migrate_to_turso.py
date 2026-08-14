"""One-time migration: copy everything from the local SQLite file into Turso.

Wipes whatever is currently in the Turso database (e.g. the fresh default-seeded categories
from init_db()) and replaces it with an exact copy of the local database, preserving primary
keys so foreign key references (goal_id, recurring_id) stay correct.

Usage (with TURSO_DATABASE_URL / TURSO_AUTH_TOKEN already set as env vars):
    python migrate_to_turso.py
"""
from __future__ import annotations

import os
import sqlite3
import sys

import db

TABLES_IN_ORDER = [
    # Parents before children that reference them via FK.
    "savings_goals",
    "recurring_transactions",
    "transactions",
    "budgets",
    "categories",
    "settings",
]


def main() -> None:
    url, token = db._turso_credentials()
    if not url:
        print("No TURSO_DATABASE_URL set — aborting so we don't accidentally no-op.")
        sys.exit(1)

    local = sqlite3.connect(db.DB_PATH)
    local.row_factory = sqlite3.Row

    db.init_db()  # make sure the Turso schema exists

    with db.get_conn() as remote:
        # Wipe remote tables (child-first, to respect FK constraints) before repopulating.
        for table in reversed(TABLES_IN_ORDER):
            remote.execute(f"DELETE FROM {table}")

        for table in TABLES_IN_ORDER:
            rows = local.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            cols = rows[0].keys()
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(cols)
            sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
            for row in rows:
                remote.execute(sql, tuple(row[c] for c in cols))
            print(f"Migrated {len(rows)} row(s) into {table}")

    local.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
    os._exit(0)
