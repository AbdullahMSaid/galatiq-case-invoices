"""Stage 1 — Ingestion: reads an invoice file and extracts structured data
(deterministic parsing for JSON; LLM extraction for txt/pdf/csv/xml)."""



from pathlib import Path
import json
from typing import List, Optional

import pdfplumber
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from invoice_agents.state import InvoiceState, ParsedInvoice


load_dotenv()


class ExtractedLineItem(BaseModel):
    item: str
    quantity: Optional[int] = None
    unit_price: Optional[float] = None


class ExtractedInvoice(BaseModel):
    invoice_number: Optional[str] = None
    vendor: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: str = "USD"
    total_amount: Optional[float] = None
    line_items: List[ExtractedLineItem] = Field(default_factory=list)
    extraction_notes: List[str] = Field(default_factory=list)


llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    temperature=0,
)

structured_llm = llm.with_structured_output(ExtractedInvoice)


def ingest(state: InvoiceState) -> dict:
    invoice_path = Path(state["invoice_path"])
    file_format = invoice_path.suffix.lower().replace(".", "")

    raw_content = _load_raw_content(invoice_path, file_format)

    if file_format == "json":
        parsed_invoice = _parse_json_invoice(raw_content, invoice_path, file_format)
    elif file_format in {"txt", "pdf", "csv", "xml"}:
        parsed_invoice = _extract_invoice_with_llm(raw_content, invoice_path, file_format)
    else:
        parsed_invoice = _empty_parsed_invoice(invoice_path, file_format)

    return {
        "file_format": file_format,
        "raw_content": raw_content,
        "parsed_invoice": parsed_invoice,
        "ingestion_warnings": [],
        "logs": [f"Ingested {invoice_path} as {file_format}"],
    }


def _load_raw_content(invoice_path: Path, file_format: str) -> str:
    if file_format == "pdf":
        return _extract_pdf_text(invoice_path)

    return invoice_path.read_text(encoding="utf-8")


def _empty_parsed_invoice(invoice_path: Path, file_format: str) -> ParsedInvoice:
    return {
        "invoice_number": None,
        "vendor": None,
        "invoice_date": None,
        "due_date": None,
        "currency": "USD",
        "total_amount": None,
        "line_items": [],
        "source_file": str(invoice_path),
        "source_format": file_format,
        "extraction_notes": [],
    }


def _first_present(data: dict, *keys: str):
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _parse_json_invoice(raw_content: str, invoice_path: Path, file_format: str) -> ParsedInvoice:
    data = json.loads(raw_content)
    parsed = _empty_parsed_invoice(invoice_path, file_format)

    vendor = data.get("vendor")
    if isinstance(vendor, dict):
        parsed["vendor"] = vendor.get("name")
    else:
        parsed["vendor"] = vendor

    parsed["invoice_number"] = _first_present(data, "invoice_number", "invoice_id", "number")
    parsed["invoice_date"] = _first_present(data, "invoice_date", "date")
    parsed["due_date"] = data.get("due_date")
    parsed["currency"] = data.get("currency") or "USD"
    parsed["total_amount"] = _first_present(data, "total_amount", "amount", "total")

    items = data.get("line_items")
    if items is None:
        items = data.get("items")
    if items is None:
        items = []

    parsed["line_items"] = [
        {
            "item": _first_present(item, "item", "name", "sku"),
            "quantity": _first_present(item, "quantity", "qty"),
            "unit_price": _first_present(item, "unit_price", "price"),
        }
        for item in items
    ]

    return parsed


def _extract_invoice_with_llm(
    raw_content: str,
    invoice_path: Path,
    file_format: str,
) -> ParsedInvoice:
    system_prompt = """
You extract structured invoice data from invoice documents.

The input may be plain text, an email, a CSV, or XML -- clean or messy.
Return the fields according to the provided schema.
Handle typos, OCR-like transcription errors (e.g. the letter "O" used for the
digit "0"), missing labels, email wrappers, and informal or tabular formatting.

Rules:
- Preserve suspicious or invalid VALUES exactly as they appear -- a due date of
  "yesterday", a future invoice date, negative quantities, an unusual total. Do
  not "fix" them; just record them and flag them in extraction_notes.
- If a field is missing, use null.
- If currency is not stated, assume USD; otherwise use the stated currency.
- Extract only actual purchased line items. Subtotal, tax, shipping, and total
  rows are NOT line items.
- Record item names exactly as they appear -- do not add or remove spaces, and
  keep qualifiers such as "(Volume Discount)". Item-name canonicalization
  happens in a later stage.
- Use extraction_notes to explain uncertainty, inferred fields, OCR ambiguity,
  fraud signals, or malformed input.
"""

    extracted: ExtractedInvoice = structured_llm.invoke(
        [
            ("system", system_prompt),
            ("user", raw_content),
        ]
    )

    parsed = _empty_parsed_invoice(invoice_path, file_format)
    parsed["invoice_number"] = extracted.invoice_number
    parsed["vendor"] = extracted.vendor
    parsed["invoice_date"] = extracted.invoice_date
    parsed["due_date"] = extracted.due_date
    parsed["currency"] = extracted.currency or "USD"
    parsed["total_amount"] = extracted.total_amount
    parsed["line_items"] = [
        item.model_dump()
        for item in extracted.line_items
    ]
    parsed["extraction_notes"] = extracted.extraction_notes

    return parsed


def _extract_pdf_text(invoice_path: Path) -> str:
    pages = []

    with pdfplumber.open(invoice_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)

    return "\n".join(pages).strip()