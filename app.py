"""AuditLedger — Executive Dashboard (Streamlit).

A single launch command brings a fresh clone fully to life:

    streamlit run app.py

On first run this builds the database, executes the agent loop, and writes the
immutable audit log; thereafter it reads from that store. The dashboard shows
live processing metrics, dollars saved vs the manual benchmark, the human
exception queue (with approve/reject sign-off), and an interactive audit-log
browser — every figure measured from the run, never fabricated.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the ``src`` layout importable from a fresh clone without installation.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def main() -> None:
    import pandas as pd
    import streamlit as st

    from auditledger import analytics, config
    from auditledger.db import audit_log, exception_queue
    from auditledger.db.database import connect
    from auditledger.service import ensure_database, explain_invoice

    st.set_page_config(page_title="AuditLedger", page_icon="🧾", layout="wide")

    # First launch builds everything; later reruns reuse the populated store.
    ensure_database(config.DB_PATH)
    conn = connect(config.DB_PATH)

    # --- Header -----------------------------------------------------------
    st.title("🧾 AuditLedger")
    st.caption(
        "Auditable AI invoice reconciliation — the LLM recommends, deterministic "
        "math decides, and every decision is logged immutably. Human sign-off is "
        "mandatory for exceptions."
    )

    roi = analytics.roi_summary(conn)
    intact, broken = audit_log.verify_chain(conn)

    # --- Top metric row ---------------------------------------------------
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Invoices processed", roi["invoices_processed"])
    c2.metric("Automation rate", f"{roi['automation_rate']:.0%}")
    c3.metric("Error catch rate", f"{analytics.overall_catch_rate(conn):.0%}")
    c4.metric("Cost avoided", f"${roi['cost_avoided_usd']:,.0f}",
              help=f"vs ${roi['manual_benchmark_per_invoice_usd']:.2f}/invoice manual benchmark")
    c5.metric("Audit chain", "INTACT ✅" if intact else f"BROKEN @ {broken} ⛔")

    # --- Sidebar ----------------------------------------------------------
    with st.sidebar:
        st.header("Controls")
        st.write(f"**Confidence threshold:** {config.CONFIDENCE_THRESHOLD:.2f}")
        st.write(f"**Model version:** `{roi_model_version(conn)}`")
        st.write(f"**DB file:** `{config.DB_PATH}`")
        st.divider()
        st.caption(
            "Metrics are queried live from the immutable audit log. "
            f"Est. hours saved: **{roi['estimated_hours_saved']}** "
            f"({roi['estimated_hours_saved_basis']})."
        )
        st.caption(f"AI cost: {roi['ai_cost_note']}")

    tab_overview, tab_queue, tab_audit = st.tabs(
        ["📊 Overview", "🙋 Exception Queue", "🔍 Audit Log Browser"]
    )

    # --- Overview ---------------------------------------------------------
    with tab_overview:
        left, right = st.columns(2)
        with left:
            st.subheader("Dispositions")
            breakdown = analytics.classification_breakdown(conn)
            st.bar_chart(pd.DataFrame(
                {"count": breakdown}).sort_index(), color="#2563eb")
        with right:
            st.subheader("Catch rate by error taxonomy")
            by_type = analytics.catch_rate_by_taxonomy(conn)
            df = pd.DataFrame([
                {"error_type": k, "caught": v["caught"], "total": v["total"],
                 "catch_rate": v["catch_rate"]}
                for k, v in sorted(by_type.items())
            ])
            st.dataframe(df, hide_index=True)

        st.subheader("ROI detail")
        st.json(roi)

    # --- Exception Queue (human-in-the-loop) ------------------------------
    with tab_queue:
        st.subheader("Pending human review")
        pending = exception_queue.list_pending(conn)
        if not pending:
            st.success("No pending exceptions — the queue is clear.")
        else:
            st.dataframe(
                pd.DataFrame([{
                    "invoice_id": r["invoice_id"],
                    "AI recommendation": r["ai_classification"],
                    "confidence": r["ai_confidence"],
                    "reasoning": r["ai_reasoning"],
                } for r in pending]),
                hide_index=True,
            )

            st.markdown("**Record a decision**")
            with st.form("resolve_form", clear_on_submit=True):
                target = st.selectbox("Invoice", [r["invoice_id"] for r in pending])
                reviewer = st.text_input("Reviewer", value="reviewer")
                decision = st.radio("Decision", [exception_queue.APPROVED, exception_queue.REJECTED],
                                    horizontal=True)
                note = st.text_area("Note (recorded immutably)")
                if st.form_submit_button("Submit sign-off"):
                    exception_queue.resolve(conn, invoice_id=target, reviewer=reviewer,
                                            decision=decision, note=note)
                    st.success(f"{decision} recorded for {target} by {reviewer}.")
                    st.rerun()

        resolved = [r for r in exception_queue.list_all(conn) if r["status"] != "PENDING"]
        if resolved:
            st.subheader("Resolved")
            st.dataframe(
                pd.DataFrame([{
                    "invoice_id": r["invoice_id"],
                    "AI reco": r["ai_classification"],
                    "human": r["status"],
                    "reviewer": r["reviewer"],
                    "note": r["human_note"],
                } for r in resolved]),
                hide_index=True,
            )

    # --- Audit Log Browser ------------------------------------------------
    with tab_audit:
        st.subheader("Explain any invoice from the log alone")
        invoice_ids = [r["invoice_id"] for r in conn.execute(
            "SELECT DISTINCT invoice_id FROM audit_log ORDER BY invoice_id").fetchall()]
        selected = st.selectbox("Invoice", invoice_ids)
        story = explain_invoice(conn, selected)

        m1, m2, m3 = st.columns(3)
        m1.metric("AI recommendation", story["ai_recommendation"])
        m2.metric("Confidence", f"{story['ai_confidence']:.2f}" if story["ai_confidence"] else "—")
        m3.metric("Final disposition", story["final_disposition"])
        st.caption(f"Input hash: `{story['input_hash']}` · model `{story['model_version']}`")

        st.markdown("**Decision timeline**")
        st.dataframe(
            pd.DataFrame([{
                "time": t["event_time"],
                "event": t["event_type"],
                "actor": t["actor"],
                "classification": t["classification"],
                "confidence": t["confidence"],
                "reasoning": t["reasoning"],
            } for t in story["timeline"]]),
            hide_index=True,
        )

    conn.close()


def roi_model_version(conn) -> str:
    row = conn.execute(
        "SELECT model_version FROM audit_log WHERE event_type='AGENT_DECISION' LIMIT 1"
    ).fetchone()
    return row["model_version"] if row else "unknown"


if __name__ == "__main__":
    main()
