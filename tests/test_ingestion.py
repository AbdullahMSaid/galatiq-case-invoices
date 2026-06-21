"""Stage 1 — ingestion. JSON is parsed deterministically (no LLM), so these run
free and offline."""

from invoice_agents.agents.ingestion import ingest

from .conftest import invoice_path


def test_ingest_json_extracts_vendor_and_line_items():
    state = {"invoice_path": invoice_path("invoice_1004.json")}
    result = ingest(state)

    parsed = result["parsed_invoice"]
    # vendor arrives as a nested {"name": ...} object and is flattened to the name.
    assert parsed["vendor"] == "Precision Parts Ltd."
    assert parsed["invoice_number"] == "INV-1004"
    assert parsed["total_amount"] == 1890.00
    assert parsed["currency"] == "USD"

    items = parsed["line_items"]
    assert len(items) == 2
    assert {(i["item"], i["quantity"]) for i in items} == {("WidgetA", 3), ("WidgetB", 2)}
    assert result["file_format"] == "json"
