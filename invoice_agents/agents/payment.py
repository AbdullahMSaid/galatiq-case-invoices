"""Stage 4 — Payment: pay() runs mock_payment for approved invoices;
log_rejection() records rejected ones (everything is simulated, no real money)."""

from __future__ import annotations

from uuid import uuid4

from invoice_agents.state import InvoiceState
from invoice_agents.tools.payment import mock_payment


def pay(state: InvoiceState) -> dict:
    parsed = state.get("parsed_invoice") or {}
    vendor = parsed.get("vendor") or "UNKNOWN VENDOR"
    amount = parsed.get("total_amount")

    result = mock_payment(vendor, amount)
    payment_id = f"PAY-{uuid4().hex[:8].upper()}"

    return {
        "payment_status": result.get("status", "unknown"),
        "payment_id": payment_id,
        "logs": [f"Payment {payment_id}: {result.get('status')} -- {amount} to {vendor}."],
    }


def log_rejection(state: InvoiceState) -> dict:
    reason = (
        state.get("reflection_reasoning")
        or state.get("approval_reasoning")
        or "No reasoning recorded."
    )
    return {
        "payment_status": "not_paid",
        "payment_id": None,
        "logs": [f"Payment skipped -- invoice rejected. Reason: {reason}"],
    }
