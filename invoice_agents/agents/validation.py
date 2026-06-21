"""Stage 2 — Validation: rule-based checks of the parsed invoice against the
inventory DB, producing flags only (issues block; warnings just flag for review)."""

from __future__ import annotations

import re

from invoice_agents.state import InvoiceState
from invoice_agents.tools.inventory import fetch_inventory


# Trailing annotation words that describe the order, not the SKU itself, so they
# are dropped before the inventory lookup ("GadgetX Expedited" -> "GadgetX").
_ANNOTATIONS = {"replacement", "expedited", "sample", "rush", "order"}


def _canonical(name: str) -> str:
    """Fold an invoice item name to a key comparable against inventory.

    Strips parenthetical qualifiers ("WidgetA (Volume Discount)" -> "WidgetA"),
    drops trailing annotation words ("WidgetA Replacement" -> "WidgetA"),
    removes spacing ("Widget A" -> "WidgetA"), and lowercases -- so OCR, quoting,
    and annotation variants all match the same inventory row. Truly unknown items
    ("WidgetC") are left intact so they still fail the lookup.
    """
    name = re.sub(r"\(.*?\)", "", name)   # drop "(Volume Discount)", "(rush order)", ...
    tokens = name.split()
    while tokens and tokens[-1].lower() in _ANNOTATIONS:
        tokens.pop()                       # "GadgetX Expedited" -> "GadgetX"
    return "".join(tokens).lower()         # "Widget A" -> "widgeta"


def validate(state: InvoiceState) -> dict:
    parsed = state.get("parsed_invoice") or {}
    line_items = parsed.get("line_items") or []

    issues: list[str] = []
    warnings: list[str] = []

    # --- whole-invoice integrity ---
    if not line_items:
        issues.append("No line items were extracted from the invoice.")

    if not parsed.get("vendor"):
        issues.append("No vendor name on the invoice.")

    total = parsed.get("total_amount")
    if total is None:
        warnings.append("No total amount on the invoice.")
    elif total <= 0:
        issues.append(f"Invoice total is non-positive: {total}.")

    currency = parsed.get("currency")
    if currency and currency != "USD":
        warnings.append(f"Currency is {currency}, not USD; payment is configured for USD.")

    # --- per-line-item integrity, then aggregate quantities per canonical SKU ---
    aggregated: dict[str, dict] = {}  # canonical key -> {"display": name, "quantity": total}
    for item in line_items:
        name = item.get("item")
        qty = item.get("quantity")

        if not name:
            issues.append("A line item has no item name.")
            continue
        if qty is None:
            issues.append(f"Item '{name}' is missing a quantity.")
            continue
        if qty <= 0:
            issues.append(f"Item '{name}' has a non-positive quantity: {qty}.")
            continue

        key = _canonical(name)
        bucket = aggregated.setdefault(key, {"display": name, "quantity": 0})
        bucket["quantity"] += qty

    # --- stock checks against inventory (aggregated per SKU) ---
    inventory = fetch_inventory()
    canonical_inventory = {_canonical(item): (item, stock) for item, stock in inventory.items()}

    for key, bucket in aggregated.items():
        name = bucket["display"]
        qty = bucket["quantity"]

        if key not in canonical_inventory:
            issues.append(f"Unknown item not in inventory: '{name}'.")
            continue

        inv_name, stock = canonical_inventory[key]
        if stock <= 0:
            issues.append(f"'{inv_name}' is out of stock (0 available) but {qty} ordered.")
        elif qty > stock:
            issues.append(f"'{inv_name}' over-ordered: {qty} requested, only {stock} in stock.")

    # --- conservative total check ---
    # We don't model tax, so a stated total ABOVE the subtotal is expected (tax,
    # shipping). Only the impossible case -- total below the subtotal -- is flagged.
    subtotal = sum(
        item["quantity"] * item["unit_price"]
        for item in line_items
        if item.get("quantity") and item.get("unit_price")
    )
    if total is not None and subtotal and total + 0.01 < subtotal:
        warnings.append(
            f"Stated total ({total}) is below the line-item subtotal ({round(subtotal, 2)})."
        )

    validation_passed = not issues
    requires_manual_review = bool(issues) or bool(warnings)

    summary = "passed" if validation_passed else f"found {len(issues)} issue(s)"
    if warnings:
        summary += f", {len(warnings)} warning(s)"

    return {
        "validation_passed": validation_passed,
        "validation_issues": issues,
        "validation_warnings": warnings,
        "requires_manual_review": requires_manual_review,
        "logs": [f"Validation {summary}."],
    }
