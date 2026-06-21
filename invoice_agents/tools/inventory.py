"""Read-only inventory lookup against the mock SQLite database (used by validation)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Relative to the current working directory, matching db/seed.py's assumption
# (run from the repo root) so both halves point at the same file.
DB_PATH = Path("inventory.db")


def fetch_inventory(db_path: Path = DB_PATH) -> dict[str, int]:
    """Return the whole inventory as {item: stock}.

    The table is tiny, so we load it once per validation run rather than
    issuing one query per line item.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT item, stock FROM inventory").fetchall()
    finally:
        conn.close()
    return {item: stock for item, stock in rows}
