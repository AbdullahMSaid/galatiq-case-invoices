"""Streamlit review console for the invoice-processing workflow.

A reviewer can pick a sample invoice (or upload one), run the existing LangGraph
pipeline, and walk each stage (ingestion -> validation -> approval -> payment) with
KPI cards, a status timeline, and expandable raw details. All business logic lives in
invoice_agents/; this file only drives and presents it.

Run with:  ./venv/bin/python -m streamlit run streamlit_app.py
"""

from __future__ import annotations

import base64
import html
import os
import traceback
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from invoice_agents.graph import build_graph

load_dotenv()

INVOICES_DIR = Path("data/invoices")
UPLOAD_DIR = Path(".tmp_uploads")
DB_PATH = Path("inventory.db")  # matches db/seed.py + tools/inventory.py (relative to CWD)
UPLOAD_TYPES = ["txt", "json", "csv", "xml", "pdf"]
# JSON is parsed deterministically; every other format goes through the LLM extractor.
LLM_FORMATS = {".txt", ".pdf", ".csv", ".xml"}
PREVIEW_LIMIT = 4000  # chars, to keep text previews from ballooning the page

WORKFLOW_TREE = """\
START
  └─ Ingestion   parse file → structured invoice (JSON local · TXT/PDF/CSV/XML via LLM)
       └─ Validation   check items & quantities against inventory.db (issues / warnings)
            └─ Approval   LLM approver → reflection/critique pass → final decision
                 ├─ approved → Payment   mock payment, mint PAY-id
                 └─ rejected → log rejection (no payment)
END"""


# ----------------------------------------------------------------------------- helpers
def list_sample_invoices() -> list[Path]:
    if not INVOICES_DIR.is_dir():
        return []
    return sorted(p for p in INVOICES_DIR.iterdir() if p.is_file())


def save_uploaded_file(uploaded_file) -> Path:
    """Persist an uploaded file to .tmp_uploads/ and return its path."""
    UPLOAD_DIR.mkdir(exist_ok=True)
    dest = UPLOAD_DIR / uploaded_file.name
    dest.write_bytes(uploaded_file.getbuffer())
    return dest


def requires_llm(path: Path) -> bool:
    return path.suffix.lower() in LLM_FORMATS


def run_workflow(invoice_path: Path) -> dict:
    """Invoke the existing LangGraph pipeline (no logic duplicated here)."""
    graph = build_graph()
    return graph.invoke({"invoice_path": str(invoice_path)})


def _decision_kind(final_decision: str, payment_status: str, requires_review: bool) -> str:
    if final_decision == "approved" and payment_status == "success":
        return "success"
    if final_decision == "rejected" or payment_status == "not_paid":
        return "error"
    if requires_review:
        return "warning"
    return "neutral"


_ICONS = {"success": "✅", "error": "⛔", "warning": "⚠️", "neutral": "⏳"}


