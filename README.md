# Contract vs. Invoice Discrepancy Agent (CrewAI)

A CrewAI crew that reads `purchase_terms_conditions.pdf` and `sample_invoice.pdf`,
extracts the contract terms and invoice data, compares every invoice line item against
the contracted price, and writes a Markdown discrepancy report.

## How it works

Four agents run sequentially:

| Agent | Tools | Output |
|---|---|---|
| Procurement Contract Analyst | `contract_terms_parser`, `pdf_text_reader` | `ContractTerms` (items, unit prices, Net days, tax clause) |
| Accounts Payable Invoice Analyst | `invoice_parser`, `pdf_text_reader` | `InvoiceData` (lines, qty, prices, tax, totals, dates) |
| Invoice Compliance Auditor | `discrepancy_calculator`, `pdf_text_reader` | `DiscrepancyReport` (per-item variance, severity, checks) |
| Audit Report Writer | none | `output/discrepancy_report.md` |

PDFs are read with LlamaIndex's `PDFReader` (local, no extra API key). All arithmetic runs in
deterministic Python (`parsing.py`), exposed to agents as tools, so the LLM never invents numbers. The agents verify the parsed data against the raw PDF text and write the narrative.

Checks performed:

- Unit price per item vs. contract (over/undercharge, % and line impact)
- Items billed that are not in the contract, and contracted items not billed
- Line math (qty x price), subtotal, tax rate x subtotal, total
- Payment terms (Net days), due date = invoice date + Net days, payment method
- Invoice number and vendor vs. the contract reference
- Offsetting errors: flags when a correct-looking total hides line-level errors

## Setup

```bash
uv venv -p 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
cp .env.example .env   # add your GOOGLE_API_KEY; MODEL defaults to gemini/gemini-3.5-flash-lite
```

## Run

```bash
# Full multi-agent CrewAI run (needs GOOGLE_API_KEY in .env)
.venv/bin/python -m invoice_discrepancy_agent.main

# Deterministic report without an LLM
.venv/bin/python -m invoice_discrepancy_agent.main --offline

# Other documents
.venv/bin/python -m invoice_discrepancy_agent.main --contract path/terms.pdf --invoice path/invoice.pdf
```

Outputs go to `output/`: `discrepancy_report.md` and `discrepancy_findings.json`.

## Tests

```bash
.venv/bin/python -m pytest -q
```
