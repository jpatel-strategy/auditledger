"""AuditLedger — Executive Dashboard (Streamlit).

A single launch command brings a fresh clone fully to life:

    streamlit run app.py

On first run this builds the database, executes the agent loop, and writes the
immutable audit log; thereafter it reads from that store. The UI is an
executive "fintech audit" skin over the existing SQLite layer — no Milestone
1–4 logic is changed here. Every figure shown is measured from the run.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the ``src`` layout importable from a fresh clone without installation.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

GITHUB_URL = "github.com/jpatel-strategy/auditledger"

# --- Design tokens (from the UI brief) ------------------------------------
_CSS = """
<style>
:root{
  --navy-900:#0D1B2A; --navy-700:#1B2D45; --teal-500:#1B9AAA; --teal-100:#E8F4F6;
  --gold-500:#D4A843; --green-600:#2E9E5B; --amber-500:#E0A100; --red-600:#C0392B;
  --gray-50:#F7F9FA; --gray-200:#E3E8EC; --gray-500:#64727D; --white:#FFFFFF;
  --mono:"JetBrains Mono","SFMono-Regular",Consolas,monospace;
}
.al-hero{padding:8px 0 4px 0;}
.al-wordmark{font-size:30px;font-weight:700;letter-spacing:-0.5px;line-height:1;}
.al-wordmark .a{color:var(--navy-900);} .al-wordmark .l{color:var(--teal-500);}
.al-tagline{font-size:17px;color:var(--navy-700);font-weight:600;margin-top:6px;}
.al-problem{font-size:14px;color:var(--gray-500);margin-top:2px;}
.al-trust{display:inline-block;margin-top:10px;padding:5px 12px;border-radius:999px;
  background:var(--teal-100);color:var(--navy-700);font-size:13px;font-weight:600;}
.al-kpis{display:flex;gap:16px;flex-wrap:wrap;margin:18px 0 6px 0;}
.al-card{flex:1 1 200px;background:var(--white);border-radius:12px;
  box-shadow:0 1px 3px rgba(13,27,42,.08);border-top:3px solid var(--teal-500);
  padding:18px 20px;}
.al-card .val{font-size:30px;font-weight:700;color:var(--navy-900);line-height:1.1;}
.al-card .val.gold{color:var(--gold-500);font-family:var(--mono);}
.al-card .lab{font-size:13px;color:var(--gray-500);margin-top:6px;}
.al-pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;
  font-weight:700;color:var(--white);}
.al-pill.green{background:var(--green-600);} .al-pill.amber{background:var(--amber-500);}
.al-pill.red{background:var(--red-600);} .al-pill.gray{background:var(--gray-500);}
.mono{font-family:var(--mono);font-size:13px;color:var(--navy-700);}
.al-stack{display:flex;height:34px;border-radius:8px;overflow:hidden;
  border:1px solid var(--gray-200);margin:6px 0 4px 0;}
.al-stack > div{display:flex;align-items:center;justify-content:center;color:#fff;
  font-size:13px;font-weight:700;min-width:38px;}
.al-barrow{display:flex;align-items:center;gap:10px;margin:4px 0;}
.al-barrow .name{width:180px;font-size:13px;color:var(--navy-700);}
.al-bartrack{flex:1;background:var(--gray-200);border-radius:6px;height:14px;}
.al-barfill{background:var(--teal-500);height:14px;border-radius:6px;}
.al-barrow .num{width:96px;font-size:12px;color:var(--gray-500);text-align:right;
  font-family:var(--mono);}
.al-footer{margin-top:28px;padding-top:12px;border-top:1px solid var(--gray-200);
  color:var(--gray-500);font-size:12px;}
.al-why{background:var(--teal-100);border-left:3px solid var(--teal-500);
  padding:10px 14px;border-radius:8px;color:var(--navy-700);font-size:14px;}
