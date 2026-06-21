
# Galatiq Invoice Processing Workflow

A local-first, agentic invoice processing workflow built for the Galatiq AI take-home assessment.

This system ingests invoices across multiple file types, extracts a normalized invoice representation, validates the invoice against a mock inventory database, simulates an approval workflow with LLM reasoning + reflection, and only executes payment when the invoice is approved.

---

## Quickstart

From the repository root:

```bash
./venv/bin/python -m invoice_agents.db.seed
./venv/bin/python main.py --invoice_path data/invoices/invoice_1001.txt
````

If you are not using the included virtual environment:

```bash
pip install -r requirements.txt
python -m invoice_agents.db.seed
python main.py --invoice_path data/invoices/invoice_1001.txt
```

---

## Overview

The workflow has four stages:

1. **Ingestion**

   * Reads invoices from TXT, JSON, CSV, XML, and PDF
   * Uses deterministic parsing for structured formats
   * Uses an LLM to extract structured data from messy TXT / PDF invoices with OCR-like errors, inconsistent labels, and noisy formatting

2. **Validation**

   * Checks parsed invoices against a local SQLite inventory database
   * Flags missing fields, negative values, unknown items, stock issues, currency mismatches, and high-value invoices

3. **Approval**

   * Uses validation findings plus LLM reasoning to simulate an approval / rejection decision
   * Includes a reflection pass to critique the initial decision before finalizing it

4. **Payment**

   * Simulates payment only for approved invoices
   * Keeps payment local / mocked for the scope of the take-home

---

## System Architecture

```text
                    ┌─────────────────────────┐
                    │      Input Invoice      │
                    │ txt / json / csv / xml │
                    │          / pdf          │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │        INGESTION        │
                    │-------------------------│
                    │ Structured parsers for  │
                    │ JSON / CSV / XML        │
                    │                         │
                    │ LLM extraction for      │
                    │ TXT / PDF               │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │       VALIDATION        │
                    │-------------------------│
                    │ SQLite inventory checks │
                    │ Data-integrity checks   │
                    │ Currency / amount flags │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │        APPROVAL         │
                    │-------------------------│
                    │ LLM approval decision   │
                    │ + reflection / critique │
                    └────────────┬────────────┘
                                 │
                   approved      │      rejected
                                 ▼
                    ┌─────────────────────────┐
                    │         PAYMENT         │
                    │-------------------------│
                    │ Mock payment execution  │
                    │ for approved invoices   │
                    └─────────────────────────┘
