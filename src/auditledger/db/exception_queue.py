"""The human-in-the-loop exception queue.

Anything the agent does not cleanly AUTO-APPROVE lands here for a person to
approve or reject. The queue row is mutable current-state, but every human
resolution is also written immutably to the audit log — so the AI recommendation
and the human's override live side by side, permanently, exactly as an auditor
would want.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import audit_log

PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue(conn: sqlite3.Connection, *, invoice_id: str, classification: str,
            confidence: float, reasoning: str) -> None:
    """Add an invoice needing human sign-off. Idempotent per invoice."""
    conn.execute(
        """INSERT OR IGNORE INTO exception_queue
           (invoice_id, ai_classification, ai_confidence, ai_reasoning, status, created_at)
           VALUES (?,?,?,?,?,?)""",
        (invoice_id, classification, confidence, reasoning, PENDING, _now()),
    )
    conn.commit()


def list_pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM exception_queue WHERE status = ? ORDER BY queue_id", (PENDING,)
    ).fetchall()


def list_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM exception_queue ORDER BY queue_id").fetchall()


def resolve(conn: sqlite3.Connection, *, invoice_id: str, reviewer: str,
            decision: str, note: str = "") -> None:
    """Record a human's approve/reject. Updates the queue AND appends an
    immutable HUMAN_DECISION entry to the audit log."""
    if decision not in (APPROVED, REJECTED):
        raise ValueError(f"decision must be {APPROVED} or {REJECTED}, got {decision!r}")

    row = conn.execute(
        "SELECT * FROM exception_queue WHERE invoice_id = ?", (invoice_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"no queued exception for invoice {invoice_id}")

    conn.execute(
        """UPDATE exception_queue
           SET status = ?, reviewer = ?, human_note = ?, resolved_at = ?
           WHERE invoice_id = ?""",
        (decision, reviewer, note, _now(), invoice_id),
    )
    conn.commit()

    audit_log.append_entry(
        conn,
        invoice_id=invoice_id,
        event_type="HUMAN_DECISION",
        actor=f"human:{reviewer}",
        classification=decision,
        reasoning=note,
        details={
            "overrode_ai_recommendation": row["ai_classification"],
            "ai_confidence": row["ai_confidence"],
        },
    )
