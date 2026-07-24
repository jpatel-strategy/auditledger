"""The shared vocabulary of invoice defects.

Both the *answer key* (seeded ground truth) and the *detector* (deterministic
matcher) import these exact strings, so the two can never drift apart. If the
matcher and the seeding used different labels, a 100% catch rate would be
meaningless — this module is what makes the verification honest.
"""

from __future__ import annotations

DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
PRICE_VARIANCE = "PRICE_VARIANCE"
QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
MISSING_PO_REFERENCE = "MISSING_PO_REFERENCE"
TAX_MATH_ERROR = "TAX_MATH_ERROR"

# The five defect types we seed and detect, in a stable order.
ALL_ERROR_TYPES: list[str] = [
    DUPLICATE_INVOICE,
    PRICE_VARIANCE,
    QUANTITY_MISMATCH,
    MISSING_PO_REFERENCE,
    TAX_MATH_ERROR,
]

# Business severity of each defect — drives triage priority in the exception
# queue (Milestone 3) and the risk weighting the Critic applies (Milestone 2).
SEVERITY: dict[str, str] = {
    DUPLICATE_INVOICE: "HIGH",       # paying twice is direct cash loss
    MISSING_PO_REFERENCE: "HIGH",    # no authorization trail at all
    PRICE_VARIANCE: "MEDIUM",        # overbilling vs agreed price
    QUANTITY_MISMATCH: "MEDIUM",     # billed for goods not received
    TAX_MATH_ERROR: "LOW",           # arithmetic slip, usually small
}
