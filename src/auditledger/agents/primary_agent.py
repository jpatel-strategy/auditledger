"""The Primary Agent: propose a disposition, a confidence score, and reasoning.

Critical design choice: the *classification* and the *confidence* are computed by
deterministic, explainable policy — not by the LLM. This is the moat. The matcher
already proved what is wrong; a hard guardrail then forbids auto-approving any
invoice carrying a discrepancy. The LLM (when available) only writes the
natural-language reasoning paragraph; offline, a template does. Either way the
money decision is never at the mercy of a black box.
"""

from __future__ import annotations

from .. import config
from ..matching.three_way_match import MatchResult
from .classification import AUTO_APPROVE, ESCALATE, FLAG_FOR_REVIEW
from .llm import LLMClient
from .models import Decision

_SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _worst_severity(match_result: MatchResult) -> str | None:
    if match_result.is_clean:
        return None
    return max((d.severity for d in match_result.discrepancies), key=_SEVERITY_ORDER.get)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_confidence(match_result: MatchResult, risk_tier: str, cfg=config) -> float:
    """A 0..1 score where every deduction traces to a named finding."""
    risk_penalty = cfg.RISK_TIER_CONFIDENCE_PENALTY[risk_tier]
    if match_result.is_clean:
        conf = 0.99 - risk_penalty
    else:
        worst = _worst_severity(match_result)
        penalty = cfg.SEVERITY_CONFIDENCE_PENALTY[worst]
        extra = 0.05 * (len(match_result.discrepancies) - 1)
        conf = 0.90 - penalty - extra - risk_penalty
    return round(_clamp(conf, 0.05, 0.99), 2)


def classify(match_result: MatchResult, risk_tier: str, confidence: float, cfg=config) -> str:
    """Map the deterministic facts to one of the three dispositions."""
    if match_result.is_clean:
        # A clean match can only be automated when confidence clears the bar.
        # A clean invoice from a poor-history vendor still gets human eyes.
        return AUTO_APPROVE if confidence >= cfg.CONFIDENCE_THRESHOLD else FLAG_FOR_REVIEW

    # Guardrail: any discrepancy means this can never be AUTO-APPROVE.
    worst = _worst_severity(match_result)
    if worst == "HIGH" or risk_tier == "HIGH":
        return ESCALATE
    return FLAG_FOR_REVIEW


def _template_reasoning(classification, confidence, match_result, vendor_name, risk_tier) -> str:
    if match_result.is_clean:
        return (
            f"3-way match is clean: invoice reconciles to its purchase order and "
            f"goods receipt with no discrepancies. Vendor {vendor_name} carries a "
            f"{risk_tier} historical risk tier. Confidence {confidence:.2f}. "
            f"Recommended disposition: {classification}."
        )
    found = ", ".join(sorted({d.type for d in match_result.discrepancies}))
    details = "; ".join(d.detail for d in match_result.discrepancies)
    return (
        f"3-way match found {len(match_result.discrepancies)} discrepancy(ies) "
        f"[{found}] for vendor {vendor_name} ({risk_tier} risk). Details: {details}. "
        f"Because at least one control failed, auto-approval is withheld. "
        f"Confidence {confidence:.2f}. Recommended disposition: {classification}."
    )


def _llm_reasoning(client: LLMClient, classification, confidence, match_result,
                   vendor_name, risk_tier) -> str:
    facts = _template_reasoning(classification, confidence, match_result, vendor_name, risk_tier)
    system = (
        "You are an AP reconciliation analyst. Given the deterministic match "
        "FACTS, write ONE concise paragraph justifying the disposition. Do not "
        "change the disposition, confidence, or invent findings — only explain."
    )
    try:
        return client.complete(system, f"FACTS: {facts}", max_tokens=256).strip() or facts
    except Exception:
        # Never let a prose call break the pipeline; fall back to the facts.
        return facts


def run_primary(match_result: MatchResult, vendor_name: str, risk_tier: str,
                client: LLMClient | None = None, cfg=config) -> Decision:
    """Produce the Primary Agent's Decision for one invoice."""
    confidence = compute_confidence(match_result, risk_tier, cfg)
    classification = classify(match_result, risk_tier, confidence, cfg)
    if client is not None:
        reasoning = _llm_reasoning(client, classification, confidence,
                                   match_result, vendor_name, risk_tier)
    else:
        reasoning = _template_reasoning(classification, confidence,
                                        match_result, vendor_name, risk_tier)
    return Decision(
        invoice_id=match_result.invoice_id,
        classification=classification,
        confidence=confidence,
        reasoning=reasoning,
        discrepancy_types=sorted({d.type for d in match_result.discrepancies}),
    )
