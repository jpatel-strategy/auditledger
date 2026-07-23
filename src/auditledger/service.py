"""Glue between the agent loop and the immutable auditor layer.

Runs the pipeline, writes every agent action to the append-only audit log, and
routes anything not cleanly auto-approved into the human exception queue. Also
provides ``explain_invoice`` — the Milestone 3 gate — which reconstructs an
invoice's entire disposition from the log alone, no pipeline re-run required.
"""

from __future__ import annotations

import sqlite3

from . import config
from .agents.classification import AUTO_APPROVE
from .agents.models import AgentReport
from .agents.pipeline import run_pipeline
from .data.schema import Dataset
from .db import audit_log, exception_queue


def persist_reports(conn: sqlite3.Connection, reports: list[AgentReport]) -> None:
    """Append two immutable entries per invoice (Primary + Critic) and enqueue
    exceptions for the human queue."""
    for r in reports:
        audit_log.append_entry(
            conn,
            invoice_id=r.invoice_id,
            event_type="AGENT_DECISION",
            actor="primary_agent",
            input_hash=r.input_hash,
            model_version=r.model_version,
            classification=r.classification,
            confidence=r.confidence,
            reasoning=r.reasoning,
            details={"discrepancy_types": r.discrepancy_types,
                     "extraction_ok": r.extraction_ok},
        )
        audit_log.append_entry(
            conn,
            invoice_id=r.invoice_id,
            event_type="CRITIC_REVIEW",
            actor="critic_agent",
            input_hash=r.input_hash,
            model_version=r.model_version,
            reasoning=("consistent with match results and vendor risk"
                       if r.critic_consistent else "; ".join(r.critic_issues)),
            details={"critic_consistent": r.critic_consistent,
                     "critic_issues": r.critic_issues},
        )
        if r.classification != AUTO_APPROVE:
            exception_queue.enqueue(
                conn,
                invoice_id=r.invoice_id,
                classification=r.classification,
                confidence=r.confidence,
                reasoning=r.reasoning,
            )


def process_dataset(conn: sqlite3.Connection, dataset: Dataset, cfg=config,
                    client="auto") -> list[AgentReport]:
    """Run the full agent loop over a dataset and persist everything."""
    reports = run_pipeline(dataset, cfg, client=client)
    persist_reports(conn, reports)
    return reports


def build_and_process(db_path: str = config.DB_PATH, cfg=config, client="auto") -> Dataset:
    """One call that builds the database from the seed, runs the agent loop, and
    persists the audit log + exception queue. Leaves a fully-populated DB file on
    disk (callers reopen it to query). Used by the CLI and the dashboard so a
    fresh clone reaches a working state in a single step."""
    from .db.database import build_database, connect

    dataset = build_database(db_path, cfg)
    conn = connect(db_path)
    try:
        process_dataset(conn, dataset, cfg, client=client)
    finally:
        conn.close()
    return dataset


def explain_invoice(conn: sqlite3.Connection, invoice_id: str) -> dict:
    """Reconstruct an invoice's complete disposition history from the audit log
    (and current queue state) WITHOUT re-running the pipeline.

    This is the Milestone 3 verification gate: the log alone must fully explain
    what happened to any invoice.
    """
    rows = audit_log.entries_for_invoice(conn, invoice_id)
    if not rows:
        raise KeyError(f"no audit history for invoice {invoice_id}")

    timeline = [
        {
            "event_time": row["event_time"],
            "event_type": row["event_type"],
            "actor": row["actor"],
            "classification": row["classification"],
            "confidence": row["confidence"],
            "reasoning": row["reasoning"],
            "details": row["details"],
            "entry_hash": row["entry_hash"],
        }
        for row in rows
    ]

    agent_entry = next((r for r in rows if r["event_type"] == "AGENT_DECISION"), None)
    human_entry = next((r for r in rows if r["event_type"] == "HUMAN_DECISION"), None)
    queue_row = conn.execute(
        "SELECT * FROM exception_queue WHERE invoice_id = ?", (invoice_id,)
    ).fetchone()

    return {
        "invoice_id": invoice_id,
        "ai_recommendation": agent_entry["classification"] if agent_entry else None,
        "ai_confidence": agent_entry["confidence"] if agent_entry else None,
        "model_version": agent_entry["model_version"] if agent_entry else None,
        "input_hash": agent_entry["input_hash"] if agent_entry else None,
        "queue_status": queue_row["status"] if queue_row else "AUTO-APPROVED (no queue)",
        "human_decision": human_entry["classification"] if human_entry else None,
        "human_reviewer": human_entry["actor"] if human_entry else None,
        "final_disposition": _final_disposition(agent_entry, human_entry, queue_row),
        "timeline": timeline,
    }


def _final_disposition(agent_entry, human_entry, queue_row) -> str:
    if human_entry is not None:
        return f"{human_entry['classification']} by {human_entry['actor']}"
    if queue_row is not None:
        return f"{queue_row['status']} (awaiting human)" if queue_row["status"] == "PENDING" \
            else queue_row["status"]
    return agent_entry["classification"] if agent_entry else "UNKNOWN"
