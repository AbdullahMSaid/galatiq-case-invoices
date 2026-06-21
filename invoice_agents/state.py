"""Shared LangGraph state (InvoiceState) passed between the four pipeline stages."""


from __future__ import annotations #lets python delay the evaluationg type hints
import operator #operator is used by langgraph to combine long lists
from typing import Any, Optional 

from typing_extensions import Annotated, TypedDict


class LineItem(TypedDict, total=False):
    item:str
    quantity:int | None 
    unit_price: float | None

class ParsedInvoice(TypedDict, total=False):
    invoice_number: str | None
    vendor: str | None
    invoice_date: str | None
    due_date: str | None
    currency: str | None
    total_amount: float | None
    line_items: list[LineItem] 
    source_file: str 
    source_format: str
    extraction_notes: list[str]

class InvoiceState(TypedDict, total=False):
    #Ingestion
    invoice_path: str
    file_format: str
    raw_content: str
    parsed_invoice: dict[str, Any]
    parse_warnings: list[str]

    #Validation
    validation_passed: bool
    validation_issues: list[str]
    validation_warnings: list[str]
    requires_manual_review: bool

    #Approval
    approval_decision: str
    approval_reasoning: str
    reflection_decision: str
    reflection_reasoning: str
    final_decision: str

    #Payment
    payment_status: str
    payment_id: Optional[str]

    #Traceability / Observability
    logs: Annotated[list[str], operator.add] #This tells langgraph to combine logs


