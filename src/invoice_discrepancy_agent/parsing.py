"""Deterministic PDF extraction and contract-vs-invoice comparison.

The LLM agents call these through tools so that every number in the report
comes from the documents, not from model arithmetic.
"""
from __future__ import annotations

import difflib
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from llama_index.readers.file import PDFReader

from .models import (
    ContractItem,
    ContractTerms,
    Discrepancy,
    DiscrepancyReport,
    InvoiceData,
    InvoiceLine,
    ItemComparison,
)

MONEY = r"\$?\s*([\d,]+(?:\.\d{1,2})?)"
TOLERANCE = 0.01  # one cent


def load_pdf_documents(path: str | Path):
    """Load a PDF as LlamaIndex Documents (one Document for the whole file)."""
    return PDFReader(return_full_document=True).load_data(file=Path(path))


def extract_pdf_text(path: str | Path) -> str:
    """Extract a PDF's text with LlamaIndex's PDFReader."""
    return "\n".join(doc.text for doc in load_pdf_documents(path))


def _money(value: str) -> float:
    return round(float(value.replace(",", "").replace("$", "").strip()), 2)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def _parse_date(text: str | None) -> date | None:
    if not text:
        return None
    text = text.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- contract
def parse_contract(text: str) -> ContractTerms:
    items = [
        ContractItem(description=m.group(1).strip(), unit_price=_money(m.group(2)))
        for m in re.finditer(r"^\s*[-•*]\s*(.+?):\s*" + MONEY + r"\s*per\s+unit", text, re.M | re.I)
    ]
    vendor = re.search(r"Vendor\s*\(([^)]+)\)", text)
    ref = re.search(r"Invoice\s+No\.?\s*([A-Z0-9-]+?)\.?(?:\s|$)", text, re.I)
    net = re.search(r"Net\s+(\d+)\s+days", text, re.I)
    methods = re.search(r"Payment method:\s*(.+)", text, re.I)
    tax = re.search(r"\d+\.\s*Taxes\s*\n(.+)", text, re.I)

    other_terms = []
    for heading in ("Delivery and Acceptance", "Revisions and Changes", "Termination"):
        m = re.search(rf"\d+\.\s*{heading}\s*\n(.+?)(?=\n\d+\.\s|\Z)", text, re.S | re.I)
        if m:
            other_terms.append(f"{heading}: {' '.join(m.group(1).split())}")

    return ContractTerms(
        vendor=vendor.group(1).strip() if vendor else None,
        invoice_reference=ref.group(1).strip() if ref else None,
        items=items,
        payment_net_days=int(net.group(1)) if net else None,
        payment_methods=[
            s.strip(" .") for s in re.split(r"\bor\b|,", methods.group(1)) if s.strip(" .")
        ] if methods else [],
        tax_clause=" ".join(tax.group(1).split()) if tax else None,
        other_terms=other_terms,
    )


