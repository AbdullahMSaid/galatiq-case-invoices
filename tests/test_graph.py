"""End-to-end pipeline test through the real LangGraph.

This is integration-style: txt ingestion and the approve/reflect stages call the
real Anthropic API, so it is marked `integration` and skipped without a key. It uses
the committed inventory.db (run `python -m invoice_agents.db.seed` first if missing).
Run just this with `-m integration`, or skip it with `-m "not integration"`.
"""

import os

import pytest

from invoice_agents.graph import build_graph

from .conftest import invoice_path

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_clean_invoice_1001_approved_and_paid():
    graph = build_graph()
    final = graph.invoke({"invoice_path": invoice_path("invoice_1001.txt")})

    # Clean, in-stock, USD invoice under the $10K threshold -> approved -> paid.
    assert final["validation_passed"] is True
    assert final["final_decision"] == "approved"
    assert final["payment_status"] == "success"
    assert final["payment_id"] and final["payment_id"].startswith("PAY-")
