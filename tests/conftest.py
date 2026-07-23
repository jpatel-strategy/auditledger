"""Shared pytest fixtures.

Builds the seeded dataset once per test session (it is deterministic, so one
build is representative of every build) and exposes both the data and the full
reconciliation result to the tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the ``src`` layout importable without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from auditledger.agents.pipeline import run_pipeline  # noqa: E402
from auditledger.data.seeding import build_full_dataset  # noqa: E402
from auditledger.matching.three_way_match import run_reconciliation  # noqa: E402


@pytest.fixture(scope="session")
def dataset():
    return build_full_dataset()


@pytest.fixture(scope="session")
def results(dataset):
    return run_reconciliation(dataset)


@pytest.fixture(scope="session")
def reports(dataset):
    # client=None forces the deterministic offline path so the gate is free,
    # reproducible, and independent of any API key.
    return run_pipeline(dataset, client=None)


@pytest.fixture(scope="session")
def ground_truth_by_invoice(dataset):
    return {gt.invoice_id: gt for gt in dataset.ground_truth}