```

---

## Repository Structure

```text
.
├── data/
│   └── invoices/                  # sample invoices from the take-home
├── invoice_agents/
│   ├── __init__.py
│   ├── graph.py                   # LangGraph workflow definition
│   ├── state.py                   # shared workflow state
│   ├── db/
│   │   ├── __init__.py
│   │   └── seed.py                # seeds local inventory.db
│   └── agents/
│       ├── ingestion.py           # parse + normalize invoice data
│       ├── validation.py          # deterministic invoice checks
│       ├── approval.py            # LLM decision + reflection pass
│       └── payment.py             # mock payment step
├── main.py                        # CLI entrypoint
├── requirements.txt
└── README.md
```

---

## Canonical Invoice Shape

All invoice formats are normalized into a common structure so downstream stages can operate on a single schema.

```python
{
    "invoice_number": str | None,
    "vendor": str | None,
    "invoice_date": str | None,
    "due_date": str | None,
    "currency": str,
    "total_amount": float | None,
    "line_items": [
        {
            "item": str | None,
            "quantity": int | float | None,
            "unit_price": float | None,
        }
    ],
    "source_file": str,
    "source_format": str,
    "extraction_notes": list[str],
}
```

---

## Workflow Design

## 1) Ingestion

The ingestion stage reads the invoice file, detects the file type, and produces a canonical `parsed_invoice` object.

### Parsing strategy

#### Deterministic parsing

Used for:

* JSON
* CSV
* XML

These formats already contain structured fields, so they are parsed directly in Python.

#### LLM extraction

Used for:

* TXT
* PDF

These are the formats where the evaluation set introduces ambiguity:

* OCR-like corruption
* inconsistent field labels
* email wrappers
* misspellings
* noisy line-item layouts

For these formats, the workflow uses Claude to normalize the invoice into the shared schema above.

### Why hybrid parsing?

I intentionally did **not** use an LLM for every file. JSON / CSV / XML are cheaper, more reliable, and easier to debug with deterministic parsing. TXT / PDF are where agentic extraction actually adds value.

---

## 2) Validation

Validation is intentionally deterministic rather than LLM-driven.

The validation stage checks the parsed invoice against a local SQLite inventory database and produces issues / warnings that feed the approval stage.

### Validation checks currently implemented

#### Invoice-level checks

* missing vendor
* missing invoice number
* missing due date
* missing total amount
* non-positive total amount
* non-USD currency warning
* high-value invoice warning / escalation

#### Line-item checks

* missing item name
* missing quantity
* non-positive quantity
* item not found in inventory
* item exists but requested quantity exceeds available stock

### Inventory model

A local `inventory.db` is seeded with a small inventory table (e.g. `WidgetA`, `WidgetB`, `GadgetX`, `FakeItem`) so the workflow is self-contained and reproducible.

### Why deterministic validation?

Inventory checks, quantity checks, and currency checks are business rules, not reasoning problems. Keeping them deterministic makes the workflow easier to debug, cheaper to run, and more trustworthy.

---

## 3) Approval

Approval is treated as a reasoning stage rather than a pure rule engine.

The approval stage consumes:

* the parsed invoice
* validation issues / warnings
* suspicious extraction notes from ingestion

It then produces:

* an initial approval decision
* a reflection / critique pass
* a final decision
* reasoning explaining the decision

### Why use an LLM here?

Validation answers **“what is wrong?”**
Approval answers **“given these findings, should we pay this invoice?”**

That second question is inherently more contextual:

* Is this a data-quality issue or a fraud signal?
* Is this a stock problem or a reason to reject payment entirely?
* Is this high-value but legitimate, or high-value and suspicious?

Using an LLM here let me keep validation deterministic while still showing an agentic approval step with self-correction.

---

## 4) Payment

Payment is intentionally mocked.

If the final approval decision is `approved`, the workflow generates a mock payment ID and records a successful payment status.

If the invoice is rejected, payment is skipped.

This keeps the take-home focused on workflow design and reasoning rather than external payment integrations.

---

## How to Run

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

If your local virtual environment was moved on disk, prefer:

```bash
./venv/bin/python -m pip install -r requirements.txt
```

## 2. Add your Anthropic API key

Create a `.env` file in the repo root:

```env
ANTHROPIC_API_KEY=your_key_here
```

## 3. Seed the local inventory database

```bash
./venv/bin/python -m invoice_agents.db.seed
```

## 4. Run a single invoice end-to-end

```bash
./venv/bin/python main.py --invoice_path data/invoices/invoice_1001.txt
```

---

## Example Test Runs

I ran the workflow end-to-end on a representative set of invoices covering clean, malformed, suspicious, high-value, PDF, and non-USD scenarios.

## Summary Table

| Invoice             | Type | Scenario                                 | Validation Result              | Final Decision                  | Notes                                                     |
| ------------------- | ---: | ---------------------------------------- | ------------------------------ | ------------------------------- | --------------------------------------------------------- |
| `invoice_1001.txt`  |  TXT | clean baseline                           | passed                         | **approved**                    | valid vendor, valid totals, inventory OK                  |
| `invoice_1002.txt`  |  TXT | typo-heavy + overstock + high-value      | failed                         | **rejected**                    | `GadgetX` quantity exceeds stock                          |
| `invoice_1003.txt`  |  TXT | fraud-style / urgent payment / fake item | failed                         | **rejected**                    | out-of-stock fake item + suspicious language              |
| `invoice_1009.json` | JSON | broken data integrity                    | failed                         | **rejected**                    | negative total, negative quantity, missing vendor         |
| `invoice_1013.pdf`  |  PDF | repeated items + high-value              | failed                         | **rejected**                    | overstock + current normalization gaps for annotated SKUs |
| `invoice_1014.xml`  |  XML | valid invoice in EUR                     | validation passed with warning | **rejected (current behavior)** | currency mismatch                                         |

---

## Representative Behaviors by Invoice

## `invoice_1001.txt` — clean baseline

**Outcome:** Approved and paid.

The workflow:

* extracted the invoice cleanly
* validated stock and totals successfully
* approved the invoice
* generated a mock payment ID

This is the “happy path” baseline.

---

## `invoice_1002.txt` — messy TXT + overstock

This file contains abbreviated / corrupted fields such as:

* `INVOCE`
* `Vndr`
* `Inv #`
* `Dt`
* `Due Dt`

### Ingestion cleanup

The ingestion stage normalized those into canonical invoice fields and preserved its interpretation in `extraction_notes`, including:

* `Vndr` → vendor
* `Inv #` → invoice number
* `Dt` → invoice date
* `Due Dt` → due date

### Validation result

The invoice was flagged because:

* `GadgetX` requested quantity exceeded available stock

### Final outcome

Rejected.

---

## `invoice_1003.txt` — suspicious / fraud-style invoice

This invoice includes multiple signals of fraud or bad data:

* vendor name: `Fraudster LLC`
* due date set to literal `"yesterday"`
* immediate wire-pressure language
* line item `FakeItem`
* high total amount

### Ingestion cleanup

The LLM extraction successfully structured the invoice and preserved the suspicious aspects in `extraction_notes`.

### Validation result

* `FakeItem` is out of stock / invalid for the seeded inventory

### Final outcome

Rejected.

---

## `invoice_1009.json` — data integrity failure

This invoice demonstrates why validation is deterministic and separate from approval.

### Problems detected

