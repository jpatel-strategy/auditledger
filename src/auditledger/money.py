"""One rounding rule for all monetary figures.

Business rationale: an auditor expects a single, predictable rounding convention
applied everywhere — never an ad-hoc decision inside each calculation. Using one
helper on both the generation side and the checking side guarantees a clean
invoice always reconciles to the cent.
"""

from __future__ import annotations


def money(amount: float) -> float:
    """Round any monetary value to 2 decimal places (cents)."""
    return round(float(amount), 2)
