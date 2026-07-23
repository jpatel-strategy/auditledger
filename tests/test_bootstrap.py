"""MILESTONE 4 VERIFICATION GATE — the single-launch bootstrap.

Simulates a fresh clone: from no database at all, one call must build the data,
run the agent loop, and populate the immutable audit log — exactly what the
dashboard's launch does before rendering. (The Streamlit UI itself is exercised
by a live headless smoke run, documented in the README; here we prove the data
path the UI depends on.)
"""

from __future__ import annotations

from auditledger import analytics
from auditledger.db import audit_log
from auditledger.db.database import connect
from auditledger.service import ensure_database, is_populated


def test_bootstrap_from_scratch(tmp_path):
    db_path = str(tmp_path / "fresh.db")

    assert is_populated(db_path) is False           # nothing exists yet
    ensure_database(db_path, client=None)           # the single launch step
    assert is_populated(db_path) is True

    conn = connect(db_path)
    try:
        # Database built...
        assert conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 100
        # ...agent loop executed and logged (2 entries per invoice)...
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type='AGENT_DECISION'"
        ).fetchone()[0] == 100
        # ...and the dashboard's headline numbers are all queryable.
        assert analytics.overall_catch_rate(conn) == 1.0
        assert analytics.roi_summary(conn)["invoices_processed"] == 100
        intact, _ = audit_log.verify_chain(conn)
        assert intact is True
    finally:
        conn.close()


def test_ensure_database_is_idempotent(tmp_path):
    """A second launch must not rebuild/wipe an already-populated database."""
    db_path = str(tmp_path / "fresh.db")
    ensure_database(db_path, client=None)

    conn = connect(db_path)
    first_count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    conn.close()

    ensure_database(db_path, client=None)  # should be a no-op
    conn = connect(db_path)
    second_count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    conn.close()

    assert first_count == second_count
