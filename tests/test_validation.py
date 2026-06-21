"""Stage 2 — validation. Validation is deterministic (no LLM), so we feed it parsed
invoices directly: real JSON files where parsing is free, and static dicts that stand
in for the LLM's extraction of the txt/pdf/xml files (mocking the LLM where possible)."""

from invoice_agents.agents.ingestion import ingest
from invoice_agents.agents.validation import validate

from .conftest import invoice_path


def _parsed(**overrides):
    """A minimal clean parsed invoice; override fields per test."""
    base = {
        "vendor": "Acme Co.",
        "currency": "USD",
        "total_amount": 1000.0,
        "line_items": [{"item": "WidgetA", "quantity": 1, "unit_price": 250.0}],
        "extraction_notes": [],
    }
    base.update(overrides)
    return {"parsed_invoice": base}


def test_overstock_is_flagged_invoice_1002(patched_inventory):
    # Mirrors invoice_1002.txt: 20x GadgetX ordered against 5 in stock.
    state = _parsed(
        vendor="Office Supplies Co",
        total_amount=15000.0,
        line_items=[{"item": "GadgetX", "quantity": 20, "unit_price": 750.0}],
    )
    result = validate(state)

    assert result["validation_passed"] is False
    assert any("over-ordered" in issue and "GadgetX" in issue for issue in result["validation_issues"])


def test_missing_vendor_is_an_issue_invoice_1009(patched_inventory):
    # Integration via the free JSON parser: 1009 has an empty vendor name.
    state = ingest({"invoice_path": invoice_path("invoice_1009.json")})
    result = validate(state)

    assert result["validation_passed"] is False
    assert any("vendor" in issue.lower() for issue in result["validation_issues"])
    # Missing vendor is now an ISSUE, never a warning.
    assert not any("vendor" in w.lower() for w in result["validation_warnings"])


def test_aggregates_annotated_skus_invoice_1013(patched_inventory):
    # Mirrors the PDF extraction of invoice_1013: repeated and annotated SKU names.
    # Normalization must fold annotations so quantities aggregate per real SKU:
    #   WidgetA: 15 + 5 + 2 = 22 (> 15),  GadgetX: 5 + 3 + 1 = 9 (> 5).
    state = _parsed(
        vendor="Atlas Industrial Supply",
        total_amount=22562.80,
        line_items=[
            {"item": "WidgetA", "quantity": 15, "unit_price": 250.0},
            {"item": "WidgetB", "quantity": 10, "unit_price": 500.0},
            {"item": "GadgetX", "quantity": 5, "unit_price": 750.0},
            {"item": "WidgetA (Volume Discount)", "quantity": 5, "unit_price": 240.0},
            {"item": "WidgetB (Volume Discount)", "quantity": 8, "unit_price": 480.0},
            {"item": "GadgetX Expedited", "quantity": 3, "unit_price": 750.0},
            {"item": "WidgetA Replacement", "quantity": 2, "unit_price": 250.0},
            {"item": "GadgetX Sample", "quantity": 1, "unit_price": 750.0},
        ],
    )
    result = validate(state)

    issues = result["validation_issues"]
    assert any("WidgetA" in i and "22" in i for i in issues), issues
    assert any("GadgetX" in i and "9" in i for i in issues), issues
    # No annotated variant should be reported as an unknown item.
    assert not any("Unknown item" in i for i in issues), issues


def test_unknown_item_is_preserved_not_normalized_away(patched_inventory):
    # "WidgetC" is genuinely unknown and must still fail the inventory lookup.
    state = _parsed(line_items=[{"item": "WidgetC", "quantity": 1, "unit_price": 100.0}])
    result = validate(state)

    assert any("Unknown item" in i and "WidgetC" in i for i in result["validation_issues"])


def test_non_usd_sets_requires_manual_review_invoice_1014(patched_inventory):
    # Mirrors invoice_1014.xml: a clean but EUR-denominated invoice.
    state = _parsed(currency="EUR")
    result = validate(state)

    assert result["requires_manual_review"] is True
    assert any("EUR" in w for w in result["validation_warnings"])
    # Currency alone is a soft warning, not a blocking issue.
    assert result["validation_passed"] is True
