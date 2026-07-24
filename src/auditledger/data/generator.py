"""Deterministic synthetic-data engine.

Produces a fully *clean* universe first — every invoice reconciles perfectly to
its PO and goods receipt. Milestone-1 defects are injected afterwards by
``seeding.py``. Splitting "generate clean" from "inject errors" keeps the two
concerns readable and lets tests reason about each independently.

Determinism note: all randomness flows through a single ``random.Random(SEED)``,
so the output is identical on every machine and every run.
"""

from __future__ import annotations

import random

from .. import config
from ..money import money
from .schema import (
    Dataset,
    GoodsReceipt,
    Invoice,
    LineItem,
    PurchaseOrder,
    ReceiptLine,
    Vendor,
)

# A curated list of realistic B2B vendors (name, category). Hardcoded rather than
# faked so the dataset is fully deterministic and carries zero extra dependency.
_VENDOR_CATALOG: list[tuple[str, str]] = [
    ("Apex Office Supplies", "Office Supplies"),
    ("BlueRidge Logistics", "Freight & Logistics"),
    ("Cardinal IT Services", "IT Services"),
    ("Delta Facilities Management", "Facilities"),
    ("Everest Packaging Co", "Packaging"),
    ("Frontier Electrical Supply", "Electrical"),
    ("Granite Construction Supply", "Construction"),
    ("Harbor Chemical Corp", "Chemicals"),
    ("Ironclad Security Systems", "Security"),
    ("Juniper Software Ltd", "Software"),
    ("Keystone Industrial Parts", "Industrial Parts"),
    ("Lakeside Catering", "Catering"),
    ("Meridian Consulting Group", "Consulting"),
    ("Northwind Traders", "Wholesale"),
    ("Orion Manufacturing", "Manufacturing"),
]

# Product nouns per category so line items read like real purchases.
_PRODUCTS: dict[str, list[str]] = {
    "Office Supplies": ["Copy Paper (case)", "Ink Cartridge", "Stapler", "Binder"],
    "Freight & Logistics": ["Pallet Shipment", "Container Haul", "Expedited Freight"],
    "IT Services": ["Managed Support (hr)", "Cloud Backup (mo)", "Network Audit"],
    "Facilities": ["Janitorial (mo)", "HVAC Service", "Landscaping (mo)"],
    "Packaging": ["Corrugated Box", "Stretch Wrap Roll", "Shipping Label (roll)"],
    "Electrical": ["Copper Wire (spool)", "Circuit Breaker", "LED Fixture"],
    "Construction": ["Rebar (ton)", "Concrete Mix (bag)", "Lumber (unit)"],
    "Chemicals": ["Industrial Solvent (drum)", "Cleaning Agent (gal)", "Coolant (gal)"],
    "Security": ["CCTV Camera", "Access Card Reader", "Alarm Panel"],
    "Software": ["User License (seat)", "API Credits (pack)", "Support Tier (mo)"],
    "Industrial Parts": ["Bearing Assembly", "Hydraulic Hose", "Drive Belt"],
    "Catering": ["Executive Lunch (head)", "Coffee Service (day)", "Event Platter"],
    "Consulting": ["Advisory (hr)", "Workshop (day)", "Assessment"],
    "Wholesale": ["Bulk Widget (case)", "Assorted Goods (lot)", "Retail Pack"],
    "Manufacturing": ["Machined Part", "Molded Component", "Assembly Unit"],
}


def _short_code(name: str) -> str:
    """Vendor invoice-number prefix, e.g. 'Apex Office Supplies' -> 'AOS'."""
    letters = [w[0] for w in name.split() if w[:1].isalpha()]
    return "".join(letters[:3]).upper()


