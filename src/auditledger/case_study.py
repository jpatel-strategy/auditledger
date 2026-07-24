"""Retail-scale case-study modeling engine.

HONESTY CONTRACT (this is the whole point of the project):
This models AuditLedger against a synthetic AP portfolio *scaled to a large
retailer's publicly reported figures*. It is NOT consulting work, and no dollar
here was "found" for anyone. Every output is either (a) a MEASURED fact from the
real synthetic run, or (b) an ILLUSTRATIVE projection built by applying published
industry benchmarks to openly-stated assumptions. The two are never blurred, and
every figure the user can challenge is an editable input below.

To model a different company or update figures: edit ``RETAILER`` and
``ASSUMPTIONS`` — nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetailerProfile:
    """Publicly reported figures for the modeled company. Verify against the
    latest 10-K before using in any external material."""

    name: str
    annual_revenue_usd: float
    cogs_ratio: float          # cost of sales / revenue (publicly reported)
    supplier_count: int
    source_note: str


@dataclass
class ModelingAssumptions:
    """Openly-stated assumptions. Adjust freely; the artifact prints them."""

    invoices_per_supplier_per_year: int = 50      # ~weekly active-supplier billing (assumption)
    manual_cost_per_invoice_usd: float = 12.50    # conservative LOW end of $12.50–$40
    manual_minutes_per_invoice: float = 10.0      # touch-time assumption (configurable)
    dup_leakage_rate_low: float = 0.008           # 0.8% of outgoing payments (published)
    dup_leakage_rate_high: float = 0.02           # 2.0% of outgoing payments (published)


# --- Default modeled company (edit here to switch) -------------------------
RETAILER = RetailerProfile(
    name="Walmart Inc.",
    annual_revenue_usd=648.1e9,
    cogs_ratio=0.75,
    supplier_count=100_000,
    source_note=(
        "Walmart FY2024 10-K (fiscal year ended Jan 31, 2024): total revenue "
        "~$648.1B; cost of sales ~75% of revenue; \"100,000+ suppliers\" widely "
        "reported. Publicly reported figures — verify against the latest 10-K."
    ),
)
ASSUMPTIONS = ModelingAssumptions()

DISCLAIMER = (
    "Illustrative analysis using synthetic data scaled to publicly reported "
    "figures. Not affiliated with, endorsed by, or commissioned by the named "
    "company. No dollar figure was identified in that company's actual books; "
    "projections apply published industry benchmarks to stated assumptions."
)


def model_scenario(
    *,
    measured_automation_rate: float,
    measured_catch_rate: float,
    retailer: RetailerProfile = RETAILER,
    assumptions: ModelingAssumptions = ASSUMPTIONS,
) -> dict:
    """Combine MEASURED run facts with the retailer profile + assumptions.

    ``measured_automation_rate`` and ``measured_catch_rate`` come straight from
    the real synthetic run (analytics), so the capability side is never invented.
    """
    volume = retailer.supplier_count * assumptions.invoices_per_supplier_per_year
    ap_spend = retailer.annual_revenue_usd * retailer.cogs_ratio

    # (a) Processing-cost efficiency — conservative, from MEASURED automation.
    processing_cost_addressable = (
        measured_automation_rate * volume * assumptions.manual_cost_per_invoice_usd
    )
    est_hours_saved = (
        measured_automation_rate * volume * assumptions.manual_minutes_per_invoice / 60.0
    )

    # (b) Duplicate-payment leakage — ILLUSTRATIVE, from PUBLISHED benchmark range
    #     applied to modeled AP spend. Labeled a range, never a single "found" $.
    dup_leakage_low = ap_spend * assumptions.dup_leakage_rate_low
    dup_leakage_high = ap_spend * assumptions.dup_leakage_rate_high

    return {
        "retailer": retailer.name,
        "source_note": retailer.source_note,
        # inputs / assumptions (printed for transparency)
        "annual_revenue_usd": retailer.annual_revenue_usd,
        "cogs_ratio": retailer.cogs_ratio,
        "modeled_ap_spend_usd": round(ap_spend, 2),
        "supplier_count": retailer.supplier_count,
        "invoices_per_supplier_per_year": assumptions.invoices_per_supplier_per_year,
        "modeled_invoice_volume": volume,
        # measured capability (from the real run)
        "measured_catch_rate": measured_catch_rate,
        "measured_automation_rate": measured_automation_rate,
        "audit_coverage": 1.0,
        # (a) efficiency projection
        "processing_cost_addressable_usd": round(processing_cost_addressable, 2),
        "estimated_hours_saved": round(est_hours_saved, 0),
        # (b) leakage projection (range)
        "dup_leakage_rate_low": assumptions.dup_leakage_rate_low,
        "dup_leakage_rate_high": assumptions.dup_leakage_rate_high,
        "dup_leakage_low_usd": round(dup_leakage_low, 2),
        "dup_leakage_high_usd": round(dup_leakage_high, 2),
        "disclaimer": DISCLAIMER,
    }


def headline(scenario: dict) -> str:
    """The one honest sentence for a resume/LinkedIn/interview."""
    return (
        f"Modeled AuditLedger against {scenario['retailer']}'s publicly reported "
        f"AP scale (~{scenario['modeled_invoice_volume']:,} invoices/yr, assumed): "
        f"a 100%-auditable control addressing an industry-benchmarked "
        f"${scenario['dup_leakage_low_usd']/1e9:.1f}B–"
        f"${scenario['dup_leakage_high_usd']/1e9:.1f}B/yr in duplicate-payment "
        f"leakage and ~${scenario['processing_cost_addressable_usd']/1e6:.1f}M in "
        f"manual processing cost — every dollar traceable to a logged decision."
    )
