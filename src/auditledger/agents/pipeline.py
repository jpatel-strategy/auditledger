"""End-to-end orchestration of the agent loop over a whole dataset.

For each invoice, in a fixed order:
    render raw text -> extract structured fields -> deterministic 3-way match
    -> Primary Agent decision -> Critic validation -> one AgentReport.

The single shared ``seen_keys`` set threaded through the matcher is what lets
duplicate submissions be caught in sequence, exactly as an AP team would.
"""

from __future__ import annotations

from collections import Counter

from .. import config
from ..data.schema import Dataset, Invoice, LineItem
from ..matching.three_way_match import match_invoice
from .critic_agent import run_critic
from .extraction import DeterministicExtractor, get_extractor
from .llm import get_client, model_version
from .models import AgentReport
from .primary_agent import run_primary
from .rendering import render_invoice_text


def _to_invoice(extracted) -> Invoice:
    """Rebuild an Invoice object from extracted fields to feed the matcher."""
    return Invoice(
        invoice_id=extracted.invoice_id,
        vendor_id=extracted.vendor_id,
        invoice_number=extracted.invoice_number,
        invoice_date=extracted.invoice_date,
        currency=extracted.currency,
        po_reference=extracted.po_reference,
        lines=[
            LineItem(li["sku"], li["description"], li["quantity"], li["unit_price"])
            for li in extracted.lines
        ],
        subtotal=extracted.subtotal,
        tax_amount=extracted.tax_amount,
        total=extracted.total,
    )


def run_pipeline(dataset: Dataset, cfg=config, client="auto") -> list[AgentReport]:
    """Run every invoice through the full loop and return one report each.

    ``client="auto"`` uses a live LLM when a key is present, else offline mode.
    Pass ``client=None`` to force the deterministic path (used by the gate).
    """
    if client == "auto":
        client = get_client()
    extractor = get_extractor(client)
    fallback_extractor = DeterministicExtractor()

    vendor_name = {v.vendor_id: v.name for v in dataset.vendors}
    risk_tier = {p.vendor_id: p.risk_tier for p in dataset.vendor_risk_profiles}
    po_by_id = {po.po_id: po for po in dataset.purchase_orders}
    receipt_by_po = {r.po_id: r for r in dataset.goods_receipts}
    seen_keys: set[tuple] = set()
    mv = model_version()

    reports: list[AgentReport] = []
    for invoice in sorted(dataset.invoices, key=lambda i: i.invoice_id):
        raw = render_invoice_text(invoice)
        try:
            extracted = extractor.extract(raw)
            extraction_ok = True
        except Exception:
            # A flaky/hallucinated LLM extraction must never break the ledger:
            # fall back to the deterministic parser and record that we did.
            extracted = fallback_extractor.extract(raw)
            extraction_ok = False

        inv = _to_invoice(extracted)
        match_result = match_invoice(inv, po_by_id, receipt_by_po, seen_keys, cfg)

        vid = extracted.vendor_id
        tier = risk_tier.get(vid, "LOW")
        decision = run_primary(match_result, vendor_name.get(vid, vid), tier, client, cfg)
        critique = run_critic(decision, match_result, tier, cfg)

        reports.append(
            AgentReport(
                invoice_id=extracted.invoice_id,
                input_hash=extracted.input_hash,
                model_version=mv,
                extraction_ok=extraction_ok,
                classification=decision.classification,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                discrepancy_types=decision.discrepancy_types,
                critic_consistent=critique.is_consistent,
                critic_issues=critique.issues,
            )
        )
    return reports


def summarize(reports: list[AgentReport]) -> dict:
    """Quick tally of dispositions and Critic consistency for dashboards/tests."""
    counts = Counter(r.classification for r in reports)
    return {
        "total": len(reports),
        "by_classification": dict(counts),
        "critic_inconsistencies": sum(1 for r in reports if not r.critic_consistent),
    }
