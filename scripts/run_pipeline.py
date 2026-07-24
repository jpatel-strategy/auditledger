"""CLI: build the database, run the full agent loop, and print the audit summary.

Usage:
    python scripts/run_pipeline.py [db_path]

This is the end-to-end entry point: source data -> agent loop -> immutable audit
log -> ROI metrics, all measured from the run (never fabricated).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditledger import analytics, config  # noqa: E402
from auditledger.db.audit_log import verify_chain  # noqa: E402
from auditledger.db.database import connect  # noqa: E402
from auditledger.service import build_and_process, explain_invoice  # noqa: E402


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else config.DB_PATH
    dataset = build_and_process(db_path)

    conn = connect(db_path)
    try:
        print(f"Processed {len(dataset.invoices)} invoices -> {db_path}\n")

        print("Disposition breakdown:")
        print(f"  {analytics.classification_breakdown(conn)}\n")

        print(f"Overall error catch rate: {analytics.overall_catch_rate(conn):.1%}")
        print("Catch rate by taxonomy:")
        for etype, t in sorted(analytics.catch_rate_by_taxonomy(conn).items()):
            print(f"  {etype:22} {t['caught']}/{t['total']}  ({t['catch_rate']:.0%})")
        print()

        print("ROI summary:")
        print(json.dumps(analytics.roi_summary(conn), indent=2))
        print()

        intact, broken = verify_chain(conn)
        print(f"Audit chain integrity: {'INTACT' if intact else f'BROKEN at {broken}'}")

        # Prove the log alone explains any invoice, no pipeline re-run needed.
        sample = dataset.invoices[0].invoice_id
        print(f"\nExplain {sample} from the audit log alone:")
        print(json.dumps(
            {k: v for k, v in explain_invoice(conn, sample).items() if k != "timeline"},
            indent=2,
        ))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
