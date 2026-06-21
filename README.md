<div align="center">

# 🧾 Invoice Processing Workflow

**A local-first, multi-agent invoice pipeline — ingest → validate → approve → pay — with LLM reasoning and a self-critique loop.**

[![Python](https://img.shields.io/badge/Python-3.9-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C)](https://langchain-ai.github.io/langgraph/)
[![Claude](https://img.shields.io/badge/LLM-Claude%20Sonnet%204.6-D97757)](https://www.anthropic.com/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Runs Offline](https://img.shields.io/badge/runtime-local--first-success)](#)

</div>

---

Built for the Galatiq AI take-home. The system ingests invoices across five file formats,
normalizes them into a single schema, validates them against a mock inventory database,
simulates a VP-style approval with **LLM reasoning plus a reflection/critique pass**, and
executes a (mocked) payment **only** when the invoice is approved — all runnable locally
with no external infrastructure.

> **TL;DR** — Deterministic where business rules belong, agentic where judgment belongs.
> JSON is parsed in plain Python; messy TXT/PDF/CSV/XML go through Claude; inventory and
> data-integrity checks are pure rules; approval is an LLM that critiques its own decision
> before committing.

---

## ✨ Highlights

- **Four-stage LangGraph pipeline** with shared, append-only audit state.
- **Hybrid ingestion** — deterministic JSON parsing; LLM extraction for noisy formats.
- **Self-correcting approval** — an approver LLM followed by a reflection pass that can
  overturn the first decision, and **fails safe to reject** on any error.
- **Deterministic validation** — SKU normalization, per-SKU quantity aggregation, and
  inventory/data-integrity checks against local SQLite.
- **Streamlit review console** — pick or upload an invoice, run the workflow, and inspect
  every stage with KPIs, an embedded file preview, a status timeline, and the audit log.
- **Tested** — an offline pytest suite (no API cost) plus one end-to-end integration test.
- **Local-first** — no internet, no real money; one command seeds a reproducible inventory.

---

## 🚀 Quickstart

```bash
# 1. install (use ./venv/bin/python if the bundled venv was moved on disk)
pip install -r requirements.txt

# 2. add your key
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# 3. seed the local inventory database
python -m invoice_agents.db.seed

# 4a. run one invoice end-to-end on the CLI
python main.py --invoice_path data/invoices/invoice_1001.txt

# 4b. …or launch the visual review console
python -m streamlit run streamlit_app.py
```

> JSON invoices are parsed locally and need no key. TXT/PDF/CSV/XML call the Claude API.

---

## 🏛️ Architecture

```text
                    ┌─────────────────────────┐
                    │      Input Invoice      │
                    │  txt · json · csv ·     │
                    │       xml · pdf         │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │        INGESTION        │
                    │ ─────────────────────── │
                    │ JSON → Python parser    │
                    │ TXT/PDF/CSV/XML → Claude│
                    │ → canonical parsed dict │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │       VALIDATION        │
                    │ ─────────────────────── │
                    │ SKU normalize+aggregate │
                    │ SQLite inventory checks │
                    │ data-integrity + flags  │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │        APPROVAL         │
                    │ ─────────────────────── │
                    │ LLM approver →          │
                    │ reflection / critique → │
                    │ final decision          │
                    └────────────┬────────────┘
                approved ◄───────┴───────► rejected
                    ▼                          ▼
        ┌───────────────────┐      ┌───────────────────┐
        │      PAYMENT      │      │   LOG REJECTION   │
        │ mock pay, mint    │      │ record reasoning, │
        │ PAY-id, success   │      │ skip payment      │
        └───────────────────┘      └───────────────────┘
```

The four stages are LangGraph nodes wired
`START → ingest → validate → approve → {pay | reject} → END`. State is a `TypedDict`;
each node returns a partial dict that LangGraph merges. The `logs` field uses an
`Annotated[list[str], operator.add]` **reducer**, so every stage *appends* to a single
audit trail rather than overwriting it.

---

## 📂 Repository structure

```text
.
├── data/invoices/                 # 20 sample invoices (clean → adversarial)
├── invoice_agents/
│   ├── state.py                   # InvoiceState — the shared, typed workflow contract
│   ├── graph.py                   # build_graph() — the LangGraph wiring
│   ├── agents/
│   │   ├── ingestion.py           # parse / LLM-extract → canonical invoice
│   │   ├── validation.py          # deterministic inventory + integrity checks
│   │   ├── approval.py            # LLM decision + reflection pass (fails safe)
│   │   └── payment.py             # mock payment / rejection logging
│   ├── tools/
│   │   ├── inventory.py           # read-only inventory lookup
│   │   └── payment.py             # mock_payment stub
│   └── db/seed.py                 # seeds the local inventory.db
├── tests/                         # pytest suite (offline + 1 integration)
├── main.py                        # CLI entrypoint
├── streamlit_app.py               # Streamlit review console
├── requirements.txt
└── README.md
```

---

## 🧩 Canonical invoice shape

Every format is normalized into one structure, so each downstream stage sees a single schema:

```python
{
    "invoice_number": str | None,
    "vendor": str | None,
    "invoice_date": str | None,
    "due_date": str | None,
    "currency": str,                 # defaults to "USD" when unstated
    "total_amount": float | None,
    "line_items": [
        {"item": str | None, "quantity": int | float | None, "unit_price": float | None}
    ],
    "source_file": str,
    "source_format": str,
    "extraction_notes": list[str],   # uncertainty / OCR ambiguity / fraud signals
}
```

---

## 🔍 How each stage works

### 1 · Ingestion — hybrid parsing

| Format | Strategy | Why |
| --- | --- | --- |
| **JSON** | Deterministic Python (`_parse_json_invoice`) | Already structured — cheap, reliable, debuggable. |
| **TXT · PDF · CSV · XML** | LLM extraction (Claude + Pydantic `with_structured_output`) | This is where the dataset hides OCR corruption, missing labels, email wrappers, and noisy line-item layouts — exactly where agentic extraction earns its keep. |

PDF text is pulled with `pdfplumber` first. The extraction prompt is tuned to fix
OCR-style transcription (`2O26` → `2026`), exclude subtotal/tax/total rows from line items,
**preserve suspicious values verbatim** (a negative quantity, a `"yesterday"` due date),
and record item names exactly as written — canonicalization is validation's job.

### 2 · Validation — deterministic by design

Inventory, quantity, and currency checks are **business rules, not reasoning problems**, so
they're pure code: reliable, reproducible, debuggable, and free. The stage:

- **normalizes item names** — strips parentheticals, collapses spacing (`"Widget A"` →
  `WidgetA`), and drops trailing annotation words (`"GadgetX Expedited"` → `GadgetX`), while
  leaving genuinely unknown items (`WidgetC`) intact;
- **aggregates quantities per real SKU** before checking stock (so repeated/annotated lines
  add up correctly);
- emits **issues** (blocking) and **warnings** (advisory), and sets `requires_manual_review`.

<details><summary><b>Checks implemented</b></summary>

**Invoice-level:** missing vendor *(blocking issue)*, missing total, non-positive total,
non-USD currency *(warning + manual review)*, total below line-item subtotal *(warning)*.

**Line-item:** missing name, missing quantity, non-positive quantity, item not in
inventory, requested quantity exceeds available stock, out-of-stock item.

</details>

### 3 · Approval — LLM with a reflection loop

Validation answers *"what's wrong?"*; approval answers *"given these findings, should we
pay?"* — an inherently contextual question (data-quality issue vs. fraud signal,
high-value-but-legitimate vs. high-value-and-suspicious). So approval is agentic:

1. builds rule-based context (>$10K scrutiny threshold, validation flags, extraction notes);
2. an **approver** LLM proposes approve/reject with reasoning;
3. a **reflection/critique** LLM independently audits and can overturn it;
4. the reflection's verdict is final — and on **any** LLM/API error it **fails safe to reject**.

### 4 · Payment — mocked, branch-aware

Approved → `mock_payment()` mints a `PAY-xxxxxxxx` id and records `success`. Rejected → the
rejection reasoning is logged and payment is skipped. Mocking keeps the take-home focused on
workflow design rather than payment-rail integration.

---

## 🖥️ Streamlit review console

```bash
python -m streamlit run streamlit_app.py
```

A polished demo UI that imports and invokes the **same** LangGraph pipeline (no logic
duplicated). It lets a reviewer:

- pick a sample invoice **or upload their own** (txt/json/csv/xml/pdf);
- see top **KPI cards** — vendor, total, currency, final decision, payment status;
- preview the **original file** — text formats inline, PDFs embedded with a download fallback;
- walk a **stage timeline** with status icons, plain-language summaries, and expandable raw JSON;
- read the full **audit log**.

It's dark-mode safe (theme-aware styling), and surfaces clear setup errors — a missing
`inventory.db` or a missing `ANTHROPIC_API_KEY` for LLM formats.

---

## ✅ Testing

```bash
python -m pytest -m "not integration"   # 8 offline tests — no API cost
python -m pytest -m integration         # 1 end-to-end test — needs ANTHROPIC_API_KEY
```

| Test file | Covers |
| --- | --- |
| `test_seed.py` | Seeding builds the canonical inventory + idempotency. |
| `test_ingestion.py` | Deterministic JSON parsing of vendor + line items. |
| `test_validation.py` | Overstock, missing-vendor-as-issue, **annotated-SKU aggregation**, unknown-item preservation, non-USD → manual review. |
| `test_graph.py` | Full graph: clean invoice → approved → payment success *(integration)*. |

Validation tests run against a **temporary** seeded database and never touch the real
`inventory.db`; LLM-format extraction is stubbed with static parsed dicts so the offline
suite is fast, free, and deterministic.

---

## 🧪 Representative behaviors

| Invoice | Type | Scenario | Validation | Final | Why |
| --- | :--: | --- | --- | --- | --- |
| `invoice_1001.txt` | TXT | clean baseline | passed | ✅ **approved** | valid vendor, totals, and stock |
| `invoice_1002.txt` | TXT | typos + overstock + high-value | failed | ⛔ **rejected** | `GadgetX` exceeds stock |
| `invoice_1003.txt` | TXT | fraud-style (urgent wire, fake item) | failed | ⛔ **rejected** | out-of-stock `FakeItem` + fraud signals |
| `invoice_1009.json` | JSON | broken data integrity | failed | ⛔ **rejected** | negative total & quantity, **missing vendor** |
| `invoice_1013.pdf` | PDF | repeated/annotated SKUs + high-value | failed | ⛔ **rejected** | SKUs aggregate (WidgetA 22>15, GadgetX 9>5); +$50 total discrepancy |
| `invoice_1014.xml` | XML | valid invoice in EUR | passed + ⚠️ review | ⛔ **rejected** | non-USD → flagged for manual review |

A couple worth calling out:

- **`invoice_1013.pdf`** stresses SKU handling: its lines include `GadgetX (Expedited)`,
  `GadgetX (Sample)`, and `WidgetA (Replacement)`. Normalization folds these back to base
  SKUs and aggregates quantities, so the genuine over-order is caught instead of being
  mislabeled "unknown item."
- **`invoice_1014.xml`** parses cleanly but is EUR-denominated. Validation flags it for
  **manual review**; approval currently rejects on currency mismatch — kept visible as a
  policy decision point (see Limitations).

---

## 🧠 Design decisions

- **Hybrid parsing over "LLM for everything."** Structured formats are parsed
  deterministically; the LLM is reserved for genuinely messy input. Lower cost, more
  predictable, easier to debug.
- **Deterministic validation.** Inventory/quantity/currency are rules, not judgment —
  keeping them out of the LLM makes results trustworthy and reproducible.
- **Agentic approval with self-critique.** A reflection pass lets the system combine weak
  signals, interpret fraud-style language, and second-guess itself — more than "parser +
  if/else," without making every stage opaque.
- **Fail safe.** Any approval-path error resolves to *reject*, never an accidental payment.

---

## ⚠️ Limitations & roadmap

Honest about where the next iteration should go:

- **No `subtotal`/`tax` in the schema.** A total above the line-item subtotal is currently
  assumed to be tax/fees. Adding `subtotal` + `tax_amount` would let validation
  *deterministically* catch discrepancies like `invoice_1013`'s deliberate +$50.
- **No true `manual_review` terminal state.** `requires_manual_review` is metadata today;
  the graph still resolves to approved/rejected. A third outcome routing into a review queue
  is the natural next step.
- **Currency policy is light.** Non-USD is flagged, but there's no exchange-rate handling,
  approved-foreign-vendor list, or per-currency escalation policy.
- **Date grounding.** The approval LLM should be passed the real current date for
  deterministic future-date reasoning.
- **Payment is mocked** — no real rail, idempotency/retry, or reconciliation (intentional
  for scope).

---

## 📝 Notes on scope

Built as a take-home MVP under ambiguity, deliberately optimized for **end-to-end
functionality**, **clear per-stage separation of responsibilities**, **agentic behavior
where it actually matters**, and **a system that runs locally with zero external
infrastructure** — understandable, testable, extensible, and honest about its edges.
