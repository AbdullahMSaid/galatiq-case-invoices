"""Stage 3 — Approval: simulates a VP review via rule-based context + an LLM
approver + a reflection/critique pass; the reflection's verdict is final
(fails safe to reject on any LLM error)."""

from __future__ import annotations

from typing import Literal

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from invoice_agents.state import InvoiceState

load_dotenv()

HIGH_VALUE_THRESHOLD = 10_000


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reasoning: str = Field(description="One short paragraph justifying the decision.")


llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
decider = llm.with_structured_output(ReviewDecision)


APPROVER_SYSTEM = """You are a cautious VP of Finance approving vendor invoice payments.

Approve ONLY if the invoice is legitimate and safe to pay. Reject if there are:
- validation issues (unknown items, over-ordered vs stock, out-of-stock items),
- data-integrity problems (negative or zero quantities or totals),
- or fraud indicators (suspicious vendor, urgency / wire-transfer pressure,
  impossible dates, amounts inconsistent with the line items).

Invoices over $10,000 deserve extra scrutiny but are not automatically rejected.

Note: a stated total ABOVE the line-item subtotal is normal -- it reflects taxes,
shipping, or fees that may not appear as separate line items. Do NOT reject solely
because the total exceeds the sum of the line items. Only a total that is BELOW the
subtotal, or wildly inconsistent with it, is a data-integrity concern.

Decide "approve" or "reject" and explain your reasoning concisely."""

REFLECTION_SYSTEM = """You are a senior finance reviewer auditing another agent's
invoice-approval decision. Re-examine the invoice and its flags independently.

If the proposed decision is wrong -- approving something fraudulent or invalid, or
rejecting a clean, in-stock, legitimate invoice -- correct it. If it is right,
confirm it.

Note: a total ABOVE the line-item subtotal is expected (taxes, shipping, fees) and
is NOT by itself grounds for rejection. Only a total BELOW the subtotal, or grossly
inconsistent with it, is suspicious.

Output your final decision ("approve" / "reject") and reasoning."""


def _format_context(state: InvoiceState) -> str:
    parsed = state.get("parsed_invoice") or {}
    total = parsed.get("total_amount")
    high_value = isinstance(total, (int, float)) and total > HIGH_VALUE_THRESHOLD

    issues = state.get("validation_issues") or []
    warnings = state.get("validation_warnings") or []
    notes = parsed.get("extraction_notes") or []

    lines = [
        "INVOICE",
        f"- Vendor: {parsed.get('vendor')}",
        f"- Total: {total} {parsed.get('currency')}",
        f"- Invoice date: {parsed.get('invoice_date')}",
        f"- Due date: {parsed.get('due_date')}",
        f"- Line items: {parsed.get('line_items') or []}",
        "",
        "RULE-BASED FLAGS",
        f"- Exceeds ${HIGH_VALUE_THRESHOLD:,} threshold (extra scrutiny): {'YES' if high_value else 'no'}",
        f"- Validation passed: {state.get('validation_passed')}",
        f"- Validation issues: {issues or 'none'}",
        f"- Validation warnings: {warnings or 'none'}",
        "",
        "EXTRACTION NOTES (data-quality / possible fraud signals)",
    ]
    lines += [f"- {n}" for n in notes] or ["- none"]
    return "\n".join(lines)


def approve(state: InvoiceState) -> dict:
    context = _format_context(state)

    try:
        first = decider.invoke([("system", APPROVER_SYSTEM), ("user", context)])

        reflection_input = (
            f"{context}\n\n"
            f"PROPOSED DECISION: {first.decision}\n"
            f"PROPOSED REASONING: {first.reasoning}\n\n"
            "Audit this decision and give your final verdict."
        )
        reflected = decider.invoke([("system", REFLECTION_SYSTEM), ("user", reflection_input)])

        approval_decision, approval_reasoning = first.decision, first.reasoning
        reflection_decision, reflection_reasoning = reflected.decision, reflected.reasoning
    except Exception as exc:  # fail safe: never auto-approve on an LLM/API error
        approval_decision = reflection_decision = "reject"
        approval_reasoning = reflection_reasoning = f"Approval failed safe (error: {exc})."

    final_decision = "approved" if reflection_decision == "approve" else "rejected"
    overturned = approval_decision != reflection_decision

    log = (
        f"Approval: approver={approval_decision}, reflection={reflection_decision}"
        f"{' (overturned)' if overturned else ''} -> {final_decision}."
    )

    return {
        "approval_decision": approval_decision,
        "approval_reasoning": approval_reasoning,
        "reflection_decision": reflection_decision,
        "reflection_reasoning": reflection_reasoning,
        "final_decision": final_decision,
        "logs": [log],
    }