def _build_vendors(rng: random.Random) -> list[Vendor]:
    terms = ["Net 15", "Net 30", "Net 45", "Net 60"]
    vendors: list[Vendor] = []
    for i, (name, category) in enumerate(_VENDOR_CATALOG, start=1):
        vendors.append(
            Vendor(
                vendor_id=f"V{i:02d}",
                name=name,
                category=category,
                payment_terms=rng.choice(terms),
                tax_id=f"TAX-{rng.randint(10_000_000, 99_999_999)}",
                baseline_reliability=round(rng.uniform(0.80, 0.99), 3),
            )
        )
    return vendors


def generate_clean_dataset(cfg=config) -> Dataset:
    """Generate ``N_INVOICES`` perfectly-reconciling Invoice/PO/Receipt triples.

    One PO, one goods receipt, and one invoice are created per transaction, all
    sharing the same line items — so before seeding, every 3-way match is clean.
    """
    rng = random.Random(cfg.SEED)
    vendors = _build_vendors(rng)

    dataset = Dataset(vendors=vendors)
    # Per-vendor running counter for human-readable invoice numbers.
    vendor_seq: dict[str, int] = {v.vendor_id: 0 for v in vendors}

    for n in range(1, cfg.N_INVOICES + 1):
        vendor = rng.choice(vendors)
        po_id = f"PO{n:04d}"
        receipt_id = f"RC{n:04d}"
        invoice_id = f"INV{n:04d}"

        # 1–4 line items per document.
        products = _PRODUCTS[vendor.category]
        n_lines = rng.randint(1, 4)
        po_lines: list[LineItem] = []
        used_skus: set[str] = set()
        for _ in range(n_lines):
            sku = f"SKU-{rng.randint(1000, 9999)}"
            while sku in used_skus:
                sku = f"SKU-{rng.randint(1000, 9999)}"
            used_skus.add(sku)
            po_lines.append(
                LineItem(
                    sku=sku,
                    description=rng.choice(products),
                    quantity=rng.randint(1, 50),
                    unit_price=money(rng.uniform(5.0, 500.0)),
                )
            )

        # PO carries the agreed prices/quantities.
        po = PurchaseOrder(
            po_id=po_id,
            vendor_id=vendor.vendor_id,
            po_date=f"2026-{rng.randint(1, 6):02d}-{rng.randint(1, 28):02d}",
            currency=cfg.CURRENCY,
            tax_rate=cfg.DEFAULT_TAX_RATE,
            lines=[LineItem(li.sku, li.description, li.quantity, li.unit_price) for li in po_lines],
        )

        # Goods receipt: everything ordered arrived in full (clean baseline).
        receipt = GoodsReceipt(
            receipt_id=receipt_id,
            po_id=po_id,
            receipt_date=po.po_date,
            received_by=f"dock-{rng.randint(1, 5)}",
            lines=[ReceiptLine(sku=li.sku, quantity_received=li.quantity) for li in po_lines],
        )

        # Invoice: bills exactly what was ordered/received, priced per the PO.
        vendor_seq[vendor.vendor_id] += 1
        invoice = Invoice(
            invoice_id=invoice_id,
            vendor_id=vendor.vendor_id,
            invoice_number=f"{_short_code(vendor.name)}-2026-{vendor_seq[vendor.vendor_id]:05d}",
            invoice_date=po.po_date,
            currency=cfg.CURRENCY,
            po_reference=po_id,
            lines=[LineItem(li.sku, li.description, li.quantity, li.unit_price) for li in po_lines],
        )
        _recompute_financials(invoice, cfg.DEFAULT_TAX_RATE)

        dataset.purchase_orders.append(po)
        dataset.goods_receipts.append(receipt)
        dataset.invoices.append(invoice)

    return dataset


def _recompute_financials(invoice: Invoice, tax_rate: float) -> None:
    """Re-derive subtotal, tax, and total from the current line items so the
    invoice is internally consistent. Called after any line-level change so that
    a seeded defect isolates to exactly the intended error type."""
    invoice.subtotal = money(sum(li.line_total for li in invoice.lines))
    invoice.tax_amount = money(invoice.subtotal * tax_rate)
    invoice.total = money(invoice.subtotal + invoice.tax_amount)
