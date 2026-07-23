"""The deterministic 3-way match — AuditLedger's core control.

Reconciles each Invoice against its Purchase Order (what we agreed to pay) and
its Goods Receipt (what we actually received). This is pure, testable Python:
no LLM ever performs the reconciliation math. The AI layer added in later
milestones only *classifies and explains* what this control has already proven.

Every check emits a ``Discrepancy`` whose ``type`` is drawn from the shared
taxonomy, so the seeded answer key and this detector speak the same language.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import config, taxonomy
from ..money import money
from ..data.schema import Dataset, Invoice


@dataclass
class Discrepancy:
    type: str
    detail: str
    severity: str


@dataclass
class MatchResult:
    invoice_id: str
    is_clean: bool
    discrepancies: list[Discrepancy] = field(default_factory=list)

    @property
    def types(self) -> set[str]:
        return {d.type for d in self.discrepancies}


def match_invoice(invoice: Invoice, po_by_id, receipt_by_po, seen_keys, cfg=config) -> MatchResult:
    """Run all five checks on a single invoice.

    ``seen_keys`` is a mutable set carried across invoices so duplicates (a later
    invoice repeating an earlier vendor+number+total) can be detected in order.
    """
    discrepancies: list[Discrepancy] = []

    # --- Check 1: Duplicate submission ------------------------------------
    key = (invoice.vendor_id, invoice.invoice_number, money(invoice.total))
    if key in seen_keys:
        discrepancies.append(
            Discrepancy(
                taxonomy.DUPLICATE_INVOICE,
                f"Invoice number {invoice.invoice_number} for {money(invoice.total)} "
                f"already seen for vendor {invoice.vendor_id}",
                taxonomy.SEVERITY[taxonomy.DUPLICATE_INVOICE],
            )
        )
    else:
        seen_keys.add(key)

    # --- Check 2: PO reference resolves -----------------------------------
    po = po_by_id.get(invoice.po_reference) if invoice.po_reference else None
    if po is None:
        discrepancies.append(
            Discrepancy(
                taxonomy.MISSING_PO_REFERENCE,
                f"po_reference {invoice.po_reference!r} does not resolve to a known PO",
                taxonomy.SEVERITY[taxonomy.MISSING_PO_REFERENCE],
            )
        )
    else:
        po_line_by_sku = {li.sku: li for li in po.lines}
        receipt = receipt_by_po.get(po.po_id)
        received_by_sku = (
            {rl.sku: rl.quantity_received for rl in receipt.lines} if receipt else {}
        )

        for line in invoice.lines:
            po_line = po_line_by_sku.get(line.sku)
            if po_line is None:
                continue  # SKU not on the PO is a variant handled by price/qty checks upstream
            # --- Check 3: Price variance vs PO --------------------------------
            ceiling = po_line.unit_price * (1 + cfg.PRICE_TOLERANCE_PCT)
            if line.unit_price > ceiling + cfg.MONEY_EPSILON:
                discrepancies.append(
                    Discrepancy(
                        taxonomy.PRICE_VARIANCE,
                        f"SKU {line.sku}: invoiced {line.unit_price} vs PO {po_line.unit_price} "
                        f"(> {cfg.PRICE_TOLERANCE_PCT:.0%} tolerance)",
                        taxonomy.SEVERITY[taxonomy.PRICE_VARIANCE],
                    )
                )
            # --- Check 4: Quantity vs goods receipt ---------------------------
            received = received_by_sku.get(line.sku)
            if received is not None and line.quantity > received:
                discrepancies.append(
                    Discrepancy(
                        taxonomy.QUANTITY_MISMATCH,
                        f"SKU {line.sku}: invoiced {line.quantity} units but only "
                        f"{received} received",
                        taxonomy.SEVERITY[taxonomy.QUANTITY_MISMATCH],
                    )
                )

    # --- Check 5: Tax & totals arithmetic ---------------------------------
    subtotal = money(sum(li.line_total for li in invoice.lines))
    expected_tax = money(subtotal * cfg.DEFAULT_TAX_RATE)
    tax_off = abs(invoice.tax_amount - expected_tax) > cfg.MONEY_EPSILON
    total_off = abs(invoice.total - money(subtotal + invoice.tax_amount)) > cfg.MONEY_EPSILON
    if tax_off or total_off:
        reason = []
        if tax_off:
            reason.append(f"tax {invoice.tax_amount} != expected {expected_tax}")
        if total_off:
            reason.append(f"total {invoice.total} != subtotal+tax {money(subtotal + invoice.tax_amount)}")
        discrepancies.append(
            Discrepancy(
                taxonomy.TAX_MATH_ERROR,
                "; ".join(reason),
                taxonomy.SEVERITY[taxonomy.TAX_MATH_ERROR],
            )
        )

    return MatchResult(
        invoice_id=invoice.invoice_id,
        is_clean=len(discrepancies) == 0,
        discrepancies=discrepancies,
    )


def run_reconciliation(dataset: Dataset, cfg=config) -> dict[str, MatchResult]:
    """Match every invoice in the dataset, in invoice-id order.

    Ordering matters only for duplicate detection: the first occurrence of a
    (vendor, number, total) key is accepted, later repeats are flagged — exactly
    how an AP clerk would treat the second copy of the same bill.
    """
    po_by_id = {po.po_id: po for po in dataset.purchase_orders}
    receipt_by_po = {r.po_id: r for r in dataset.goods_receipts}
    seen_keys: set[tuple] = set()

    results: dict[str, MatchResult] = {}
    for invoice in sorted(dataset.invoices, key=lambda inv: inv.invoice_id):
        results[invoice.invoice_id] = match_invoice(
            invoice, po_by_id, receipt_by_po, seen_keys, cfg
        )
    return results
