"""THE MILESTONE 1 VERIFICATION GATE.

Proves two things against the hidden ground-truth answer key:
  1. The deterministic matcher catches 100% of every seeded error TYPE.
  2. It raises zero false positives on the clean invoices.

If either fails, Milestone 1 is not done — no LLM work may begin.
"""

from __future__ import annotations

import pytest

from auditledger import taxonomy


def test_no_false_positives_on_clean_invoices(results, ground_truth_by_invoice):
    """Every invoice the answer key marks clean must reconcile cleanly."""
    false_positives = {}
    for invoice_id, result in results.items():
        gt = ground_truth_by_invoice[invoice_id]
        if not gt.is_seeded_error and not result.is_clean:
            false_positives[invoice_id] = result.types
    assert false_positives == {}, f"clean invoices wrongly flagged: {false_positives}"


@pytest.mark.parametrize("error_type", taxonomy.ALL_ERROR_TYPES)
def test_each_seeded_error_type_is_caught(error_type, results, ground_truth_by_invoice):
    """For every seeded invoice of a given type, the matcher's discrepancies must
    include that exact type. Parametrized so failures name the guilty type."""
    misses = []
    for invoice_id, gt in ground_truth_by_invoice.items():
        if gt.is_seeded_error and gt.error_type == error_type:
            caught = results[invoice_id].types
            if error_type not in caught:
                misses.append((invoice_id, caught))
    assert misses == [], f"{error_type} not caught for: {misses}"


def test_overall_catch_rate_is_100_percent(results, ground_truth_by_invoice):
    """The headline metric: catch rate across ALL seeded errors == 1.0."""
    seeded = [iid for iid, gt in ground_truth_by_invoice.items() if gt.is_seeded_error]
    caught = [
        iid for iid in seeded
        if ground_truth_by_invoice[iid].error_type in results[iid].types
    ]
    catch_rate = len(caught) / len(seeded)
    assert catch_rate == 1.0, (
        f"catch rate {catch_rate:.1%} ({len(caught)}/{len(seeded)}); "
        f"missed: {[i for i in seeded if i not in caught]}"
    )