# --------------------------------------------------------------------------- invoice
def parse_invoice(text: str) -> InvoiceData:
    def grab(pattern: str) -> str | None:
        m = re.search(pattern, text, re.I | re.M)
        return m.group(1).strip() if m else None

    # Line items: "Description\n qty\n $unit\n $amount" (column layout from PDFReader)
    # or "Description qty $unit $amount" on one line.
    item_pattern = re.compile(
        r"^(?P<desc>[A-Za-z][^\n$]*?)\s*(?:\n\s*|\s+)(?P<qty>\d+(?:\.\d+)?)\s*(?:\n\s*|\s+)"
        r"\$(?P<unit>[\d,]+\.\d{2})\s*(?:\n\s*|\s+)\$(?P<amt>[\d,]+\.\d{2})",
        re.M,
    )
    table_start = re.search(r"^\s*Amount\s*$", text, re.M)
    table_text = text[table_start.end():] if table_start else text
    table_end = re.search(r"^\s*Subtotal\b", table_text, re.M)
    table_text = table_text[: table_end.start()] if table_end else table_text
    lines = [
        InvoiceLine(
            description=m.group("desc").strip(),
            quantity=float(m.group("qty")),
            unit_price=_money(m.group("unit")),
            amount=_money(m.group("amt")),
        )
        for m in item_pattern.finditer(table_text)
    ]

    bill_to = re.search(r"BILL TO\s*\n\s*(.+)", text)
    vendor = re.search(r"^(?:SAMPLE\s*\n)?(?:Sample invoice\s*\n)?\s*(.+?)\s*\n\s*\d+ .+Street", text, re.M)
    tax = re.search(r"Sales Tax\s*\(([\d.]+)%\)\s*\n?\s*" + MONEY, text, re.I)

    inv_date = _parse_date(grab(r"Invoice Date:\s*(.+)$"))
    due_date = _parse_date(grab(r"Due Date:\s*(.+)$"))
    subtotal = grab(r"Subtotal\s*\n?\s*" + MONEY)
    total = grab(r"Total Due\s*\n?\s*" + MONEY)

    return InvoiceData(
        vendor=vendor.group(1).strip() if vendor else None,
        bill_to=bill_to.group(1).strip() if bill_to else None,
        invoice_number=grab(r"Invoice\s*#:\s*(\S+)"),
        invoice_date=inv_date.isoformat() if inv_date else None,
        due_date=due_date.isoformat() if due_date else None,
        payment_terms=grab(r"Payment Terms:\s*(.+)$"),
        payment_method=grab(r"Payment Method:\s*(.+)$"),
        lines=lines,
        subtotal=_money(subtotal) if subtotal else None,
        tax_rate_percent=float(tax.group(1)) if tax else None,
        tax_amount=_money(tax.group(2)) if tax else None,
        total_due=_money(total) if total else None,
    )


# --------------------------------------------------------------------------- comparison
def _match_contract_item(desc: str, items: list[ContractItem]) -> ContractItem | None:
    by_norm = {_norm(i.description): i for i in items}
    if _norm(desc) in by_norm:
        return by_norm[_norm(desc)]
    close = difflib.get_close_matches(_norm(desc), list(by_norm), n=1, cutoff=0.8)
    return by_norm[close[0]] if close else None


def _fmt(v: float | None) -> str:
    return "n/a" if v is None else f"${v:,.2f}"


