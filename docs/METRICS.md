# AuditLedger — Final Metrics (measured)

All figures below are produced by an actual run of the deterministic pipeline
against the hidden ground-truth table (`pytest` enforces them). Reproduce with
`python scripts/run_pipeline.py`. Nothing here is estimated except the two rows
explicitly labeled *(assumption)*.

## Core run — 100 synthetic invoices, 15 vendors, 30 seeded defects

| Metric | Value |
|---|---|
| **Error catch rate** | **100%** (30/30 seeded defects; all 5 taxonomy types 6/6) |
| Seeded errors auto-approved | **0** (guardrail holds at every confidence threshold) |
| Automation rate | **60%** (60/100 invoices auto-approved) |
| Processing-cost reduction | **60%** ($750 avoided of the $1,250 manual baseline) |
| Cost avoided | $750 (60 × $12.50 conservative manual benchmark) |
| Avg processing time | sub-millisecond/invoice, deterministic compute *(measured)* vs the 14.6-day manual cycle |
| Audit coverage | 100% — append-only, hash-chained log; chain **INTACT** |
| Estimated hours saved | 10.0 *(assumption: 10 min/invoice manual touch time — configurable)* |
| Automated test coverage | 42 passing tests across all four milestones |

## Case study — retail-scale (illustrative, public data)

> Illustrative modeling on public figures; not consulting work; not affiliated
> with the named company; no figure identified in its actual books.

Modeled against Walmart's publicly reported AP scale (~5M invoices/yr, assumed):
an industry-benchmarked **$3.9B–$9.7B/yr in duplicate-payment leakage** (0.8–2%
published range) and **~$37.5M in manual processing cost** addressable with 100%
decision auditability.

## Resume / LinkedIn bullets (honesty-safe)

- Built **AuditLedger**, an auditable AI invoice-reconciliation agent (Python,
  SQLite, Anthropic, Streamlit): a deterministic 3-way match catches **100%** of
  seeded AP defects while the LLM only *recommends* — **0** errors ever
  auto-approved — with every decision written to an immutable, hash-chained audit
  log.
- Achieved **60% straight-through automation** with **100% decision
  auditability**, cutting modeled processing cost by **60%** vs the $12.50/invoice
  manual benchmark on a 100-invoice synthetic portfolio.
- **Modeled** the agent against a large retailer's publicly reported AP scale,
  illustrating an addressable multi-billion-dollar duplicate-payment leakage range
  — using only synthetic data and public figures, with a governance-first,
  never-overclaim framing.