</style>
"""

_PILL_CLASS = {
    "AUTO-APPROVE": "green", "APPROVED": "green",
    "FLAG FOR REVIEW": "amber", "PENDING": "amber",
    "ESCALATE": "red", "REJECTED": "red",
}
_SEV_DOT = {"AUTO-APPROVE": "🟩", "FLAG FOR REVIEW": "🟧", "ESCALATE": "🟥"}


def _pill(label: str) -> str:
    return f'<span class="al-pill {_PILL_CLASS.get(label, "gray")}">{label}</span>'


def _fmt_ms(ms) -> str:
    """Adaptive precision so sub-millisecond compute never reads as a bare '0'."""
    if not ms:
        return "—"
    if ms < 1:
        return f"{ms:.2f} ms"
    if ms < 100:
        return f"{ms:.1f} ms"
    return f"{ms:.0f} ms"


def _kpi_card(value: str, label: str, gold: bool = False) -> str:
    cls = "val gold" if gold else "val"
    return f'<div class="al-card"><div class="{cls}">{value}</div><div class="lab">{label}</div></div>'


def _stacked_bar(breakdown: dict[str, int]) -> str:
    order = ["AUTO-APPROVE", "FLAG FOR REVIEW", "ESCALATE"]
    color = {"AUTO-APPROVE": "var(--green-600)", "FLAG FOR REVIEW": "var(--amber-500)",
             "ESCALATE": "var(--red-600)"}
    total = sum(breakdown.values()) or 1
    segs = ""
    for k in order:
        n = breakdown.get(k, 0)
        if n:
            pct = n / total * 100
            segs += f'<div style="width:{pct:.1f}%;background:{color[k]}" title="{k}: {n}">{n}</div>'
    return f'<div class="al-stack">{segs}</div>'


def _taxonomy_bars(by_type: dict[str, dict]) -> str:
    rows = ""
    for etype, t in sorted(by_type.items()):
        pct = t["catch_rate"] * 100
        rows += (
            f'<div class="al-barrow"><div class="name">{etype}</div>'
            f'<div class="al-bartrack"><div class="al-barfill" style="width:{pct:.0f}%"></div></div>'
            f'<div class="num">{t["caught"]}/{t["total"]} ({pct:.0f}%)</div></div>'
        )
    return rows


def main() -> None:
    import pandas as pd
    import streamlit as st

    from auditledger import analytics, config
    from auditledger.agents.classification import AUTO_APPROVE
    from auditledger.db import audit_log, exception_queue
    from auditledger.db.database import connect
    from auditledger.service import ensure_database, explain_invoice

    st.set_page_config(page_title="AuditLedger", page_icon="🧾", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)

    ensure_database(config.DB_PATH)      # first launch builds everything
    conn = connect(config.DB_PATH)

    roi = analytics.roi_summary(conn)
    proc = analytics.processing_stats(conn)
    catch = analytics.overall_catch_rate(conn)
    intact, broken = audit_log.verify_chain(conn)

    # --- Hero -------------------------------------------------------------
    st.markdown(
        '<div class="al-hero">'
        '<div class="al-wordmark"><span class="a">Audit</span><span class="l">Ledger</span></div>'
        '<div class="al-tagline">The AI invoice agent that shows its work.</div>'
        '<div class="al-problem">Companies spend $12.50–$40 processing each invoice, '
        'and 39% contain errors. AuditLedger recommends — it never pays without '
        'confidence or human sign-off.</div>'
        '<div class="al-trust">Every decision logged · Nothing paid without confidence or human sign-off</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # --- KPI row ----------------------------------------------------------
    proc_display = _fmt_ms(proc["avg_ms_per_invoice"])
    chain_val = "100% ✅" if intact else f"BROKEN @{broken}"
    st.markdown(
        '<div class="al-kpis">'
        + _kpi_card(f"{catch:.0%}", "Error catch rate")
        + _kpi_card(f'${roi["cost_avoided_usd"]:,.0f}', "Cost avoided vs manual", gold=True)
        + _kpi_card(proc_display, "Avg processing time / invoice")
        + _kpi_card(chain_val, "Audit coverage (chain intact)")
        + '</div>',
        unsafe_allow_html=True,
    )

    # --- Sidebar ----------------------------------------------------------
    with st.sidebar:
        st.markdown('<div class="al-wordmark" style="font-size:22px">'
                    '<span class="a">Audit</span><span class="l">Ledger</span></div>',
                    unsafe_allow_html=True)
        st.caption("Auditable AI invoice reconciliation")
        st.divider()
        st.metric("Invoices processed", roi["invoices_processed"])
        st.metric("Automation rate", f"{roi['automation_rate']:.0%}")
        st.write(f"**Confidence threshold:** `{config.CONFIDENCE_THRESHOLD:.2f}`")
        st.write(f"**Model:** `{proc['model_version']}`")
        st.divider()
        st.caption(
            f"Est. hours saved: **{roi['estimated_hours_saved']}** "
            f"({roi['estimated_hours_saved_basis']})."
        )
        st.caption(f"AI cost: {roi['ai_cost_note']}")
        st.caption(f"Manual cycle benchmark: {proc['manual_cycle_days']} days → "
                   f"AuditLedger: {proc_display}/invoice (deterministic compute; "
                   f"excludes human review of exceptions).")

    tab_overview, tab_queue, tab_audit, tab_case = st.tabs(
        ["📊 Overview", "🙋 Exception Queue", "🔍 Audit Log", "🏢 Case Study"]
    )

    # --- Overview ---------------------------------------------------------
    with tab_overview:
        breakdown = analytics.classification_breakdown(conn)
        st.markdown("##### Disposition breakdown")
        st.markdown(_stacked_bar(breakdown), unsafe_allow_html=True)
        legend = "  ".join(
            f'{_pill(k)}&nbsp;{v}' for k, v in (
                ("AUTO-APPROVE", breakdown.get("AUTO-APPROVE", 0)),
                ("FLAG FOR REVIEW", breakdown.get("FLAG FOR REVIEW", 0)),
                ("ESCALATE", breakdown.get("ESCALATE", 0)),
            )
        )
        st.markdown(legend, unsafe_allow_html=True)

        st.markdown("##### Error catch rate by taxonomy")
        st.markdown(_taxonomy_bars(analytics.catch_rate_by_taxonomy(conn)),
                    unsafe_allow_html=True)

        with st.expander("Full ROI detail (every figure measured from the run)"):
            st.json(roi)

    # --- Exception Queue --------------------------------------------------
    with tab_queue:
        pending = exception_queue.list_pending(conn)
        resolved = [r for r in exception_queue.list_all(conn) if r["status"] != "PENDING"]
        st.markdown(f"**{len(pending)} pending** · {len(resolved)} resolved")

        if not pending:
            st.success("No pending exceptions — the queue is clear.")
        for r in pending:
            iid, cls = r["invoice_id"], r["ai_classification"]
            with st.expander(f'{_SEV_DOT.get(cls, "⬜")}  {iid}  ·  {cls}  ·  conf {r["ai_confidence"]:.2f}'):
                st.markdown(f'AI recommendation: {_pill(cls)}', unsafe_allow_html=True)
                st.markdown(f'<div class="al-why"><b>Why:</b> {r["ai_reasoning"]}</div>',
                            unsafe_allow_html=True)
                st.write("")
                reviewer = st.text_input("Reviewer", value="reviewer", key=f"rev_{iid}")
                note = st.text_area("Note (recorded immutably in the audit log)", key=f"note_{iid}")
                c1, c2, _ = st.columns([1, 1, 3])
                if c1.button("✓ Approve", key=f"appr_{iid}"):
                    exception_queue.resolve(conn, invoice_id=iid, reviewer=reviewer or "reviewer",
                                            decision=exception_queue.APPROVED, note=note)
                    st.rerun()
                if c2.button("✗ Reject", key=f"rej_{iid}"):
                    exception_queue.resolve(conn, invoice_id=iid, reviewer=reviewer or "reviewer",
                                            decision=exception_queue.REJECTED, note=note)
                    st.rerun()

        if resolved:
            st.markdown("##### Resolved")
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

    # --- Audit Log --------------------------------------------------------
    with tab_audit:
        st.markdown("##### Explain any invoice from the log alone")
        all_ids = [r["invoice_id"] for r in conn.execute(
            "SELECT DISTINCT invoice_id FROM audit_log ORDER BY invoice_id").fetchall()]
        query = st.text_input("Search invoice ID", placeholder="e.g. INV0042")
        ids = [i for i in all_ids if query.upper() in i] if query else all_ids
        if not ids:
            st.warning("No matching invoice.")
        else:
            selected = st.selectbox("Invoice", ids)
            story = explain_invoice(conn, selected)

            c1, c2, c3 = st.columns(3)
            c1.markdown("AI recommendation<br>" + _pill(story["ai_recommendation"]),
                        unsafe_allow_html=True)
            c2.markdown("Final disposition<br>" + _pill(story["final_disposition"].split(" by ")[0]
                        if story["final_disposition"] else "—"), unsafe_allow_html=True)
            c3.markdown(f'Confidence<br><span class="mono">'
                        f'{story["ai_confidence"]:.2f}</span>' if story["ai_confidence"]
                        else "Confidence<br>—", unsafe_allow_html=True)
            st.markdown(
                f'<div style="margin-top:10px" class="mono">input hash: {story["input_hash"]}<br>'
                f'model: {story["model_version"]}</div>', unsafe_allow_html=True)

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

    # --- Case Study (retail-scale modeling) -------------------------------
    with tab_case:
        from auditledger import case_study

        s = case_study.model_scenario(
            measured_automation_rate=roi["automation_rate"],
            measured_catch_rate=catch,
        )
        st.markdown(
            '<div style="background:#FFF7E0;border-left:3px solid var(--amber-500);'
            'padding:10px 14px;border-radius:8px;color:var(--navy-700);font-size:13px">'
            '<b>Illustrative modeling on public data.</b> Not affiliated with, endorsed '
            'by, or commissioned by the named company. No dollar figure was identified in '
            'its actual books — projections apply published benchmarks to stated '
            'assumptions.</div>', unsafe_allow_html=True)

        st.markdown(f"##### {s['retailer']} — modeled AP-risk scenario")
        st.markdown(f'<div class="al-why">{case_study.headline(s)}</div>',
                    unsafe_allow_html=True)

        st.markdown(
            '<div class="al-kpis">'
            + _kpi_card(f'{s["modeled_invoice_volume"]/1e6:.1f}M/yr', "Modeled invoice volume")
            + _kpi_card(f'${s["dup_leakage_low_usd"]/1e9:.1f}B–${s["dup_leakage_high_usd"]/1e9:.1f}B',
                        "Duplicate-payment leakage addressable*", gold=True)
            + _kpi_card(f'${s["processing_cost_addressable_usd"]/1e6:.0f}M',
                        "Processing cost addressable", gold=True)
            + _kpi_card(f'{s["measured_catch_rate"]:.0%}', "Measured catch rate (real run)")
            + '</div>', unsafe_allow_html=True)
        st.caption("*Published 0.8–2% duplicate-payment benchmark applied to modeled AP "
                   "spend — an addressable range, not a figure found in any company's books.")

        c_assume, c_result = st.columns(2)
        with c_assume:
            st.markdown("**Assumptions** — edit in `src/auditledger/case_study.py`")
            st.dataframe(pd.DataFrame([
                ("Company (public)", s["retailer"]),
                ("Annual revenue (public)", f'${s["annual_revenue_usd"]/1e9:.1f}B'),
                ("Cost-of-sales ratio", f'{s["cogs_ratio"]:.0%}'),
                ("Modeled AP spend", f'${s["modeled_ap_spend_usd"]/1e9:.1f}B'),
                ("Suppliers (public)", f'{s["supplier_count"]:,}+'),
                ("Invoices/supplier/yr (assumed)", str(s["invoices_per_supplier_per_year"])),
                ("Modeled invoice volume", f'{s["modeled_invoice_volume"]:,}/yr'),
            ], columns=["assumption", "value"]), hide_index=True)
        with c_result:
            st.markdown("**Modeled results**")
            st.dataframe(pd.DataFrame([
                ("Measured catch rate (real run)", f'{s["measured_catch_rate"]:.0%}'),
                ("Measured automation rate (real run)", f'{s["measured_automation_rate"]:.0%}'),
                ("Processing cost addressable", f'${s["processing_cost_addressable_usd"]/1e6:.1f}M'),
                ("Duplicate leakage addressable", f'${s["dup_leakage_low_usd"]/1e9:.1f}B–${s["dup_leakage_high_usd"]/1e9:.1f}B'),
                ("Estimated hours saved", f'{s["estimated_hours_saved"]:,.0f}'),
                ("Audit coverage", f'{s["audit_coverage"]:.0%}'),
            ], columns=["metric", "value"]), hide_index=True)

        st.caption(f"Source: {s['source_note']}")
        st.caption(f"⚖️ {s['disclaimer']}")

    st.markdown(
        f'<div class="al-footer">Illustrative demo · synthetic data · {GITHUB_URL}</div>',
        unsafe_allow_html=True,
    )
    conn.close()


if __name__ == "__main__":
    main()
