"""Shared pytest fixtures for the invoice pipeline tests.

The validation stage is the only place that reads the inventory DB, so we seed a
throwaway SQLite file per test and redirect the lookup at it -- the unit tests stay
deterministic and never touch the committed inventory.db.
"""

from pathlib import Path

import pytest

from invoice_agents.db import seed
from invoice_agents.tools.inventory import fetch_inventory

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "invoices"


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """Seed a temp inventory DB and point seed.DB_PATH at it; return the path."""
    db_path = tmp_path / "inventory.db"
    monkeypatch.setattr(seed, "DB_PATH", db_path)
    seed.seed_database()
    return db_path


@pytest.fixture
def patched_inventory(seeded_db, monkeypatch):
    """Make validation.validate() read the seeded temp DB instead of the default."""
    monkeypatch.setattr(
        "invoice_agents.agents.validation.fetch_inventory",
        lambda: fetch_inventory(seeded_db),
    )
    return seeded_db


def invoice_path(name: str) -> str:
    """Absolute path to a sample invoice, so tests run from any CWD."""
    return str(DATA_DIR / name)
