"""Verify the synthetic-data engine: counts, referential integrity, determinism."""

from __future__ import annotations

from auditledger import config
from auditledger.data.generator import generate_clean_dataset
from auditledger.data.seeding import build_full_dataset


def test_counts_match_config():
    ds = generate_clean_dataset()
    assert len(ds.vendors) == config.N_VENDORS
    assert len(ds.invoices) == config.N_INVOICES
    assert len(ds.purchase_orders) == config.N_INVOICES
    assert len(ds.goods_receipts) == config.N_INVOICES


def test_referential_integrity():
    ds = generate_clean_dataset()
    vendor_ids = {v.vendor_id for v in ds.vendors}
    po_ids = {po.po_id for po in ds.purchase_orders}
    receipt_pos = {r.po_id for r in ds.goods_receipts}

    for inv in ds.invoices:
        assert inv.vendor_id in vendor_ids
    for po in ds.purchase_orders:
        assert po.vendor_id in vendor_ids
        assert po.po_id in receipt_pos  # every PO has a goods receipt
    assert po_ids == receipt_pos


def test_clean_dataset_reconciles_perfectly():
    """Before seeding, every 3-way match must be clean — otherwise a 'caught'
    error later could be a generation artifact rather than a real defect."""
    from auditledger.matching.three_way_match import run_reconciliation

    ds = generate_clean_dataset()
    results = run_reconciliation(ds)
    dirty = {iid: r.types for iid, r in results.items() if not r.is_clean}
    assert dirty == {}, f"clean dataset should have no discrepancies, found: {dirty}"


def test_generation_is_deterministic():
    """Same seed -> byte-identical data. This is the reproducibility guarantee."""
    a = build_full_dataset()
    b = build_full_dataset()
    sig_a = [(i.invoice_id, i.vendor_id, i.invoice_number, i.total, i.po_reference)
             for i in a.invoices]
    sig_b = [(i.invoice_id, i.vendor_id, i.invoice_number, i.total, i.po_reference)
             for i in b.invoices]
    assert sig_a == sig_b
