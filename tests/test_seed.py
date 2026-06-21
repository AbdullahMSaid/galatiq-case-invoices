"""Stage 0 — the seed script builds the canonical inventory the README defines."""

import sqlite3

from invoice_agents.tools.inventory import fetch_inventory


def test_seed_creates_canonical_inventory(seeded_db):
    inventory = fetch_inventory(seeded_db)
    assert inventory == {"WidgetA": 15, "WidgetB": 10, "GadgetX": 5, "FakeItem": 0}


def test_seed_is_idempotent(seeded_db):
    # Re-seeding must not duplicate rows (item is the PRIMARY KEY, DELETE-then-insert).
    from invoice_agents.db import seed

    seed.seed_database()
    conn = sqlite3.connect(seeded_db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
    finally:
        conn.close()
    assert count == 4
