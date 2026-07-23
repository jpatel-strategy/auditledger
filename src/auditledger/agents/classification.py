"""The three dispositions the Primary Agent may recommend.

These are recommendations only — a human signs off on anything that is not a
clean AUTO-APPROVE (see the exception queue in Milestone 3).
"""

from __future__ import annotations

AUTO_APPROVE = "AUTO-APPROVE"       # clean 3-way match, confidence above threshold
FLAG_FOR_REVIEW = "FLAG FOR REVIEW" # something needs a human's eyes, low risk
ESCALATE = "ESCALATE"               # high-severity / high-risk, senior sign-off

ALL_CLASSIFICATIONS: list[str] = [AUTO_APPROVE, FLAG_FOR_REVIEW, ESCALATE]
