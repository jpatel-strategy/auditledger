"""The ROI & analytics engine.

Every number here is derived from what was actually persisted (the audit log,
ground truth, and exception queue) — never hard-coded or guessed. Where a figure
rests on an assumption (manual touch time) or cannot be measured offline (live
API cost), the output says so explicitly. This honesty is the point: an auditor
should be able to trace each metric back to a query.
"""

from __future__ import annotations

import sqlite3

from . import config
from .agents.classification import AUTO_APPROVE


def catch_rate_by_taxonomy(conn: sqlite3.Connection) -> dict[str, dict]:
    """For each seeded error type: how many were caught (i.e. NOT auto-approved),
    measured from the agent decisions in the audit log."""
    rows = conn.execute(
        """SELECT gt.error_type AS error_type, al.classification AS classification
           FROM ground_truth gt
           JOIN audit_log al
             ON al.invoice_id = gt.invoice_id AND al.event_type = 'AGENT_DECISION'
           WHERE gt.is_seeded_error = 1"""
    ).fetchall()

    tally: dict[str, dict] = {}
    for row in rows:
        t = tally.setdefault(row["error_type"], {"total": 0, "caught": 0})
        t["total"] += 1
        if row["classification"] != AUTO_APPROVE:
            t["caught"] += 1
    for t in tally.values():
        t["catch_rate"] = round(t["caught"] / t["total"], 4) if t["total"] else 0.0
    return tally


def overall_catch_rate(conn: sqlite3.Connection) -> float:
    by_type = catch_rate_by_taxonomy(conn)
    total = sum(t["total"] for t in by_type.values())
    caught = sum(t["caught"] for t in by_type.values())
    return round(caught / total, 4) if total else 0.0


def classification_breakdown(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """SELECT classification, COUNT(*) AS n
           FROM audit_log WHERE event_type = 'AGENT_DECISION'
           GROUP BY classification"""
    ).fetchall()
    return {row["classification"]: row["n"] for row in rows}


def roi_summary(conn: sqlite3.Connection, cfg=config) -> dict:
    """Cost avoided, estimated hours saved, and honest AI-cost accounting."""
    breakdown = classification_breakdown(conn)
    total = sum(breakdown.values())
    auto_approved = breakdown.get(AUTO_APPROVE, 0)
    exceptions = total - auto_approved

    manual_baseline = round(total * cfg.MANUAL_COST_PER_INVOICE_USD, 2)
    # Conservative: only fully-automated invoices count as cost avoided;
    # exceptions still require manual handling.
    cost_avoided = round(auto_approved * cfg.MANUAL_COST_PER_INVOICE_USD, 2)
    est_hours_saved = round(auto_approved * cfg.MANUAL_MINUTES_PER_INVOICE / 60.0, 2)

    # AI processing cost: measured only when a live model ran. Offline (the
    # default / CI), no API cost is incurred and per-invoice LLM cost is not
    # measured — we report that plainly rather than inventing a figure.
    model_versions = {
        row["model_version"]
        for row in conn.execute(
            "SELECT DISTINCT model_version FROM audit_log WHERE event_type='AGENT_DECISION'"
        ).fetchall()
    }
    offline = model_versions == {"deterministic-fallback-v1"} or not model_versions

    return {
        "invoices_processed": total,
        "auto_approved": auto_approved,
        "exceptions": exceptions,
        "automation_rate": round(auto_approved / total, 4) if total else 0.0,
        "manual_baseline_cost_usd": manual_baseline,
        "cost_avoided_usd": cost_avoided,
        "estimated_hours_saved": est_hours_saved,
        "estimated_hours_saved_basis": (
            f"assumes {cfg.MANUAL_MINUTES_PER_INVOICE:.0f} min manual touch time "
            f"per automated invoice (configurable)"
        ),
        "ai_processing_cost_usd": 0.0 if offline else None,
        "ai_cost_note": (
            "offline mode: no API cost incurred; per-invoice LLM cost not measured"
            if offline else "live model used; token cost measurement not yet wired"
        ),
        "manual_benchmark_per_invoice_usd": cfg.MANUAL_COST_PER_INVOICE_USD,
    }


def queue_stats(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM exception_queue GROUP BY status"
    ).fetchall()
    return {row["status"]: row["n"] for row in rows}