def _status(kind: str, message: str) -> None:
    {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(message)


def _html_block(text: str, css_class: str) -> None:
    """Render prose inside a styled card (HTML-escaped, newlines preserved)."""
    safe = html.escape(str(text)).replace("\n", "<br>")
    st.markdown(f'<div class="{css_class}">{safe}</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------- renderers
def render_metrics(result: dict) -> None:
    parsed = result.get("parsed_invoice") or {}
    final_decision = result.get("final_decision", "unknown")
    payment_status = result.get("payment_status", "unknown")
    requires_review = result.get("requires_manual_review", False)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Vendor", parsed.get("vendor") or "—")
    total = parsed.get("total_amount")
    c2.metric("Total", "—" if total is None else f"{total:,.2f}")
    c3.metric("Currency", parsed.get("currency") or "—")
    c4.metric("Final Decision", final_decision)
    c5.metric("Payment Status", payment_status)

    kind = _decision_kind(final_decision, payment_status, requires_review)
    if requires_review:
        _status("warning", "⚠️ Flagged for manual review")
    _status(kind, f"{_ICONS[kind]} Final decision: **{final_decision}** · payment **{payment_status}**")


def render_original_file(path: Path) -> None:
    st.markdown(f"**Source file:** `{path.name}`")
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            data = path.read_bytes()
            b64 = base64.b64encode(data).decode()
            st.markdown(
                f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="600" '
                'style="border:1px solid rgba(128,128,128,0.25); border-radius:12px;"></iframe>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "Download original PDF", data, file_name=path.name, mime="application/pdf"
            )
        except Exception as exc:
            st.warning(f"Could not preview PDF: {exc}")
        st.caption("pdfplumber extracts the PDF text downstream during ingestion.")
        return

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        st.warning(f"Could not preview file: {exc}")
        return
    truncated = len(text) > PREVIEW_LIMIT
    body = text[:PREVIEW_LIMIT] + ("\n… (truncated)" if truncated else "")
    _html_block(body, "preview-card")
    if truncated:
        st.caption(f"Preview limited to {PREVIEW_LIMIT:,} characters.")


def render_parsed_invoice(parsed: dict) -> None:
    if not parsed:
        st.warning("No parsed invoice data.")
        return

    left, right = st.columns(2)
    with left:
        st.markdown(f"**Vendor:** {parsed.get('vendor') or '—'}")
        st.markdown(f"**Invoice #:** {parsed.get('invoice_number') or '—'}")
        st.markdown(f"**Currency:** {parsed.get('currency') or '—'}")
    with right:
        st.markdown(f"**Invoice date:** {parsed.get('invoice_date') or '—'}")
        st.markdown(f"**Due date:** {parsed.get('due_date') or '—'}")
        total = parsed.get("total_amount")
        st.markdown(f"**Total:** {'—' if total is None else f'{total:,.2f}'}")

    items = parsed.get("line_items") or []
    if items:
        st.markdown("**Line items**")
        st.dataframe(items, use_container_width=True, hide_index=True)
    else:
        st.caption("No line items extracted.")

    notes = parsed.get("extraction_notes") or []
    with st.expander(f"Extraction notes ({len(notes)})"):
        if notes:
            for n in notes:
                st.markdown(f"- {n}")
        else:
            st.caption("None.")
    with st.expander("Raw parsed invoice (JSON)"):
        st.json(parsed)


def render_validation(result: dict) -> None:
    passed = result.get("validation_passed")
    issues = result.get("validation_issues") or []
    warnings = result.get("validation_warnings") or []
    requires_review = result.get("requires_manual_review", False)

    if passed:
        _status("success", "Validation passed — no blocking issues.")
    else:
        _status("error", f"Validation failed — {len(issues)} blocking issue(s).")
    if requires_review:
        _status("warning", "Manual review recommended.")

    if issues:
        st.markdown("**Issues**")
        for i in issues:
            st.error(i)
    if warnings:
        st.markdown("**Warnings**")
        for w in warnings:
            st.warning(w)
    if not issues and not warnings:
        st.caption("No issues or warnings.")

    with st.expander("Raw validation (JSON)"):
        st.json(
            {
                "validation_passed": passed,
                "requires_manual_review": requires_review,
                "validation_issues": issues,
                "validation_warnings": warnings,
            }
        )


def render_approval(result: dict) -> None:
    final_decision = result.get("final_decision", "unknown")
    approver = result.get("approval_decision", "—")
    reflection = result.get("reflection_decision", "—")

    c1, c2, c3 = st.columns(3)
    c1.metric("Approver", approver)
    c2.metric("Reflection", reflection)
    c3.metric("Final", final_decision)
    if approver != reflection:
        st.caption("↻ Reflection pass overturned the initial decision.")

    reasoning = result.get("reflection_reasoning") or result.get("approval_reasoning")
    if reasoning:
        st.markdown("**Reasoning**")
        _html_block(reasoning, "reasoning-box")

    with st.expander("Raw approval (JSON)"):
        st.json(
            {
                "approval_decision": approver,
                "approval_reasoning": result.get("approval_reasoning"),
                "reflection_decision": reflection,
                "reflection_reasoning": result.get("reflection_reasoning"),
                "final_decision": final_decision,
            }
        )


def render_payment(result: dict) -> None:
    status = result.get("payment_status", "unknown")
    payment_id = result.get("payment_id")
    if status == "success":
        _status("success", f"Payment executed — ID `{payment_id}`.")
    elif status == "not_paid":
        _status("error", "Payment skipped — invoice was rejected.")
    else:
        _status("neutral", f"Payment status: {status}.")
    with st.expander("Raw payment (JSON)"):
        st.json({"payment_status": status, "payment_id": payment_id})


def render_logs(logs: list) -> None:
    if not logs:
        st.caption("No log entries recorded.")
        return
    for i, entry in enumerate(logs, start=1):
        safe = html.escape(str(entry))
        st.markdown(
            f'<div class="log-item"><span class="log-idx">{i}.</span>{safe}</div>',
            unsafe_allow_html=True,
        )


# A timeline stage: (header, kind, one-line summary, render-body callable).
def _stage_summary(result: dict) -> list[tuple]:
    parsed = result.get("parsed_invoice") or {}
    items = parsed.get("line_items") or []
    issues = result.get("validation_issues") or []
    warnings = result.get("validation_warnings") or []
    final_decision = result.get("final_decision", "unknown")
    payment_status = result.get("payment_status", "unknown")

    ingest_kind = "success" if parsed.get("vendor") or items else "warning"
    val_kind = "success" if result.get("validation_passed") else "error"
    if result.get("validation_passed") and result.get("requires_manual_review"):
        val_kind = "warning"
    appr_kind = "success" if final_decision == "approved" else "error"
    pay_kind = {"success": "success", "not_paid": "error"}.get(payment_status, "neutral")

    return [
        (
            "1 · Ingestion",
            ingest_kind,
            f"Parsed {len(items)} line item(s) from vendor “{parsed.get('vendor') or 'unknown'}”.",
            lambda: render_parsed_invoice(parsed),
        ),
        (
            "2 · Validation",
            val_kind,
            f"{len(issues)} issue(s), {len(warnings)} warning(s).",
            lambda: render_validation(result),
        ),
        (
            "3 · Approval",
            appr_kind,
            f"Approver={result.get('approval_decision','—')}, "
            f"reflection={result.get('reflection_decision','—')} → {final_decision}.",
            lambda: render_approval(result),
        ),
        (
            "4 · Payment",
            pay_kind,
            f"Status: {payment_status}.",
            lambda: render_payment(result),
        ),
    ]


# ----------------------------------------------------------------------------- page setup
st.set_page_config(layout="wide", page_title="Invoice Workflow", page_icon="🧾")

st.markdown(
    """
    <style>
      /* Theme-aware: inherits Streamlit's light/dark palette via CSS variables,
         with neutral-gray borders that read well in both modes. */
      .main .block-container { padding-top: 2rem; max-width: 1200px; }

      /* Consistent prose typography for all natural-language text. */
      .main p, .main li, .reasoning-box, .log-item {
          font-size: 0.95rem;
          line-height: 1.6;
      }

      div[data-testid="stExpander"], div[data-testid="stMetric"] {
          background: var(--secondary-background-color);
          border: 1px solid rgba(128, 128, 128, 0.25);
          border-radius: 12px;
          padding: 0.4rem 0.9rem;
      }
      div[data-testid="stMetric"] { padding: 0.8rem 1rem; }
      h3, h4 { margin-top: 0.6rem; }

      .reasoning-box {
          background: var(--secondary-background-color);
          color: var(--text-color);
          border: 1px solid rgba(128, 128, 128, 0.25);
          border-left: 4px solid rgba(120, 120, 200, 0.6);
          border-radius: 12px;
          padding: 1rem 1.2rem;
          margin: 0.4rem 0 0.8rem 0;
      }
      .log-item {
          background: var(--secondary-background-color);
          color: var(--text-color);
          border-left: 3px solid rgba(128, 128, 128, 0.45);
          border-radius: 6px;
          padding: 0.4rem 0.9rem;
          margin: 0.3rem 0;
      }
      .log-item .log-idx { opacity: 0.55; margin-right: 0.5rem; font-variant-numeric: tabular-nums; }
      .preview-card {
          background: var(--secondary-background-color);
          color: var(--text-color);
          border: 1px solid rgba(128, 128, 128, 0.25);
          border-radius: 12px;
          padding: 1rem 1.2rem;
          white-space: pre-wrap;
          word-break: break-word;
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 0.85rem;
          line-height: 1.5;
          max-height: 480px;
          overflow: auto;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Invoice Processing Workflow")
st.caption("Ingestion → Validation → Approval → Payment")

# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Run a workflow")
    mode = st.radio("Invoice source", ["Sample invoice", "Upload invoice"], index=0)

    invoice_path: Path | None = None
    if mode == "Sample invoice":
        samples = list_sample_invoices()
        if not samples:
            st.error(f"No invoices found in `{INVOICES_DIR}/`.")
        else:
            chosen = st.selectbox("Sample invoice", [p.name for p in samples])
            invoice_path = INVOICES_DIR / chosen
    else:
        uploaded = st.file_uploader("Upload an invoice", type=UPLOAD_TYPES)
        if uploaded is not None:
            try:
                invoice_path = save_uploaded_file(uploaded)
                st.caption(f"Saved to `{invoice_path}`")
            except Exception as exc:
                st.error(f"Could not save upload: {exc}")
        st.caption("Uploaded TXT / PDF / CSV / XML invoices may call the Anthropic LLM API.")

    run = st.button("Run Workflow", type="primary", use_container_width=True, disabled=invoice_path is None)

    st.divider()
    st.markdown("**Setup reminders**")
    st.markdown("- Seed inventory: `./venv/bin/python -m invoice_agents.db.seed`")
    st.markdown("- `ANTHROPIC_API_KEY` is required for TXT/PDF/CSV/XML extraction.")

# ----------------------------------------------------------------------------- main
if not run:
    st.subheader("What this does")
    st.write(
        "Pick a sample invoice or upload your own, then click **Run Workflow**. The app "
        "runs the invoice through a four-stage LangGraph pipeline and shows what happened "
        "at each step — the cleaned-up parsed invoice, inventory validation flags, the "
        "LLM approval (with a reflection/critique pass), and the simulated payment."
    )
    st.subheader("Workflow")
    st.code(WORKFLOW_TREE, language="text")
    st.stop()

# --- preconditions ---
if invoice_path is None:
    st.warning("Select or upload an invoice first.")
    st.stop()

if not DB_PATH.exists():
    st.error(
        "Inventory database `inventory.db` is missing. Seed it first:\n\n"
        "```bash\n./venv/bin/python -m invoice_agents.db.seed\n```"
    )
    st.stop()

if requires_llm(invoice_path) and not os.getenv("ANTHROPIC_API_KEY"):
    st.error(
        f"`{invoice_path.name}` needs LLM extraction, but `ANTHROPIC_API_KEY` is not set. "
        "Add it to a `.env` file in the repo root, or use a `.json` invoice (parsed locally)."
    )
    st.stop()

# --- run ---
try:
    with st.spinner("Running the workflow…"):
        result = run_workflow(invoice_path)
except Exception as exc:
    st.error(f"Workflow failed: {exc}")
    with st.expander("Traceback"):
        st.code(traceback.format_exc())
    st.stop()

# --- results ---
render_metrics(result)

st.divider()
col_file, col_flow = st.columns([1, 2])
with col_file:
    st.subheader("Original file")
    render_original_file(invoice_path)
with col_flow:
    st.subheader("Workflow timeline")
    for header, kind, summary, body in _stage_summary(result):
        st.markdown(f"#### {_ICONS[kind]} {header}")
        st.caption(summary)
        with st.expander("Details"):
            body()

st.divider()
st.subheader("Audit log")
render_logs(result.get("logs") or [])
