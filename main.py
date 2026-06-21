"""CLI entry point: runs one invoice through the LangGraph pipeline and prints a report."""

from __future__ import annotations

import argparse

from invoice_agents.graph import build_graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Process one invoice end-to-end.")
    parser.add_argument("--invoice_path", required=True, help="Path to the invoice file.")
    args = parser.parse_args()

    graph = build_graph()
    final_state = graph.invoke({"invoice_path": args.invoice_path, "logs": []})

    _print_report(final_state)


def _print_report(state: dict) -> None:
    parsed = state.get("parsed_invoice") or {}

    print("\n" + "=" * 64)
    print("INVOICE PROCESSING REPORT")
    print("=" * 64)
    print(f"File:   {state.get('invoice_path')} ({state.get('file_format')})")
    print(f"Vendor: {parsed.get('vendor')}")
    print(f"Total:  {parsed.get('total_amount')} {parsed.get('currency')}")

    print("\n--- Validation ---")
    print(f"Passed: {state.get('validation_passed')}   Manual review: {state.get('requires_manual_review')}")
    for i in state.get("validation_issues") or []:
        print(f"  ISSUE:   {i}")
    for w in state.get("validation_warnings") or []:
        print(f"  warning: {w}")

    print("\n--- Approval ---")
    print(f"Approver:   {state.get('approval_decision')}")
    print(f"Reflection: {state.get('reflection_decision')}")
    print(f"FINAL:      {state.get('final_decision')}")
    print(f"Reasoning:  {state.get('reflection_reasoning')}")

    print("\n--- Payment ---")
    print(f"Status: {state.get('payment_status')}   ID: {state.get('payment_id')}")

    print("\n--- Log trail ---")
    for entry in state.get("logs") or []:
        print(f"  - {entry}")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
