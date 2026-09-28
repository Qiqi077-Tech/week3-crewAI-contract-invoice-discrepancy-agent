"""Render a DiscrepancyReport as Markdown without an LLM (used by --offline)."""
from __future__ import annotations

from .models import DiscrepancyReport, InvoiceData

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
STATUS_LABEL = {
    "match": "OK", "overcharged": "OVERCHARGED", "undercharged": "UNDERCHARGED",
    "not_in_contract": "NOT IN CONTRACT", "math_error": "MATH ERROR",
}


def _m(v: float | None) -> str:
    return "n/a" if v is None else f"${v:,.2f}"


def _signed(v: float | None) -> str:
    return "n/a" if v is None else f"{'+' if v > 0 else '-' if v < 0 else ''}${abs(v):,.2f}"


def render_markdown(r: DiscrepancyReport, inv: InvoiceData | None = None) -> str:
    issues = sorted(r.discrepancies, key=lambda d: SEVERITY_ORDER[d.severity])
    net = round(r.total_overcharge - r.total_undercharge, 2)
    masked = (
        r.invoiced_subtotal is not None and r.expected_subtotal is not None
        and abs(r.invoiced_subtotal - r.expected_subtotal) <= 0.01 and issues
    )
    verdict = "HOLD - discrepancies found" if any(d.severity in ("high", "medium") for d in issues) else "APPROVE"
    out = [f"# Invoice Discrepancy Report: {r.invoice_number or 'Unknown invoice'}", ""]

    out += ["## 1. Executive summary", "",
            f"- **Verdict:** {verdict}",
            f"- **Discrepancies found:** {len(issues)}",
            f"- **Overbilled:** {_m(r.total_overcharge)}; **underbilled:** {_m(r.total_undercharge)}; "
            f"**net impact on subtotal:** {_signed(net)}"]
    if masked:
        out.append("- **Warning:** the invoice subtotal matches the contract-priced subtotal only because "
                   "line-level overcharges and undercharges cancel out. A totals-only review would miss these errors.")
    out.append("")

    out += ["## 2. Document overview", "", "| Field | Value |", "|---|---|",
            f"| Vendor | {r.vendor or 'n/a'} |", f"| Buyer | {r.buyer or 'n/a'} |",
            f"| Invoice number | {r.invoice_number or 'n/a'} |"]
    if inv:
        out += [f"| Invoice date | {inv.invoice_date or 'n/a'} |", f"| Due date | {inv.due_date or 'n/a'} |",
                f"| Payment terms | {inv.payment_terms or 'n/a'} |", f"| Payment method | {inv.payment_method or 'n/a'} |"]
    out.append("")

    out += ["## 3. Item-by-item comparison", "",
            "| Item | Qty | Contract price | Invoiced price | Variance / unit | Line impact | Status |",
            "|---|---:|---:|---:|---:|---:|---|"]
    for c in r.item_comparisons:
        out.append(f"| {c.invoice_description} | {c.quantity:g} | {_m(c.contract_unit_price)} | "
                   f"{_m(c.invoiced_unit_price)} | {_signed(c.unit_price_variance)} | "
                   f"{_signed(c.amount_variance)} | {STATUS_LABEL[c.status]} |")
    out.append("")

    out += ["## 4. Discrepancy details", ""]
    if not issues:
        out.append("No discrepancies found.")
    for i, d in enumerate(issues, 1):
        out += [f"### 4.{i} [{d.severity.upper()}] {d.category}: {d.item}", "",
                f"- **Expected (contract):** {d.expected}", f"- **Actual (invoice):** {d.actual}"]
        if d.variance is not None and d.category not in ("Due date",):
            out.append(f"- **Variance:** {_signed(d.variance)}")
        out += [f"- **Finding:** {d.explanation}", ""]

    tax_inv = tax_exp = None
    if inv and inv.tax_rate_percent is not None and r.expected_subtotal is not None:
        tax_inv = inv.tax_amount
        tax_exp = round(r.expected_subtotal * inv.tax_rate_percent / 100, 2)
    out += ["## 5. Totals reconciliation", "", "| Line | Invoiced | Expected per contract | Difference |",
            "|---|---:|---:|---:|",
            f"| Subtotal | {_m(r.invoiced_subtotal)} | {_m(r.expected_subtotal)} | "
            f"{_signed(None if r.invoiced_subtotal is None or r.expected_subtotal is None else round(r.invoiced_subtotal - r.expected_subtotal, 2))} |"]
    if tax_exp is not None:
        out.append(f"| Sales tax ({inv.tax_rate_percent}%) | {_m(tax_inv)} | {_m(tax_exp)} | "
                   f"{_signed(None if tax_inv is None else round(tax_inv - tax_exp, 2))} |")
    out += [f"| Total due | {_m(r.invoiced_total)} | {_m(r.expected_total)} | "
            f"{_signed(None if r.invoiced_total is None or r.expected_total is None else round(r.invoiced_total - r.expected_total, 2))} |", ""]

    out += ["## 6. Checks passed", ""] + [f"- {c}" for c in r.checks_passed] + [""]

    out += ["## 7. Recommendation", "", r.recommendation, ""]
    if issues:
        out += ["Next steps for accounts payable:", "",
                "1. Do not release payment on the current invoice.",
                "2. Send the vendor the item table above and request a corrected invoice at contract prices.",
                "3. If the vendor claims a price change, require a signed amendment to the purchase terms.",
                "4. Re-run this check on the revised invoice before approving payment.", ""]
    return "\n".join(out)
