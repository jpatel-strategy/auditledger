"""CLI: build the AuditLedger SQLite database from the deterministic seed.

Usage:
    python scripts/build_db.py [db_path]

Prints a short, honest summary of what was written so a reviewer can sanity-check
the counts before opening the file.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``src`` importable when run directly from a fresh clone.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditledger import config  # noqa: E402
from auditledger.db.database import build_database  # noqa: E402


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else config.DB_PATH
    dataset = build_database(db_path)

    seeded = sum(1 for gt in dataset.ground_truth if gt.is_seeded_error)
    print(f"Built {db_path}")
    print(f"  vendors           : {len(dataset.vendors)}")
    print(f"  purchase_orders   : {len(dataset.purchase_orders)}")
    print(f"  goods_receipts    : {len(dataset.goods_receipts)}")
    print(f"  invoices          : {len(dataset.invoices)}")
    print(f"  seeded errors     : {seeded} ({seeded / len(dataset.invoices):.0%})")
    print(f"  vendor risk rows  : {len(dataset.vendor_risk_profiles)}")


if __name__ == "__main__":
    main()
