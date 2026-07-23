"""MILESTONE 3 VERIFICATION GATE — the immutable auditor layer.

Proves: the log is append-only and tamper-evident; every decision is recorded;
exceptions route to a human queue that logs human sign-off alongside the AI
recommendation; analytics are measured from the log; and — the headline gate —
the audit log ALONE fully explains any invoice's disposition with no pipeline
re-run.
"""

from __future__ import annotations

import sqlite3

import pytest

from auditledger import analytics
from auditledger.agents.classification import AUTO_APPROVE
from auditledger.db import audit_log, exception_queue


def test_every_invoice_has_agent_and_critic_entries(audit_db, dataset):
    for inv in dataset.invoices:
        rows = audit_log.entries_for_invoice(audit_db, inv.invoice_id)
        event_types = {r["event_type"] for r in rows}
        assert "AGENT_DECISION" in event_types
        assert "CRITIC_REVIEW" in event_types


def test_audit_log_rejects_updates(audit_db):
    with pytest.raises(sqlite3.Error) as exc:
        audit_db.execute("UPDATE audit_log SET reasoning = 'x' WHERE entry_id = 1")
    assert "append-only" in str(exc.value)


def test_audit_log_rejects_deletes(audit_db):
    with pytest.raises(sqlite3.Error) as exc:
        audit_db.execute("DELETE FROM audit_log WHERE entry_id = 1")
    assert "append-only" in str(exc.value)


def test_hash_chain_is_intact(audit_db):
    intact, broken = audit_log.verify_chain(audit_db)
    assert intact is True and broken is None


def test_tampering_is_detected_by_the_hash_chain(fresh_db):
    """Simulate an attacker who bypasses the triggers at the file level: the
    hash chain must still expose the edit."""
    fresh_db.executescript(
        "DROP TRIGGER trg_audit_log_no_update; DROP TRIGGER trg_audit_log_no_delete;"
    )
    fresh_db.execute("UPDATE audit_log SET reasoning = 'tampered' WHERE entry_id = 1")
    fresh_db.commit()

    intact, broken = audit_log.verify_chain(fresh_db)
    assert intact is False
    assert broken == 1


def test_all_non_auto_approved_invoices_are_queued(audit_db):
    decisions = audit_db.execute(
        "SELECT invoice_id, classification FROM audit_log WHERE event_type='AGENT_DECISION'"
    ).fetchall()
    expected_exceptions = {d["invoice_id"] for d in decisions if d["classification"] != AUTO_APPROVE}
    queued = {r["invoice_id"] for r in exception_queue.list_all(audit_db)}
    assert queued == expected_exceptions
    # Auto-approved invoices must NOT be in the human queue.
    auto = {d["invoice_id"] for d in decisions if d["classification"] == AUTO_APPROVE}
    assert auto.isdisjoint(queued)


def test_explain_invoice_from_log_alone_auto_approved(audit_db):
    """The Milestone 3 gate for an automated invoice."""
    row = audit_db.execute(
        "SELECT invoice_id FROM audit_log "
        "WHERE event_type='AGENT_DECISION' AND classification=? LIMIT 1",
        (AUTO_APPROVE,),
    ).fetchone()
    story = analytics_explain(audit_db, row["invoice_id"])
    assert story["ai_recommendation"] == AUTO_APPROVE
    assert story["human_decision"] is None
    assert story["final_disposition"] == AUTO_APPROVE
    assert story["input_hash"] and story["model_version"]


def test_human_resolution_is_recorded_alongside_ai(fresh_db):
    """A reviewer approves a queued exception; the human decision and the AI
    recommendation must both live in the immutable log, and the chain stays
    intact."""
    pending = exception_queue.list_pending(fresh_db)
    assert pending, "expected some exceptions to review"
    target = pending[0]["invoice_id"]
    ai_reco = pending[0]["ai_classification"]

    exception_queue.resolve(
        fresh_db, invoice_id=target, reviewer="j.patel",
        decision=exception_queue.APPROVED, note="Verified against contract pricing.",
    )

    story = analytics_explain(fresh_db, target)
    assert story["ai_recommendation"] == ai_reco          # AI reco preserved
    assert story["human_decision"] == exception_queue.APPROVED
    assert story["human_reviewer"] == "human:j.patel"
    assert "APPROVED" in story["final_disposition"]

    intact, _ = audit_log.verify_chain(fresh_db)
    assert intact is True


def test_catch_rate_is_100_percent_by_taxonomy(audit_db):
    by_type = analytics.catch_rate_by_taxonomy(audit_db)
    assert len(by_type) == 5
    for etype, t in by_type.items():
        assert t["catch_rate"] == 1.0, f"{etype} catch rate {t['catch_rate']}"
    assert analytics.overall_catch_rate(audit_db) == 1.0


def test_roi_summary_is_internally_consistent(audit_db):
    roi = analytics.roi_summary(audit_db)
    assert roi["invoices_processed"] == 100
    assert roi["auto_approved"] + roi["exceptions"] == roi["invoices_processed"]
    assert roi["cost_avoided_usd"] == round(roi["auto_approved"] * 12.50, 2)
    assert roi["manual_baseline_cost_usd"] == round(100 * 12.50, 2)
    # Offline run: AI cost is reported as $0 with an honest note, never invented.
    assert roi["ai_processing_cost_usd"] == 0.0
    assert "not measured" in roi["ai_cost_note"]


# --- helper ---------------------------------------------------------------
def analytics_explain(conn, invoice_id):
    from auditledger.service import explain_invoice
    return explain_invoice(conn, invoice_id)
