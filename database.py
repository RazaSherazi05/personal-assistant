"""
database.py - Creates the database and all tables.
Run this file once. It is safe to run again: existing data is never deleted.
"""

import os
import sqlite3

from config import DB_PATH


def get_connection():
    """Open a connection to the database (creates the file if missing)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def create_tables(verbose=True):
    conn = get_connection()
    cur = conn.cursor()

    # Every food item you eat
    cur.execute("""
        CREATE TABLE IF NOT EXISTS food_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT NOT NULL,          -- e.g. 2026-10-09
            time      TEXT,                   -- e.g. 13:45
            food_name TEXT NOT NULL,
            grams     REAL,
            calories  REAL,
            protein   REAL,
            fat       REAL,
            carbs     REAL
        )
    """)

    # Each German study session (clock in / clock out)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS german_sessions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT NOT NULL,
            clock_in  TEXT NOT NULL,          -- e.g. 2026-10-09 18:00:00
            clock_out TEXT,                   -- empty while session is running
            minutes   REAL
        )
    """)

    # Missed targets, plus your own note on what went wrong
    cur.execute("""
        CREATE TABLE IF NOT EXISTS breaches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start  TEXT NOT NULL,        -- Monday of that week
            target_name TEXT NOT NULL,        -- e.g. 'weekly_deficit'
            target      REAL,
            actual      REAL,
            note        TEXT                  -- your reflection, added later
        )
    """)

    # Added later: marks German sessions already sent to the web server
    columns = [row[1] for row in cur.execute("PRAGMA table_info(german_sessions)")]
    if "synced" not in columns:
        cur.execute("ALTER TABLE german_sessions ADD COLUMN synced INTEGER DEFAULT 0")

    conn.commit()
    conn.close()
    if verbose:
        print(f"Database ready at: {DB_PATH}")


if __name__ == "__main__":
    create_tables()
