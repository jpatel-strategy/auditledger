"""Central configuration for AuditLedger.

Every business control that a reviewer might want to challenge lives here in one
visible place — nothing material is hidden inside the code. This mirrors how an
auditor expects materiality thresholds and policy settings to be documented,
not buried in procedures.
"""

from __future__ import annotations

import os

# --- Reproducibility -------------------------------------------------------
# A single fixed seed drives the entire synthetic dataset so every run — yours,
# mine, or a CI job — produces byte-identical data. An audit artifact must be
# reproducible on demand.
SEED: int = 42

# --- Dataset shape ---------------------------------------------------------
N_INVOICES: int = 100            # total synthetic invoices to generate
N_VENDORS: int = 15              # realistic B2B vendors
ERROR_RATE: float = 0.30         # 30% of invoices carry a deliberate, tagged defect
N_SEEDED_ERRORS: int = int(round(N_INVOICES * ERROR_RATE))  # == 30

# --- Financial controls (auditor-set materiality thresholds) ---------------
DEFAULT_TAX_RATE: float = 0.08   # single-jurisdiction sales tax for v1 scope
PRICE_TOLERANCE_PCT: float = 0.02  # invoices priced >2% above PO are flagged
MONEY_EPSILON: float = 0.01      # amounts within one cent are treated as equal
CURRENCY: str = "USD"            # single currency in v1 (see README Limitations)

# --- Storage ---------------------------------------------------------------
# The database is a single local file precisely so a reviewer can open it in any
# SQLite browser and inspect every decision themselves.
DB_PATH: str = os.getenv("AUDITLEDGER_DB_PATH", "auditledger.db")

# --- AI layer (used from Milestone 2 onward) -------------------------------
# Latest Haiku-class model keeps per-invoice economics low. The key is read from
# a git-ignored .env file — never committed.
MODEL: str = os.getenv("AUDITLEDGER_MODEL", "claude-haiku-4-5-20251001")

# The manual-processing benchmark we measure savings against. Deliberately the
# conservative LOW end of the published $12.50–$40 range so ROI is never inflated.
MANUAL_COST_PER_INVOICE_USD: float = 12.50
