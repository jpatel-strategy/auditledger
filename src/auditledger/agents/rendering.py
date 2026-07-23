"""Render a structured Invoice into a raw text document.

In the real world an invoice arrives as a PDF/email that must be parsed. Our
synthetic invoices start structured, so we first flatten them to realistic raw
text; the extractor then recovers the structure — exercising the full
extract-then-match pipeline exactly as production would.
"""

from __future__ import annotations

import hashlib

from ..data.schema import Invoice


def render_invoice_text(invoice: Invoice) -> str:
    """Produce the raw text a vendor might send us."""
    po_ref = invoice.po_reference if invoice.po_reference else "(none)"
    lines = [
        "INVOICE",
        f"Invoice Number: {invoice.invoice_number}",
        f"Invoice Date: {invoice.invoice_date}",
        f"Vendor ID: {invoice.vendor_id}",
        f"PO Reference: {po_ref}",
        f"Currency: {invoice.currency}",
        f"Invoice ID: {invoice.invoice_id}",
        "",
        "Line Items:",
    ]
    for li in invoice.lines:
        lines.append(
            f"- {li.sku} | {li.description} | Qty: {li.quantity} | "
            f"Unit Price: {li.unit_price:.2f} | Line Total: {li.line_total:.2f}"
        )
    lines += [
        "",
        f"Subtotal: {invoice.subtotal:.2f}",
        f"Tax: {invoice.tax_amount:.2f}",
        f"Total: {invoice.total:.2f}",
    ]
    return "\n".join(lines)


def hash_text(raw_text: str) -> str:
    """The immutable evidence anchor: a hash of exactly what we processed."""
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
