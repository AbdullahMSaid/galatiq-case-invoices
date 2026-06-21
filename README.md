# Galatiq Invoice Processing Workflow

A local, agentic invoice-processing workflow built for the Galatiq take-home assessment.

## Overview

This project processes invoices end-to-end using a hybrid deterministic + LLM pipeline:

1. **Ingestion**

   * Parses invoices from multiple formats: TXT, PDF, JSON, CSV, and XML
   * Uses deterministic parsers for structured formats (JSON / CSV / XML)
   * Uses an LLM for messy unstructured invoices (TXT / PDF), including OCR-like errors, inconsistent labels, and email-wrapped invoice text

2. **Validation**

   * Checks parsed invoices against a local SQLite inventory database
   * Flags:

     * unknown items
     * out-of-stock items
     * quantities exceeding available inventory
     * negative / missing values
     * high-value invoices
     * non-USD invoices

3. **Approval**

   * Simulates a finance / VP approval workflow
   * Combines validation results with LLM reasoning
   * Includes a reflection / self-critique pass before finalizing the decision

4. **Payment**

   * Simulates payment for approved invoices only
   * Keeps payment local / mocked for the take-home scope

---

## Architecture

```text
Invoice Input
   ↓
Ingestion
   ├─ Structured parsers (JSON / CSV / XML)
   └─ LLM extraction (TXT / PDF)
   ↓
Validation
   └─ SQLite inventory checks + business rule flags
   ↓
Approval
   ├─ Initial LLM decision
   └─ Reflection / critique pass
   ↓
Payment
   └─ Mock payment execution for approved invoices
```

---

## Tech Stack

* **Python**
* **LangGraph** for orchestration
* **Claude / Anthropic** for LLM-based extraction and approval reasoning
* **SQLite** for local inventory validation
* **pdfplumber** for PDF text extraction

---

## Repository Structure

```text
.
├── main.py
├── requirements.txt
├── inventory.db
├── data/
│   └── invoices/
├── invoice_agents/
│   ├── state.py
│   ├── graph.py
│   ├── db/
│   │   └── seed.py
│   └── agents/
│       ├── ingestion.py
│       ├── validation.py
│       ├── approval.py
│       └── payment.py
```

---

## Running the Project

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

Create a `.env` file with your Anthropic API key:

```env
ANTHROPIC_API_KEY=your_key_here
```

### 3. Seed the inventory database

```bash
python -m invoice_agents.db.seed
```

### 4. Run the workflow on a single invoice

```bash
python main.py --invoice_path data/invoices/invoice_1001.txt
```

---

## Example Scenarios Covered

The invoice set includes examples such as:

* clean baseline invoices
* typo-heavy TXT invoices
* fraud / urgency style invoices
* revised invoices
* high-value invoices
* repeated SKUs / stock overages
* OCR-style PDF corruption
* non-USD invoices
* malformed / invalid invoices

---

## Design Decisions

### Deterministic parsing for structured formats

JSON, CSV, and XML are parsed locally without an LLM where possible.

### LLM extraction for messy documents

TXT and PDF invoices can contain OCR errors, typos, and inconsistent formatting. Those go through an LLM extraction step into a common structured invoice schema.

### Validation is deterministic

Inventory checks and business-rule flags are handled with standard Python + SQLite rather than an LLM.

### Approval includes reflection

Approval is treated as a reasoning problem rather than a pure rule-based filter. The workflow includes a second reflection pass to critique the initial approval decision before finalizing.

---

## Current Status

This repo currently includes the end-to-end workflow implementation. I am still tightening:

* automated tests
* README examples / sample outputs
* optional UI for interacting with the workflow visually

---

## Future Improvements

If this were extended beyond take-home scope, I would add:

* stronger unit / integration test coverage
* a Streamlit or lightweight web UI
* batch invoice processing
* richer fraud heuristics and vendor history
* structured observability / run traces
* human-in-the-loop review queues for manual review cases

---

## Notes

This project is intentionally local-first:

* no cloud deployment required
* no external business APIs required
* payment execution is mocked
* inventory validation uses a local SQLite database
