"""Verify the seeded error taxonomy and the vendor risk profile table."""

from __future__ import annotations

from auditledger import config, taxonomy


def test_exactly_thirty_percent_seeded(dataset):
    seeded = [gt for gt in dataset.ground_truth if gt.is_seeded_error]
    assert len(seeded) == config.N_SEEDED_ERRORS == 30
    assert len(dataset.ground_truth) == config.N_INVOICES  # one row per invoice


def test_all_five_error_types_present(dataset):
    seeded_types = {gt.error_type for gt in dataset.ground_truth if gt.is_seeded_error}
    assert seeded_types == set(taxonomy.ALL_ERROR_TYPES)


def test_error_types_evenly_distributed(dataset):
    counts: dict[str, int] = {}
    for gt in dataset.ground_truth:
        if gt.is_seeded_error:
            counts[gt.error_type] = counts.get(gt.error_type, 0) + 1
    # 30 errors across 5 types == 6 each.
    assert all(c == 6 for c in counts.values()), counts


def test_clean_invoices_have_no_error_metadata(dataset):
    for gt in dataset.ground_truth:
        if not gt.is_seeded_error:
            assert gt.error_type is None
            assert gt.severity is None


def test_risk_profiles_reconcile_to_ground_truth(dataset):
    profiles = dataset.vendor_risk_profiles
    assert len(profiles) == config.N_VENDORS

    # The per-vendor error counts must sum to the total seeded errors, and the
    # per-vendor invoice counts must sum to the whole population.
    assert sum(p.seeded_error_count for p in profiles) == config.N_SEEDED_ERRORS
    assert sum(p.total_invoices for p in profiles) == config.N_INVOICES

    # Each rate is internally consistent with its own counts (stored to 4 dp).
    for p in profiles:
        if p.total_invoices:
            expected = round(p.seeded_error_count / p.total_invoices, 4)
            assert p.historical_error_rate == expected