* negative invoice total
* negative quantity for `WidgetA`
* missing vendor
* missing due date

### Final outcome

Rejected.

---

## `invoice_1013.pdf` — repeated items and PDF extraction

This PDF contains repeated items, different order notes, and a large total.

### Ingestion behavior

The LLM extraction pulled out line items such as:

* `WidgetA`
* `WidgetB`
* `GadgetX`
* `WidgetA (Replacement)`
* `GadgetX (Expedited)`
* `GadgetX (Sample)`

### Validation result

Current behavior flags:

* over-ordering on `WidgetA`
* over-ordering on `WidgetB`
* “unknown item” issues for annotated variants like `GadgetX (Expedited)`

### Why this matters

This is a good example of where the workflow is functional but still improvable:
the invoice is clearly parseable, but the **SKU normalization layer** should collapse item variants like `GadgetX (Expedited)` back to base inventory keys such as `GadgetX`.

### Final outcome

Rejected.

---

## `invoice_1014.xml` — non-USD invoice

This invoice parses cleanly and validates structurally, but is denominated in **EUR** rather than USD.

### Current behavior

* validation passes with a warning
* approval currently rejects the invoice due to currency mismatch

### Intended business behavior

In a production workflow, I would likely treat this as **manual review / escalation** rather than an automatic rejection, unless policy explicitly forbids non-USD payment.

I’ve kept the current behavior visible as a known limitation / policy decision point rather than hiding it.

---

## Design Decisions

## Hybrid parsing instead of “LLM for everything”

I intentionally split ingestion into:

* **deterministic parsing** for JSON / CSV / XML
* **LLM extraction** for TXT / PDF

This keeps costs lower, makes structured formats more predictable, and still demonstrates where agentic extraction actually adds value.

## Deterministic validation instead of LLM validation

Inventory checks, quantity checks, and currency checks are business rules, not reasoning problems. I kept them deterministic for:

* reliability
* debuggability
* reproducibility
* lower cost

## LLM approval with reflection

Approval is where I wanted the system to be more agentic:

* combine multiple weak signals
* interpret fraud-style language
* weigh validation issues in context
* run a second critique / reflection pass before finalizing

That gave me a workflow that is more than just “parser + if/else rules” without making every stage opaque.

---

## Known Issues / Current Limitations

### 1) Annotated SKU normalization is incomplete

In invoices like `invoice_1013.pdf`, item variants such as:

* `GadgetX (Expedited)`
* `WidgetA (Replacement)`
* `GadgetX (Sample)`

should ideally be normalized back to:

* `GadgetX`
* `WidgetA`

before inventory validation.

Right now, those are treated as unknown items, which is conservative but not ideal.

---

### 2) “Manual review” is represented as escalation metadata, not a final workflow branch

The validation stage can mark invoices as requiring additional scrutiny, but the current workflow still resolves to a final approval decision of **approved** or **rejected**.

If I extended the workflow, I would add a true third final state such as:

* `approved`
* `rejected`
* `manual_review`

---

### 3) Currency handling is policy-light

The current system flags non-USD invoices and the approval stage may reject them, but there is not yet a formal currency policy layer for:

* exchange-rate handling
* approved foreign vendors
* finance escalation rules by currency

---

### 4) Approval reasoning can be overly strict on future-dated invoices

In the current outputs, the approval stage treats some future-dated invoices as suspicious. Depending on the business context, that could be acceptable or overly conservative.

I left this behavior visible because it is a real tradeoff between:

* fraud sensitivity
* operational false positives

---

### 5) Payment is mocked

This is intentional for the take-home scope, but it means:

* no real payment API integration
* no idempotency / retry logic
* no ledgering or payment reconciliation

---

## Future Improvements

If I continued this beyond take-home scope, I would prioritize:

### 1) A true manual-review branch

Add a third final workflow outcome and route escalated invoices into a review queue instead of forcing a binary approve/reject.

### 2) Better SKU normalization

Normalize item variants such as:

* `Widget A`
* `WidgetA (Replacement)`
* `GadgetX - Expedited`

back to base inventory SKUs before stock validation.

### 3) Better validation severity modeling

Split validation findings into:

* hard failures
* review-required flags
* informational warnings

and feed those severities explicitly into approval.

### 4) More automated tests

Expand unit and integration coverage for:

* structured parsers
* LLM extraction fallbacks
* repeated-item aggregation
* approval edge cases

### 5) Lightweight UI

A Streamlit UI would make the workflow easier to demo by showing:

* raw invoice input
* parsed invoice output
* validation issues
* approval reasoning
* payment status
* log trail

---

## Notes on Scope

This project was built as a take-home MVP under ambiguity, so I deliberately optimized for:

* **end-to-end functionality**
* **clear separation of responsibilities by stage**
* **showing agentic behavior where it matters**
* **keeping the system runnable locally without external infrastructure**

Rather than overbuilding a full AP platform, I focused on producing a workflow that is:

* understandable
* testable
* extensible
* and honest about where the next iteration should go.
