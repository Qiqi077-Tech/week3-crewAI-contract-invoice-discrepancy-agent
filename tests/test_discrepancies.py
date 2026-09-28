from pathlib import Path

from invoice_discrepancy_agent.models import ContractItem, ContractTerms, InvoiceData, InvoiceLine
from invoice_discrepancy_agent.parsing import analyze_files, compare

ROOT = Path(__file__).resolve().parents[1]


def test_sample_documents():
    r = analyze_files(ROOT / "purchase_terms_conditions.pdf", ROOT / "sample_invoice.pdf")
    status = {c.invoice_description: (c.status, c.unit_price_variance) for c in r.item_comparisons}
    assert status == {
        "Website design consultation": ("match", 0.0),
        "Homepage wireframe and revisions": ("overcharged", 10.0),
        "Product photo retouching package": ("undercharged", -5.0),
        "Monthly hosting setup": ("undercharged", -5.0),
    }
    assert len(r.discrepancies) == 3
    assert (r.total_overcharge, r.total_undercharge) == (10.0, 10.0)
    assert (r.invoiced_subtotal, r.expected_subtotal, r.invoiced_total) == (595.0, 595.0, 644.09)


def test_detects_unlisted_item_bad_math_and_terms():
    contract = ContractTerms(items=[ContractItem(description="Widget", unit_price=10)], payment_net_days=30,
                             invoice_reference="INV-1")
    invoice = InvoiceData(
        invoice_number="INV-2", invoice_date="2026-01-01", due_date="2026-01-15", payment_terms="Net 14",
        lines=[InvoiceLine(description="Widget", quantity=3, unit_price=10, amount=35),
               InvoiceLine(description="Rush fee", quantity=1, unit_price=20, amount=20)],
        subtotal=50, tax_rate_percent=10, tax_amount=5, total_due=60,
    )
    cats = {d.category for d in compare(contract, invoice).discrepancies}
    assert {"Line arithmetic", "Unauthorized item", "Subtotal arithmetic", "Total arithmetic",
            "Payment terms", "Due date", "Reference"} <= cats
