"""Verify the case-study modeling engine: transparent math + honesty guardrails."""

from __future__ import annotations

from auditledger import case_study


def _scenario():
    # Feed FIXED measured values so the math is deterministic to assert on.
    return case_study.model_scenario(
        measured_automation_rate=0.60,
        measured_catch_rate=1.0,
    )


def test_volume_and_ap_spend_are_transparent():
    s = _scenario()
    # volume = suppliers * invoices/supplier (Walmart default: 100,000 * 50)
    assert s["modeled_invoice_volume"] == 100_000 * 50 == 5_000_000
    # AP spend = revenue * cogs_ratio
    assert s["modeled_ap_spend_usd"] == round(648.1e9 * 0.75, 2)


def test_processing_efficiency_uses_measured_automation():
    s = _scenario()
    # conservative: automation_rate * volume * $12.50 manual benchmark
    assert s["processing_cost_addressable_usd"] == round(0.60 * 5_000_000 * 12.50, 2)
    assert s["estimated_hours_saved"] == round(0.60 * 5_000_000 * 10.0 / 60.0, 0)


def test_leakage_is_a_published_benchmark_range():
    s = _scenario()
    ap = s["modeled_ap_spend_usd"]
    assert s["dup_leakage_low_usd"] == round(ap * 0.008, 2)
    assert s["dup_leakage_high_usd"] == round(ap * 0.02, 2)
    assert s["dup_leakage_low_usd"] < s["dup_leakage_high_usd"]  # it's a range, not one number


def test_measured_facts_pass_through_unchanged():
    s = _scenario()
    assert s["measured_catch_rate"] == 1.0
    assert s["measured_automation_rate"] == 0.60
    assert s["audit_coverage"] == 1.0


def test_disclaimer_and_source_are_present_and_honest():
    s = _scenario()
    assert "Not affiliated" in s["disclaimer"]
    assert "No dollar figure was identified" in s["disclaimer"]
    assert "10-K" in s["source_note"]


def test_headline_is_honestly_framed():
    s = _scenario()
    h = case_study.headline(s)
    assert "Walmart" in h
    assert "traceable to a logged decision" in h
    # never claims to have "found" or "saved for" the company
    assert "found" not in h.lower()
    assert "saved for" not in h.lower()
