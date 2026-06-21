"""Mock payment execution -- no real money moves, everything is simulated."""

from __future__ import annotations


def mock_payment(vendor: str, amount: float) -> dict:
    """Pretend to pay `amount` to `vendor`. Mirrors the README's stub."""
    print(f"[mock_payment] Paid {amount} to {vendor}")
    return {"status": "success"}