def compare(contract: ContractTerms, invoice: InvoiceData) -> DiscrepancyReport:
    report = DiscrepancyReport(
        invoice_number=invoice.invoice_number,
        vendor=invoice.vendor or contract.vendor,
        buyer=invoice.bill_to,
    )
    d, ok = report.discrepancies, report.checks_passed
    expected_subtotal = 0.0
    matched: set[str] = set()

    # ---- line items
    for line in invoice.lines:
        c = _match_contract_item(line.description, contract.items)
        math_ok = abs(line.quantity * line.unit_price - line.amount) <= TOLERANCE
        if not math_ok:
            d.append(Discrepancy(
                category="Line arithmetic", item=line.description,
                expected=_fmt(line.quantity * line.unit_price), actual=_fmt(line.amount),
                variance=round(line.amount - line.quantity * line.unit_price, 2), severity="high",
                explanation="Line amount does not equal quantity x unit price.",
            ))
        if c is None:
            expected_subtotal += line.amount
            report.item_comparisons.append(ItemComparison(
                invoice_description=line.description, quantity=line.quantity,
                invoiced_unit_price=line.unit_price, invoiced_amount=line.amount,
                status="not_in_contract", note="No matching item in the purchase terms.",
            ))
            d.append(Discrepancy(
                category="Unauthorized item", item=line.description, expected="Not in contract",
                actual=_fmt(line.amount), variance=line.amount, severity="high",
                explanation="Invoice bills an item that the purchase terms do not cover.",
            ))
            report.total_overcharge += line.amount
            continue

        matched.add(c.description)
        expected_amount = round(line.quantity * c.unit_price, 2)
        expected_subtotal += expected_amount
        unit_var = round(line.unit_price - c.unit_price, 2)
        amt_var = round(line.amount - expected_amount, 2)
        if abs(unit_var) <= TOLERANCE:
            status = "match" if math_ok else "math_error"
            note = "Unit price matches contract." if math_ok else "Price matches but line math is wrong."
        elif unit_var > 0:
            status, note = "overcharged", f"Billed {_fmt(unit_var)} per unit above contract price."
        else:
            status, note = "undercharged", f"Billed {_fmt(-unit_var)} per unit below contract price."
        report.item_comparisons.append(ItemComparison(
            invoice_description=line.description, contract_description=c.description,
            quantity=line.quantity, invoiced_unit_price=line.unit_price,
            contract_unit_price=c.unit_price, unit_price_variance=unit_var,
            invoiced_amount=line.amount, expected_amount=expected_amount,
            amount_variance=amt_var, status=status, note=note,
        ))
        if status in ("overcharged", "undercharged"):
            pct = unit_var / c.unit_price * 100
            d.append(Discrepancy(
                category="Unit price", item=line.description,
                expected=f"{_fmt(c.unit_price)} per unit", actual=f"{_fmt(line.unit_price)} per unit",
                variance=amt_var, severity="high" if unit_var > 0 else "medium",
                explanation=(
                    f"{status.capitalize()} by {_fmt(abs(unit_var))}/unit ({pct:+.1f}%) "
                    f"x {line.quantity:g} = {_fmt(abs(amt_var))} line impact."
                ),
            ))
            if amt_var > 0:
                report.total_overcharge += amt_var
            else:
                report.total_undercharge += -amt_var
        elif status == "match":
            ok.append(f"'{line.description}' unit price {_fmt(line.unit_price)} matches contract.")

    for c in contract.items:
        if c.description not in matched:
            d.append(Discrepancy(
                category="Missing item", item=c.description, expected=f"{_fmt(c.unit_price)} per unit",
                actual="Not invoiced", severity="info",
                explanation="Contracted item does not appear on the invoice (may be pending delivery).",
            ))

    # ---- totals
    expected_subtotal = round(expected_subtotal, 2)
    report.expected_subtotal = expected_subtotal
    report.invoiced_subtotal = invoice.subtotal
    line_sum = round(sum(line.amount for line in invoice.lines), 2)
    if invoice.subtotal is not None:
        if abs(line_sum - invoice.subtotal) > TOLERANCE:
            d.append(Discrepancy(
                category="Subtotal arithmetic", item="Subtotal", expected=_fmt(line_sum),
                actual=_fmt(invoice.subtotal), variance=round(invoice.subtotal - line_sum, 2),
                severity="high", explanation="Invoice subtotal does not equal the sum of its lines.",
            ))
        else:
            ok.append(f"Invoice subtotal {_fmt(invoice.subtotal)} equals the sum of its line items.")

    rate = (invoice.tax_rate_percent or 0) / 100
    if invoice.tax_amount is not None and invoice.subtotal is not None:
        calc_tax = round(invoice.subtotal * rate, 2)
        if abs(calc_tax - invoice.tax_amount) > TOLERANCE:
            d.append(Discrepancy(
                category="Tax arithmetic", item="Sales tax", expected=_fmt(calc_tax),
                actual=_fmt(invoice.tax_amount), variance=round(invoice.tax_amount - calc_tax, 2),
                severity="medium", explanation=f"Tax at {invoice.tax_rate_percent}% of subtotal is miscalculated.",
            ))
        else:
            ok.append(
                f"Sales tax {_fmt(invoice.tax_amount)} is {invoice.tax_rate_percent}% of the subtotal "
                "(contract clause 5 allows sales tax to be added)."
            )
        if invoice.total_due is not None:
            calc_total = round(invoice.subtotal + invoice.tax_amount, 2)
            if abs(calc_total - invoice.total_due) > TOLERANCE:
                d.append(Discrepancy(
                    category="Total arithmetic", item="Total due", expected=_fmt(calc_total),
                    actual=_fmt(invoice.total_due), variance=round(invoice.total_due - calc_total, 2),
                    severity="high", explanation="Total due does not equal subtotal plus tax.",
                ))
            else:
                ok.append(f"Total due {_fmt(invoice.total_due)} equals subtotal plus tax.")
    report.invoiced_total = invoice.total_due
    report.expected_total = round(expected_subtotal * (1 + rate), 2)

    # ---- payment terms, dates, references
    if contract.payment_net_days is not None:
        m = re.search(r"(\d+)", invoice.payment_terms or "")
        inv_net = int(m.group(1)) if m else None
        if inv_net != contract.payment_net_days:
            d.append(Discrepancy(
                category="Payment terms", item="Payment terms",
                expected=f"Net {contract.payment_net_days}", actual=invoice.payment_terms or "missing",
                severity="medium", explanation="Invoice payment terms differ from the contract.",
            ))
        else:
            ok.append(f"Payment terms Net {inv_net} match the contract.")
        inv_d, due_d = _parse_date(invoice.invoice_date), _parse_date(invoice.due_date)
        if inv_d and due_d:
            exp_due = inv_d + timedelta(days=contract.payment_net_days)
            if exp_due != due_d:
                d.append(Discrepancy(
                    category="Due date", item="Due date", expected=exp_due.isoformat(),
                    actual=due_d.isoformat(), variance=float((due_d - exp_due).days),
                    severity="medium" if due_d < exp_due else "low",
                    explanation=f"Due date should be invoice date + {contract.payment_net_days} days.",
                ))
            else:
                ok.append(f"Due date {due_d.isoformat()} is invoice date + {contract.payment_net_days} days.")

    if contract.payment_methods and invoice.payment_method:
        if any(_norm(m) in _norm(invoice.payment_method) or _norm(invoice.payment_method) in _norm(m)
               for m in contract.payment_methods):
            ok.append(f"Payment method '{invoice.payment_method}' is permitted by the contract.")
        else:
            d.append(Discrepancy(
                category="Payment method", item="Payment method",
                expected=" or ".join(contract.payment_methods), actual=invoice.payment_method,
                severity="low", explanation="Payment method is not one listed in the contract.",
            ))

    if contract.invoice_reference and invoice.invoice_number:
        if contract.invoice_reference != invoice.invoice_number:
            d.append(Discrepancy(
                category="Reference", item="Invoice number", expected=contract.invoice_reference,
                actual=invoice.invoice_number, severity="high",
                explanation="Invoice number does not match the one the contract governs.",
            ))
        else:
            ok.append(f"Invoice number {invoice.invoice_number} matches the contract reference.")

    if contract.vendor and invoice.vendor and _norm(contract.vendor) != _norm(invoice.vendor):
        d.append(Discrepancy(
            category="Vendor", item="Vendor name", expected=contract.vendor, actual=invoice.vendor,
            severity="high", explanation="Invoice vendor differs from the contracted vendor.",
        ))

    report.total_overcharge = round(report.total_overcharge, 2)
    report.total_undercharge = round(report.total_undercharge, 2)
    price_issues = [x for x in d if x.severity in ("high", "medium")]
    if not price_issues:
        report.recommendation = "Approve for payment: the invoice conforms to the purchase terms."
    else:
        report.recommendation = (
            "Hold for correction: request a revised invoice billing every line at contract prices "
            f"(expected subtotal {_fmt(expected_subtotal)}, expected total {_fmt(report.expected_total)})."
        )
    return report


def analyze_files(contract_pdf: str | Path, invoice_pdf: str | Path) -> DiscrepancyReport:
    return compare(parse_contract(extract_pdf_text(contract_pdf)), parse_invoice(extract_pdf_text(invoice_pdf)))
