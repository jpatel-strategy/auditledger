"""Immutable, tamper-evident audit log operations.

Every entry is hash-chained to the one before it (like a miniature blockchain):
``entry_hash = sha256(prev_hash + canonical_content)``. Change any historical
field and every subsequent hash stops matching, so silent edits are detectable —
and DB triggers forbid UPDATE/DELETE outright. This is the moat: a permanent,
verifiable record of exactly what the agent decided and why.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

GENESIS_HASH = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_content(entry: dict) -> str:
    """Deterministic serialization of the fields the hash protects."""
    protected = {
        k: entry.get(k)
        for k in (
            "event_time", "invoice_id", "event_type", "actor", "input_hash",
            "model_version", "classification", "confidence", "reasoning", "details",
        )
    }
    return json.dumps(protected, sort_keys=True, default=str)


def compute_entry_hash(prev_hash: str, entry: dict) -> str:
    return hashlib.sha256(f"{prev_hash}|{_canonical_content(entry)}".encode()).hexdigest()


def _last_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT entry_hash FROM audit_log ORDER BY entry_id DESC LIMIT 1"
    ).fetchone()
    return row["entry_hash"] if row else GENESIS_HASH


def append_entry(
    conn: sqlite3.Connection,
    *,
    invoice_id: str,
    event_type: str,
    actor: str,
    input_hash: str | None = None,
    model_version: str | None = None,
    classification: str | None = None,
    confidence: float | None = None,
    reasoning: str | None = None,
    details: dict | None = None,
) -> str:
    """Append one immutable entry and return its hash. Never updates anything."""
    entry = {
        "event_time": _now(),
        "invoice_id": invoice_id,
        "event_type": event_type,
        "actor": actor,
        "input_hash": input_hash,
        "model_version": model_version,
        "classification": classification,
        "confidence": confidence,
        "reasoning": reasoning,
        "details": json.dumps(details or {}, sort_keys=True),
    }
    prev_hash = _last_hash(conn)
    entry_hash = compute_entry_hash(prev_hash, entry)
    conn.execute(
        """INSERT INTO audit_log
           (event_time, invoice_id, event_type, actor, input_hash, model_version,
            classification, confidence, reasoning, details, prev_hash, entry_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            entry["event_time"], invoice_id, event_type, actor, input_hash,
            model_version, classification, confidence, reasoning, entry["details"],
            prev_hash, entry_hash,
        ),
    )
    conn.commit()
    return entry_hash


def entries_for_invoice(conn: sqlite3.Connection, invoice_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM audit_log WHERE invoice_id = ? ORDER BY entry_id", (invoice_id,)
    ).fetchall()


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, int | None]:
    """Recompute the whole chain; return (is_intact, first_broken_entry_id)."""
    prev_hash = GENESIS_HASH
    rows = conn.execute("SELECT * FROM audit_log ORDER BY entry_id").fetchall()
    for row in rows:
        entry = {
            "event_time": row["event_time"],
            "invoice_id": row["invoice_id"],
            "event_type": row["event_type"],
            "actor": row["actor"],
            "input_hash": row["input_hash"],
            "model_version": row["model_version"],
            "classification": row["classification"],
            "confidence": row["confidence"],
            "reasoning": row["reasoning"],
            "details": row["details"],
        }
        expected = compute_entry_hash(prev_hash, entry)
        if row["prev_hash"] != prev_hash or row["entry_hash"] != expected:
            return False, row["entry_id"]
        prev_hash = row["entry_hash"]
    return True, None
