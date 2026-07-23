"""Structured outputs passed along the agent loop.

Keeping these as plain dataclasses (not free-form LLM text) is what makes the
pipeline auditable: every stage hands the next a typed, inspectable record.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedInvoice:
    """Structured fields recovered from a raw invoice document."""

    invoice_id: str
    vendor_id: str
    invoice_number: str
    invoice_date: str
    currency: str
    po_reference: str | None
    lines: list[dict]          # each: sku, description, quantity, unit_price
    subtotal: float
    tax_amount: float
    total: float
    input_hash: str            # sha256 of the raw text — the evidence anchor


@dataclass
class Decision:
    """The Primary Agent's proposed disposition for one invoice."""

    invoice_id: str
    classification: str        # one of agents.classification.*
    confidence: float          # 0..1, deterministic and explainable
    reasoning: str             # human-readable paragraph
    discrepancy_types: list[str] = field(default_factory=list)


@dataclass
class Critique:
    """The Critic Agent's consistency verdict. It never changes the decision."""

    invoice_id: str
    is_consistent: bool
    issues: list[str] = field(default_factory=list)


@dataclass
class AgentReport:
    """The full per-invoice record the audit layer (Milestone 3) will persist."""

    invoice_id: str
    input_hash: str
    model_version: str
    extraction_ok: bool
    classification: str
    confidence: float
    reasoning: str
    discrepancy_types: list[str]
    critic_consistent: bool
    critic_issues: list[str]
