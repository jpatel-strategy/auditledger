"""Generate the one-page case-study export (HTML always; PDF if a browser is available).

Usage:
    python scripts/build_case_study.py

Writes docs/case_study.html (self-contained, print-ready). If Playwright + a
Chromium build are available it also writes docs/case_study.pdf; otherwise it
tells you to open the HTML and print to PDF. The repo itself does NOT depend on
Playwright — the PDF is a convenience, the HTML is the source of truth.

Every number is derived from the real synthetic run (automation + catch rate)
combined with the openly-stated assumptions in auditledger.case_study.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditledger import case_study  # noqa: E402
from auditledger.agents.pipeline import run_pipeline  # noqa: E402
from auditledger.data.seeding import build_full_dataset  # noqa: E402

DOCS = Path(__file__).resolve().parents[1] / "docs"


def _measured_metrics() -> tuple[float, float]:
    """Run the real pipeline once to get MEASURED automation and catch rates."""
    ds = build_full_dataset()
    reports = run_pipeline(ds, client=None)
    gt = {g.invoice_id: g for g in ds.ground_truth}
    total = len(reports)
    auto = sum(1 for r in reports if r.classification == "AUTO-APPROVE")
    seeded = [r for r in reports if gt[r.invoice_id].is_seeded_error]
    caught = sum(1 for r in seeded if gt[r.invoice_id].error_type in r.discrepancy_types)
    return auto / total, (caught / len(seeded) if seeded else 0.0)


def _row(label: str, value: str) -> str:
    return f'<tr><td class="k">{label}</td><td class="v">{value}</td></tr>'


def render_html(s: dict) -> str:
    usd_b = lambda x: f"${x/1e9:.1f}B"
    usd_m = lambda x: f"${x/1e6:.1f}M"
    assumptions = "".join([
        _row("Company (public)", s["retailer"]),
        _row("Annual revenue (public)", usd_b(s["annual_revenue_usd"])),
        _row("Cost-of-sales ratio", f'{s["cogs_ratio"]:.0%}'),
        _row("Modeled AP spend", usd_b(s["modeled_ap_spend_usd"])),
        _row("Suppliers (public)", f'{s["supplier_count"]:,}+'),
        _row("Invoices/supplier/yr (assumed)", str(s["invoices_per_supplier_per_year"])),
        _row("Modeled invoice volume", f'{s["modeled_invoice_volume"]:,}/yr'),
    ])
    results = "".join([
        _row("Measured catch rate (real run)", f'{s["measured_catch_rate"]:.0%}'),
        _row("Measured automation rate (real run)", f'{s["measured_automation_rate"]:.0%}'),
        _row("Processing cost addressable", usd_m(s["processing_cost_addressable_usd"])),
        _row("Duplicate leakage addressable*",
             f'{usd_b(s["dup_leakage_low_usd"])}–{usd_b(s["dup_leakage_high_usd"])}'),
        _row("Estimated hours saved", f'{s["estimated_hours_saved"]:,.0f}'),
        _row("Audit coverage", f'{s["audit_coverage"]:.0%}'),
    ])
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 16mm; }}
body {{ font-family: system-ui, sans-serif; color:#0D1B2A; margin:0; }}
.wm {{ font-size:26px; font-weight:700; letter-spacing:-.5px; }}
.wm .l {{ color:#1B9AAA; }}
.sub {{ color:#64727D; font-size:13px; margin-top:2px; }}
.banner {{ background:#FFF7E0; border-left:3px solid #E0A100; padding:8px 12px;
  border-radius:8px; font-size:12px; color:#1B2D45; margin:14px 0; }}
.head {{ background:#E8F4F6; border-left:3px solid #1B9AAA; padding:12px 14px;
  border-radius:8px; font-size:14px; margin:12px 0 18px; }}
.grid {{ display:flex; gap:20px; }}
.col {{ flex:1; }}
h3 {{ font-size:14px; margin:0 0 6px; }}
table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
td {{ padding:5px 6px; border-bottom:1px solid #E3E8EC; }}
td.k {{ color:#64727D; }} td.v {{ text-align:right; font-weight:600;
  font-family:"JetBrains Mono",monospace; }}
.foot {{ margin-top:18px; font-size:10.5px; color:#64727D; border-top:1px solid #E3E8EC;
  padding-top:8px; }}
.gold {{ color:#D4A843; }}
</style></head><body>
<div class="wm"><span>Audit</span><span class="l">Ledger</span> · Case Study</div>
<div class="sub">Modeling AP risk at retail scale</div>
<div class="banner"><b>Illustrative modeling on public data.</b> Not affiliated with,
endorsed by, or commissioned by the named company. No dollar figure was identified in
its actual books — projections apply published benchmarks to stated assumptions.</div>
<div class="head">{case_study.headline(s)}</div>
<div class="grid">
  <div class="col"><h3>Assumptions</h3><table>{assumptions}</table></div>
  <div class="col"><h3>Modeled results</h3><table>{results}</table></div>
</div>
<p style="font-size:11px;color:#64727D;margin-top:10px">*Published 0.8–2% duplicate-payment
benchmark applied to modeled AP spend — an addressable range, not a figure found in any
company's books.</p>
<div class="foot"><b>Source:</b> {s['source_note']}<br><br>{s['disclaimer']}<br>
github.com/jpatel-strategy/-auditledger · synthetic data</div>
</body></html>"""


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    auto, catch = _measured_metrics()
    scenario = case_study.model_scenario(measured_automation_rate=auto, measured_catch_rate=catch)
    html = render_html(scenario)

    html_path = DOCS / "case_study.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"Wrote {html_path}")
    print(case_study.headline(scenario))

    # Optional PDF via a pre-installed Chromium (never a hard dependency).
    try:
        from playwright.sync_api import sync_playwright

        chrome = os.getenv("CHROME_PATH")
        with sync_playwright() as p:
            launch = {"headless": True, "args": ["--no-sandbox"]}
            if chrome:
                launch["executable_path"] = chrome
            browser = p.chromium.launch(**launch)
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.pdf(path=str(DOCS / "case_study.pdf"), format="A4",
                     print_background=True)
            browser.close()
        print(f"Wrote {DOCS / 'case_study.pdf'}")
    except Exception as exc:  # noqa: BLE001
        print(f"(PDF skipped: {exc}. Open {html_path} and print to PDF.)")


if __name__ == "__main__":
    main()
