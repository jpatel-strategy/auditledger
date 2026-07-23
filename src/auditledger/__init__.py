"""AuditLedger — an auditable AI invoice reconciliation agent.

The package is deliberately layered so each concern can be inspected on its own,
the way an auditor separates source records, controls, and evidence:

- ``data``     : synthetic source documents (vendors, POs, receipts, invoices)
- ``matching`` : the deterministic 3-way match control (pure Python, no LLM)
- ``db``       : the single-file SQLite store reviewers can open and inspect
"""

__version__ = "0.1.0"
