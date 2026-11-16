"""
Phase 2 Database Migration
============================
Safely adds the three new Phase 2 columns to the 'products' table in the
existing SQLite database. This is non-destructive — it only adds columns
that do not already exist. Existing rows get NULL for the new columns.

Run from the backend/ directory:
    python migrate_phase2.py

The script is idempotent — running it multiple times is safe.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ── Find the database ─────────────────────────────────────────────────────────
DB_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "instance", "circular_economy.db"),
    os.path.join(os.path.dirname(__file__), "circular_economy.db"),
    os.path.join(os.path.dirname(__file__), "database.db"),
    os.path.join(os.path.dirname(__file__), "instance", "database.db"),
]


def find_db() -> str:
    for path in DB_CANDIDATES:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "database.db not found. Run the Flask app once first to create it.\n"
        f"Searched: {DB_CANDIDATES}"
    )


# ── New columns to add ────────────────────────────────────────────────────────
# Format: (column_name, sql_type, default_value_or_None)
NEW_COLUMNS = [
    ("material",        "VARCHAR(100)", None),
    ("co2_saved_kg",    "FLOAT",        None),
    ("resale_estimate", "FLOAT",        None),
]


def migrate():
    import sqlite3

    db_path = find_db()
    logger.info("Connecting to database: %s", db_path)

    conn   = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get existing column names in 'products' table
    cursor.execute("PRAGMA table_info(products)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    logger.info("Existing columns: %s", sorted(existing_cols))

    added = []
    skipped = []

    for col_name, col_type, default in NEW_COLUMNS:
        if col_name in existing_cols:
            skipped.append(col_name)
            continue

        if default is not None:
            sql = f"ALTER TABLE products ADD COLUMN {col_name} {col_type} DEFAULT {default}"
        else:
            sql = f"ALTER TABLE products ADD COLUMN {col_name} {col_type}"

        try:
            cursor.execute(sql)
            added.append(col_name)
            logger.info("  + Added column: %s (%s)", col_name, col_type)
        except sqlite3.OperationalError as e:
            logger.error("  ✗ Failed to add column %s: %s", col_name, e)

    conn.commit()
    conn.close()

    if added:
        logger.info("Migration complete. Added columns: %s", added)
    if skipped:
        logger.info("Columns already existed (skipped): %s", skipped)
    if not added and not skipped:
        logger.warning("No columns processed — check table name.")

    logger.info("Phase 2 migration finished.")


if __name__ == "__main__":
    migrate()
