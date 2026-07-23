"""Extract structured invoice data from raw text.

Two interchangeable strategies behind one function:

- ``LLMExtractor``            : asks the model to return strict JSON (production).
- ``DeterministicExtractor``  : parses our rendered format with regex (offline,
                                 and used by the verification gate so it is free
                                 and reproducible).

Both return the same ``ExtractedInvoice``, which is then fed to the deterministic
matcher — satisfying "extract from raw text, then reconcile with pure math."
"""

from __future__ import annotations

import json
import re

from ..money import money
from .llm import LLMClient
from .models import ExtractedInvoice
from .rendering import hash_text

_LINE_RE = re.compile(
    r"^- (?P<sku>[^|]+?) \| (?P<desc>.+?) \| Qty: (?P<qty>\d+) \| "
    r"Unit Price: (?P<price>[\d.]+) \| Line Total: [\d.]+$"
)


def _field(raw: str, label: str) -> str:
    m = re.search(rf"^{re.escape(label)}:\s*(.*)$", raw, re.MULTILINE)
    return m.group(1).strip() if m else ""


class DeterministicExtractor:
    """Parse the rendered invoice text without any model call."""

    def extract(self, raw_text: str) -> ExtractedInvoice:
        po_ref = _field(raw_text, "PO Reference")
        po_reference = None if po_ref in ("", "(none)") else po_ref

        lines = []
        for line in raw_text.splitlines():
            m = _LINE_RE.match(line)
            if m:
                lines.append(
                    {
                        "sku": m.group("sku").strip(),
                        "description": m.group("desc").strip(),
                        "quantity": int(m.group("qty")),
                        "unit_price": money(float(m.group("price"))),
                    }
                )

        return ExtractedInvoice(
            invoice_id=_field(raw_text, "Invoice ID"),
            vendor_id=_field(raw_text, "Vendor ID"),
            invoice_number=_field(raw_text, "Invoice Number"),
            invoice_date=_field(raw_text, "Invoice Date"),
            currency=_field(raw_text, "Currency"),
            po_reference=po_reference,
            lines=lines,
            subtotal=money(float(_field(raw_text, "Subtotal") or 0)),
            tax_amount=money(float(_field(raw_text, "Tax") or 0)),
            total=money(float(_field(raw_text, "Total") or 0)),
            input_hash=hash_text(raw_text),
        )


class LLMExtractor:
    """Ask the model to return structured JSON, then validate it into the model."""

    _SYSTEM = (
        "You extract invoice fields from raw text and return STRICT JSON only. "
        "Keys: invoice_id, vendor_id, invoice_number, invoice_date, currency, "
        "po_reference (null if absent), lines (list of {sku, description, "
        "quantity, unit_price}), subtotal, tax_amount, total. No commentary."
    )

    def __init__(self, client: LLMClient):
        self._client = client

    def extract(self, raw_text: str) -> ExtractedInvoice:
        text = self._client.complete(self._SYSTEM, raw_text, max_tokens=1024)
        data = json.loads(_strip_code_fence(text))
        return ExtractedInvoice(
            invoice_id=str(data["invoice_id"]),
            vendor_id=str(data["vendor_id"]),
            invoice_number=str(data["invoice_number"]),
            invoice_date=str(data["invoice_date"]),
            currency=str(data["currency"]),
            po_reference=data.get("po_reference") or None,
            lines=[
                {
                    "sku": str(li["sku"]),
                    "description": str(li["description"]),
                    "quantity": int(li["quantity"]),
                    "unit_price": money(float(li["unit_price"])),
                }
                for li in data["lines"]
            ],
            subtotal=money(float(data["subtotal"])),
            tax_amount=money(float(data["tax_amount"])),
            total=money(float(data["total"])),
            input_hash=hash_text(raw_text),
        )


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def get_extractor(client: LLMClient | None):
    """Pick the live extractor when a client exists, else the offline parser."""
    return LLMExtractor(client) if client is not None else DeterministicExtractor()
