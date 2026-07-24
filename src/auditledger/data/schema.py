"""In-memory data model for AuditLedger.

These dataclasses mirror the SQLite tables one-to-one and model AP documents the
way they actually exist in the real world: one header (invoice / PO) with many
line items underneath. Keeping the shape realistic is what lets the deterministic
3-way match look like a control an accountant would recognize.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..money import money


@dataclass
class Vendor:
    """A supplier we transact with."""

    vendor_id: str
    name: str
    category: str
    payment_terms: str          # e.g. "Net 30"
    tax_id: str
    # Baseline reliability is only used to make the synthetic data feel realistic;
    # the risk profile the Critic trusts is computed from actual ground truth.
    baseline_reliability: float


@dataclass
class LineItem:
    """A single billed/ordered line. line_total is always derived, never stored
    independently, so a line can't silently disagree with its own arithmetic."""

    sku: str
    description: str
    quantity: int
    unit_price: float

    @property
    def line_total(self) -> float:
        return money(self.quantity * self.unit_price)


@dataclass
class PurchaseOrder:
    """The authorized commitment to buy — the 'what we agreed to pay' record."""

    po_id: str
    vendor_id: str
    po_date: str
    currency: str
    tax_rate: float
    lines: list[LineItem] = field(default_factory=list)

    @property
    def subtotal(self) -> float:
        return money(sum(li.line_total for li in self.lines))

    @property
    def tax_amount(self) -> float:
        return money(self.subtotal * self.tax_rate)

    @property
    def total(self) -> float:
        return money(self.subtotal + self.tax_amount)


@dataclass
class ReceiptLine:
    """How much of a SKU actually arrived on the dock."""

    sku: str
    quantity_received: int


@dataclass
class GoodsReceipt:
    """Proof of physical delivery — the 'what we actually received' record."""

    receipt_id: str
    po_id: str
    receipt_date: str
    received_by: str
    lines: list[ReceiptLine] = field(default_factory=list)


@dataclass
class Invoice:
    """The vendor's bill — the 'what they're asking us to pay' record.

    subtotal / tax_amount / total are stored explicitly (not derived) because a
    seeded defect must be able to make them disagree with the line items — that
    disagreement is exactly what the matcher is meant to catch.
    """

    invoice_id: str
    vendor_id: str
    invoice_number: str
    invoice_date: str
    currency: str
    po_reference: str | None
    lines: list[LineItem] = field(default_factory=list)
    subtotal: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0


@dataclass
class GroundTruth:
    """The hidden answer key. Stored in its own table and never shown to the
    matcher, so a 100% catch rate is earned rather than leaked."""

    invoice_id: str
    is_seeded_error: bool
    error_type: str | None
    error_detail: dict
    severity: str | None


@dataclass
class VendorRisk:
    """Historical error rate per vendor, derived from ground truth. The Milestone 2
    Critic depends on this table existing to weight how much it trusts a vendor."""

    vendor_id: str
    total_invoices: int
    seeded_error_count: int
    historical_error_rate: float
    risk_tier: str


@dataclass
class Dataset:
    """The complete synthetic universe passed between generation, seeding,
    persistence, and matching."""

    vendors: list[Vendor] = field(default_factory=list)
    purchase_orders: list[PurchaseOrder] = field(default_factory=list)
    goods_receipts: list[GoodsReceipt] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    ground_truth: list[GroundTruth] = field(default_factory=list)
    vendor_risk_profiles: list[VendorRisk] = field(default_factory=list)
