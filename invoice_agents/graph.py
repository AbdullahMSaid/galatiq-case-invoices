"""Wires the four stages into a LangGraph: ingest -> validate -> approve -> (pay | reject)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from invoice_agents.state import InvoiceState
from invoice_agents.agents.ingestion import ingest
from invoice_agents.agents.validation import validate
from invoice_agents.agents.approval import approve
from invoice_agents.agents.payment import pay, log_rejection


def _route_after_approval(state: InvoiceState) -> str:
    """Send approved invoices to payment, everything else to the rejection log."""
    return "approved" if state.get("final_decision") == "approved" else "rejected"


def build_graph():
    builder = StateGraph(InvoiceState)

    builder.add_node("ingest", ingest)
    builder.add_node("validate", validate)
    builder.add_node("approve", approve)
    builder.add_node("pay", pay)
    builder.add_node("reject", log_rejection)

    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "validate")
    builder.add_edge("validate", "approve")
    builder.add_conditional_edges(
        "approve",
        _route_after_approval,
        {"approved": "pay", "rejected": "reject"},
    )
    builder.add_edge("pay", END)
    builder.add_edge("reject", END)

    return builder.compile()
