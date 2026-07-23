"""MILESTONE 2 VERIFICATION GATE — the agentic evaluation loop.

The headline guarantee: run all 100 invoices end-to-end through
extract -> match -> Primary -> Critic, and confirm ZERO seeded errors slip into
the AUTO-APPROVE bucket. Also proves extraction round-trips and the Critic finds
the deterministic pipeline internally consistent.
"""

from __future__ import annotations

from auditledger.agents.classification import AUTO_APPROVE, ESCALATE, FLAG_FOR_REVIEW
from auditledger.agents.extraction import DeterministicExtractor
from auditledger.agents.rendering import render_invoice_text


def test_extraction_round_trips(dataset):
    """Raw-text extraction must faithfully recover the invoice fields, or the
    downstream match would be reconciling the wrong numbers."""
    extractor = DeterministicExtractor()
    for invoice in dataset.invoices:
        ex = extractor.extract(render_invoice_text(invoice))
        assert ex.invoice_id == invoice.invoice_id
        assert ex.vendor_id == invoice.vendor_id
        assert ex.po_reference == invoice.po_reference
        assert ex.total == invoice.total
        assert len(ex.lines) == len(invoice.lines)


def test_no_seeded_error_is_auto_approved(reports, ground_truth_by_invoice):
    """THE gate: every seeded error must be withheld from automation."""
    leaked = [
        r.invoice_id
        for r in reports
        if r.classification == AUTO_APPROVE
        and ground_truth_by_invoice[r.invoice_id].is_seeded_error
    ]
    assert leaked == [], f"seeded errors auto-approved (should be impossible): {leaked}"


def test_every_seeded_error_is_flagged_or_escalated(reports, ground_truth_by_invoice):
    by_id = {r.invoice_id: r for r in reports}
    for iid, gt in ground_truth_by_invoice.items():
        if gt.is_seeded_error:
            assert by_id[iid].classification in (FLAG_FOR_REVIEW, ESCALATE), (
                f"{iid} ({gt.error_type}) got {by_id[iid].classification}"
            )


def test_high_severity_errors_escalate(reports, ground_truth_by_invoice):
    """Duplicate and missing-PO defects (HIGH severity) must ESCALATE."""
    by_id = {r.invoice_id: r for r in reports}
    for iid, gt in ground_truth_by_invoice.items():
        if gt.is_seeded_error and gt.severity == "HIGH":
            assert by_id[iid].classification == ESCALATE, (
                f"{iid} ({gt.error_type}) should ESCALATE, got {by_id[iid].classification}"
            )


def test_clean_low_risk_invoices_are_auto_approved(reports, ground_truth_by_invoice, dataset):
    """Automation must actually happen: clean invoices from non-high-risk vendors
    should auto-approve — otherwise the tool delivers no efficiency."""
    tier = {p.vendor_id: p.risk_tier for p in dataset.vendor_risk_profiles}
    inv_vendor = {i.invoice_id: i.vendor_id for i in dataset.invoices}
    by_id = {r.invoice_id: r for r in reports}

    auto = 0
    for iid, gt in ground_truth_by_invoice.items():
        if not gt.is_seeded_error and tier[inv_vendor[iid]] != "HIGH":
            assert by_id[iid].classification == AUTO_APPROVE, (
                f"clean invoice {iid} was not auto-approved"
            )
            auto += 1
    assert auto > 0  # sanity: at least some automation occurred


def test_clean_high_risk_vendor_is_not_auto_approved(reports, ground_truth_by_invoice, dataset):
    """A clean invoice from a poor-history vendor still deserves human eyes —
    the risk profile actively shapes the disposition."""
    tier = {p.vendor_id: p.risk_tier for p in dataset.vendor_risk_profiles}
    inv_vendor = {i.invoice_id: i.vendor_id for i in dataset.invoices}
    by_id = {r.invoice_id: r for r in reports}

    for iid, gt in ground_truth_by_invoice.items():
        if not gt.is_seeded_error and tier[inv_vendor[iid]] == "HIGH":
            assert by_id[iid].classification != AUTO_APPROVE


def test_critic_finds_pipeline_consistent(reports):
    """The deterministic Primary policy should never contradict itself, so the
    Critic must report zero inconsistencies across all 100 invoices."""
    inconsistent = [(r.invoice_id, r.critic_issues) for r in reports if not r.critic_consistent]
    assert inconsistent == [], f"Critic found inconsistencies: {inconsistent}"


def test_all_invoices_processed(reports, dataset):
    assert len(reports) == len(dataset.invoices) == 100
