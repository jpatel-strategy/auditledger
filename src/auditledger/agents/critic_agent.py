"""The Critic Agent: a lightweight, independent consistency check.

It re-reads the Primary Agent's Decision against two sources of truth — the
deterministic match result and the vendor risk profile — and flags any
inconsistency. It explicitly does NOT override or re-decide; a genuine second
control catches a broken first control, it does not replace it.

The checks are deterministic and structured (not free-form) so the validation
is itself auditable and reproducible — a control you can't re-run predictably is
not much of a control.
"""

from __future__ import annotations

from .. import config
from ..matching.three_way_match import MatchResult
from .classification import AUTO_APPROVE, ESCALATE
from .models import Critique, Decision


def run_critic(decision: Decision, match_result: MatchResult, risk_tier: str,
               cfg=config) -> Critique:
    """Return a consistency verdict for one Primary Decision."""
    issues: list[str] = []

    # 1. The cardinal rule: nothing with a discrepancy may be AUTO-APPROVE.
    if decision.classification == AUTO_APPROVE and not match_result.is_clean:
        issues.append(
            f"AUTO-APPROVE proposed despite {len(match_result.discrepancies)} "
            f"deterministic discrepancy(ies)."
        )

    # 2. AUTO-APPROVE must clear the visible confidence threshold.
    if decision.classification == AUTO_APPROVE and decision.confidence < cfg.CONFIDENCE_THRESHOLD:
        issues.append(
            f"AUTO-APPROVE with confidence {decision.confidence:.2f} below "
            f"threshold {cfg.CONFIDENCE_THRESHOLD:.2f}."
        )

    # 3. A high-risk vendor should never be silently automated.
    if decision.classification == AUTO_APPROVE and risk_tier == "HIGH":
        issues.append("AUTO-APPROVE for a HIGH-risk vendor; expected human review.")

    # 4. A high-severity finding must escalate, not merely flag.
    has_high = any(d.severity == "HIGH" for d in match_result.discrepancies)
    if has_high and decision.classification != ESCALATE:
        issues.append("High-severity discrepancy present but not ESCALATED.")

    # 5. The Primary's cited findings must match what the matcher actually found.
    actual = sorted({d.type for d in match_result.discrepancies})
    if decision.discrepancy_types != actual:
        issues.append(
            f"Reasoning cites {decision.discrepancy_types} but matcher found {actual}."
        )

    return Critique(
        invoice_id=decision.invoice_id,
        is_consistent=len(issues) == 0,
        issues=issues,
    )
