"""SQLite persistence for AuditLedger.

SQLite was chosen deliberately: the entire ledger is a single file a reviewer can
open in any SQLite browser and inspect for themselves — no server, no hidden
state. This module owns the schema (DDL) and the load helpers that write a
generated dataset to disk.

The immutable audit-log and exception-queue tables are added in Milestone 3;
this module currently persists the source documents, the hidden ground truth,
and the vendor risk profiles.
"""

from __future__ import annotations

import json
import os
import sqlite3

from .. import config
from ..data.schema import Dataset

# --- Data Definition Language ---------------------------------------------
SCHEMA_DDL = """
CREATE TABLE vendors (
    vendor_id            TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    category             TEXT NOT NULL,
    payment_terms        TEXT NOT NULL,
    tax_id               TEXT NOT NULL,
    baseline_reliability REAL NOT NULL
);

CREATE TABLE purchase_orders (
    po_id      TEXT PRIMARY KEY,
    vendor_id  TEXT NOT NULL REFERENCES vendors(vendor_id),
    po_date    TEXT NOT NULL,
    currency   TEXT NOT NULL,
    tax_rate   REAL NOT NULL,
    subtotal   REAL NOT NULL,
    tax_amount REAL NOT NULL,
    total      REAL NOT NULL
);

CREATE TABLE po_line_items (
    po_line_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id       TEXT NOT NULL REFERENCES purchase_orders(po_id),
    sku         TEXT NOT NULL,
    description TEXT NOT NULL,
    quantity    INTEGER NOT NULL,
    unit_price  REAL NOT NULL,
    line_total  REAL NOT NULL
);

CREATE TABLE goods_receipts (
    receipt_id   TEXT PRIMARY KEY,
    po_id        TEXT NOT NULL REFERENCES purchase_orders(po_id),
    receipt_date TEXT NOT NULL,
    received_by  TEXT NOT NULL
);

CREATE TABLE receipt_line_items (
    receipt_line_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id        TEXT NOT NULL REFERENCES goods_receipts(receipt_id),
    sku               TEXT NOT NULL,
    quantity_received INTEGER NOT NULL
);

CREATE TABLE invoices (
    invoice_id     TEXT PRIMARY KEY,
    vendor_id      TEXT NOT NULL REFERENCES vendors(vendor_id),
    invoice_number TEXT NOT NULL,
    invoice_date   TEXT NOT NULL,
    currency       TEXT NOT NULL,
    po_reference   TEXT,
    subtotal       REAL NOT NULL,
    tax_amount     REAL NOT NULL,
    total          REAL NOT NULL
);

CREATE TABLE invoice_line_items (
    invoice_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id      TEXT NOT NULL REFERENCES invoices(invoice_id),
    sku             TEXT NOT NULL,
    description     TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    unit_price      REAL NOT NULL,
    line_total      REAL NOT NULL
);

-- Hidden answer key: kept in its own table and never read by the matcher.
CREATE TABLE ground_truth (
    gt_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id      TEXT NOT NULL REFERENCES invoices(invoice_id),
    is_seeded_error INTEGER NOT NULL,
    error_type      TEXT,
    error_detail    TEXT,
    severity        TEXT
);

CREATE TABLE vendor_risk_profiles (
    vendor_id             TEXT PRIMARY KEY REFERENCES vendors(vendor_id),
    total_invoices        INTEGER NOT NULL,
    seeded_error_count    INTEGER NOT NULL,
    historical_error_rate REAL NOT NULL,
    risk_tier             TEXT NOT NULL
);
"""


def connect(db_path: str = config.DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_DDL)


def load_dataset(conn: sqlite3.Connection, dataset: Dataset) -> None:
    """Persist a generated + seeded dataset into an empty schema."""
    cur = conn.cursor()

    cur.executemany(
        "INSERT INTO vendors VALUES (?,?,?,?,?,?)",
        [(v.vendor_id, v.name, v.category, v.payment_terms, v.tax_id, v.baseline_reliability)
         for v in dataset.vendors],
    )

    for po in dataset.purchase_orders:
        cur.execute(
            "INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?,?)",
            (po.po_id, po.vendor_id, po.po_date, po.currency, po.tax_rate,
             po.subtotal, po.tax_amount, po.total),
        )
        cur.executemany(
            "INSERT INTO po_line_items (po_id, sku, description, quantity, unit_price, line_total) "
            "VALUES (?,?,?,?,?,?)",
            [(po.po_id, li.sku, li.description, li.quantity, li.unit_price, li.line_total)
             for li in po.lines],
        )

    for r in dataset.goods_receipts:
        cur.execute(
            "INSERT INTO goods_receipts VALUES (?,?,?,?)",
            (r.receipt_id, r.po_id, r.receipt_date, r.received_by),
        )
        cur.executemany(
            "INSERT INTO receipt_line_items (receipt_id, sku, quantity_received) VALUES (?,?,?)",
            [(r.receipt_id, rl.sku, rl.quantity_received) for rl in r.lines],
        )

    for inv in dataset.invoices:
        cur.execute(
            "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?)",
            (inv.invoice_id, inv.vendor_id, inv.invoice_number, inv.invoice_date,
             inv.currency, inv.po_reference, inv.subtotal, inv.tax_amount, inv.total),
        )
        cur.executemany(
            "INSERT INTO invoice_line_items (invoice_id, sku, description, quantity, unit_price, line_total) "
            "VALUES (?,?,?,?,?,?)",
            [(inv.invoice_id, li.sku, li.description, li.quantity, li.unit_price, li.line_total)
             for li in inv.lines],
        )

    cur.executemany(
        "INSERT INTO ground_truth (invoice_id, is_seeded_error, error_type, error_detail, severity) "
        "VALUES (?,?,?,?,?)",
        [(gt.invoice_id, int(gt.is_seeded_error), gt.error_type,
          json.dumps(gt.error_detail), gt.severity) for gt in dataset.ground_truth],
    )

    cur.executemany(
        "INSERT INTO vendor_risk_profiles VALUES (?,?,?,?,?)",
        [(p.vendor_id, p.total_invoices, p.seeded_error_count,
          p.historical_error_rate, p.risk_tier) for p in dataset.vendor_risk_profiles],
    )

    conn.commit()


def build_database(db_path: str = config.DB_PATH, cfg=config) -> Dataset:
    """Generate a fresh dataset and write it to ``db_path`` (overwriting any
    existing file, since the data is fully reproducible from the seed)."""
    from ..data.seeding import build_full_dataset

    if os.path.exists(db_path):
        os.remove(db_path)

    dataset = build_full_dataset(cfg)
    conn = connect(db_path)
    try:
        create_schema(conn)
        load_dataset(conn, dataset)
    finally:
        conn.close()
    return dataset
