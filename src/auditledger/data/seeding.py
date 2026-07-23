"""Seeded error taxonomy + hidden ground truth + vendor risk profiles.

Takes a clean dataset and deliberately injects realistic AP defects into 30% of
invoices, tagging each in a hidden ground-truth table. Each seeded defect is
isolated to a single error type (all other fields are kept internally
consistent) so the verification gate can prove the matcher catches each type
without ambiguity.

Determinism note: seeding uses its own ``random.Random(SEED + 1)`` stream so it
is reproducible yet independent of the generation stream.
"""

from __future__ import annotations

import copy
import random

from .. import config, taxonomy
from ..money import money
from .generator import _recompute_financials
from .schema import Dataset, GroundTruth, Invoice, VendorRisk


def seed_errors(dataset: Dataset, cfg=config) -> Dataset:
    """Inject exactly ``N_SEEDED_ERRORS`` defects, then build ground truth and
    the vendor risk profile table. Mutates and returns ``dataset``."""
    rng = random.Random(cfg.SEED + 1)
    invoices = dataset.invoices
    n = len(invoices)

    # Choose which invoices get a defect (indices into the invoice list).
    error_slots = sorted(rng.sample(range(n), cfg.N_SEEDED_ERRORS))

    # Assign the 6 highest slots to DUPLICATE (guarantees an earlier clean
    # invoice always exists to copy from), and distribute the rest evenly across
    # the remaining four types.
    per_type = cfg.N_SEEDED_ERRORS // len(taxonomy.ALL_ERROR_TYPES)  # 30 / 5 == 6
    dup_slots = set(error_slots[-per_type:])
    other_slots = error_slots[:-per_type]

    non_dup_types = [t for t in taxonomy.ALL_ERROR_TYPES if t != taxonomy.DUPLICATE_INVOICE]
    type_pool: list[str] = []
    for t in non_dup_types:
        type_pool.extend([t] * per_type)
    rng.shuffle(type_pool)
    slot_type = dict(zip(other_slots, type_pool))
    for s in dup_slots:
        slot_type[s] = taxonomy.DUPLICATE_INVOICE

    po_by_id = {po.po_id: po for po in dataset.purchase_orders}
    receipt_by_po = {r.po_id: r for r in dataset.goods_receipts}
    error_index = {i for i in error_slots}

    ground_truth: list[GroundTruth] = []
    for i, invoice in enumerate(invoices):
        if i not in error_index:
            ground_truth.append(
                GroundTruth(invoice.invoice_id, False, None, {}, None)
            )
            continue

        etype = slot_type[i]
        detail = _inject(etype, i, invoice, invoices, error_index,
                         po_by_id, receipt_by_po, rng, cfg)
        ground_truth.append(
            GroundTruth(
                invoice_id=invoice.invoice_id,
                is_seeded_error=True,
                error_type=etype,
                error_detail=detail,
                severity=taxonomy.SEVERITY[etype],
            )
        )

    dataset.ground_truth = ground_truth
    dataset.vendor_risk_profiles = _build_risk_profiles(dataset)
    return dataset


def _inject(etype, idx, invoice, invoices, error_index,
            po_by_id, receipt_by_po, rng, cfg) -> dict:
    """Apply one defect of ``etype`` to ``invoice`` in place; return a detail dict
    describing what was changed (recorded in ground truth for later evidence)."""

    if etype == taxonomy.MISSING_PO_REFERENCE:
        original = invoice.po_reference
        invoice.po_reference = None
        return {"was": original, "now": None}

    if etype == taxonomy.PRICE_VARIANCE:
        # Inflate one line's unit price well beyond the 2% tolerance, then keep
        # the invoice internally consistent so ONLY the price check fires.
        line = rng.choice(invoice.lines)
        old = line.unit_price
        line.unit_price = money(old * rng.uniform(1.15, 1.40))
        _recompute_financials(invoice, cfg.DEFAULT_TAX_RATE)
        return {"sku": line.sku, "po_unit_price": old, "invoiced_unit_price": line.unit_price}

    if etype == taxonomy.QUANTITY_MISMATCH:
        # Bill for more units than were received.
        line = rng.choice(invoice.lines)
        received = line.quantity
        line.quantity = received + rng.randint(1, 10)
        _recompute_financials(invoice, cfg.DEFAULT_TAX_RATE)
        return {"sku": line.sku, "received_qty": received, "invoiced_qty": line.quantity}

    if etype == taxonomy.TAX_MATH_ERROR:
        # Corrupt the tax figure (total stays subtotal+tax so exactly the
        # tax-rate check trips, not the arithmetic-of-total check).
        correct_tax = invoice.tax_amount
        bad_tax = money(correct_tax + rng.choice([7.50, 12.25, -6.00, 9.99]))
        invoice.tax_amount = bad_tax
        invoice.total = money(invoice.subtotal + bad_tax)
        return {"expected_tax": correct_tax, "invoiced_tax": bad_tax}

    if etype == taxonomy.DUPLICATE_INVOICE:
        # Replace this slot with a faithful copy of an earlier CLEAN invoice:
        # same vendor, number, and total — a classic double-submission. Keeps
        # this invoice's own id so both rows coexist in the ledger.
        clean_earlier = [j for j in range(idx) if j not in error_index]
        source = invoices[rng.choice(clean_earlier)]
        _copy_invoice_content(source, invoice)
        return {"duplicate_of": source.invoice_id, "invoice_number": source.invoice_number}

    raise ValueError(f"Unknown error type: {etype}")


def _copy_invoice_content(source: Invoice, target: Invoice) -> None:
    """Copy everything that defines a duplicate (vendor, number, PO ref, lines,
    financials) from ``source`` into ``target``, preserving ``target``'s own id."""
    target.vendor_id = source.vendor_id
    target.invoice_number = source.invoice_number
    target.po_reference = source.po_reference
    target.lines = copy.deepcopy(source.lines)
    target.subtotal = source.subtotal
    target.tax_amount = source.tax_amount
    target.total = source.total


def _build_risk_profiles(dataset: Dataset) -> list[VendorRisk]:
    """Compute historical error rate per vendor from the ground-truth answer key.

    Business rationale: the Critic (Milestone 2) trusts a vendor's track record,
    not a gut feeling — so risk must be measured, not assumed.
    """
    gt_by_invoice = {gt.invoice_id: gt for gt in dataset.ground_truth}
    totals: dict[str, int] = {}
    errors: dict[str, int] = {}
    for inv in dataset.invoices:
        totals[inv.vendor_id] = totals.get(inv.vendor_id, 0) + 1
        if gt_by_invoice[inv.invoice_id].is_seeded_error:
            errors[inv.vendor_id] = errors.get(inv.vendor_id, 0) + 1

    profiles: list[VendorRisk] = []
    for vendor in dataset.vendors:
        total = totals.get(vendor.vendor_id, 0)
        err = errors.get(vendor.vendor_id, 0)
        rate = round(err / total, 4) if total else 0.0
        profiles.append(
            VendorRisk(
                vendor_id=vendor.vendor_id,
                total_invoices=total,
                seeded_error_count=err,
                historical_error_rate=rate,
                risk_tier=_risk_tier(rate),
            )
        )
    return profiles


def _risk_tier(rate: float) -> str:
    if rate > 0.40:
        return "HIGH"
    if rate > 0.15:
        return "MEDIUM"
    return "LOW"


def build_full_dataset(cfg=config) -> Dataset:
    """Convenience: generate a clean universe and seed it in one call."""
    from .generator import generate_clean_dataset

    return seed_errors(generate_clean_dataset(cfg), cfg)
